"""scripts/compute_foss_metadata.py — pre-compute FOSS project metadata.

Fills foss_projects.file_count and foss_projects.test_coverage with REAL values
computed from the cloned FOSS projects on the server (mounted read-only at
/app/foss/<slug> per docker-compose). Run once after migration 002, and again
whenever the FOSS catalogue changes.

  file_count    — source files, excluding node_modules/target/build/.git/etc.
  test_coverage — line coverage %, measured by JaCoCo (Java) or c8 (JS)

Coverage requires building/running each project's test suite, so this is slow
and is meant to be run manually, not on the request path. file_count is cheap.

Usage (inside the API/worker container, which has the toolchains + DB env):
  python -m scripts.compute_foss_metadata                  # all active projects
  python -m scripts.compute_foss_metadata --slug gson      # just one
  python -m scripts.compute_foss_metadata --skip-coverage  # file_count only (fast)
  python -m scripts.compute_foss_metadata --foss-dir /app/foss --timeout 600

Coverage on a read-only mount: JaCoCo/c8 may need to write build output. If
/app/foss is mounted read-only, pass --work-dir to copy each project into a
writable scratch dir before measuring (e.g. --work-dir /app/foss-tmp).
"""
from __future__ import annotations

import argparse
import logging
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("compute_foss_metadata")


def _sync_engine():
    from config.settings import get_settings
    import sqlalchemy as sa
    s = get_settings()
    url = s.DATABASE_URL_SYNC or s.DATABASE_URL.replace(
        "postgresql+asyncpg", "postgresql+psycopg2"
    ).replace("sqlite+aiosqlite", "sqlite").replace("?ssl=require", "?sslmode=require")
    return sa.create_engine(url, pool_pre_ping=True,
                            connect_args={"connect_timeout": 5} if "postgresql" in url else {})


def _resolve_project_dir(foss_dir: Path, slug: str, work_dir: Path | None) -> Path | None:
    src = foss_dir / slug
    if not src.exists():
        # Some catalogues nest under a version folder; take the first child dir.
        alts = [d for d in foss_dir.glob(f"{slug}*") if d.is_dir()]
        if not alts:
            return None
        src = alts[0]
    if work_dir is None:
        return src
    dst = work_dir / slug
    if dst.exists():
        shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(src, dst, symlinks=True, ignore=shutil.ignore_patterns(
        "node_modules", "target", "build", "dist", ".git", "coverage"))
    return dst


def main() -> int:
    ap = argparse.ArgumentParser(description="Pre-compute FOSS project metadata.")
    ap.add_argument("--foss-dir", default="/app/foss",
                    help="Container path where FOSS projects are mounted (read-only).")
    ap.add_argument("--work-dir", default="/app/foss-tmp",
                    help="Writable scratch dir (container path) projects are copied into "
                         "before coverage is measured; maps to the host foss-tmp mount. "
                         "Pass '' to measure in place (only works if --foss-dir is writable).")
    ap.add_argument("--slug", default=None, help="Only this project slug.")
    ap.add_argument("--skip-coverage", action="store_true",
                    help="Only compute file_count (fast).")
    ap.add_argument("--timeout", type=int, default=900,
                    help="Per-project coverage timeout in seconds.")
    args = ap.parse_args()
    if args.work_dir == "":
        args.work_dir = None

    from services.metadata import count_source_files, measure_line_coverage
    import sqlalchemy as sa

    # Reuse the PIT adapter's per-project Maven/Gradle config so Java coverage
    # builds with the same flags (submodule, enforcer.skip, compiler version, …).
    try:
        from adapters.pit_adapter import PITAdapter
        PIT_CFG = dict(PITAdapter.FOSS_PROJECT_CONFIGS)
    except Exception as exc:
        log.warning("Could not load PIT project configs (%s); using plain mvn", exc)
        PIT_CFG = {}

    foss_dir = Path(args.foss_dir)
    work_dir = Path(args.work_dir) if args.work_dir else None
    if work_dir:
        work_dir.mkdir(parents=True, exist_ok=True)

    engine = _sync_engine()
    with engine.connect() as conn:
        q = "SELECT id, slug, language FROM foss_projects WHERE is_active = true"
        rows = list(conn.execute(sa.text(q)))
    if args.slug:
        rows = [r for r in rows if r.slug == args.slug]

    if not rows:
        log.warning("No matching FOSS projects found.")
        return 1

    log.info("Computing metadata for %d project(s). Coverage: %s",
             len(rows), "skipped" if args.skip_coverage else "enabled")

    ok = fail = 0
    for r in rows:
        proj = _resolve_project_dir(foss_dir, r.slug, work_dir)
        if proj is None:
            log.warning("[%s] directory not found under %s — skipping", r.slug, foss_dir)
            fail += 1
            continue

        files = count_source_files(proj, r.language)
        coverage = None
        if not args.skip_coverage:
            cfg = PIT_CFG.get(r.slug, {})
            log.info("[%s] measuring coverage (timeout %ss)…", r.slug, args.timeout)
            coverage = measure_line_coverage(
                proj, r.language, timeout_s=args.timeout,
                build=cfg.get("build"),
                extra_maven_args=cfg.get("extra_maven_args"),
                submodule=cfg.get("submodule"),
            )

        with engine.begin() as conn:
            if args.skip_coverage:
                conn.execute(
                    sa.text("UPDATE foss_projects SET file_count=:fc WHERE id=:id"),
                    {"fc": files, "id": r.id},
                )
            else:
                conn.execute(
                    sa.text("UPDATE foss_projects SET file_count=:fc, test_coverage=:cov WHERE id=:id"),
                    {"fc": files, "cov": coverage, "id": r.id},
                )
        cov_str = "n/a" if coverage is None else f"{coverage:.1f}%"
        log.info("[%s] file_count=%d  coverage=%s", r.slug, files, cov_str)
        ok += 1

        if work_dir:  # clean scratch copy to save space
            shutil.rmtree(work_dir / r.slug, ignore_errors=True)

    engine.dispose()
    log.info("Done. %d updated, %d skipped/failed.", ok, fail)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

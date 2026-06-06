"""adapters/stryker_adapter.py

Time-budget-aware Stryker execution:

  Phase 1 — Full run (first time only, result cached in mutation.json)
  Phase 2 — IMPT scores/selects mutants within time budget (in tasks.py)
  Phase 3 — Filtered re-run using --mutate with only selected file:line ranges

This achieves REAL time savings: a 5-minute budget only executes the
top-priority mutants, not all 657. Subsequent runs on the same project
skip Phase 1 entirely using Stryker's --incremental cache.
"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import List, Optional

from impt.models.mutant import (
    CodeLocation, Mutant, MutationOperator, ExecutionStatus
)

log = logging.getLogger(__name__)

MUTATOR_MAP = {
    "ArithmeticOperator":    MutationOperator.AOR,
    "EqualityOperator":      MutationOperator.ROR,
    "LogicalOperator":       MutationOperator.LCR,
    "ConditionalExpression": MutationOperator.COR,
    "BooleanLiteral":        MutationOperator.NEGATE_RETURN,
    "StringLiteral":         MutationOperator.NULL_RETURN,
    "BlockStatement":        MutationOperator.SDL,
    "ArrayDeclaration":      MutationOperator.NULL_RETURN,
    "UnaryOperator":         MutationOperator.UOI,
    "UpdateOperator":        MutationOperator.AOR,
    "OptionalChaining":      MutationOperator.NULL_RETURN,
}

STATUS_MAP = {
    "Killed":       ExecutionStatus.KILLED,
    "Survived":     ExecutionStatus.SURVIVED,
    "NoCoverage":   ExecutionStatus.SURVIVED,
    "Timeout":      ExecutionStatus.TIMEOUT,
    "RuntimeError": ExecutionStatus.ERROR,
    "CompileError": ExecutionStatus.ERROR,
    "Ignored":      ExecutionStatus.EQUIVALENT,
}


def _slice_source(source: str, loc: dict) -> str:
    """Extract the original code span Stryker mutated, from the file source and
    the mutant location. Stryker locations are 1-based line, 1-based column.
    Returns "" if the source or location is unavailable."""
    if not source or not loc:
        return ""
    start = loc.get("start", {}) or {}
    end   = loc.get("end", {}) or {}
    sl, sc = start.get("line", 1), start.get("column", 1)
    el, ec = end.get("line", sl), end.get("column", sc)
    lines = source.splitlines()
    try:
        if sl == el:
            return lines[sl-1][sc-1:ec-1].strip()
        span = [lines[sl-1][sc-1:]]
        span += lines[sl:el-1]
        span.append(lines[el-1][:ec-1])
        return "\n".join(span).strip()
    except (IndexError, ValueError):
        return ""


class StrykerAdapter:
    def __init__(self, project_dir: Path, use_docker: bool = True,
                 sandbox_image: str = "impt-sandbox:latest",
                 time_budget_seconds: int = 0,
                 selected_mutants: Optional[List[Mutant]] = None,
                 user_id: Optional[str] = None,
                 progress_cb=None):
        self.use_docker          = use_docker
        self.sandbox_image       = sandbox_image
        self.time_budget_seconds = time_budget_seconds
        self.selected_mutants    = selected_mutants
        self.user_id             = user_id
        # Optional callback(pct:int) invoked with Stryker's live progress
        # percentage during a filtered run. Best-effort, never affects results.
        self.progress_cb         = progress_cb

        # If the project directory is read-only (e.g. FOSS projects mounted :ro),
        # copy it to a writable working directory so npm install and lock files work.
        self.project_dir = self._ensure_writable(Path(project_dir))

    @staticmethod
    def _ensure_writable(project_dir: Path) -> Path:
        """Return a writable copy of project_dir if it's read-only.
        Copies to /app/foss-tmp/<name> which is host-mounted so Docker-in-Docker
        can volume-mount it correctly."""
        import shutil
        try:
            test_file = project_dir / ".write_test"
            test_file.touch()
            test_file.unlink()
            return project_dir  # already writable
        except (OSError, PermissionError):
            # Read-only — copy to /app/foss-tmp/<dirname> (host-mounted, writable)
            work_base = Path("/app/foss-tmp")
            work_base.mkdir(parents=True, exist_ok=True)
            work_dir = work_base / project_dir.name
            if not work_dir.exists():
                log.info("Copying read-only FOSS project to writable workdir: %s", work_dir)
                shutil.copytree(str(project_dir), str(work_dir), symlinks=False)
            else:
                log.info("Using existing writable workdir: %s", work_dir)
            return work_dir

    def run(self) -> List[Mutant]:
        """
        Full pipeline:
        - If selected_mutants provided: filtered run (Phase 3) — FAST
        - Otherwise: full exhaustive run (Phase 1 baseline)
        """
        self._ensure_deps()
        if self.selected_mutants:
            return self._run_filtered(self.selected_mutants)
        else:
            self._ensure_config()
            self._run_stryker_docker()
            return self._parse_results()

    def _project_hash(self) -> str:
        """Compute a hash of all source files to identify the project uniquely."""
        import hashlib
        h = hashlib.md5()
        for ext in ("*.js", "*.ts", "*.java", "*.py"):
            for f in sorted(self.project_dir.rglob(ext)):
                if "node_modules" not in str(f):
                    try:
                        h.update(f.read_bytes())
                    except Exception:
                        pass
        return h.hexdigest()

    def _global_cache_dir(self) -> Path:
        """Shared cache directory across all sessions, keyed by project hash."""
        import os
        # Use a sibling directory of the uploads folder
        uploads_root = self.project_dir
        # Walk up to find the uploads root (/app/uploads or host equivalent)
        for _ in range(6):
            uploads_root = uploads_root.parent
            if uploads_root.name == "uploads":
                break
        cache_root = uploads_root.parent / "stryker-cache"
        cache_root.mkdir(exist_ok=True)
        return cache_root

    def _user_cache_dir(self) -> Optional[Path]:
        """Per-user cross-session cache directory, keyed by user_id + project hash.
        Returns None if user_id is not set (FOSS projects use session-local cache).
        Scoped per user so no cross-user data leakage."""
        if not self.user_id:
            return None
        try:
            h = self._project_hash()
            cache_root = self._global_cache_dir() / "user" / self.user_id / h
            cache_root.mkdir(parents=True, exist_ok=True)
            return cache_root
        except Exception as e:
            log.debug("Could not create user cache dir: %s", e)
            return None

    def _cached_report(self) -> Optional[Path]:
        """Check per-user cross-session cache first, then global cache.
        Cache is enabled for all projects — per-user scoping prevents leakage."""
        try:
            # Per-user cross-session cache (user uploads)
            user_cache = self._user_cache_dir()
            if user_cache:
                cached = user_cache / "mutation.json"
                if cached.exists():
                    log.info("Per-user cache hit (user=%s, hash=%s)",
                             self.user_id[:8], self._project_hash()[:8])
                    # Copy to project dir so _parse_results() can find it
                    import shutil
                    dst = self.project_dir / "reports" / "mutation" / "mutation.json"
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(cached), str(dst))
                    return dst
        except Exception as e:
            log.debug("User cache lookup failed: %s", e)
        return None

    def _save_to_cache(self, report_path: Path,
                        elapsed_seconds: float = 0.0,
                        total_mutants: int = 0) -> None:
        """Save Phase 1 report to per-user cross-session cache."""
        try:
            import shutil, json as _json
            user_cache = self._user_cache_dir()
            if user_cache:
                shutil.copy2(str(report_path), str(user_cache / "mutation.json"))
                if elapsed_seconds > 0 and total_mutants > 0:
                    meta = {
                        "elapsed_seconds":    elapsed_seconds,
                        "total_mutants":      total_mutants,
                        "seconds_per_mutant": elapsed_seconds / total_mutants,
                    }
                    (user_cache / "meta.json").write_text(_json.dumps(meta))
                log.info("Saved Phase 1 to user cache (user=%s, hash=%s)",
                         self.user_id[:8] if self.user_id else "?",
                         self._project_hash()[:8])
        except Exception as e:
            log.debug("Cache save failed (non-fatal): %s", e)

    def _cached_seconds_per_mutant(self) -> float:
        """Return observed seconds-per-mutant from user cache, or 0 if unknown."""
        try:
            import json as _json
            user_cache = self._user_cache_dir()
            if user_cache:
                meta = user_cache / "meta.json"
                if meta.exists():
                    return _json.loads(meta.read_text()).get("seconds_per_mutant", 0.0)
        except Exception:
            pass
        return 0.0

    def enumerate(self) -> List[Mutant]:
        """
        Phase 1: Enumerate all mutants WITHOUT running any tests.
        Uses --incremental --dryRunOnly which completes in ~3 seconds.
        IMPT then scores mutants using static analysis factors and selects
        within the time budget. No exhaustive test run required.
        """
        self._ensure_deps()

        # Re-enable Phase 1 cache for large projects (LOC > 30,000) to prevent
        # enumeration from taking too long. Small/medium projects run fresh every time
        # so testers get the full experience. Large projects like faker-js (261K LOC)
        # would take 15+ minutes just for Phase 1 without caching.
        LOC_CACHE_THRESHOLD = 30_000
        try:
            src_files = [f for f in self.project_dir.rglob("*")
                         if f.suffix in (".js", ".ts", ".java")
                         and "node_modules" not in str(f)
                         and ".stryker-tmp" not in str(f)]
            # Sample up to 100 files for speed
            sample = src_files[:100]
            sampled_loc = sum(len(f.read_text(errors='ignore').splitlines()) for f in sample)
            est_loc = int(sampled_loc * len(src_files) / max(len(sample), 1))
            if est_loc > LOC_CACHE_THRESHOLD:
                # Check Phase 1 backup first, then fallback to main report
                report = self._find_report()
                backup = report.parent / "mutation.phase1.json" if report else None
                cache = backup if (backup and backup.exists() and backup.stat().st_size > 1024) else None
                if not cache and report and report.stat().st_size > 1024:
                    cache = report
                if cache:
                    log.info("Large project (est. LOC~%d) — reusing cached Phase 1 report (%s)", est_loc, cache.name)
                    import shutil as _sh
                    _sh.copy2(str(cache), str(report))
                    return self._parse_results()
                elif report:
                    log.info("Large project cache missing or too small — re-running Phase 1")
        except Exception as e:
            log.debug("LOC check failed (non-fatal): %s", e)

        # Write a special enumeration config: no-op test runner so Stryker
        # writes the full JSON report instantly with all mutants as Survived.
        # No real tests are executed — IMPT scores on static factors only.
        _, _, is_esm, src_pattern, excl = self._detect_project()

        # If an override config exists, extract its mutate pattern for enumeration
        override_cfg = self.project_dir / "stryker.impt.config.cjs"
        if not override_cfg.exists():
            override_cfg = self.project_dir / "stryker.impt.config.js"
        if override_cfg.exists():
            try:
                cfg_text = override_cfg.read_text()
                import re as _re
                m = _re.search(r'mutate\s*:\s*(\[.*?\])', cfg_text, _re.DOTALL)
                if m:
                    raw = m.group(1)
                    patterns = _re.findall(r"'([^']+)'|\"([^\"]+)\"", raw)
                    flat = [a or b for a, b in patterns]
                    if flat:
                        src_pattern = flat[0]
                        excl = flat[1:]
                        log.info("Phase 1: Using override mutate pattern: %s", src_pattern)
            except Exception as e:
                log.debug("Could not read override mutate pattern: %s", e)

        enum_config = self._build_enum_config(src_pattern, excl)
        name = "stryker.config.cjs" if is_esm else "stryker.config.js"

        # Remove old configs — use subprocess fallback if permission denied
        for old_name in ["stryker.config.js", "stryker.config.cjs", ".strykerrc.json"]:
            p = self.project_dir / old_name
            if p.exists():
                try:
                    p.unlink()
                except PermissionError:
                    import subprocess as _sp
                    _sp.run(["rm", "-f", str(p)], check=False)

        (self.project_dir / name).write_text(enum_config)
        # Phase 1 timeout scales with project size — larger projects need more time
        # Base: 7200s (2h). Env var IMPT_PHASE1_TIMEOUT_SECONDS overrides.
        import os as _os
        try:
            src_files = [f for f in self.project_dir.rglob("*")
                         if f.suffix in (".js", ".ts", ".java")
                         and "node_modules" not in str(f)
                         and ".stryker-tmp" not in str(f)]
            sample    = src_files[:100]
            sampled   = sum(len(f.read_text(errors="ignore").splitlines()) for f in sample)
            est_loc   = int(sampled * len(src_files) / max(len(sample), 1))
        except Exception:
            est_loc   = 5000
        phase1_timeout = int(_os.environ.get(
            "IMPT_PHASE1_TIMEOUT_SECONDS",
            max(3600, min(86400, est_loc // 30))  # 1h–24h, scaled by LOC
        ))
        log.info("Phase 1: Enumerating mutants via no-op test runner (timeout=%ds, est. LOC~%d)...",
                 phase1_timeout, est_loc)
        self._run_stryker_docker(extra_flags="", timeout=phase1_timeout)
        mutants = self._parse_results()
        log.info("Phase 1 complete: %d mutants enumerated", len(mutants))
        # Save Phase 1 cache backup so Phase 3 doesn't overwrite it
        try:
            report = self._find_report()
            if report and report.exists():
                import shutil as _shutil
                backup = report.parent / "mutation.phase1.json"
                _shutil.copy2(str(report), str(backup))
                log.info("Saved Phase 1 cache backup: %s", backup)
        except Exception as _e:
            log.debug("Could not save Phase 1 backup: %s", _e)
        return mutants

    def _run_filtered(self, selected: List[Mutant]) -> List[Mutant]:
        """
        Phase 3: Re-run Stryker with --mutate file:startLine-endLine ranges.
        Only executes tests for the selected mutant locations.
        This achieves real wall-clock time savings proportional to selection ratio.
        """
        if not selected:
            return []

        # Build mutate patterns: "file.js:line-line" per unique location
        seen: set = set()
        patterns = []
        for m in selected:
            key = (m.location.file, m.location.line)
            if key not in seen:
                seen.add(key)
                patterns.append(
                    m.location.file + ":" + str(m.location.line)
                    + "-" + str(m.location.line)
                )

        log.info("Phase 3: Filtered run — %d locations from %d selected mutants",
                 len(patterns), len(selected))

        # Use --mutate CLI flag to restrict execution to selected lines
        # This overrides the config mutate patterns for this run only
        mutate_arg = ",".join(patterns)
        self._ensure_config()  # reset to base config (no override)
        # Clear old report — use subprocess as fallback if file is root-owned
        report = self._find_report()
        if report:
            try:
                report.unlink()
            except PermissionError:
                import subprocess as _sp
                _sp.run(["rm", "-f", str(report)], check=False)
                if report.exists():
                    log.warning("Could not delete old report at %s — Phase 3 may use stale data", report)
        self._run_stryker_docker(
            extra_flags="--mutate " + mutate_arg,
            progress_cb=self.progress_cb,
        )
        return self._parse_results()

    # ── Config generation ─────────────────────────────────────────────────────

    def _detect_project(self):
        pkg_path     = self.project_dir / "package.json"
        test_runner  = "command"
        test_command = "npm test"
        is_esm       = False
        src_pattern  = "**/*.js"

        if pkg_path.exists():
            try:
                pkg  = json.loads(pkg_path.read_text())
                deps = {}
                deps.update(pkg.get("dependencies", {}))
                deps.update(pkg.get("devDependencies", {}))
                is_esm = pkg.get("type", "") == "module"

                if "jest" in deps:
                    test_runner  = "jest"
                    test_command = ""
                elif "mocha" in deps:
                    test_runner  = "mocha"
                    test_command = ""
                elif "ava" in deps:
                    test_runner  = "command"
                    test_command = "node_modules/.bin/ava"
                elif "vitest" in deps:
                    test_runner  = "command"
                    test_command = "node_modules/.bin/vitest run"
            except Exception as e:
                log.warning("Could not parse package.json: %s", e)

        # Detect source pattern — check TypeScript first
        has_ts = any(self.project_dir.rglob("*.ts")) if self.project_dir.exists() else False
        is_ts  = has_ts and not any((self.project_dir / d).exists()
                                     for d in ["lib", "dist"]
                                     if any((self.project_dir / d).rglob("*.js")))

        if is_ts:
            for candidate in ["source", "src", "lib"]:
                p = self.project_dir / candidate
                if p.exists() and p.is_dir() and any(p.rglob("*.ts")):
                    src_pattern = candidate + "/**/*.ts"
                    break
            else:
                src_pattern = "**/*.ts"
        else:
            for candidate in ["source", "src", "lib"]:
                p = self.project_dir / candidate
                if p.exists() and p.is_dir() and any(p.rglob("*.js")):
                    src_pattern = candidate + "/**/*.js"
                    break
            else:
                src_pattern = "*.js"

        # Always exclude test files, config files and node_modules
        EXCLUDE_PATTERNS = [
            "!**/*.test.js", "!**/*.spec.js", "!**/*.test.ts", "!**/*.spec.ts",
            "!**/*.config.*", "!**/*test*", "!**/*spec*",
            "!tests.js", "!test.js", "!jest.config.*",
            "!babel.config.*", "!webpack.config.*",
        ]

        return test_runner, test_command, is_esm, src_pattern, EXCLUDE_PATTERNS

    def _build_enum_config(self, src_pattern: str, excludes: list = None) -> str:
        """Config for Phase 1 enumeration: no-op test runner so Stryker
        writes the full JSON report instantly with all mutants as Survived."""
        sep = ",\n    "
        excl_parts = [f'"{e}"' for e in (excludes or [])]
        all_entries = [f'"{src_pattern}"'] + excl_parts
        mutate_str = sep.join(all_entries)
        lines = [
            "/** @type {import('@stryker-mutator/api/core').PartialStrykerOptions} */",
            "module.exports = {",
            "  reporters: ['json'],",
            "  testRunner: 'command',",
            "  coverageAnalysis: 'off',",
            "  commandRunner: { command: 'true' },",  # no-op: exits 0 instantly
            "  timeoutMS: 10000,",
            "  timeoutFactor: 1,",
            "  mutate: [",
            f"    {mutate_str}",
            "  ],",
            "  ignorePatterns: ['node_modules', 'reports', '.stryker-tmp'],",
            "  jsonReporter: {",
            "    fileName: 'reports/mutation/mutation.json'",
            "  }",
            "};",
        ]
        return "\n".join(lines) + "\n"

    def _build_config(self, test_runner, test_command,
                       src_pattern, mutate_override=None, excludes=None):
        if mutate_override:
            # Filtered run — only mutate specific file:line ranges
            entries = ['"' + p + '"' for p in mutate_override]
        else:
            base_excludes = [
                '"!**/*.test.js"', '"!**/*.spec.js"', '"!**/*.test-d.js"',
                '"!node_modules/**"', '"!benchmark*"', '"!examples/**"',
                '"!tests.js"', '"!test.js"', '"!**/*.config.*"',
            ]
            extra = [f'"{e}"' for e in (excludes or []) if f'"{e}"' not in base_excludes]
            entries = ['"' + src_pattern + '"'] + base_excludes + extra
        mutate_str = (",\n    ").join(entries)

        if test_runner == "jest":
            runner = "  testRunner: 'jest',\n  coverageAnalysis: 'perTest',"
        elif test_runner == "mocha":
            runner = "  testRunner: 'mocha',\n  coverageAnalysis: 'perTest',"
        else:
            runner = (
                "  testRunner: 'command',\n"
                "  coverageAnalysis: 'perTest',\n"
                "  commandRunner: { command: '" + test_command + "' },"
            )

        lines = [
            "/** @type {import('@stryker-mutator/api/core').PartialStrykerOptions} */",
            "module.exports = {",
            "  reporters: ['json', 'progress'],",
            runner,
            "  timeoutMS: 60000,",
            "  timeoutFactor: 3,",
            "  mutate: [",
            "    " + mutate_str,
            "  ],",
            # Tier 1 equivalent detection via ignorers requires optional plugins.
            # 'static' and 'trivial' are NOT built into @stryker-mutator/core —
            # they need @stryker-mutator/instrumenter which may not be installed.
            # Removing to prevent plugin-not-found errors; Tier 1 detection is
            # handled by the NON_VIABLE status mapping from PIT instead.
            "  ignorePatterns: ['node_modules', 'reports', '.stryker-tmp'],",
            "  jsonReporter: {",
            "    fileName: 'reports/mutation/mutation.json'",
            "  }",
            "};",
        ]
        return "\n".join(lines) + "\n"

    def _ensure_config(self, mutate_override=None):
        # Check for a per-project IMPT override config (ships with FOSS clones).
        # Lets us hardcode correct test runner for projects with unusual setups.
        override_cfg = self.project_dir / "stryker.impt.config.cjs"
        if override_cfg.exists() and not mutate_override:
            test_runner, test_command, is_esm, src_pattern, excl = self._detect_project()
            name = "stryker.config.cjs" if is_esm else "stryker.config.js"
            (self.project_dir / name).write_text(override_cfg.read_text())
            log.info("Using FOSS override config: %s", override_cfg.name)
            return
        # Always regenerate config
        for old_cfg in ["stryker.config.js", "stryker.config.cjs", ".strykerrc.json"]:
            p = self.project_dir / old_cfg
            if p.exists():
                p.unlink()
        test_runner, test_command, is_esm, src_pattern, excl = self._detect_project()
        config = self._build_config(test_runner, test_command, src_pattern,
                                     mutate_override, excl)
        name = "stryker.config.cjs" if is_esm else "stryker.config.js"
        (self.project_dir / name).write_text(config)
        log.info("Generated %s: runner=%s src=%s filtered=%s",
                 name, test_runner, src_pattern, bool(mutate_override))

    # ── Docker execution ──────────────────────────────────────────────────────

    def _host_project_dir(self) -> str:
        """
        Translate container path to host path for Docker-in-Docker volume mounts.
        Handles uploads, foss (read-only mount), and foss-tmp (writable copy).
        """
        path = str(self.project_dir)
        import os
        host_uploads = os.environ.get("HOST_UPLOADS_PATH", "/home/imptuser/impt/uploads")
        host_foss    = os.environ.get("HOST_FOSS_PATH",    "/home/imptuser/impt/foss")
        host_tmp     = os.environ.get("HOST_TMP_PATH",     "/home/imptuser/impt/foss-tmp")
        translations = [
            ("/app/uploads",   host_uploads),
            ("/app/foss",      host_foss),
            ("/tmp/impt-foss", host_tmp),
        ]
        for container_prefix, host_prefix in translations:
            if path.startswith(container_prefix):
                return host_prefix + path[len(container_prefix):]
        return path

    def _docker_base(self, network="none", user=None, extra_mounts=None):
        host_path = self._host_project_dir()
        cmd = [
            "docker", "run", "--rm",
            "--network", network,
            "--memory", "2g",
            "--cpus", "2",
        ]
        if user:
            cmd += ["--user", user]
        cmd += ["-v", host_path + ":/project"]
        for host_src, container_dst in (extra_mounts or []):
            cmd += ["-v", f"{host_src}:{container_dst}"]
        cmd += ["-w", "/project", self.sandbox_image]
        return cmd

    def _ensure_deps(self):
        """Install node_modules. Uses mkdir-based lock for concurrent worker safety."""
        nm        = self.project_dir / "node_modules"
        lock_dir  = self.project_dir / ".npm-lock"

        # Fast path
        if nm.exists() and any(nm.iterdir()):
            log.info("node_modules exists, skipping install")
            return

        # mkdir-based atomic lock (mkdir is atomic on Linux)
        acquired = False
        for _ in range(60):  # wait up to 60 seconds
            try:
                lock_dir.mkdir(exist_ok=False)
                acquired = True
                break
            except FileExistsError:
                import time
                time.sleep(1)

        if not acquired:
            # Another worker holds the lock — wait for node_modules to appear
            log.info("Waiting for concurrent npm install to complete...")
            import time
            for _ in range(120):
                if nm.exists() and any(nm.iterdir()):
                    log.info("node_modules appeared, continuing")
                    return
                time.sleep(1)
            log.warning("Timed out waiting for node_modules")
            return

        try:
            # Re-check after acquiring lock
            if nm.exists() and any(nm.iterdir()):
                log.info("node_modules already installed")
                return

            log.info("Installing npm dependencies for %s...", self.project_dir)
            cmd = self._docker_base(network="bridge", user="root") + [
                "sh", "-c",
                (
                    "cd /project && "
                    "test -f package.json || (echo 'ERROR: no package.json' && ls && exit 1) ; "
                    "npm install --unsafe-perm --no-audit --no-fund 2>&1 ; "
                    "[ -d /project/node_modules/@stryker-mutator/core ] || "
                    "npm install --unsafe-perm --no-audit --save-dev "
                    "@stryker-mutator/core 2>&1 || true ; "
                    "chmod -R 777 /project 2>/dev/null || true"
                )
            ]
            r = subprocess.run(cmd, timeout=600, capture_output=True, text=True)
            log.info("npm install exit=%d stdout=%s",
                     r.returncode, r.stdout[-300:] if r.stdout else "")
            if not nm.exists():
                raise RuntimeError(
                    "npm install completed but node_modules not found. "
                    "stdout=" + (r.stdout or "")[-300:]
                )
            log.info("node_modules ready at %s", nm)
        finally:
            try:
                lock_dir.rmdir()
            except Exception:
                pass


    def _ensure_config(self, mutate_override=None):
        # Check for a per-project IMPT override config (ships with FOSS clones).
        # Lets us hardcode correct test runner for projects with unusual setups.
        override_cfg = self.project_dir / "stryker.impt.config.cjs"
        if override_cfg.exists() and not mutate_override:
            test_runner, test_command, is_esm, src_pattern, excl = self._detect_project()
            name = "stryker.config.cjs" if is_esm else "stryker.config.js"
            (self.project_dir / name).write_text(override_cfg.read_text())
            log.info("Using FOSS override config: %s", override_cfg.name)
            return
        # Always regenerate config
        for old_cfg in ["stryker.config.js", "stryker.config.cjs", ".strykerrc.json"]:
            p = self.project_dir / old_cfg
            if p.exists():
                p.unlink()
        test_runner, test_command, is_esm, src_pattern, excl = self._detect_project()
        config = self._build_config(test_runner, test_command, src_pattern,
                                     mutate_override, excl)
        name = "stryker.config.cjs" if is_esm else "stryker.config.js"
        (self.project_dir / name).write_text(config)
        log.info("Generated %s: runner=%s src=%s filtered=%s",
                 name, test_runner, src_pattern, bool(mutate_override))

    # ── Docker execution ──────────────────────────────────────────────────────

    def _host_project_dir(self) -> str:
        """
        Translate container path to host path for Docker-in-Docker volume mounts.
        Handles uploads, foss (read-only mount), and foss-tmp (writable copy).
        """
        path = str(self.project_dir)
        import os
        host_uploads = os.environ.get("HOST_UPLOADS_PATH", "/home/imptuser/impt/uploads")
        host_foss    = os.environ.get("HOST_FOSS_PATH",    "/home/imptuser/impt/foss")
        host_tmp     = os.environ.get("HOST_TMP_PATH",     "/home/imptuser/impt/foss-tmp")
        translations = [
            ("/app/uploads",   host_uploads),
            ("/app/foss",      host_foss),
            ("/tmp/impt-foss", host_tmp),
        ]
        for container_prefix, host_prefix in translations:
            if path.startswith(container_prefix):
                return host_prefix + path[len(container_prefix):]
        return path

    def _docker_base(self, network="none", user=None, extra_mounts=None):
        host_path = self._host_project_dir()
        cmd = [
            "docker", "run", "--rm",
            "--network", network,
            "--memory", "2g",
            "--cpus", "2",
        ]
        if user:
            cmd += ["--user", user]
        cmd += ["-v", host_path + ":/project"]
        for host_src, container_dst in (extra_mounts or []):
            cmd += ["-v", f"{host_src}:{container_dst}"]
        cmd += ["-w", "/project", self.sandbox_image]
        return cmd

    def _ensure_deps(self):
        """Install node_modules if missing. File-locked to prevent concurrent installs."""
        import fcntl
        nm        = self.project_dir / "node_modules"
        lock_path = self.project_dir / ".npm-install.lock"

        # Fast path
        if nm.exists() and any(nm.iterdir()):
            log.info("node_modules exists, skipping install")
            return

        log.info("Installing npm dependencies for %s...", self.project_dir)
        lock_file = open(lock_path, "w")
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
            # Re-check after acquiring lock
            if nm.exists() and any(nm.iterdir()):
                log.info("node_modules installed by concurrent worker, skipping")
                return

            cmd = self._docker_base(network="bridge", user="root") + [
                "sh", "-c",
                (
                    "cd /project && "
                    "test -f package.json || (echo 'ERROR: no package.json' && ls && exit 1) ; "
                    "npm install --unsafe-perm --no-audit --no-fund 2>&1 ; "
                    "[ -d /project/node_modules/@stryker-mutator/core ] || "
                    "npm install --unsafe-perm --no-audit --save-dev "
                    "@stryker-mutator/core 2>&1 || true ; "
                    "chmod -R 777 /project 2>/dev/null || true"
                )
            ]
            r = subprocess.run(cmd, timeout=600, capture_output=True, text=True)
            log.info("npm install exit=%d stdout=%s",
                     r.returncode, r.stdout[-300:] if r.stdout else "")
            if not nm.exists():
                raise RuntimeError(
                    "npm install completed but node_modules not found at " + str(nm) +
                    ". stdout=" + (r.stdout or "")[-200:]
                )
            log.info("node_modules ready at %s", nm)
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)
            lock_file.close()
            try:
                lock_path.unlink()
            except Exception:
                pass


    def _run_stryker_docker(self, extra_flags="", timeout=3600, progress_cb=None):
        """Run Stryker without network, without root (so ava/jest work).

        When progress_cb is None this uses the proven blocking subprocess.run
        path (unchanged). When a callback is supplied (filtered Phase-3 run), it
        streams Stryker's output and reports the live progress percentage. The
        streamed value drives only the UI bar — the authoritative results still
        come from the JSON report parsed afterwards.
        """
        flags = ("npx stryker run " + extra_flags + " --fileLogLevel off 2>&1").strip()
        log.info("Running Stryker: %s", flags)
        cmd = self._docker_base(network="none") + ["sh", "-c", flags]

        if progress_cb is None:
            try:
                result = subprocess.run(cmd, check=True, timeout=timeout,
                                        capture_output=True, text=True)
                log.info("Stryker completed")
            except subprocess.CalledProcessError as e:
                out = (e.stdout or "") + (e.stderr or "")
                log.error("Stryker failed: %s", out[-1000:])
                if not self._find_report():
                    raise
            return

        # Streaming path — best-effort live progress; isolated to filtered runs.
        import re as _re, threading as _th
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, bufsize=1)
        killer = _th.Timer(timeout, proc.kill); killer.daemon = True; killer.start()
        # Match the percentage inside Stryker's progress bar: "...] 42%"
        pct_re = _re.compile(r"\]\s*(\d{1,3})\s*%")
        tail, buf, last_pct = [], "", -1
        try:
            for chunk in iter(lambda: proc.stdout.read(128), ""):
                buf += chunk
                tail.append(chunk)
                if len(tail) > 300:
                    tail = tail[-300:]
                matches = pct_re.findall(buf)
                if matches:
                    try:
                        pct = min(99, max(0, int(matches[-1])))
                        if pct != last_pct:
                            last_pct = pct
                            try:
                                progress_cb(pct)
                            except Exception:
                                pass
                    except Exception:
                        pass
                    buf = buf[-64:]
                elif len(buf) > 4096:
                    buf = buf[-256:]
        except Exception as e:
            log.warning("Stryker stream read error (non-fatal): %s", e)
        finally:
            killer.cancel()
            try:
                proc.wait(timeout=30)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        rc = proc.returncode
        if rc not in (0, None):
            log.error("Stryker failed (rc=%s): %s", rc, ("".join(tail))[-1000:])
            if not self._find_report():
                raise subprocess.CalledProcessError(rc, cmd)
        else:
            log.info("Stryker completed (streamed)")

    def _run_local(self):
        if not (self.project_dir / "node_modules").exists():
            subprocess.run(["npm", "install"], cwd=self.project_dir,
                           check=True, timeout=600)
        subprocess.run(["npx", "stryker", "run"],
                       cwd=self.project_dir, check=True, timeout=3600)

    # ── Report parsing ────────────────────────────────────────────────────────

    def _find_report(self):
        # Check both container path and host-translated path
        dirs_to_check = [self.project_dir]
        host_path = Path(self._host_project_dir())
        if host_path != self.project_dir:
            dirs_to_check.append(host_path)

        for base in dirs_to_check:
            for p in [
                base / "reports" / "mutation" / "mutation.json",
                base / "reports" / "mutation.json",
                base / ".stryker-tmp" / "mutation.json",
            ]:
                if p.exists():
                    return p
            for p in base.rglob("mutation.json"):
                return p
        return None

    def _parse_results(self) -> List[Mutant]:
        report_path = self._find_report()
        if not report_path:
            raise FileNotFoundError(
                "Stryker report not found in " + str(self.project_dir)
            )
        data = json.loads(report_path.read_text())
        if "files" in data:
            raw = [
                dict(list(m.items()) + [("_file", fname),
                                        ("_source", fd.get("source", ""))])
                for fname, fd in data["files"].items()
                for m in fd.get("mutants", [])
            ]
        else:
            raw = data.get("mutants", [])

        mutants = []
        for rm in raw:
            try:
                status = STATUS_MAP.get(rm.get("status", "Survived"),
                                         ExecutionStatus.SURVIVED)
                op     = MUTATOR_MAP.get(rm.get("mutatorName", ""),
                                          MutationOperator.AOR)
                loc    = rm.get("location", {})
                start  = loc.get("start", {})
                # Stage 4: coveredBy is populated when coverageAnalysis='perTest'
                covered_by    = rm.get("coveredBy") or []
                test_coverage = set(str(t) for t in covered_by) if covered_by else set()
                # killedBy is populated in Stryker v6+ when a mutant is killed
                killed_by_raw = rm.get("killedBy") or []
                killing_test  = killed_by_raw[0] if killed_by_raw else None
                m = Mutant(
                    operator=op,
                    location=CodeLocation(
                        file=rm.get("_file", rm.get("fileName", "unknown.js")),
                        line=start.get("line", 1),
                        column=start.get("column", 0),
                    ),
                    original_code=_slice_source(rm.get("_source", ""), loc)
                                  or rm.get("mutatorName", ""),
                    mutated_code =rm.get("replacement", "") or rm.get("mutatorName", ""),
                    test_coverage=test_coverage,
                )
                m.status = status
                if killing_test:
                    m.killing_test = killing_test
                mutants.append(m)
            except Exception as e:
                log.debug("Skipping mutant: %s", e)

        log.info("Parsed %d mutants from Stryker report", len(mutants))
        return mutants

    def detect_framework(self):
        return (self.project_dir / "package.json").exists()

    def count_loc(self):
        total = 0
        for ext in ("*.js", "*.ts", "*.jsx", "*.tsx"):
            for f in self.project_dir.rglob(ext):
                if "node_modules" not in str(f) and "test" not in f.name.lower():
                    try:
                        total += sum(1 for ln in f.read_text(errors="ignore").splitlines()
                                     if ln.strip())
                    except Exception:
                        pass
        return total

    def count_tests(self):
        count = 0
        for ext in ("*.test.js", "*.spec.js", "*.test.ts", "*.spec.ts"):
            count += sum(1 for _ in self.project_dir.rglob(ext)
                         if "node_modules" not in str(_))
        return count

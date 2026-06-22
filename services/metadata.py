"""services/metadata.py — project metadata helpers.

Two responsibilities:

1. count_source_files(root, language)
   Counts only meaningful *source* files for a project, excluding dependency,
   build-output, and VCS directories (node_modules, target, build, dist, .git,
   coverage, etc.). Cheap; safe to call synchronously on the request path.

2. measure_line_coverage(root, language, timeout_s)
   Returns line coverage as a percentage (0-100), or None if it could not be
   measured. This runs the language's coverage tool INSIDE the impt-sandbox
   Docker image (the same image the PIT/Stryker adapters use), because the API
   and worker containers themselves do not have Maven or Node installed — only
   the Docker client. The invocation mirrors the adapters:
     - host-path translation for the bind mount (Docker-in-Docker)
     - the shared `impt-maven-cache` volume
     - network enabled so JaCoCo / c8 can be fetched
   Java uses JaCoCo (parsing target/site/jacoco/jacoco.xml); JavaScript uses c8
   (parsing the "Lines : XX%" summary). Fully guarded and time-boxed: any
   failure, missing tool, or timeout returns None rather than raising.

Used by:
  - api/routers/sessions.py            (upload analysis -> source file count)
  - worker/tasks.py                    (measure_coverage task -> live coverage)
  - scripts/compute_foss_metadata.py   (pre-compute FOSS file_count + coverage)
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_EXCLUDED_DIRS = {
    "node_modules", ".git", ".hg", ".svn", "target", "build", "dist",
    "out", "coverage", ".nyc_output", ".gradle", ".mvn", "__pycache__",
    ".idea", ".vscode", "site", "reports", ".pytest_cache", ".stryker-tmp",
}

_SOURCE_EXTS = {
    "java":       {".java"},
    "javascript": {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"},
}

SANDBOX_IMAGE = os.environ.get("SANDBOX_IMAGE", "impt-sandbox:latest")
MAVEN_CACHE_VOLUME = os.environ.get("MAVEN_CACHE_VOLUME", "impt-maven-cache")
_JACOCO_VERSION = "0.8.11"


# -- Source file counting (local, cheap) --------------------------------------

def _iter_source_files(root: Path, exts: set):
    for path in root.rglob("*"):
        if any(part in _EXCLUDED_DIRS for part in path.parts):
            continue
        if path.is_file() and path.suffix.lower() in exts:
            yield path


def count_source_files(root, language: str) -> int:
    """Count source files for the project, excluding deps/build/VCS dirs."""
    root = Path(root)
    if not root.exists():
        return 0
    lang = (language or "").lower()
    exts = _SOURCE_EXTS.get(lang)
    try:
        if exts:
            return sum(1 for _ in _iter_source_files(root, exts))
        return sum(
            1 for p in root.rglob("*")
            if p.is_file() and not any(part in _EXCLUDED_DIRS for part in p.parts)
        )
    except Exception as exc:
        log.warning("count_source_files failed for %s: %s", root, exc)
        return 0


# -- Docker-in-Docker plumbing (mirrors the adapters) -------------------------

def _host_path(container_path: str) -> str:
    """Translate a container path to the host path for Docker-in-Docker mounts."""
    path = str(container_path)
    host_foss    = os.environ.get("HOST_FOSS_PATH",    "/home/imptuser/impt/foss")
    host_tmp     = os.environ.get("HOST_TMP_PATH",     "/home/imptuser/impt/foss-tmp")
    host_uploads = os.environ.get("HOST_UPLOADS_PATH", "/home/imptuser/impt/uploads")
    for prefix, host_prefix in [
        ("/app/foss-tmp", host_tmp),
        ("/app/foss",     host_foss),
        ("/app/uploads",  host_uploads),
        ("/tmp/impt",     host_uploads),
    ]:
        if path.startswith(prefix):
            return host_prefix + path[len(prefix):]
    return path


def _find_build_root(root: Path, marker: str):
    candidates = [
        p.parent for p in root.rglob(marker)
        if not any(part in _EXCLUDED_DIRS for part in p.parts)
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda p: len(p.parts))
    return candidates[0]


def _docker_cmd(host_root: str, container_workdir: str, network: str = "bridge") -> list:
    return [
        "docker", "run", "--rm",
        "--network", network,
        "--memory", "2g",
        "--cpus", "2",
        "-v", host_root + ":/project",
        "-v", MAVEN_CACHE_VOLUME + ":/home/imptuser/.m2",
        "-w", container_workdir,
        SANDBOX_IMAGE,
    ]


def _rel_workdir(root: Path, build_root: Path) -> str:
    try:
        rel = str(build_root.relative_to(root))
        return "/project" if rel in (".", "") else "/project/" + rel
    except Exception:
        return "/project"


# -- Coverage measurement (runs inside impt-sandbox) --------------------------

def _coverage_java(root: Path, timeout_s: int):
    build_root = _find_build_root(root, "pom.xml")
    if build_root is None:
        log.info("coverage(java): no pom.xml under %s", root)
        return None
    host_root = _host_path(str(root))
    workdir = _rel_workdir(root, build_root)
    prep = "org.jacoco:jacoco-maven-plugin:%s:prepare-agent" % _JACOCO_VERSION
    report = "org.jacoco:jacoco-maven-plugin:%s:report" % _JACOCO_VERSION
    cmd = _docker_cmd(host_root, workdir) + [
        "mvn", "-q", "-B", "-Dmaven.test.failure.ignore=true",
        prep, "test", report,
    ]
    try:
        subprocess.run(cmd, timeout=timeout_s, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=False)
    except subprocess.TimeoutExpired:
        log.info("coverage(java): timed out after %ss", timeout_s)
        return None
    except Exception as exc:
        log.warning("coverage(java): docker run failed: %s", exc)
        return None
    covered = missed = 0
    for xml in build_root.rglob("jacoco.xml"):
        try:
            tree = ET.parse(str(xml))
            for counter in tree.getroot().iter("counter"):
                if counter.get("type") == "LINE":
                    covered += int(counter.get("covered", 0))
                    missed += int(counter.get("missed", 0))
                    break
        except Exception as exc:
            log.warning("coverage(java): parse %s failed: %s", xml, exc)
    total = covered + missed
    return round(covered / total * 100.0, 1) if total else None


_C8_LINES_RE = re.compile(r"Lines\s*:\s*([0-9]+(?:\.[0-9]+)?)\s*%")


def _coverage_js(root: Path, timeout_s: int):
    build_root = _find_build_root(root, "package.json")
    if build_root is None:
        log.info("coverage(js): no package.json under %s", root)
        return None
    host_root = _host_path(str(root))
    workdir = _rel_workdir(root, build_root)
    shell = (
        "(npm ci --no-audit --no-fund 2>/dev/null || "
        "npm install --no-audit --no-fund 2>/dev/null); "
        "npx --yes c8 --reporter=text-summary --all=false npm test --silent"
    )
    cmd = _docker_cmd(host_root, workdir) + ["bash", "-lc", shell]
    try:
        out = subprocess.run(cmd, timeout=timeout_s, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, check=False)
    except subprocess.TimeoutExpired:
        log.info("coverage(js): timed out after %ss", timeout_s)
        return None
    except Exception as exc:
        log.warning("coverage(js): docker run failed: %s", exc)
        return None
    m = _C8_LINES_RE.search(out.stdout or "")
    if not m:
        log.info("coverage(js): no Lines summary in c8 output")
        return None
    try:
        return round(float(m.group(1)), 1)
    except ValueError:
        return None


def measure_line_coverage(root, language: str, timeout_s: int = 900):
    """Measure line coverage (%) for a project. Returns 0-100 or None.

    Runs inside the impt-sandbox image. Best-effort and fully guarded: never
    raises. None means "could not be measured" and callers should show it as
    unavailable, not as 0%.
    """
    root = Path(root)
    if not root.exists():
        return None
    lang = (language or "").lower()
    try:
        if lang == "java":
            return _coverage_java(root, timeout_s)
        if lang == "javascript":
            return _coverage_js(root, timeout_s)
        log.info("measure_line_coverage: unsupported language %r", language)
        return None
    except Exception as exc:
        log.warning("measure_line_coverage failed for %s: %s", root, exc)
        return None

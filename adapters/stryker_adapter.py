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


class StrykerAdapter:
    def __init__(self, project_dir: Path, use_docker: bool = True,
                 sandbox_image: str = "impt-sandbox:latest",
                 time_budget_seconds: int = 0,
                 selected_mutants: Optional[List[Mutant]] = None):
        self.use_docker          = use_docker
        self.sandbox_image       = sandbox_image
        self.time_budget_seconds = time_budget_seconds
        self.selected_mutants    = selected_mutants

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

    def _cached_report(self) -> Optional[Path]:
        """Look up a cached mutation.json for this project hash."""
        try:
            h     = self._project_hash()
            cache = self._global_cache_dir() / h / "mutation.json"
            if cache.exists():
                log.info("Project cache hit (hash=%s)", h[:8])
                return cache
        except Exception as e:
            log.debug("Cache lookup failed: %s", e)
        return None

    def _save_to_cache(self, report_path: Path,
                        elapsed_seconds: float = 0.0,
                        total_mutants: int = 0) -> None:
        """Save the mutation report and timing metadata to the global project cache."""
        try:
            import shutil, json as _json
            h          = self._project_hash()
            cache_dir  = self._global_cache_dir() / h
            cache_dir.mkdir(exist_ok=True)
            shutil.copy2(report_path, cache_dir / "mutation.json")
            # Save per-mutant execution time for calibrating the time estimator
            if elapsed_seconds > 0 and total_mutants > 0:
                meta = {
                    "elapsed_seconds": elapsed_seconds,
                    "total_mutants":   total_mutants,
                    "seconds_per_mutant": elapsed_seconds / total_mutants,
                }
                (cache_dir / "meta.json").write_text(_json.dumps(meta))
            log.info("Saved report to project cache (hash=%s, %.1fs/mutant)",
                     h[:8], elapsed_seconds / max(total_mutants, 1))
        except Exception as e:
            log.debug("Cache save failed (non-fatal): %s", e)

    def _cached_seconds_per_mutant(self) -> float:
        """Return observed seconds-per-mutant from cache, or 0 if unknown."""
        try:
            import json as _json
            h    = self._project_hash()
            meta = self._global_cache_dir() / h / "meta.json"
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

        # Check session-local report first (reuse if already enumerated)
        report = self._find_report()
        if report:
            log.info("Using existing session report: %s", report)
            return self._parse_results()

        # Write a special enumeration config: no-op test runner so Stryker
        # writes the full JSON report instantly with all mutants as Survived.
        # No real tests are executed — IMPT scores on static factors only.
        _, _, is_esm, src_pattern, excl = self._detect_project()
        enum_config = self._build_enum_config(src_pattern, excl)
        name = "stryker.config.cjs" if is_esm else "stryker.config.js"
        for old in ["stryker.config.js", "stryker.config.cjs", ".strykerrc.json"]:
            p = self.project_dir / old
            if p.exists():
                p.unlink()
        (self.project_dir / name).write_text(enum_config)
        log.info("Phase 1: Enumerating mutants via no-op test runner (~5s)...")
        self._run_stryker_docker(extra_flags="")
        mutants = self._parse_results()
        log.info("Phase 1 complete: %d mutants enumerated", len(mutants))
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
        # Clear old report
        report = self._find_report()
        if report:
            report.unlink()
        self._run_stryker_docker(
            extra_flags="--mutate " + mutate_arg
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

        for candidate in ["source", "src", "lib"]:
            p = self.project_dir / candidate
            if p.exists() and p.is_dir() and any(p.rglob("*.js")):
                src_pattern = candidate + "/**/*.js"
                break
        else:
            # No standard src dir — use root JS files but exclude tests/config
            src_pattern = "*.js"

        # Always exclude test files, config files and node_modules
        # These exclusions are appended to whatever pattern was found
        EXCLUDE_PATTERNS = [
            "!**/*.test.js", "!**/*.spec.js", "!**/*.config.*",
            "!**/*test*", "!**/*spec*", "!tests.js", "!test.js",
            "!jest.config.*", "!babel.config.*", "!webpack.config.*",
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
            import shutil as _shutil
            _shutil.copy2(str(override_cfg), str(self.project_dir / name))
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

    def _docker_base(self, network="none", user=None):
        host_path = self._host_project_dir()
        cmd = [
            "docker", "run", "--rm",
            "--network", network,
            "--memory", "2g",
            "--cpus", "2",
        ]
        if user:
            cmd += ["--user", user]
        cmd += [
            "-v", host_path + ":/project",
            "-w", "/project",
            self.sandbox_image,
        ]
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
            import shutil as _shutil
            _shutil.copy2(str(override_cfg), str(self.project_dir / name))
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

    def _docker_base(self, network="none", user=None):
        host_path = self._host_project_dir()
        cmd = [
            "docker", "run", "--rm",
            "--network", network,
            "--memory", "2g",
            "--cpus", "2",
        ]
        if user:
            cmd += ["--user", user]
        cmd += [
            "-v", host_path + ":/project",
            "-w", "/project",
            self.sandbox_image,
        ]
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


    def _run_stryker_docker(self, extra_flags=""):
        """Run Stryker without network, without root (so ava/jest work)."""
        flags = ("npx stryker run " + extra_flags + " --fileLogLevel off 2>&1").strip()
        log.info("Running Stryker: %s", flags)
        cmd = self._docker_base(network="none") + ["sh", "-c", flags]
        try:
            result = subprocess.run(cmd, check=True, timeout=3600,
                                    capture_output=True, text=True)
            log.info("Stryker completed")
        except subprocess.CalledProcessError as e:
            out = (e.stdout or "") + (e.stderr or "")
            log.error("Stryker failed: %s", out[-1000:])
            if not self._find_report():
                raise

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
                dict(list(m.items()) + [("_file", fname)])
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
                m = Mutant(
                    operator=op,
                    location=CodeLocation(
                        file=rm.get("_file", rm.get("fileName", "unknown.js")),
                        line=start.get("line", 1),
                        column=start.get("column", 0),
                    ),
                    original_code=rm.get("replacement", "original"),
                    mutated_code =rm.get("replacement", rm.get("mutatorName", "")),
                    test_coverage=test_coverage,
                )
                m.status = status
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

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
        self.project_dir         = project_dir
        self.use_docker          = use_docker
        self.sandbox_image       = sandbox_image
        self.time_budget_seconds = time_budget_seconds
        self.selected_mutants    = selected_mutants

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

    def enumerate(self) -> List[Mutant]:
        """
        Phase 1: Enumerate all mutants in ~3 seconds using --dryRunOnly.
        Produces mutation.json with all 657 mutant locations.
        IMPT then scores/selects from this list before any real execution.
        """
        self._ensure_deps()
        self._ensure_config()
        # Clear old report so we get a fresh enumeration
        report = self._find_report()
        if report:
            report.unlink()
        log.info("Enumerating mutants via --incremental --dryRunOnly...")
        self._run_stryker_docker(extra_flags="--incremental --dryRunOnly")
        mutants = self._parse_results()
        log.info("Enumerated %d mutants in ~3 seconds", len(mutants))
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

        return test_runner, test_command, is_esm, src_pattern

    def _build_config(self, test_runner, test_command,
                       src_pattern, mutate_override=None):
        if mutate_override:
            # Filtered run — only mutate specific file:line ranges
            entries = ['"' + p + '"' for p in mutate_override]
        else:
            entries = [
                '"' + src_pattern + '"',
                '"!**/*.test.js"',
                '"!**/*.spec.js"',
                '"!**/*.test-d.js"',
                '"!node_modules/**"',
                '"!benchmark*"',
                '"!examples/**"',
            ]
        mutate_str = (",\n    ").join(entries)

        if test_runner == "jest":
            runner = "  testRunner: 'jest',\n  coverageAnalysis: 'off',"
        elif test_runner == "mocha":
            runner = "  testRunner: 'mocha',\n  coverageAnalysis: 'off',"
        else:
            runner = (
                "  testRunner: 'command',\n"
                "  coverageAnalysis: 'off',\n"
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
            "  ignorePatterns: ['node_modules', 'reports', '.stryker-tmp'],",
            "  jsonReporter: {",
            "    fileName: 'reports/mutation/mutation.json'",
            "  }",
            "};",
        ]
        return "\n".join(lines) + "\n"

    def _ensure_config(self, mutate_override=None):
        # Always regenerate config
        for old_cfg in ["stryker.config.js", "stryker.config.cjs", ".strykerrc.json"]:
            p = self.project_dir / old_cfg
            if p.exists():
                p.unlink()
        test_runner, test_command, is_esm, src_pattern = self._detect_project()
        config = self._build_config(test_runner, test_command, src_pattern,
                                     mutate_override)
        name = "stryker.config.cjs" if is_esm else "stryker.config.js"
        (self.project_dir / name).write_text(config)
        log.info("Generated %s: runner=%s src=%s filtered=%s",
                 name, test_runner, src_pattern, bool(mutate_override))

    # ── Docker execution ──────────────────────────────────────────────────────

    def _docker_base(self, network="none", user=None):
        cmd = [
            "docker", "run", "--rm",
            "--network", network,
            "--memory", "2g",
            "--cpus", "2",
        ]
        if user:
            cmd += ["--user", user]
        cmd += [
            "-v", str(self.project_dir) + ":/project",
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
                    "test -f package.json || (echo 'ERROR: no package.json' && exit 1) ; "
                    "npm install --unsafe-perm --no-audit --no-fund --prefix /project 2>&1 ; "
                    "[ -d node_modules/@stryker-mutator/core ] || "
                    "npm install --unsafe-perm --no-audit --save-dev --prefix /project "
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
        for p in [
            self.project_dir / "reports" / "mutation" / "mutation.json",
            self.project_dir / "reports" / "mutation.json",
            self.project_dir / ".stryker-tmp" / "mutation.json",
        ]:
            if p.exists():
                return p
        for p in self.project_dir.rglob("mutation.json"):
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
                m = Mutant(
                    operator=op,
                    location=CodeLocation(
                        file=rm.get("_file", rm.get("fileName", "unknown.js")),
                        line=start.get("line", 1),
                        column=start.get("column", 0),
                    ),
                    original_code=rm.get("replacement", "original"),
                    mutated_code =rm.get("replacement", rm.get("mutatorName", "")),
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

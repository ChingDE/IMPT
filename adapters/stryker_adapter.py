"""adapters/stryker_adapter.py"""
from __future__ import annotations
import json, logging, subprocess
from pathlib import Path
from typing import List, Optional
from impt.models.mutant import CodeLocation, Mutant, MutationOperator, ExecutionStatus

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
                 sandbox_image: str = "impt-sandbox:latest"):
        self.project_dir   = project_dir
        self.use_docker    = use_docker
        self.sandbox_image = sandbox_image

    def run(self) -> List[Mutant]:
        self._ensure_config()
        if self.use_docker:
            self._install_deps_docker()
            self._run_stryker_docker()
        else:
            self._run_local()
        return self._parse_results()

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

    def _build_config(self, test_runner, test_command, src_pattern):
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

    def _ensure_config(self):
        # Always regenerate — old configs from failed runs may have wrong settings
        for old_cfg in ["stryker.config.js", "stryker.config.cjs", ".strykerrc.json"]:
            p = self.project_dir / old_cfg
            if p.exists():
                p.unlink()
                log.info("Removed old config: %s", old_cfg)
        test_runner, test_command, is_esm, src_pattern = self._detect_project()
        config = self._build_config(test_runner, test_command, src_pattern)
        # Always use .cjs — works for both ESM and CJS projects
        name = "stryker.config.cjs"
        (self.project_dir / name).write_text(config)
        log.info("Generated %s: runner=%s src=%s esm=%s", name, test_runner, src_pattern, is_esm)

    def _docker_base(self, network="none"):
        return [
            "docker", "run", "--rm",
            "--network", network,
            "--memory", "2g",
            "--cpus", "2",
            "-v", str(self.project_dir) + ":/project",
            "-w", "/project",
            self.sandbox_image,
        ]

    def _install_deps_docker(self):
        nm = self.project_dir / "node_modules"
        if nm.exists():
            import shutil
            shutil.rmtree(nm)
            log.info("Cleared old node_modules")
        log.info("Phase 1: npm install (network enabled, running as root)...")
        # Use root explicitly for install phase so it can write to mounted volume
        cmd = [
            "docker", "run", "--rm",
            "--network", "bridge",
            "--memory", "2g",
            "--user", "root",
            "-v", str(self.project_dir) + ":/project",
            "-w", "/project",
            self.sandbox_image,
            "sh", "-c",
            (
                "npm install --unsafe-perm --no-audit --no-fund 2>&1 ; "
                "[ -d node_modules/@stryker-mutator/core ] || "
                "npm install --unsafe-perm --no-audit --save-dev "
                "@stryker-mutator/core 2>&1 || true ; "
                # Fix permissions so non-root can read node_modules
                "chmod -R 755 node_modules 2>/dev/null || true"
            )
        ]
        try:
            r = subprocess.run(cmd, timeout=600, capture_output=True, text=True)
            log.info("npm install done (exit %d)", r.returncode)
        except Exception as e:
            log.warning("npm install warning: %s", e)

    def _run_stryker_docker(self):
        log.info("Phase 2: Running Stryker (network disabled)...")
        cmd = self._docker_base(network="none") + [
            "sh", "-c", "npx stryker run --fileLogLevel off 2>&1"
        ]
        try:
            subprocess.run(cmd, check=True, timeout=3600,
                           capture_output=True, text=True)
            log.info("Stryker completed")
        except subprocess.CalledProcessError as e:
            out = (e.stdout or "") + (e.stderr or "")
            log.error("Stryker failed: %s", out[-1000:])
            if not self._find_report():
                raise

    def _run_local(self):
        if not (self.project_dir / "node_modules").exists():
            subprocess.run(["npm", "install"], cwd=self.project_dir, check=True, timeout=600)
        subprocess.run(["npx", "stryker", "run"], cwd=self.project_dir, check=True, timeout=3600)

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

    def _parse_results(self):
        report_path = self._find_report()
        if not report_path:
            raise FileNotFoundError("Stryker report not found in " + str(self.project_dir))
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
                op     = MUTATOR_MAP.get(rm.get("mutatorName", ""), MutationOperator.AOR)
                status = STATUS_MAP.get(rm.get("status", "Survived"), ExecutionStatus.SURVIVED)
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
                        total += sum(1 for l in f.read_text(errors="ignore").splitlines() if l.strip())
                    except Exception:
                        pass
        return total

    def count_tests(self):
        count = 0
        for ext in ("*.test.js", "*.spec.js", "*.test.ts", "*.spec.ts"):
            count += sum(1 for _ in self.project_dir.rglob(ext) if "node_modules" not in str(_))
        return count

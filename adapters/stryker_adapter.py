"""adapters/stryker_adapter.py — Stryker mutation testing adapter for JavaScript/TypeScript."""
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

DEFAULT_STRYKER_CONFIG = """\
/** @type {import('@stryker-mutator/api/core').PartialStrykerOptions} */
module.exports = {
  reporters: ['json', 'progress'],
  testRunner: 'command',
  coverageAnalysis: 'off',
  timeoutMS: 60000,
  timeoutFactor: 3,
  commandRunner: {
    command: 'node --experimental-vm-modules node_modules/.bin/jest 2>/dev/null || npm test 2>/dev/null || true'
  },
  mutate: [
    'source/**/*.{js,ts,mjs}',
    'src/**/*.{js,ts,mjs}',
    '*.{js,ts,mjs}',
    '!**/*.test.{js,ts}',
    '!**/*.spec.{js,ts}',
    '!**/*.test-d.{js,ts}',
    '!node_modules/**',
    '!stryker.config.{js,cjs}',
    '!jest.config.{js,cjs}',
  ],
  ignorePatterns: ['node_modules', 'reports', '.stryker-tmp'],
  jsonReporter: {
    fileName: 'reports/mutation/mutation.json'
  }
};
"""


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

    def _ensure_config(self) -> None:
        """Create a Stryker config based on the actual project structure."""
        has_config = any([
            (self.project_dir / "stryker.config.js").exists(),
            (self.project_dir / "stryker.config.cjs").exists(),
            (self.project_dir / ".strykerrc.json").exists(),
        ])
        if not has_config:
            log.info("No Stryker config found, creating config from project structure")
            config = self._generate_config()
            # Use .cjs extension for ES module projects ("type": "module")
            try:
                import json as _j
                pkg = _j.loads((self.project_dir / "package.json").read_text())
                is_esm = pkg.get("type", "") == "module"
            except Exception:
                is_esm = False
            config_name = "stryker.config.cjs" if is_esm else "stryker.config.js"
            (self.project_dir / config_name).write_text(config)
            log.info("Wrote %s", config_name)

    def _generate_config(self) -> str:
        """Generate a Stryker config tailored to the actual project."""
        import json as _json

        # Detect test framework from package.json
        test_runner = "command"
        test_command = "npm test"
        pkg_path = self.project_dir / "package.json"
        if pkg_path.exists():
            try:
                pkg = _json.loads(pkg_path.read_text())
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                scripts = pkg.get("scripts", {})
                test_script = scripts.get("test", "")
                if "jest" in deps or "jest" in test_script:
                    test_runner = "jest"
                    test_command = ""
                elif "mocha" in deps:
                    test_runner = "mocha"
                    test_command = ""
                elif "ava" in deps:
                    # Use ava directly — avoids running linters/type-checkers from npm test
                    test_runner = "command"
                    test_command = "node_modules/.bin/ava"
                elif "vitest" in deps:
                    test_runner = "command"
                    test_command = "node_modules/.bin/vitest run"
                elif "test" in scripts:
                    # Use npm test but strip linting steps if present
                    test_command = "npm test"
            except Exception:
                pass

        # Detect source directories
        src_patterns = []
        for candidate in ["source", "src", "lib", "index.js"]:
            p = self.project_dir / candidate
            if p.exists():
                if p.is_dir():
                    src_patterns.append(f"{candidate}/**/*.{{js,ts,mjs,cjs}}")
                else:
                    src_patterns.append(candidate)
        if not src_patterns:
            src_patterns = ["**/*.{{js,ts,mjs,cjs}}"]

        mutate_str = ",
    ".join([f"'{p}'" for p in src_patterns] + [
            "'!**/*.test.{js,ts}'",
            "'!**/*.spec.{js,ts}'",
            "'!**/*.test-d.{js,ts}'",
            "'!node_modules/**'",
        ])

        if test_runner == "jest":
            runner_cfg = "testRunner: 'jest',
  coverageAnalysis: 'off',"
        elif test_runner == "mocha":
            runner_cfg = "testRunner: 'mocha',
  coverageAnalysis: 'off',"
        else:
            runner_cfg = f"testRunner: 'command',
  coverageAnalysis: 'off',
  commandRunner: {{ command: '{test_command}' }},"

        return f"""/** @type {{import('@stryker-mutator/api/core').PartialStrykerOptions}} */
module.exports = {{
  reporters: ['json', 'progress'],
  {runner_cfg}
  timeoutMS: 60000,
  timeoutFactor: 3,
  mutate: [
    {mutate_str}
  ],
  ignorePatterns: ['node_modules', 'reports', '.stryker-tmp'],
  jsonReporter: {{
    fileName: 'reports/mutation/mutation.json'
  }}
}};
"""

    def _docker_base(self, network: str = "none") -> list:
        """Base docker run command."""
        return [
            "docker", "run", "--rm",
            "--network", network,
            "--memory", "2g",
            "--cpus", "2",
            "--user", "root",
            "-v", f"{self.project_dir}:/project",
            "-w", "/project",
            self.sandbox_image,
        ]

    def _install_deps_docker(self) -> None:
        """
        Phase 1: Install npm dependencies WITH network access.
        Only runs if node_modules doesn't already exist.
        """
        node_modules = self.project_dir / "node_modules"
        if node_modules.exists() and any(node_modules.iterdir()):
            log.info("node_modules already exists, skipping npm install")
            return

        log.info("Phase 1: Installing npm dependencies (network enabled)…")
        cmd = self._docker_base(network="bridge") + [
            "sh", "-c",
            # Install project deps
            "npm install --prefer-offline --no-audit --no-fund --unsafe-perm 2>&1 || "
            "npm install --no-audit --no-fund --unsafe-perm 2>&1; "
            # Ensure Stryker core is available (in case it's not in project deps)
            "[ -d node_modules/@stryker-mutator/core ] || "
            "npm install --unsafe-perm --no-audit --save-dev "
            "@stryker-mutator/core 2>&1 || true"
        ]
        try:
            result = subprocess.run(
                cmd, check=True, timeout=600,
                capture_output=True, text=True
            )
            log.info("npm install completed: %s", result.stdout[-500:] if result.stdout else "")
        except subprocess.CalledProcessError as e:
            log.warning("npm install had errors (may still work): %s",
                        e.stderr[-500:] if e.stderr else "")

    def _install_stryker_docker(self) -> None:
        """Install Stryker packages if not present."""
        pkg_json = self.project_dir / "package.json"
        if not pkg_json.exists():
            return
        pkg = json.loads(pkg_json.read_text())
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        has_stryker = any("stryker" in k for k in deps)
        if not has_stryker:
            log.info("Installing Stryker packages…")
            cmd = self._docker_base(network="bridge") + [
                "sh", "-c",
                "npm install --save-dev @stryker-mutator/core @stryker-mutator/javascript-mutator "
                "@stryker-mutator/jest-runner --no-audit --no-fund 2>&1"
            ]
            subprocess.run(cmd, timeout=300, capture_output=True)

    def _run_stryker_docker(self) -> None:
        """
        Phase 2: Run Stryker WITHOUT network access for security.
        node_modules must already be installed by Phase 1.
        """
        log.info("Phase 2: Running Stryker mutation testing (network disabled)…")
        cmd = self._docker_base(network="none") + [
            "sh", "-c",
            "npx stryker run --fileLogLevel off 2>&1"
        ]
        try:
            result = subprocess.run(
                cmd, check=True, timeout=3600,
                capture_output=True, text=True
            )
            log.info("Stryker completed successfully")
            log.debug("Stryker output: %s", result.stdout[-1000:] if result.stdout else "")
        except subprocess.CalledProcessError as e:
            output = (e.stdout or "") + (e.stderr or "")
            log.error("Stryker failed: %s", output[-1000:])
            # Check if report was still generated despite non-zero exit
            report = self._find_report()
            if report:
                log.warning("Stryker exited with error but report found — proceeding")
            else:
                raise

    def _run_local(self) -> None:
        """Run locally without Docker (development only)."""
        # Install deps first
        if not (self.project_dir / "node_modules").exists():
            subprocess.run(["npm", "install"], cwd=self.project_dir,
                           check=True, timeout=600)
        subprocess.run(["npx", "stryker", "run"],
                       cwd=self.project_dir, check=True, timeout=3600)

    def _find_report(self) -> Optional[Path]:
        candidates = [
            self.project_dir / "reports" / "mutation" / "mutation.json",
            self.project_dir / "reports" / "mutation.json",
            self.project_dir / ".stryker-tmp" / "mutation.json",
        ]
        for p in candidates:
            if p.exists():
                return p
        for p in self.project_dir.rglob("mutation.json"):
            return p
        return None

    def _parse_results(self) -> List[Mutant]:
        report_path = self._find_report()
        if not report_path:
            raise FileNotFoundError(
                f"Stryker report not found in {self.project_dir}. "
                "Stryker may have failed to run."
            )

        data = json.loads(report_path.read_text())

        # Support v5 (flat list) and v6 (files dict) formats
        if "files" in data:
            raw_mutants = [
                {**m, "_file": fname}
                for fname, fdata in data["files"].items()
                for m in fdata.get("mutants", [])
            ]
        else:
            raw_mutants = data.get("mutants", [])

        mutants = []
        for rm in raw_mutants:
            try:
                mutator_name = rm.get("mutatorName", "")
                operator     = MUTATOR_MAP.get(mutator_name, MutationOperator.AOR)
                status       = STATUS_MAP.get(rm.get("status", "Survived"),
                                               ExecutionStatus.SURVIVED)
                location = rm.get("location", {})
                start    = location.get("start", {})

                loc = CodeLocation(
                    file=rm.get("_file", rm.get("fileName", "unknown.js")),
                    line=start.get("line", 1),
                    column=start.get("column", 0),
                )
                m = Mutant(
                    operator=operator, location=loc,
                    original_code=rm.get("replacement", "original"),
                    mutated_code =rm.get("replacement", mutator_name),
                )
                m.status = status
                mutants.append(m)
            except Exception as e:
                log.debug("Skipping malformed mutant: %s", e)

        log.info("Parsed %d mutants from Stryker report", len(mutants))
        return mutants

    def detect_framework(self) -> bool:
        return (self.project_dir / "package.json").exists()

    def count_loc(self) -> int:
        total = 0
        for ext in ("*.js", "*.ts", "*.jsx", "*.tsx"):
            for f in self.project_dir.rglob(ext):
                if "node_modules" not in str(f) and "test" not in f.name.lower():
                    try:
                        total += sum(1 for l in f.read_text(errors="ignore").splitlines()
                                     if l.strip())
                    except Exception:
                        pass
        return total

    def count_tests(self) -> int:
        count = 0
        for ext in ("*.test.js", "*.spec.js", "*.test.ts", "*.spec.ts",
                    "*.test.jsx", "*.spec.jsx"):
            count += sum(1 for _ in self.project_dir.rglob(ext)
                         if "node_modules" not in str(_))
        return count

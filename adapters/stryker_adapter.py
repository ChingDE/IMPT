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
    "ArithmeticOperator":  MutationOperator.AOR,
    "EqualityOperator":    MutationOperator.ROR,
    "LogicalOperator":     MutationOperator.LCR,
    "ConditionalExpression": MutationOperator.COR,
    "BooleanLiteral":      MutationOperator.NEGATE_RETURN,
    "StringLiteral":       MutationOperator.NULL_RETURN,
    "BlockStatement":      MutationOperator.SDL,
    "ArrayDeclaration":    MutationOperator.NULL_RETURN,
    "UnaryOperator":       MutationOperator.UOI,
    "UpdateOperator":      MutationOperator.AOR,
    "OptionalChaining":    MutationOperator.NULL_RETURN,
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
module.exports = {
  reporters: ['json'],
  testRunner: 'jest',
  coverageAnalysis: 'off',
  jsonReporter: { fileName: 'reports/mutation/mutation.json' }
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
            self._run_docker()
        else:
            self._run_local()
        return self._parse_results()

    def _ensure_config(self) -> None:
        has_config = any([
            (self.project_dir / "stryker.config.js").exists(),
            (self.project_dir / "stryker.config.cjs").exists(),
            (self.project_dir / ".strykerrc.json").exists(),
        ])
        if not has_config:
            (self.project_dir / "stryker.config.js").write_text(DEFAULT_STRYKER_CONFIG)

    def _run_docker(self) -> None:
        cmd = [
            "docker", "run", "--rm",
            "--network", "none",
            "--memory", "2g",
            "--cpus", "2",
            "-v", f"{self.project_dir}:/project",
            "-w", "/project",
            self.sandbox_image,
            "npx", "stryker", "run",
        ]
        subprocess.run(cmd, check=True, timeout=3600)

    def _run_local(self) -> None:
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
            raise FileNotFoundError(f"Stryker report not found in {self.project_dir}")

        data = json.loads(report_path.read_text())

        # Support v5 (flat) and v6 (files dict) formats
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
                operator = MUTATOR_MAP.get(mutatorName, MutationOperator.AOR) if (mutatorName := mutator_name) else MutationOperator.AOR
                status   = STATUS_MAP.get(rm.get("status", "Survived"), ExecutionStatus.SURVIVED)
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
                    mutated_code=rm.get("replacement", mutator_name),
                )
                m.status = status
                mutants.append(m)
            except Exception as e:
                log.debug("Skipping malformed mutant: %s", e)

        return mutants

    def detect_framework(self) -> bool:
        return (self.project_dir / "package.json").exists()

    def count_loc(self) -> int:
        total = 0
        for ext in ("*.js", "*.ts", "*.jsx", "*.tsx"):
            for f in self.project_dir.rglob(ext):
                if "node_modules" not in str(f) and "test" not in f.name.lower():
                    try:
                        total += sum(1 for l in f.read_text(errors="ignore").splitlines() if l.strip())
                    except Exception:
                        pass
        return total

    def count_tests(self) -> int:
        count = 0
        for ext in ("*.test.js", "*.spec.js", "*.test.ts", "*.spec.ts"):
            count += sum(1 for _ in self.project_dir.rglob(ext)
                         if "node_modules" not in str(_))
        return count

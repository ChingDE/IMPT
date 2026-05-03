"""
adapters/stryker_adapter.py
Stryker Adapter for JavaScript / TypeScript projects
=====================================================
Runs Stryker mutation testing, parses the JSON report, and converts
every mutant into an IMPT Mutant object.

Stryker invocation:
  npx stryker run --reporters json --coverageAnalysis off

JSON report location:
  reports/mutation/mutation.json   (Stryker v6+)
  reports/mutation.json            (Stryker v5)

Stryker JSON schema (per mutant):
{
  "id": "abc123",
  "mutatorName": "ConditionalExpression",
  "replacement": "true",
  "fileName": "src/foo.js",
  "location": {
    "start": { "line": 10, "column": 5 },
    "end":   { "line": 10, "column": 20 }
  },
  "status": "Killed",           // Killed | Survived | NoCoverage | Timeout | RuntimeError | CompileError
  "coveredBy": ["test1", "test2"],
  "killedBy": ["test1"],
  "statusReason": "..."
}
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any, List, Optional

from impt.models.mutant import (
    CodeLocation,
    ExecutionStatus,
    Mutant,
    MutationOperator,
    PriorityFactors,
)

log = logging.getLogger(__name__)

# ── Stryker mutator → IMPT operator mapping ──────────────────────────────────
_MUTATOR_MAP: dict[str, MutationOperator] = {
    "conditionalexpression":   MutationOperator.COR,
    "equalityoperator":        MutationOperator.ROR,
    "logicaloperator":         MutationOperator.LCR,
    "arithmeticoperator":      MutationOperator.AOR,
    "unaryoperator":           MutationOperator.UOI,
    "updateoperator":          MutationOperator.UOI,
    "stringliteral":           MutationOperator.SDL,
    "blockstatement":          MutationOperator.SDL,
    "booleansubstitution":     MutationOperator.NEGATE_RETURN,
    "optionalchaining":        MutationOperator.NULL_RETURN,
    "nullcoalescing":          MutationOperator.NULL_RETURN,
    "arrayobjectremoval":      MutationOperator.VDL,
    "methodexpression":        MutationOperator.ODL,
    "objectliteral":           MutationOperator.VDL,
    "regexmutator":            MutationOperator.AOR,
    "assignment":              MutationOperator.AOR,
}

_STATUS_MAP: dict[str, ExecutionStatus] = {
    "killed":       ExecutionStatus.KILLED,
    "survived":     ExecutionStatus.SURVIVED,
    "nocoverage":   ExecutionStatus.SURVIVED,
    "timeout":      ExecutionStatus.TIMEOUT,
    "runtimeerror": ExecutionStatus.ERROR,
    "compileerror": ExecutionStatus.ERROR,
    "ignored":      ExecutionStatus.EQUIVALENT,
}


class StrykerAdapter:
    """
    Runs Stryker on a Node.js / npm project and returns parsed mutants.

    Parameters
    ----------
    project_dir : Path
        Root directory of the JS/TS project (must contain package.json).
    node_path : str, optional
        Path to the node binary. Defaults to system node.
    timeout_seconds : int
        Hard kill timeout for the Stryker subprocess.
    use_docker : bool
        If True, run Stryker inside the sandbox Docker container.
    """

    REPORT_PATHS = [
        "reports/mutation/mutation.json",   # Stryker v6+
        "reports/mutation.json",            # Stryker v5
        ".stryker-tmp/reports/mutation.json",
    ]

    def __init__(
        self,
        project_dir: Path,
        node_path: str = "node",
        timeout_seconds: int = 3600,
        use_docker: bool = True,
    ) -> None:
        self.project_dir    = Path(project_dir)
        self.node_path      = node_path
        self.timeout        = timeout_seconds
        self.use_docker     = use_docker

    # ── Public API ───────────────────────────────────────────────────────────

    def run(self) -> List[Mutant]:
        """Execute Stryker and return the full list of mutants."""
        log.info("StrykerAdapter: starting on %s", self.project_dir)
        self._ensure_stryker_config()
        report_path = self._execute_stryker()
        mutants = self._parse_report(report_path)
        log.info("StrykerAdapter: parsed %d mutants", len(mutants))
        return mutants

    def detect_framework(self) -> bool:
        """Returns True if this looks like a Node.js project."""
        return (self.project_dir / "package.json").exists()

    def count_loc(self) -> int:
        """Count JS/TS source lines (non-blank, non-comment)."""
        total = 0
        exts  = {".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"}
        skip  = {"node_modules", ".stryker-tmp", "dist", "build", "coverage"}
        for f in self.project_dir.rglob("*"):
            if any(p in f.parts for p in skip):
                continue
            if f.suffix in exts and f.is_file():
                try:
                    lines = f.read_text(errors="ignore").splitlines()
                    total += sum(
                        1 for l in lines
                        if l.strip() and not l.strip().startswith("//")
                    )
                except OSError:
                    pass
        return total

    def count_tests(self) -> int:
        """Count test functions in Jest/Mocha/Jasmine style."""
        total = 0
        keywords = ["it(", "test(", "it.each(", "test.each("]
        test_exts = {".spec.js", ".test.js", ".spec.ts", ".test.ts",
                     ".spec.jsx", ".test.jsx", ".spec.tsx", ".test.tsx"}
        for f in self.project_dir.rglob("*"):
            if "node_modules" in f.parts:
                continue
            if any(f.name.endswith(e) for e in test_exts):
                try:
                    content = f.read_text(errors="ignore")
                    total += sum(content.count(k) for k in keywords)
                except OSError:
                    pass
        return total

    # ── Stryker execution ────────────────────────────────────────────────────

    def _ensure_stryker_config(self) -> None:
        """Write a minimal stryker.config.js if one doesn't exist."""
        config_files = ["stryker.config.js", "stryker.config.mjs", ".strykerrc.json"]
        if any((self.project_dir / c).exists() for c in config_files):
            return   # project already has config

        config = {
            "reporters": ["json"],
            "coverageAnalysis": "off",
            "timeoutMS": min(self.timeout * 1000, 60000),
            "concurrency": 2,
            "ignorePatterns": ["node_modules", "dist", "build", "coverage"],
        }
        config_path = self.project_dir / ".strykerrc.json"
        config_path.write_text(json.dumps(config, indent=2))
        log.info("StrykerAdapter: wrote default .strykerrc.json")

    def _build_stryker_command(self) -> list[str]:
        return [
            "npx", "--yes", "stryker",
            "run",
            "--reporters", "json",
            "--coverageAnalysis", "off",
        ]

    def _execute_stryker(self) -> Path:
        if self.use_docker:
            return self._run_in_docker()
        return self._run_directly()

    def _run_directly(self) -> Path:
        cmd = self._build_stryker_command()
        env = dict(os.environ)
        env["CI"] = "true"

        result = subprocess.run(
            cmd,
            cwd=self.project_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=self.timeout,
        )

        if result.returncode not in (0, 1):
            # Stryker exits 1 when mutation score < threshold — still produces report
            log.error("Stryker stderr:\n%s", result.stderr[-3000:])
            raise RuntimeError(f"Stryker exited with code {result.returncode}")

        return self._find_report()

    def _run_in_docker(self) -> Path:
        inner_cmd = " ".join(self._build_stryker_command())
        docker_cmd = [
            "docker", "run", "--rm",
            "--name", f"impt-stryker-{os.getpid()}",
            "--memory", "2g",
            "--cpus", "2",
            "--network", "none",
            "--read-only",
            "--tmpfs", "/tmp:size=512m",
            "--tmpfs", "/root/.npm:size=256m",
            "-v", f"{self.project_dir}:/project:rw",
            "-w", "/project",
            "-e", "CI=true",
            "impt-sandbox:latest",
            "/bin/sh", "-c",
            f"npm install --prefer-offline --silent 2>/dev/null; {inner_cmd}",
        ]

        result = subprocess.run(
            docker_cmd,
            capture_output=True,
            text=True,
            timeout=self.timeout + 60,
        )

        if result.returncode not in (0, 1):
            log.error("Docker Stryker stderr:\n%s", result.stderr[-3000:])
            raise RuntimeError(f"Stryker container exited {result.returncode}")

        return self._find_report()

    def _find_report(self) -> Path:
        for rel in self.REPORT_PATHS:
            p = self.project_dir / rel
            if p.exists():
                return p
        raise RuntimeError(
            f"Stryker report not found. Checked: "
            + ", ".join(str(self.project_dir / r) for r in self.REPORT_PATHS)
        )

    # ── JSON parsing ─────────────────────────────────────────────────────────

    def _parse_report(self, report_path: Path) -> List[Mutant]:
        data = json.loads(report_path.read_text())
        mutants: List[Mutant] = []

        # Stryker v6: { files: { "src/foo.js": { mutants: [...] } } }
        # Stryker v5: { mutants: [...] }
        if "files" in data:
            for file_entry in data["files"].values():
                for raw in file_entry.get("mutants", []):
                    m = self._parse_mutant(raw)
                    if m:
                        mutants.append(m)
        else:
            for raw in data.get("mutants", []):
                m = self._parse_mutant(raw)
                if m:
                    mutants.append(m)

        return mutants

    def _parse_mutant(self, raw: dict[str, Any]) -> Optional[Mutant]:
        try:
            status_str = raw.get("status", "Survived").lower().replace(" ", "")
            status = _STATUS_MAP.get(status_str, ExecutionStatus.SURVIVED)

            file_name = raw.get("fileName", raw.get("sourceFilePath", "unknown.js"))
            location  = raw.get("location", {})
            start     = location.get("start", {})
            line      = start.get("line", 0)
            col       = start.get("column", 0)

            mutator_name = raw.get("mutatorName", "").lower()
            operator = self._map_operator(mutator_name)

            original  = raw.get("original", "[original]")
            replacement = raw.get("replacement", raw.get("mutatedCode", "[mutated]"))

            covered_by = set(raw.get("coveredBy", []))
            killed_by  = set(raw.get("killedBy", []))
            coverage   = covered_by | killed_by

            loc = CodeLocation(
                file=file_name,
                line=line,
                column=col,
                method=None,
            )

            m = Mutant(
                operator=operator,
                location=loc,
                original_code=str(original)[:200],
                mutated_code=str(replacement)[:200],
                status=status,
                factors=PriorityFactors(),
            )
            m.test_coverage = coverage
            return m

        except Exception as exc:
            log.debug("Skipping malformed Stryker mutant: %s", exc)
            return None

    @staticmethod
    def _map_operator(mutator_name: str) -> MutationOperator:
        lower = mutator_name.lower()
        for key, op in _MUTATOR_MAP.items():
            if key in lower:
                return op
        return MutationOperator.AOR

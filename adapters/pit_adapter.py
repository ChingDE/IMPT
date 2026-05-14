"""adapters/pit_adapter.py — PIT mutation testing adapter for Java projects."""
from __future__ import annotations
import logging
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Optional

from impt.models.mutant import (
    CodeLocation, Mutant, MutationOperator, PriorityFactors, ExecutionStatus
)

log = logging.getLogger(__name__)

MUTATOR_MAP = {
    "ArithmeticOperatorReplacementMutator":   MutationOperator.AOR,
    "ConditionalsBoundaryMutator":            MutationOperator.ABS,
    "NegateConditionalsMutator":              MutationOperator.ROR,
    "MathMutator":                            MutationOperator.AOR,
    "IncrementsMutator":                      MutationOperator.AOR,
    "InvertNegsMutator":                      MutationOperator.UOI,
    "ReturnValsMutator":                      MutationOperator.NEGATE_RETURN,
    "VoidMethodCallMutator":                  MutationOperator.SDL,
    "EmptyObjectReturnValsMutator":           MutationOperator.NULL_RETURN,
    "NullReturnValsMutator":                  MutationOperator.NULL_RETURN,
    "PrimitiveReturnsMutator":                MutationOperator.NEGATE_RETURN,
    "BooleanTrueReturnValsMutator":           MutationOperator.NEGATE_RETURN,
    "BooleanFalseReturnValsMutator":          MutationOperator.NEGATE_RETURN,
    "RemoveConditionalMutator_EQUAL_ELSE":    MutationOperator.COR,
    "RemoveConditionalMutator_EQUAL_IF":      MutationOperator.COR,
    "RemoveConditionalMutator_ORDER_ELSE":    MutationOperator.ROR,
    "RemoveConditionalMutator_ORDER_IF":      MutationOperator.ROR,
}

STATUS_MAP = {
    "KILLED":     ExecutionStatus.KILLED,
    "SURVIVED":   ExecutionStatus.SURVIVED,
    "NO_COVERAGE": ExecutionStatus.SURVIVED,
    "TIMED_OUT":  ExecutionStatus.TIMEOUT,
    "MEMORY_ERROR": ExecutionStatus.ERROR,
    "RUN_ERROR":  ExecutionStatus.ERROR,
}


class PITAdapter:
    def __init__(self, project_dir: Path, use_docker: bool = True,
                 sandbox_image: str = "impt-sandbox:latest"):
        self.project_dir   = project_dir
        self.use_docker    = use_docker
        self.sandbox_image = sandbox_image

    def run(self) -> List[Mutant]:
        if self.use_docker:
            self._run_docker()
        else:
            self._run_local()
        return self._parse_results()

    def _run_docker(self) -> None:
        cmd = [
            "docker", "run", "--rm",
            "--network", "none",
            "--memory", "2g",
            "--cpus", "2",
            "-v", f"{self.project_dir}:/project",
            "-w", "/project",
            self.sandbox_image,
            "mvn", "org.pitest:pitest-maven:mutationCoverage",
            "-DtimestampedReports=false",
            "-DoutputFormats=XML",
            "-DmutationThreshold=0",
            "-DfailWhenNoMutations=false",
            "--batch-mode",
        ]
        subprocess.run(cmd, check=True, timeout=3600)

    def _run_local(self) -> None:
        if (self.project_dir / "pom.xml").exists():
            cmd = ["mvn", "org.pitest:pitest-maven:mutationCoverage",
                   "-DtimestampedReports=false", "-DoutputFormats=XML",
                   "-DmutationThreshold=0", "-DfailWhenNoMutations=false", "--batch-mode"]
        else:
            cmd = ["./gradlew", "pitest"]
        subprocess.run(cmd, cwd=self.project_dir, check=True, timeout=3600)

    def _find_report(self) -> Optional[Path]:
        candidates = [
            self.project_dir / "target" / "pit-reports" / "mutations.xml",
            self.project_dir / "build" / "reports" / "pitest" / "mutations.xml",
        ]
        for p in candidates:
            if p.exists():
                return p
        for p in self.project_dir.rglob("mutations.xml"):
            return p
        return None

    def _parse_results(self) -> List[Mutant]:
        report = self._find_report()
        if not report:
            raise FileNotFoundError(f"PIT report not found in {self.project_dir}")

        mutants = []
        root    = ET.parse(report).getroot()

        for m_elem in root.findall(".//mutation"):
            try:
                mutator_class = m_elem.findtext("mutator", "").split(".")[-1]
                operator      = MUTATOR_MAP.get(mutator_class, MutationOperator.AOR)
                status_str    = m_elem.get("status", "SURVIVED")
                detected      = m_elem.get("detected", "false").lower() == "true"
                status        = STATUS_MAP.get(status_str, ExecutionStatus.SURVIVED)
                if detected and status == ExecutionStatus.SURVIVED:
                    status = ExecutionStatus.KILLED

                loc = CodeLocation(
                    file=m_elem.findtext("sourceFile", "Unknown.java"),
                    line=int(m_elem.findtext("lineNumber", "1")),
                    method_name=m_elem.findtext("mutatedMethod"),
                    class_name=m_elem.findtext("mutatedClass"),
                )
                original = m_elem.findtext("description", "original")
                mutated  = f"[{mutator_class}] {original}"

                mutant = Mutant(
                    operator=operator, location=loc,
                    original_code=original, mutated_code=mutated,
                )
                mutant.status = status
                mutants.append(mutant)
            except Exception as e:
                log.debug("Skipping malformed mutation element: %s", e)

        return mutants

    def detect_framework(self) -> bool:
        return ((self.project_dir / "pom.xml").exists() or
                (self.project_dir / "build.gradle").exists())

    def count_loc(self) -> int:
        total = 0
        for f in self.project_dir.rglob("*.java"):
            if "test" not in str(f).lower():
                try:
                    lines = f.read_text(errors="ignore").splitlines()
                    total += sum(1 for l in lines if l.strip() and not l.strip().startswith("//"))
                except Exception:
                    pass
        return total

    def count_tests(self) -> int:
        count = 0
        for f in self.project_dir.rglob("*.java"):
            if "test" in str(f).lower():
                try:
                    count += f.read_text(errors="ignore").count("@Test")
                except Exception:
                    pass
        return count

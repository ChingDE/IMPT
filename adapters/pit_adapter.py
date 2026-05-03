"""
adapters/pit_adapter.py
PIT (PITest) Adapter for Java projects
=======================================
Runs PIT mutation testing inside a Docker container, parses the XML
report, and converts every mutant into an IMPT Mutant object.

PIT invocation:
  mvn org.pitest:pitest-maven:mutationCoverage
    -DtimestampedReports=false
    -DoutputFormats=XML
    -DmutationThreshold=0

XML report location:
  target/pit-reports/mutations.xml

PIT XML schema (per mutant):
  <mutation detected="true|false" status="KILLED|SURVIVED|NO_COVERAGE|...">
    <sourceFile>Foo.java</sourceFile>
    <mutatedClass>com.example.Foo</mutatedClass>
    <mutatedMethod>doSomething</mutatedMethod>
    <lineNumber>42</lineNumber>
    <mutator>org.pitest.mutationtest.engine.gregor.mutators.ConditionalsBoundaryMutator</mutator>
    <description>changed conditional boundary</description>
    <killingTest>com.example.FooTest.testDoSomething(com.example.FooTest)</killingTest>
  </mutation>
"""

from __future__ import annotations

import logging
import os
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Optional, Tuple

from impt.models.mutant import (
    CodeLocation,
    ExecutionStatus,
    Mutant,
    MutationOperator,
    PriorityFactors,
)

log = logging.getLogger(__name__)

# ── PIT mutator → IMPT operator mapping ─────────────────────────────────────
_MUTATOR_MAP: dict[str, MutationOperator] = {
    "ConditionalsBoundaryMutator":      MutationOperator.ABS,
    "CONDITIONALS_BOUNDARY":            MutationOperator.ABS,
    "NegateConditionalsMutator":        MutationOperator.ROR,
    "NEGATE_CONDITIONALS":              MutationOperator.ROR,
    "MathMutator":                      MutationOperator.AOR,
    "MATH":                             MutationOperator.AOR,
    "VoidMethodCallMutator":            MutationOperator.SDL,
    "VOID_METHOD_CALLS":                MutationOperator.SDL,
    "ReturnValsMutator":                MutationOperator.NEGATE_RETURN,
    "RETURN_VALS":                      MutationOperator.NEGATE_RETURN,
    "NullReturnValsMutator":            MutationOperator.NULL_RETURN,
    "NULL_RETURNS":                     MutationOperator.NULL_RETURN,
    "EmptyObjectReturnValsMutator":     MutationOperator.NULL_RETURN,
    "EMPTY_RETURNS":                    MutationOperator.NULL_RETURN,
    "IncrementsMutator":                MutationOperator.UOI,
    "INCREMENTS":                       MutationOperator.UOI,
    "InvertNegsMutator":                MutationOperator.UOI,
    "INVERT_NEGS":                      MutationOperator.UOI,
    "RemoveConditionalMutator":         MutationOperator.COR,
    "REMOVE_CONDITIONALS":              MutationOperator.COR,
}

# PIT status → IMPT ExecutionStatus
_STATUS_MAP: dict[str, ExecutionStatus] = {
    "KILLED":          ExecutionStatus.KILLED,
    "SURVIVED":        ExecutionStatus.SURVIVED,
    "NO_COVERAGE":     ExecutionStatus.SURVIVED,   # no tests cover it → treat as survived
    "TIMED_OUT":       ExecutionStatus.TIMEOUT,
    "RUN_ERROR":       ExecutionStatus.ERROR,
    "NON_VIABLE":      ExecutionStatus.EQUIVALENT,
    "MEMORY_ERROR":    ExecutionStatus.ERROR,
}


class PITAdapter:
    """
    Runs PIT on a Maven/Gradle Java project and returns parsed mutants.

    Parameters
    ----------
    project_dir : Path
        Root of the uploaded Java project (must contain pom.xml or build.gradle).
    java_home : str, optional
        Path to JDK. Defaults to JAVA_HOME env var or system default.
    maven_opts : str
        Extra Maven options (e.g. memory settings).
    timeout_seconds : int
        Hard kill timeout for the PIT subprocess.
    use_docker : bool
        If True, run PIT inside the sandbox Docker container.
        If False, run directly (dev mode only — never in production).
    """

    REPORT_SUBPATH = "target/pit-reports/mutations.xml"
    GRADLE_REPORT_SUBPATH = "build/reports/pitest/mutations.xml"

    def __init__(
        self,
        project_dir: Path,
        java_home: Optional[str] = None,
        maven_opts: str = "-Xmx1g",
        timeout_seconds: int = 3600,
        use_docker: bool = True,
    ) -> None:
        self.project_dir  = Path(project_dir)
        self.java_home    = java_home or os.environ.get("JAVA_HOME", "")
        self.maven_opts   = maven_opts
        self.timeout      = timeout_seconds
        self.use_docker   = use_docker
        self._is_gradle   = (self.project_dir / "build.gradle").exists() or \
                            (self.project_dir / "build.gradle.kts").exists()

    # ── Public API ───────────────────────────────────────────────────────────

    def run(self) -> List[Mutant]:
        """
        Execute PIT and return the full list of mutants.
        Raises RuntimeError if PIT fails or produces no report.
        """
        log.info("PITAdapter: starting on %s (gradle=%s)", self.project_dir, self._is_gradle)
        report_path = self._execute_pit()
        mutants = self._parse_report(report_path)
        log.info("PITAdapter: parsed %d mutants from %s", len(mutants), report_path)
        return mutants

    def detect_framework(self) -> bool:
        """Returns True if this looks like a Maven/Gradle Java project."""
        return (
            (self.project_dir / "pom.xml").exists()
            or (self.project_dir / "build.gradle").exists()
            or (self.project_dir / "build.gradle.kts").exists()
        )

    def count_loc(self) -> int:
        """Count Java source lines (non-blank, non-comment)."""
        total = 0
        for f in self.project_dir.rglob("*.java"):
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
        """Count Java test methods (methods annotated with @Test)."""
        total = 0
        test_dirs = ["src/test", "src/androidTest"]
        for d in test_dirs:
            test_root = self.project_dir / d
            if test_root.exists():
                for f in test_root.rglob("*.java"):
                    try:
                        total += f.read_text(errors="ignore").count("@Test")
                    except OSError:
                        pass
        return total

    # ── PIT execution ────────────────────────────────────────────────────────

    def _execute_pit(self) -> Path:
        """Run PIT, return path to the XML report."""
        if self.use_docker:
            return self._run_in_docker()
        return self._run_directly()

    def _build_maven_command(self) -> list[str]:
        return [
            "mvn",
            "org.pitest:pitest-maven:mutationCoverage",
            "-DtimestampedReports=false",
            "-DoutputFormats=XML",
            "-DmutationThreshold=0",
            "-DfailWhenNoMutations=false",
            f"-DMAVEN_OPTS={self.maven_opts}",
            "--batch-mode",
            "--no-transfer-progress",
        ]

    def _build_gradle_command(self) -> list[str]:
        return ["./gradlew", "pitest", "--no-daemon", "--console=plain"]

    def _run_directly(self) -> Path:
        """Run PIT in the current process (dev only)."""
        cmd = self._build_gradle_command() if self._is_gradle else self._build_maven_command()
        env = dict(os.environ)
        if self.java_home:
            env["JAVA_HOME"] = self.java_home

        log.info("PITAdapter: running %s", " ".join(cmd))
        result = subprocess.run(
            cmd,
            cwd=self.project_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=self.timeout,
        )

        if result.returncode != 0:
            log.error("PIT stderr:\n%s", result.stderr[-3000:])
            raise RuntimeError(
                f"PIT exited with code {result.returncode}.\n"
                f"STDOUT tail: {result.stdout[-1000:]}"
            )

        report = self.project_dir / (
            self.GRADLE_REPORT_SUBPATH if self._is_gradle else self.REPORT_SUBPATH
        )
        if not report.exists():
            raise RuntimeError(f"PIT report not found at {report}")
        return report

    def _run_in_docker(self) -> Path:
        """
        Run PIT inside the impt-sandbox Docker container.
        The project directory is mounted at /project inside the container.
        The report is written to /project/target/pit-reports/mutations.xml
        and is accessible on the host because of the volume mount.
        """
        report_subpath = self.GRADLE_REPORT_SUBPATH if self._is_gradle else self.REPORT_SUBPATH
        inner_cmd = " ".join(
            self._build_gradle_command() if self._is_gradle else self._build_maven_command()
        )

        docker_cmd = [
            "docker", "run", "--rm",
            "--name", f"impt-pit-{os.getpid()}",
            "--memory", "2g",
            "--cpus", "2",
            "--network", "none",           # no internet access during execution
            "--read-only",
            "--tmpfs", "/tmp:size=512m",
            "--tmpfs", "/root/.m2/repository:size=512m",
            "-v", f"{self.project_dir}:/project:rw",
            "-w", "/project",
            "impt-sandbox:latest",
            "/bin/sh", "-c", inner_cmd,
        ]

        log.info("PITAdapter: docker run for project %s", self.project_dir.name)
        result = subprocess.run(
            docker_cmd,
            capture_output=True,
            text=True,
            timeout=self.timeout + 60,    # extra 60s for container startup
        )

        if result.returncode != 0:
            log.error("Docker PIT stderr:\n%s", result.stderr[-3000:])
            raise RuntimeError(
                f"PIT container exited {result.returncode}.\n"
                f"Tail: {result.stderr[-500:]}"
            )

        report = self.project_dir / report_subpath
        if not report.exists():
            raise RuntimeError(f"PIT report not found at {report}")
        return report

    # ── XML parsing ──────────────────────────────────────────────────────────

    def _parse_report(self, report_path: Path) -> List[Mutant]:
        tree = ET.parse(report_path)
        root = tree.getroot()
        mutants: List[Mutant] = []

        for elem in root.iter("mutation"):
            try:
                mutant = self._parse_mutation(elem)
                if mutant:
                    mutants.append(mutant)
            except Exception as exc:
                log.debug("Skipping malformed mutation element: %s", exc)

        return mutants

    def _parse_mutation(self, elem: ET.Element) -> Optional[Mutant]:
        status_str = elem.get("status", "SURVIVED").upper()
        detected   = elem.get("detected", "false").lower() == "true"

        source_file    = self._text(elem, "sourceFile", "Unknown.java")
        mutated_class  = self._text(elem, "mutatedClass", "")
        mutated_method = self._text(elem, "mutatedMethod", "")
        line_number    = int(self._text(elem, "lineNumber", "0"))
        mutator_full   = self._text(elem, "mutator", "")
        description    = self._text(elem, "description", "")

        operator = self._map_operator(mutator_full)
        status   = _STATUS_MAP.get(status_str, ExecutionStatus.SURVIVED)

        # Override detected flag if status explicitly says killed
        if detected and status == ExecutionStatus.SURVIVED:
            status = ExecutionStatus.KILLED

        loc = CodeLocation(
            file=source_file,
            line=line_number,
            column=0,
            method=mutated_method,
            class_name=mutated_class,
        )

        # Build a synthetic original/mutated code snippet from description
        original_code = f"[{mutated_method}:{line_number}] original"
        mutated_code  = description or f"[{operator.value}] mutated"

        # Derive test coverage from killing test (if any)
        killing_test = self._text(elem, "killingTest", "")
        coverage = {killing_test} if killing_test else set()

        m = Mutant(
            operator=operator,
            location=loc,
            original_code=original_code,
            mutated_code=mutated_code,
            status=status,
            factors=PriorityFactors(),  # will be enriched by FactorEnricher
        )
        m.test_coverage = coverage
        return m

    @staticmethod
    def _text(elem: ET.Element, tag: str, default: str = "") -> str:
        child = elem.find(tag)
        return (child.text or default).strip() if child is not None else default

    @staticmethod
    def _map_operator(mutator_full: str) -> MutationOperator:
        """Map a fully-qualified PIT mutator class name to an IMPT operator."""
        short = mutator_full.split(".")[-1].replace("Mutator", "")
        for key, op in _MUTATOR_MAP.items():
            if key.lower() in mutator_full.lower():
                return op
        # Fallback by keyword
        upper = short.upper()
        for op in MutationOperator:
            if op.value in upper:
                return op
        return MutationOperator.AOR   # safe default

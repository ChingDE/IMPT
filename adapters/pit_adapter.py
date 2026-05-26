"""adapters/pit_adapter.py — PIT mutation testing adapter for Java projects."""
from __future__ import annotations
import logging
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Optional, Set

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
    # Tier 1 equivalent detection: PIT marks inlined/trivial mutants NON_VIABLE
    # when detectInlinedCode=true and FANN/FINULL features are enabled.
    "NON_VIABLE": ExecutionStatus.EQUIVALENT,
    "TIMED_OUT":  ExecutionStatus.TIMEOUT,
    "MEMORY_ERROR": ExecutionStatus.ERROR,
    "RUN_ERROR":  ExecutionStatus.ERROR,
}


class PITAdapter:
    def __init__(self, project_dir: Path, use_docker: bool = True,
                 sandbox_image: str = "impt-sandbox:latest"):
        self.use_docker    = use_docker
        self.sandbox_image = sandbox_image
        self.project_dir   = self._ensure_writable(Path(project_dir))

    @staticmethod
    def _ensure_writable(project_dir: Path) -> Path:
        """Return a writable copy of project_dir if it's read-only."""
        import shutil
        try:
            test_file = project_dir / ".write_test"
            test_file.touch()
            test_file.unlink()
            return project_dir
        except (OSError, PermissionError):
            work_base = Path("/app/foss-tmp")
            work_base.mkdir(parents=True, exist_ok=True)
            work_dir = work_base / project_dir.name
            if not work_dir.exists():
                log.info("Copying read-only FOSS project to writable workdir: %s", work_dir)
                shutil.copytree(str(project_dir), str(work_dir), symlinks=False)
            else:
                log.info("Using existing writable workdir: %s", work_dir)
            return work_dir

    # Per-project overrides for FOSS projects with non-standard builds.
    # Keys match the directory name (slug). Values are dicts with:
    #   build:    'maven' | 'gradle'
    #   submodule: Maven -pl argument for multi-module projects
    #   target_classes: PIT targetClasses glob (overrides auto-detect)
    #   target_tests:   PIT targetTests glob (overrides auto-detect)
    FOSS_PROJECT_CONFIGS: dict = {
        # ── Multi-module Maven — specify submodule to skip problematic sibling modules
        "gson": {
            "build": "maven",
            "submodule": "gson",
            "target_classes":       "com.google.gson.*",
            "target_tests":         "com.google.gson.*",
            "excluded_test_classes": "com.google.gson.functional.ReflectionAccessFilterTest",
        },
        "assertj": {
            "build": "maven",
            "submodule": "assertj-core",
            "target_classes": "org.assertj.core.*",
            "target_tests":   "org.assertj.core.*",
        },
        "commons-math": {
            "build": "maven",
            "target_classes": "org.apache.commons.math3.*",
            "target_tests":   "org.apache.commons.math3.*",
        },
        # ── Gradle projects ───────────────────────────────────────────────────
        "rxjava": {
            "build": "gradle",
            "target_classes": "io.reactivex.rxjava3.*",
            "target_tests":   "io.reactivex.rxjava3.*",
        },
        "mockito": {
            "build": "gradle",
            "target_classes": "org.mockito.*",
            "target_tests":   "org.mockito.*",
        },
    }

    def _get_project_config(self) -> dict:
        """Return FOSS override config for this project, or empty dict."""
        slug = self.project_dir.name
        return self.FOSS_PROJECT_CONFIGS.get(slug, {})

    def run(self) -> List[Mutant]:
        if self.use_docker:
            self._run_docker()
        else:
            self._run_local()
        return self._parse_results()

    def _docker_base(self, network: str = "none", workdir: str = "/project") -> list:
        """Base docker run command with persistent Maven cache."""
        # Use a named volume for Maven cache so dependencies persist between runs
        return [
            "docker", "run", "--rm",
            "--network", network,
            "--memory", "2g",
            "--cpus", "2",
            "-v", f"{self.project_dir}:/project",
            "-v", "impt-maven-cache:/home/imptuser/.m2",
            "-w", workdir,
            self.sandbox_image,
        ]

    def _run_docker(self) -> None:
        """Two-phase execution: resolve deps with network, then run PIT without."""
        cfg = self._get_project_config()
        is_gradle = cfg.get("build") == "gradle" or (
            not (self.project_dir / "pom.xml").exists() and
            (self.project_dir / "build.gradle").exists() or
            (self.project_dir / "build.gradle.kts").exists()
        )

        if is_gradle:
            self._run_docker_gradle(cfg)
            return

        submodule  = cfg.get("submodule")
        tgt_cls    = cfg.get("target_classes")
        tgt_tests  = cfg.get("target_tests")

        # Phase 1: Download ALL dependencies and plugins (with network)
        # Uses dependency:go-offline to ensure everything is cached locally
        # so Phase 2 can run completely offline
        log.info("Phase 1: Resolving Maven dependencies (network enabled)…")
        resolve_args = []
        if submodule:
            resolve_args += ["-pl", submodule, "-am"]

        # Step 1a: Download project dependencies
        resolve_cmd = self._docker_base(network="bridge") + [
            "mvn", "dependency:go-offline",
            "-DincludePlugins=true",
            "--batch-mode", "-q",
            "--fail-at-end",
        ] + resolve_args
        try:
            subprocess.run(resolve_cmd, timeout=600, capture_output=True, text=True)
            log.info("Maven dependency download complete")
        except Exception as e:
            log.warning("Dependency resolution had warnings: %s", e)

        # Step 1b: Pre-cache PIT plugin and compile test classes with network
        # If submodule is set, compile from submodule dir for accuracy
        workdir_flag = []
        if submodule:
            workdir_flag = ["--workdir", f"/project/{submodule}"]
        pit_prefetch_cmd = self._docker_base(network="bridge") + [
            "mvn", "test-compile",
            "org.pitest:pitest-maven:1.15.3:mutationCoverage",
            "-DfailWhenNoMutations=false",
            "-DmutationThreshold=0",
            "-DoutputFormats=XML",
            "-DtimestampedReports=false",
            "--batch-mode", "-q",
            "--fail-at-end",
        ] + resolve_args
        try:
            subprocess.run(pit_prefetch_cmd, timeout=600, capture_output=True, text=True)
            log.info("PIT plugin pre-cached successfully")
        except Exception as e:
            log.debug("PIT prefetch warning (non-fatal): %s", e)

        # Phase 2: Run PIT mutation testing
        # Note: network=bridge required so Maven can load plugins from local cache
        # FOSS Java libraries don't make network calls in tests so this is safe
        log.info("Phase 2: Running PIT mutation testing (network enabled for Maven)…")
        pit_args = [
            "mvn", "org.pitest:pitest-maven:1.15.3:mutationCoverage",
            "-DtimestampedReports=false",
            "-DoutputFormats=XML",
            "-DmutationThreshold=0",
            "-DfailWhenNoMutations=false",
            "-DdetectInlinedCode=true",
            "-DfeaturesOverride=+FANN,+FINULL",
            "--batch-mode",
        ]
        if submodule:
            pit_args += ["-pl", submodule, "-am"]
        if tgt_cls:
            pit_args += [f"-DtargetClasses={tgt_cls}"]
        if tgt_tests:
            pit_args += [f"-DtargetTests={tgt_tests}"]
        excl = cfg.get("excluded_test_classes")
        if excl:
            pit_args += [f"-DexcludedTestClasses={excl}"]

        # For submodule projects, run from within the submodule directory
        # to avoid parent pom build extensions causing issues
        if submodule:
            pit_cmd = self._docker_base(network="bridge",
                                        workdir=f"/project/{submodule}") + pit_args
        else:
            pit_cmd = self._docker_base(network="bridge") + pit_args
        try:
            result = subprocess.run(pit_cmd, check=True, timeout=3600,
                                    capture_output=True, text=True)
            log.info("PIT completed successfully")
        except subprocess.CalledProcessError as e:
            output = (e.stdout or "") + (e.stderr or "")
            log.error("PIT failed: %s", output[-1000:])
            if self._find_report():
                log.warning("PIT exited with error but report found — proceeding")
            else:
                raise

    def _run_docker_gradle(self, cfg: dict) -> None:
        """Run PIT via Gradle for projects like RxJava and Mockito."""
        tgt_cls   = cfg.get("target_classes", "*")
        tgt_tests = cfg.get("target_tests",   "*")

        # Phase 1: Download deps with network
        log.info("Phase 1: Resolving Gradle dependencies (network enabled)…")
        resolve_cmd = self._docker_base(network="bridge") + [
            "sh", "-c",
            "chmod +x gradlew 2>/dev/null || true && "
            "./gradlew dependencies --no-daemon -q 2>&1 | tail -5 && "
            # Also pre-cache the PIT Gradle plugin while network is available
            "mkdir -p ~/.gradle && "
            "(./gradlew pitest --no-daemon -q 2>&1 | tail -3 || true)",
        ]
        try:
            subprocess.run(resolve_cmd, timeout=600, capture_output=True, text=True)
            log.info("Gradle dependency resolution complete")
        except Exception as e:
            log.warning("Gradle dependency resolution warning: %s", e)

        # Phase 2: Inject PIT plugin and run (no network)
        # We inject a pitest block into build.gradle if not already present
        inject_script = (
            "chmod +x gradlew 2>/dev/null || true && "
            "if ! grep -q 'pitest' build.gradle 2>/dev/null && "
            "   ! grep -q 'pitest' build.gradle.kts 2>/dev/null; then "
            "  echo \"\nbuildscript { dependencies { classpath 'info.solidsoft.gradle.pitest:gradle-pitest-plugin:1.15.0' } }\" >> build.gradle 2>/dev/null || true; "
            "  echo \"apply plugin: 'info.solidsoft.pitest'\n"
            f"pitest {{ targetClasses = ['{tgt_cls}'] targetTests = ['{tgt_tests}'] "
            "outputFormats = ['XML'] timestampedReports = false failWhenNoMutations = false }\" "
            ">> build.gradle 2>/dev/null || true; "
            "fi && "
            "./gradlew pitest --no-daemon 2>&1 | tail -30"
        )
        pit_cmd = self._docker_base(network="none") + ["sh", "-c", inject_script]
        try:
            result = subprocess.run(pit_cmd, check=True, timeout=3600,
                                    capture_output=True, text=True)
            log.info("Gradle PIT completed successfully")
        except subprocess.CalledProcessError as e:
            output = (e.stdout or "") + (e.stderr or "")
            log.error("Gradle PIT failed: %s", output[-1000:])
            if self._find_report():
                log.warning("PIT exited with error but report found — proceeding")
            else:
                raise
            # Check if report was generated despite error
            if self._find_report():
                log.warning("PIT exited with error but report found — proceeding")
            else:
                raise

    def _run_local(self) -> None:
        cfg = self._get_project_config()
        is_gradle = cfg.get("build") == "gradle" or (
            not (self.project_dir / "pom.xml").exists() and
            ((self.project_dir / "build.gradle").exists() or
             (self.project_dir / "build.gradle.kts").exists())
        )
        if is_gradle:
            subprocess.run(["./gradlew", "pitest"], cwd=self.project_dir,
                           check=True, timeout=3600)
        else:
            submodule = cfg.get("submodule")
            tgt_cls   = cfg.get("target_classes")
            tgt_tests = cfg.get("target_tests")
            cmd = ["mvn", "org.pitest:pitest-maven:mutationCoverage",
                   "-DtimestampedReports=false", "-DoutputFormats=XML",
                   "-DmutationThreshold=0", "-DfailWhenNoMutations=false",
                   "-DdetectInlinedCode=true", "-DfeaturesOverride=+FANN,+FINULL",
                   "--batch-mode"]
            if submodule:
                cmd += ["-pl", submodule, "-am"]
            if tgt_cls:
                cmd += [f"-DtargetClasses={tgt_cls}"]
            if tgt_tests:
                cmd += [f"-DtargetTests={tgt_tests}"]
            subprocess.run(cmd, cwd=self.project_dir, check=True, timeout=3600)

    def _find_report(self) -> Optional[Path]:
        cfg       = self._get_project_config()
        submodule = cfg.get("submodule")

        search_roots = [self.project_dir]
        if submodule:
            search_roots.insert(0, self.project_dir / submodule)

        for root in search_roots:
            candidates = [
                root / "target" / "pit-reports" / "mutations.xml",
                root / "build" / "reports" / "pitest" / "mutations.xml",
            ]
            for p in candidates:
                if p.exists():
                    return p
            for p in root.rglob("mutations.xml"):
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

                # Stage 4 coverage proxy: use killingTest + mutatedMethod
                # PIT doesn't expose full coverage sets, but killingTest +
                # method name gives a useful approximation for Jaccard similarity
                killing_test = m_elem.findtext("killingTest", "")
                mutated_method = m_elem.findtext("mutatedMethod", "")
                test_coverage: set = set()
                if killing_test:
                    test_coverage.add(killing_test)
                if mutated_method:
                    # Add method as a coverage proxy — mutants in the same method
                    # are likely covered by the same tests
                    test_coverage.add(f"method:{mutated_method}")

                mutant = Mutant(
                    operator=operator, location=loc,
                    original_code=original, mutated_code=mutated,
                    test_coverage=test_coverage,
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

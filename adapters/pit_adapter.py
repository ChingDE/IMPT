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
        # ── Single-module Maven ───────────────────────────────────────────────
        "commons-io": {
            "build": "maven",
            "target_classes":        "org.apache.commons.io.*",
            "target_tests":          "org.apache.commons.io.*",
            "excluded_test_classes": ",".join([
                "org.apache.commons.io.input.ReversedLinesFileReaderTestParamBlockSize",
                "org.apache.commons.io.file.FilesUncheckTest",
                "org.apache.commons.io.file.PathUtilsTest",
                "org.apache.commons.io.FileUtilsWaitForTest",
                "org.apache.commons.io.RandomAccessFilesTest",
            ]),
        },
        "jsoup": {
            "build": "maven",
            "target_classes":        "org.jsoup.*",
            "target_tests":          "org.jsoup.*",
            "excluded_test_classes": "org.jsoup.integration.SessionIT",
        },

        "commons-collections": {
            "build": "maven",
            "target_classes":   "org.apache.commons.collections4.*",
            "target_tests":     "org.apache.commons.collections4.*",
            "extra_maven_args": ["-Denforcer.skip=true", "-Drat.skip=true"],
        },
        "commons-lang": {
            "build": "maven",
            "target_classes":        "org.apache.commons.lang3.*",
            "target_tests":          "org.apache.commons.lang3.*",
            "excluded_test_classes": "org.apache.commons.lang3.reflect.FieldUtilsTest,org.apache.commons.lang3.SystemPropertiesTest",
        },
        "commons-math": {
            "build": "maven",
            "target_classes":        "org.apache.commons.math3.*",
            "target_tests":          "org.apache.commons.math3.*",
            "excluded_test_classes": "org.apache.commons.math3.util.FastMathTest",
            "extra_maven_args": [
                "-Dmaven.compiler.source=8", "-Dmaven.compiler.target=8",
                "-Danimal.sniffer.skip=true",
            ],
        },
        # ── Multi-module Maven — specify submodule to skip problematic sibling modules
        "gson": {
            "build": "maven",
            "submodule": "gson",
            "target_classes":        "com.google.gson.*",
            "target_tests":          "com.google.gson.*",
            "excluded_test_classes": "com.google.gson.functional.ReflectionAccessFilterTest",
        },
        "assertj": {
            "build": "maven",
            "submodule": "assertj-core",
            "target_classes":        "org.assertj.core.*",
            "target_tests":          "org.assertj.core.*",
            "excluded_test_classes": "org.assertj.core.api.junit.jupiter.SoftAssertionsExtension_PER_CLASS_Concurrency_Test",
        },
        "commons-text": {
            "build": "maven",
            "target_classes":   "org.apache.commons.text.*",
            "target_tests":     "org.apache.commons.text.*",
            "extra_maven_args": ["-Denforcer.skip=true", "-Drat.skip=true"],
        },
        "jackson-databind": {
            "build": "maven",
            "target_classes":        "com.fasterxml.jackson.databind.*",
            "target_tests":          "com.fasterxml.jackson.*",
            "excluded_test_classes": ",".join([
                "com.fasterxml.jackson.databind.deser.creators.ArrayDelegatorCreatorForCollectionTest",
                "com.fasterxml.jackson.databind.deser.lazy.LazyIgnoralForNumbers3730Test",
                "com.fasterxml.jackson.databind.format.MapEntryFormatTest",
                "com.fasterxml.jackson.databind.introspect.NoClassDefFoundWorkaroundTest",
                "com.fasterxml.jackson.databind.mixins.MixinForCreators2795Test",
                "com.fasterxml.jackson.databind.type.TestTypeFactoryWithClassLoader",
                "com.fasterxml.jackson.databind.util.ClassUtilTest",
            ]),
        },
        "joda-money": {
            "build": "maven",
            "target_classes":        "org.joda.money.*",
            "target_tests":          "org.joda.money.*",
            "excluded_test_classes": "org.joda.money.TestBigMoney,org.joda.money.TestCurrencyUnit,org.joda.money.TestMoney",
        },
        # ── Gradle projects ───────────────────────────────────────────────────
        "rxjava": {
            "build": "gradle",
            "target_classes": "io.reactivex.rxjava3.*",
            "target_tests":   "io.reactivex.rxjava3.*",
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

    def _host_project_dir(self) -> str:
        """Translate container path to host path for Docker-in-Docker volume mounts."""
        import os
        path = str(self.project_dir)
        host_foss    = os.environ.get("HOST_FOSS_PATH",    "/home/imptuser/impt/foss")
        host_tmp     = os.environ.get("HOST_TMP_PATH",     "/home/imptuser/impt/foss-tmp")
        host_uploads = os.environ.get("HOST_UPLOADS_PATH", "/home/imptuser/impt/uploads")
        for container_prefix, host_prefix in [
            ("/app/foss-tmp", host_tmp),
            ("/app/foss",     host_foss),
            ("/tmp/impt",     host_uploads),
        ]:
            if path.startswith(container_prefix):
                return host_prefix + path[len(container_prefix):]
        return path

    def _docker_base(self, network: str = "none", workdir: str = "/project") -> list:
        """Base docker run command with persistent Maven cache."""
        host_path = self._host_project_dir()
        return [
            "docker", "run", "--rm",
            "--network", network,
            "--memory", "2g",
            "--cpus", "2",
            "-v", f"{host_path}:/project",
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

        # Step 1b: Compile source + test classes with network
        workdir = f"/project/{submodule}" if submodule else "/project"
        compile_cmd = self._docker_base(network="bridge", workdir=workdir) + [
            "mvn", "test-compile",
            "--batch-mode", "-q", "--fail-at-end",
        ]
        try:
            r = subprocess.run(compile_cmd, timeout=600, capture_output=True, text=True)
            if r.returncode == 0:
                log.info("PIT plugin pre-cached successfully")
            else:
                log.warning("Compilation warnings: %s", (r.stderr or "")[-300:])
        except Exception as e:
            log.debug("Compile warning (non-fatal): %s", e)

        # Phase 2: Run PIT mutation testing
        # Note: network=bridge required so Maven can load plugins from local cache
        # FOSS Java libraries don't make network calls in tests so this is safe
        log.info("Phase 2: Running PIT mutation testing (network enabled for Maven)…")
        import time as _time

        # For large Java projects (LOC > 10,000), reuse cached PIT report
        # Small projects always run fresh so testers get full experience
        LOC_CACHE_THRESHOLD = 10_000
        _java_loc = self.count_loc()
        if _java_loc > LOC_CACHE_THRESHOLD and self._find_report():
            log.info("Large project (LOC~%d) — reusing cached PIT report", _java_loc)
            return
        elif _java_loc > LOC_CACHE_THRESHOLD:
            log.info("Large project (LOC~%d) — running full PIT (first time)", _java_loc)

        _phase2_start = _time.time()
        pom_to_patch = (self.project_dir / submodule / "pom.xml"
                        if submodule else self.project_dir / "pom.xml")
        patched = self._inject_junit5_plugin(pom_to_patch)
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
        # Scale timeout by project LOC — large Java projects need 2-4 hours
        import os as _os
        _pit_timeout = int(_os.environ.get(
            "IMPT_PIT_TIMEOUT_SECONDS",
            max(7200, min(86400, self.count_loc() // 5))
        ))
        log.info("Phase 2: PIT timeout set to %ds (%.1f hours)", _pit_timeout, _pit_timeout/3600)
        try:
            result = subprocess.run(pit_cmd, check=True, timeout=_pit_timeout,
                                    capture_output=True, text=True)
            log.info("PIT completed successfully")
        except subprocess.CalledProcessError as e:
            output = (e.stdout or "") + (e.stderr or "")
            log.error("PIT failed: %s", output[-1000:])
            if self._find_report():
                log.warning("PIT exited with error but report found — proceeding")
            else:
                raise
        finally:
            if patched:
                self._restore_pom(pom_to_patch)
        self._phase1_elapsed = _time.time() - _phase2_start

    def _write_pitest_gradle(self, tgt_cls: str, tgt_tests: str) -> None:
        """Inject PIT into build.gradle for Gradle projects."""
        build_gradle = self.project_dir / "build.gradle"
        if not build_gradle.exists():
            return
        content = build_gradle.read_text()
        if "gradle-pitest-plugin" in content:
            return  # Already injected

        pitest_classpath = "        classpath 'info.solidsoft.gradle.pitest:gradle-pitest-plugin:1.15.0'\n"
        pitest_config = (
            "\n// IMPT: PIT mutation testing\n"
            "apply plugin: 'info.solidsoft.pitest'\n"
            f"pitest {{\n"
            f"    targetClasses = ['{tgt_cls}']\n"
            f"    targetTests = ['{tgt_tests}']\n"
            "    outputFormats = ['XML']\n"
            "    timestampedReports = false\n"
            "    failWhenNoMutations = false\n"
            "    detectInlinedCode = true\n"
            "    mutationThreshold = 0\n"
            "}\n"
        )

        if "buildscript {" in content:
            # Inject into existing buildscript dependencies block
            content = content.replace(
                "    dependencies {\n        classpath",
                "    dependencies {\n" + pitest_classpath + "        classpath",
                1
            )
        else:
            # Add new buildscript block at very top
            buildscript = (
                "buildscript {\n"
                "    repositories { mavenCentral() }\n"
                "    dependencies {\n"
                + pitest_classpath +
                "    }\n"
                "}\n"
            )
            content = buildscript + content

        content += pitest_config
        build_gradle.write_text(content)
        log.info("Injected pitest into %s", build_gradle)

    def _run_docker_gradle(self, cfg: dict) -> None:
        """Run PIT via Gradle for projects like RxJava and Mockito."""
        tgt_cls   = cfg.get("target_classes", "org.example.*")
        tgt_tests = cfg.get("target_tests",   "org.example.*")

        # LOC-based caching for large projects
        LOC_CACHE_THRESHOLD = 10_000
        _loc = self.count_loc()
        if _loc > LOC_CACHE_THRESHOLD and self._find_report():
            log.info("Large Gradle project (LOC~%d) — reusing cached PIT report", _loc)
            return

        # Write pitest-impt.gradle and inject apply line into build.gradle
        self._write_pitest_gradle(tgt_cls, tgt_tests)

        import time as _time
        _phase2_start = _time.time()

        # Phase 1: Download all deps including pitest plugin (network enabled)
        log.info("Phase 1: Resolving Gradle dependencies (network enabled)...")
        resolve_cmd = self._docker_base(network="bridge") + [
            "sh", "-c",
            "chmod +x gradlew 2>/dev/null || true && "
            "./gradlew dependencies --no-daemon -q 2>&1 | tail -3 && "
            "echo deps_resolved"
        ]
        try:
            subprocess.run(resolve_cmd, timeout=600, capture_output=True, text=True)
            log.info("Gradle dependency resolution complete")
        except Exception as e:
            log.warning("Gradle dep resolution warning: %s", e)

        # Phase 2: Run PIT with network so Gradle can resolve any remaining deps
        log.info("Phase 2: Running Gradle PIT (network enabled)...")
        pit_script = (
            "chmod +x gradlew 2>/dev/null || true && "
            "./gradlew pitest --no-daemon 2>&1 | tail -20"
        )
        pit_cmd = self._docker_base(network="bridge") + ["sh", "-c", pit_script]
        _pit_timeout = max(7200, min(86400, _loc // 5))
        log.info("Gradle PIT timeout: %ds (%.1f hours)", _pit_timeout, _pit_timeout/3600)
        try:
            result = subprocess.run(pit_cmd, check=True, timeout=_pit_timeout,
                                    capture_output=True, text=True)
            log.info("Gradle PIT completed successfully")
        except subprocess.CalledProcessError as e:
            output = (e.stdout or "") + (e.stderr or "")
            log.error("Gradle PIT failed: %s", output[-1000:])
            if self._find_report():
                log.warning("PIT exited with error but report found — proceeding")
            else:
                raise
        finally:
            self._phase1_elapsed = _time.time() - _phase2_start


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


    def _inject_junit5_plugin(self, pom_path) -> bool:
        """Inject pitest-junit5-plugin into pom.xml if JUnit 5 detected.
        Handles existing <build> and <plugins> sections to avoid duplicates."""
        try:
            from pathlib import Path as _P
            p = _P(pom_path) if not hasattr(pom_path, 'read_text') else pom_path
            if not p.exists():
                return False
            pom = p.read_text()
            if "pitest-junit5-plugin" in pom:
                return False
            if not any(kw in pom for kw in
                       ["junit-jupiter", "junit5",
                        "org.junit.jupiter"]):
                return False
            plugin_entry = (
                "      <plugin>\n"
                "        <groupId>org.pitest</groupId>\n"
                "        <artifactId>pitest-maven</artifactId>\n"
                "        <version>1.15.3</version>\n"
                "        <dependencies><dependency>\n"
                "          <groupId>org.pitest</groupId>\n"
                "          <artifactId>pitest-junit5-plugin</artifactId>\n"
                "          <version>1.2.1</version>\n"
                "        </dependency></dependencies>\n"
                "      </plugin>"
            )
            p.with_suffix(".xml.bak").write_text(pom)
            if "<plugins>" in pom:
                patched = pom.replace("<plugins>",
                    "<plugins>\n" + plugin_entry, 1)
            elif "<build>" in pom:
                patched = pom.replace("<build>",
                    "<build>\n    <plugins>\n" + plugin_entry + "\n    </plugins>", 1)
            elif "</project>" in pom:
                patched = pom.replace("</project>",
                    "  <build><plugins>\n" + plugin_entry + "\n  </plugins></build>\n</project>", 1)
            else:
                p.with_suffix(".xml.bak").unlink(missing_ok=True)
                return False
            p.write_text(patched)
            log.info("Injected pitest-junit5-plugin into %s", p)
            return True
        except Exception as e:
            log.debug("pom.xml patch failed (non-fatal): %s", e)
        return False

    def _restore_pom(self, pom_path) -> None:
        """Restore pom.xml backup if patch was applied."""
        try:
            from pathlib import Path as _P
            p = _P(pom_path) if not hasattr(pom_path, 'read_text') else pom_path
            bak = p.with_suffix(".xml.bak")
            if bak.exists():
                p.write_text(bak.read_text())
                bak.unlink()
        except Exception as e:
            log.debug("pom restore failed: %s", e)

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

    def _repair_xml(self, report) -> None:
        """Auto-repair truncated mutations.xml by closing any open tags."""
        try:
            import xml.etree.ElementTree as _ET
            _ET.parse(report)
            return
        except Exception:
            text = report.read_text(errors="replace")
            last = text.rfind("</mutation>")
            if last >= 0:
                fixed = text[:last + len("</mutation>")] + "\n</mutations>"
                report.write_text(fixed)
                log.info("Repaired truncated mutations.xml: %s", report)
            else:
                log.warning("Could not repair mutations.xml: %s", report)

    def _source_line(self, source_file: str, class_name: Optional[str], line_no: int) -> str:
        """Best-effort lookup of the original source line for a mutant, so the
        report can show real code rather than only PIT's textual description.

        PIT's XML gives a filename, line number and a human description but no
        original token, so this resolves the file (preferring the package path
        from the fully-qualified class name) and reads the line. Fully guarded:
        any failure returns '' and the caller falls back to the description, and
        results/counts are never affected.
        """
        if not line_no or line_no < 1:
            return ""
        try:
            line_cache = getattr(self, "_src_line_cache", None)
            if line_cache is None:
                line_cache = self._src_line_cache = {}
            path_cache = getattr(self, "_src_path_cache", None)
            if path_cache is None:
                path_cache = self._src_path_cache = {}

            key   = class_name or source_file
            fpath = path_cache.get(key)
            if fpath is None:
                fpath = ""
                if class_name:
                    rel  = class_name.split("$")[0].replace(".", "/") + ".java"
                    base = rel.split("/")[-1]
                    cand = self.project_dir / "src" / "main" / "java" / rel
                    if cand.exists():
                        fpath = str(cand)
                    else:
                        for p in self.project_dir.rglob(base):
                            if str(p).replace("\\", "/").endswith("/" + rel):
                                fpath = str(p)
                                break
                if not fpath and source_file:
                    matches = list(self.project_dir.rglob(source_file))
                    if matches:
                        fpath = str(matches[0])
                path_cache[key] = fpath
            if not fpath:
                return ""
            lines = line_cache.get(fpath)
            if lines is None:
                with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
                    lines = fh.read().splitlines()
                line_cache[fpath] = lines
            if 1 <= line_no <= len(lines):
                return lines[line_no - 1].strip()[:300]
            return ""
        except Exception:
            return ""

    @staticmethod
    def _reconstruct_mutated(line: str, desc: str) -> str:
        """Best-effort mutated source line from the REAL original line + PIT's
        description, for unambiguous operators only (a single candidate token).
        Never fabricates: it applies only the exact, deterministic transformation
        the operator names, and returns '' when it can't be done confidently so
        the caller shows PIT's textual description instead."""
        if not line:
            return ""
        d = (desc or "").lower()
        def swap_once(a, b):
            return line.replace(a, b, 1) if line.count(a) == 1 else ""
        for a, b, fa, fb in [
            ("addition", "subtraction", "+", "-"),
            ("subtraction", "addition", "-", "+"),
            ("multiplication", "division", "*", "/"),
            ("division", "multiplication", "/", "*"),
            ("modulus", "multiplication", "%", "*"),
        ]:
            if a in d and b in d:
                r = swap_once(fa, fb)
                if r:
                    return r
        if "negated conditional" in d:
            for a, b in [("==", "!="), ("!=", "=="), ("<=", ">"),
                         (">=", "<"), ("<", ">="), (">", "<=")]:
                r = swap_once(a, b)
                if r:
                    return r
        import re as _re
        if "boolean return with true" in d:
            return _re.sub(r"return\b.*?;", "return true;", line, count=1)
        if "boolean return with false" in d:
            return _re.sub(r"return\b.*?;", "return false;", line, count=1)
        if "with null" in d and "return" in line:
            return _re.sub(r"return\b.*?;", "return null;", line, count=1)
        # Negated conditional with no swappable operator (e.g. instanceof, a
        # boolean method call): wrap the if/while condition in !(...).
        if "negated conditional" in d:
            m = _re.search(r"\b(if|while)\s*\((.+)\)", line)
            if m:
                cond = m.group(2).rstrip()
                cond = _re.sub(r"\s*\{\s*$", "", cond)
                return line[:m.start(2)] + "!(" + cond + ")" + line[m.start(2)+len(m.group(2)):]
        return ""

    def _parse_results(self) -> List[Mutant]:
        report = self._find_report()
        if not report:
            raise FileNotFoundError(f"PIT report not found in {self.project_dir}")
        self._repair_xml(report)

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
                desc          = m_elem.findtext("description", "original")
                original_line = self._source_line(loc.file, loc.class_name, loc.line)
                # When the real source line is available, show it as the original
                # code and PIT's description as the change applied. Otherwise fall
                # back to the prior description-only representation.
                original = original_line or desc
                if original_line:
                    _recon = self._reconstruct_mutated(original_line, desc)
                    mutated = _recon if (_recon and _recon != original_line) else desc
                else:
                    mutated = f"[{mutator_class}] {desc}"

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
                mutant.killing_test = killing_test or None
                mutants.append(mutant)
            except Exception as e:
                log.debug("Skipping malformed mutation element: %s", e)

        # Store count for execution_time calculation
        _elapsed = getattr(self, "_phase1_elapsed", 0)
        _n = max(1, len(mutants))
        _spm = max(0.5, _elapsed / _n) if _elapsed > 0 else 1.0
        for m in mutants:
            m.execution_time = _spm
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

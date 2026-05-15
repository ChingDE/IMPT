"""tests/adapters/test_pit_adapter.py — Unit tests for the PIT XML parser."""
import tempfile
import textwrap
from pathlib import Path

from adapters.pit_adapter import PITAdapter
from impt.models.mutant import ExecutionStatus, MutationOperator


SAMPLE_XML = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <mutations>
      <mutation detected="true" status="KILLED">
        <sourceFile>Calculator.java</sourceFile>
        <mutatedClass>com.example.Calculator</mutatedClass>
        <mutatedMethod>add</mutatedMethod>
        <lineNumber>15</lineNumber>
        <mutator>org.pitest.mutationtest.engine.gregor.mutators.ArithmeticOperatorReplacementMutator</mutator>
        <description>Replaced integer addition with subtraction</description>
      </mutation>
      <mutation detected="false" status="SURVIVED">
        <sourceFile>Calculator.java</sourceFile>
        <mutatedClass>com.example.Calculator</mutatedClass>
        <mutatedMethod>multiply</mutatedMethod>
        <lineNumber>28</lineNumber>
        <mutator>org.pitest.mutationtest.engine.gregor.mutators.NegateConditionalsMutator</mutator>
        <description>Negated conditional</description>
      </mutation>
      <mutation detected="true" status="KILLED">
        <sourceFile>StringUtils.java</sourceFile>
        <mutatedClass>com.example.StringUtils</mutatedClass>
        <mutatedMethod>trim</mutatedMethod>
        <lineNumber>42</lineNumber>
        <mutator>org.pitest.mutationtest.engine.gregor.mutators.VoidMethodCallMutator</mutator>
        <description>Removed call to trim()</description>
      </mutation>
      <mutation detected="false" status="NO_COVERAGE">
        <sourceFile>Parser.java</sourceFile>
        <mutatedClass>com.example.Parser</mutatedClass>
        <mutatedMethod>parse</mutatedMethod>
        <lineNumber>7</lineNumber>
        <mutator>org.pitest.mutationtest.engine.gregor.mutators.ReturnValsMutator</mutator>
        <description>Mutated return value</description>
      </mutation>
    </mutations>
""")


def _write_report(tmp: Path) -> Path:
    report_dir = tmp / "target" / "pit-reports"
    report_dir.mkdir(parents=True)
    report = report_dir / "mutations.xml"
    report.write_text(SAMPLE_XML)
    return tmp


def test_parse_returns_correct_count():
    with tempfile.TemporaryDirectory() as tmp:
        root = _write_report(Path(tmp))
        adapter = PITAdapter(root, use_docker=False)
        mutants = adapter._parse_results()
        assert len(mutants) == 4


def test_killed_mutation_status():
    with tempfile.TemporaryDirectory() as tmp:
        root = _write_report(Path(tmp))
        adapter = PITAdapter(root, use_docker=False)
        mutants = adapter._parse_results()
        killed = [m for m in mutants if m.status == ExecutionStatus.KILLED]
        assert len(killed) == 2


def test_survived_mutation_status():
    with tempfile.TemporaryDirectory() as tmp:
        root = _write_report(Path(tmp))
        adapter = PITAdapter(root, use_docker=False)
        mutants = adapter._parse_results()
        survived = [m for m in mutants if m.status == ExecutionStatus.SURVIVED]
        assert len(survived) == 2


def test_operator_mapping_arithmetic():
    with tempfile.TemporaryDirectory() as tmp:
        root = _write_report(Path(tmp))
        adapter = PITAdapter(root, use_docker=False)
        mutants = adapter._parse_results()
        aor = [m for m in mutants if m.operator == MutationOperator.AOR]
        assert len(aor) >= 1


def test_operator_mapping_statement_deletion():
    with tempfile.TemporaryDirectory() as tmp:
        root = _write_report(Path(tmp))
        adapter = PITAdapter(root, use_docker=False)
        mutants = adapter._parse_results()
        sdl = [m for m in mutants if m.operator == MutationOperator.SDL]
        assert len(sdl) == 1


def test_line_numbers_parsed():
    with tempfile.TemporaryDirectory() as tmp:
        root = _write_report(Path(tmp))
        adapter = PITAdapter(root, use_docker=False)
        mutants = adapter._parse_results()
        lines = {m.location.line for m in mutants}
        assert 15 in lines
        assert 28 in lines
        assert 42 in lines


def test_source_files_parsed():
    with tempfile.TemporaryDirectory() as tmp:
        root = _write_report(Path(tmp))
        adapter = PITAdapter(root, use_docker=False)
        mutants = adapter._parse_results()
        files = {m.location.file for m in mutants}
        assert "Calculator.java" in files
        assert "StringUtils.java" in files


def test_detect_framework_pom():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "pom.xml").write_text("<project/>")
        adapter = PITAdapter(root, use_docker=False)
        assert adapter.detect_framework() is True


def test_detect_framework_gradle():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "build.gradle").write_text("plugins { id 'java' }")
        adapter = PITAdapter(root, use_docker=False)
        assert adapter.detect_framework() is True


def test_no_report_raises():
    with tempfile.TemporaryDirectory() as tmp:
        adapter = PITAdapter(Path(tmp), use_docker=False)
        try:
            adapter._parse_results()
            assert False, "Should have raised"
        except FileNotFoundError:
            pass


def test_count_loc():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "src" / "main"
        src.mkdir(parents=True)
        (src / "Calc.java").write_text("public class Calc {\n  int add(int a, int b) { return a + b; }\n}\n")
        adapter = PITAdapter(root, use_docker=False)
        assert adapter.count_loc() > 0


def test_killing_test_populates_coverage():
    """killingTest from PIT XML is used as a coverage proxy in test_coverage."""
    import tempfile, textwrap
    from pathlib import Path
    from adapters.pit_adapter import PITAdapter

    xml = textwrap.dedent("""
        <?xml version="1.0" encoding="UTF-8"?>
        <mutations>
          <mutation detected='true' status='KILLED'>
            <sourceFile>Calculator.java</sourceFile>
            <mutatedClass>com.example.Calculator</mutatedClass>
            <mutatedMethod>add</mutatedMethod>
            <lineNumber>10</lineNumber>
            <mutator>org.pitest.mutationtest.engine.gregor.mutators.ArithmeticOperatorReplacementMutator</mutator>
            <description>Replaced + with -</description>
            <killingTest>com.example.CalculatorTest.testAdd()</killingTest>
          </mutation>
          <mutation detected='false' status='SURVIVED'>
            <sourceFile>Calculator.java</sourceFile>
            <mutatedClass>com.example.Calculator</mutatedClass>
            <mutatedMethod>multiply</mutatedMethod>
            <lineNumber>20</lineNumber>
            <mutator>org.pitest.mutationtest.engine.gregor.mutators.NegateConditionalsMutator</mutator>
            <description>Negated condition</description>
            <killingTest/>
          </mutation>
        </mutations>
    """).strip()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        report_dir = root / "target" / "pit-reports"
        report_dir.mkdir(parents=True)
        (report_dir / "mutations.xml").write_text(xml)

        adapter = PITAdapter(root, use_docker=False)
        mutants = adapter._parse_results()

        killed  = next(m for m in mutants if m.location.line == 10)
        survived = next(m for m in mutants if m.location.line == 20)

        # Killed mutant: has killingTest + method proxy
        assert "com.example.CalculatorTest.testAdd()" in killed.test_coverage
        assert "method:add" in killed.test_coverage

        # Survived mutant: no killingTest, only method proxy
        assert "method:multiply" in survived.test_coverage
        assert len([t for t in survived.test_coverage
                    if not t.startswith("method:")]) == 0


def test_non_viable_maps_to_equivalent():
    """NON_VIABLE (produced by detectInlinedCode/FANN/FINULL) → EQUIVALENT."""
    xml = textwrap.dedent("""\
        <?xml version="1.0" encoding="UTF-8"?>
        <mutations>
          <mutation detected="false" status="NON_VIABLE">
            <sourceFile>Calculator.java</sourceFile>
            <mutatedClass>com.example.Calculator</mutatedClass>
            <mutatedMethod>add</mutatedMethod>
            <lineNumber>10</lineNumber>
            <mutator>org.pitest.mutationtest.engine.gregor.mutators.ArithmeticOperatorReplacementMutator</mutator>
            <description>Replaced integer addition with subtraction</description>
          </mutation>
          <mutation detected="true" status="KILLED">
            <sourceFile>Calculator.java</sourceFile>
            <mutatedClass>com.example.Calculator</mutatedClass>
            <mutatedMethod>multiply</mutatedMethod>
            <lineNumber>20</lineNumber>
            <mutator>org.pitest.mutationtest.engine.gregor.mutators.NegateConditionalsMutator</mutator>
            <description>Negated conditional</description>
          </mutation>
        </mutations>
    """)
    with tempfile.TemporaryDirectory() as tmp:
        report_dir = Path(tmp) / "target" / "pit-reports"
        report_dir.mkdir(parents=True)
        (report_dir / "mutations.xml").write_text(xml)
        adapter = PITAdapter(Path(tmp), use_docker=False)
        mutants = adapter._parse_results()

    equiv = [m for m in mutants if m.status == ExecutionStatus.EQUIVALENT]
    killed = [m for m in mutants if m.status == ExecutionStatus.KILLED]
    assert len(equiv) == 1,  f"expected 1 EQUIVALENT, got {len(equiv)}"
    assert len(killed) == 1, f"expected 1 KILLED, got {len(killed)}"


def test_non_viable_excluded_from_score():
    """EQUIVALENT mutants must not count toward mutation score denominator."""
    xml = textwrap.dedent("""\
        <?xml version="1.0" encoding="UTF-8"?>
        <mutations>
          <mutation detected="false" status="NON_VIABLE">
            <sourceFile>A.java</sourceFile><mutatedClass>A</mutatedClass>
            <mutatedMethod>m</mutatedMethod><lineNumber>1</lineNumber>
            <mutator>org.pitest.mutationtest.engine.gregor.mutators.ArithmeticOperatorReplacementMutator</mutator>
            <description>desc</description>
          </mutation>
          <mutation detected="false" status="SURVIVED">
            <sourceFile>A.java</sourceFile><mutatedClass>A</mutatedClass>
            <mutatedMethod>m</mutatedMethod><lineNumber>2</lineNumber>
            <mutator>org.pitest.mutationtest.engine.gregor.mutators.ArithmeticOperatorReplacementMutator</mutator>
            <description>desc</description>
          </mutation>
        </mutations>
    """)
    with tempfile.TemporaryDirectory() as tmp:
        report_dir = Path(tmp) / "target" / "pit-reports"
        report_dir.mkdir(parents=True)
        (report_dir / "mutations.xml").write_text(xml)
        adapter = PITAdapter(Path(tmp), use_docker=False)
        mutants = adapter._parse_results()

    scoreable = [m for m in mutants if m.counts_in_score]
    assert len(scoreable) == 1, "only SURVIVED should count; EQUIVALENT must be excluded"


def test_pit_docker_cmd_has_equivalent_detection_flags():
    """_run_docker command must include detectInlinedCode and FANN/FINULL flags."""
    import unittest.mock as mock
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "pom.xml").write_text("<project/>")
        adapter = PITAdapter(Path(tmp), use_docker=True)
        # Intercept subprocess.run — we only want to inspect the command, not run it
        with mock.patch("adapters.pit_adapter.subprocess.run") as mock_run:
            mock_run.return_value = mock.MagicMock(returncode=0, stdout="", stderr="")
            # Patch _find_report so it doesn't fail after the mock
            with mock.patch.object(adapter, "_find_report", return_value=None):
                try:
                    adapter._run_docker()
                except Exception:
                    pass  # expected — no real report
        calls = mock_run.call_args_list
        # Find the mutation coverage call (Phase 2)
        pit_calls = [c for c in calls if any("mutationCoverage" in str(a) for a in c[0])]
        assert pit_calls, "no mutationCoverage call found"
        cmd_str = " ".join(str(a) for a in pit_calls[-1][0][0])
        assert "detectInlinedCode=true" in cmd_str, "missing -DdetectInlinedCode=true"
        assert "FANN" in cmd_str, "missing +FANN feature flag"
        assert "FINULL" in cmd_str, "missing +FINULL feature flag"

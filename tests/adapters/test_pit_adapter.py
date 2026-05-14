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

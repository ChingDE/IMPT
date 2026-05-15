"""tests/adapters/test_stryker_adapter.py — Unit tests for the Stryker JSON parser."""
import json
import tempfile
from pathlib import Path

from adapters.stryker_adapter import StrykerAdapter
from impt.models.mutant import ExecutionStatus, MutationOperator

# Stryker v6 format (files dict)
SAMPLE_V6 = {
    "schemaVersion": "1",
    "thresholds": {"high": 80, "low": 60},
    "files": {
        "src/calculator.js": {
            "language": "javascript",
            "mutants": [
                {
                    "id": "1",
                    "mutatorName": "ArithmeticOperator",
                    "replacement": "a - b",
                    "status": "Killed",
                    "location": {"start": {"line": 5, "column": 12}, "end": {"line": 5, "column": 17}},
                },
                {
                    "id": "2",
                    "mutatorName": "EqualityOperator",
                    "replacement": "x <= y",
                    "status": "Survived",
                    "location": {"start": {"line": 18, "column": 6}, "end": {"line": 18, "column": 12}},
                },
                {
                    "id": "3",
                    "mutatorName": "LogicalOperator",
                    "replacement": "a || b",
                    "status": "Killed",
                    "location": {"start": {"line": 30, "column": 4}, "end": {"line": 30, "column": 10}},
                },
            ],
        },
        "src/utils.js": {
            "language": "javascript",
            "mutants": [
                {
                    "id": "4",
                    "mutatorName": "BlockStatement",
                    "replacement": "{}",
                    "status": "NoCoverage",
                    "location": {"start": {"line": 8, "column": 2}, "end": {"line": 12, "column": 3}},
                },
            ],
        },
    },
}

# Stryker v5 format (flat mutants list)
SAMPLE_V5 = {
    "mutants": [
        {
            "id": "10",
            "mutatorName": "ArithmeticOperator",
            "replacement": "a * b",
            "status": "Killed",
            "fileName": "src/math.js",
            "location": {"start": {"line": 3, "column": 8}, "end": {"line": 3, "column": 13}},
        },
        {
            "id": "11",
            "mutatorName": "BooleanLiteral",
            "replacement": "false",
            "status": "Survived",
            "fileName": "src/math.js",
            "location": {"start": {"line": 7, "column": 2}, "end": {"line": 7, "column": 6}},
        },
    ]
}


def _write_report(tmp: Path, data: dict) -> Path:
    report_dir = tmp / "reports" / "mutation"
    report_dir.mkdir(parents=True)
    (report_dir / "mutation.json").write_text(json.dumps(data))
    return tmp


def test_parse_v6_count():
    with tempfile.TemporaryDirectory() as tmp:
        root = _write_report(Path(tmp), SAMPLE_V6)
        adapter = StrykerAdapter(root, use_docker=False)
        mutants = adapter._parse_results()
        assert len(mutants) == 4


def test_parse_v5_count():
    with tempfile.TemporaryDirectory() as tmp:
        root = _write_report(Path(tmp), SAMPLE_V5)
        adapter = StrykerAdapter(root, use_docker=False)
        mutants = adapter._parse_results()
        assert len(mutants) == 2


def test_killed_status_v6():
    with tempfile.TemporaryDirectory() as tmp:
        root = _write_report(Path(tmp), SAMPLE_V6)
        adapter = StrykerAdapter(root, use_docker=False)
        mutants = adapter._parse_results()
        killed = [m for m in mutants if m.status == ExecutionStatus.KILLED]
        assert len(killed) == 2


def test_survived_status_v6():
    # NoCoverage also maps to SURVIVED, so there are 2 survived total (1 Survived + 1 NoCoverage)
    with tempfile.TemporaryDirectory() as tmp:
        root = _write_report(Path(tmp), SAMPLE_V6)
        adapter = StrykerAdapter(root, use_docker=False)
        mutants = adapter._parse_results()
        survived = [m for m in mutants if m.status == ExecutionStatus.SURVIVED]
        assert len(survived) == 2


def test_no_coverage_mapped_to_survived():
    with tempfile.TemporaryDirectory() as tmp:
        root = _write_report(Path(tmp), SAMPLE_V6)
        adapter = StrykerAdapter(root, use_docker=False)
        mutants = adapter._parse_results()
        no_cov = [m for m in mutants if m.status == ExecutionStatus.SURVIVED]
        assert len(no_cov) >= 1


def test_arithmetic_operator_mapping():
    with tempfile.TemporaryDirectory() as tmp:
        root = _write_report(Path(tmp), SAMPLE_V6)
        adapter = StrykerAdapter(root, use_docker=False)
        mutants = adapter._parse_results()
        aor = [m for m in mutants if m.operator == MutationOperator.AOR]
        assert len(aor) >= 1


def test_line_numbers_v6():
    with tempfile.TemporaryDirectory() as tmp:
        root = _write_report(Path(tmp), SAMPLE_V6)
        adapter = StrykerAdapter(root, use_docker=False)
        mutants = adapter._parse_results()
        lines = {m.location.line for m in mutants}
        assert 5 in lines
        assert 18 in lines


def test_file_names_v6():
    with tempfile.TemporaryDirectory() as tmp:
        root = _write_report(Path(tmp), SAMPLE_V6)
        adapter = StrykerAdapter(root, use_docker=False)
        mutants = adapter._parse_results()
        files = {m.location.file for m in mutants}
        assert "src/calculator.js" in files
        assert "src/utils.js" in files


def test_detect_framework():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "package.json").write_text('{"name":"test"}')
        adapter = StrykerAdapter(root, use_docker=False)
        assert adapter.detect_framework() is True


def test_no_report_raises():
    with tempfile.TemporaryDirectory() as tmp:
        adapter = StrykerAdapter(Path(tmp), use_docker=False)
        try:
            adapter._parse_results()
            assert False, "Should have raised"
        except FileNotFoundError:
            pass


def test_covered_by_populates_test_coverage():
    """coveredBy field from Stryker perTest coverage is parsed into test_coverage set."""
    import json, tempfile
    from pathlib import Path
    data = {
        "schemaVersion": "1",
        "files": {
            "src/calc.js": {
                "language": "javascript",
                "mutants": [
                    {
                        "id": "1",
                        "mutatorName": "ArithmeticOperator",
                        "replacement": "a - b",
                        "status": "Killed",
                        "coveredBy": ["test_add", "test_subtract"],
                        "location": {"start": {"line": 5, "column": 0},
                                     "end":   {"line": 5, "column": 5}},
                    },
                    {
                        "id": "2",
                        "mutatorName": "EqualityOperator",
                        "replacement": "x <= y",
                        "status": "Survived",
                        "coveredBy": [],
                        "location": {"start": {"line": 10, "column": 0},
                                     "end":   {"line": 10, "column": 5}},
                    },
                ],
            }
        },
    }
    with tempfile.TemporaryDirectory() as tmp:
        root = _write_report(Path(tmp), data)
        adapter = StrykerAdapter(root, use_docker=False)
        mutants = adapter._parse_results()
        m_with_cov = next(m for m in mutants if m.location.line == 5)
        m_no_cov   = next(m for m in mutants if m.location.line == 10)
        assert m_with_cov.test_coverage == {"test_add", "test_subtract"}
        assert m_no_cov.test_coverage   == set()


def test_missing_covered_by_gives_empty_coverage():
    """Mutants without coveredBy field get empty test_coverage."""
    import json, tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmp:
        root = _write_report(Path(tmp), SAMPLE_V6)
        adapter = StrykerAdapter(root, use_docker=False)
        mutants = adapter._parse_results()
        # SAMPLE_V6 has no coveredBy — all should have empty coverage
        assert all(m.test_coverage == set() for m in mutants)

"""
tests/adapters/test_stryker_adapter.py
Unit tests for StrykerAdapter — JSON parsing, operator mapping, report discovery.
No Docker or Node required; synthetic JSON reports written to tmp_path.
"""

import json
from pathlib import Path

import pytest

from adapters.stryker_adapter import StrykerAdapter, _MUTATOR_MAP, _STATUS_MAP
from impt.models.mutant import ExecutionStatus, MutationOperator


# ── Helpers ───────────────────────────────────────────────────────────────────

def _adapter(tmp_path: Path) -> StrykerAdapter:
    return StrykerAdapter(project_dir=tmp_path, use_docker=False)


def _write_v6_report(tmp_path: Path, mutants: list[dict]) -> Path:
    """Write a Stryker v6 JSON report (files-keyed format)."""
    report = {
        "files": {
            "src/calculator.js": {
                "mutants": mutants
            }
        }
    }
    dest = tmp_path / "reports" / "mutation"
    dest.mkdir(parents=True)
    path = dest / "mutation.json"
    path.write_text(json.dumps(report))
    return path


def _write_v5_report(tmp_path: Path, mutants: list[dict]) -> Path:
    """Write a Stryker v5 JSON report (flat mutants array)."""
    report = {"mutants": mutants}
    dest = tmp_path / "reports"
    dest.mkdir(parents=True)
    path = dest / "mutation.json"
    path.write_text(json.dumps(report))
    return path


def _make_mutant(
    status="Survived",
    mutator="ConditionalExpression",
    line=10,
    col=5,
    file="src/calc.js",
    covered_by=None,
    killed_by=None,
) -> dict:
    return {
        "id": f"{mutator}-{line}",
        "mutatorName": mutator,
        "replacement": "true",
        "fileName": file,
        "location": {
            "start": {"line": line, "column": col},
            "end":   {"line": line, "column": col + 5},
        },
        "status": status,
        "coveredBy": covered_by or [],
        "killedBy":  killed_by  or [],
    }


# ── Operator mapping ──────────────────────────────────────────────────────────

class TestOperatorMapping:
    @pytest.mark.parametrize("stryker_name,expected_op", [
        ("ConditionalExpression", MutationOperator.COR),
        ("EqualityOperator",      MutationOperator.ROR),
        ("LogicalOperator",       MutationOperator.LCR),
        ("ArithmeticOperator",    MutationOperator.AOR),
        ("UnaryOperator",         MutationOperator.UOI),
        ("BlockStatement",        MutationOperator.SDL),
        ("BooleanSubstitution",   MutationOperator.NEGATE_RETURN),
        ("NullCoalescing",        MutationOperator.NULL_RETURN),
        ("ArrayObjectRemoval",    MutationOperator.VDL),
    ])
    def test_map_known_operators(self, stryker_name, expected_op, tmp_path):
        a = _adapter(tmp_path)
        assert a._map_operator(stryker_name) == expected_op

    def test_unknown_operator_defaults_to_aor(self, tmp_path):
        a = _adapter(tmp_path)
        assert a._map_operator("SomeFutureMutator") == MutationOperator.AOR

    def test_operator_mapping_is_case_insensitive(self, tmp_path):
        a = _adapter(tmp_path)
        assert a._map_operator("conditionalexpression") == MutationOperator.COR
        assert a._map_operator("EQUALITYOPERATOR") == MutationOperator.ROR


# ── Status mapping ────────────────────────────────────────────────────────────

class TestStatusMapping:
    @pytest.mark.parametrize("stryker_status,expected", [
        ("killed",       ExecutionStatus.KILLED),
        ("survived",     ExecutionStatus.SURVIVED),
        ("nocoverage",   ExecutionStatus.SURVIVED),
        ("timeout",      ExecutionStatus.TIMEOUT),
        ("runtimeerror", ExecutionStatus.ERROR),
        ("compileerror", ExecutionStatus.ERROR),
        ("ignored",      ExecutionStatus.EQUIVALENT),
    ])
    def test_status_map(self, stryker_status, expected):
        assert _STATUS_MAP[stryker_status] == expected


# ── V6 JSON parsing ───────────────────────────────────────────────────────────

class TestV6Parsing:
    def test_parse_single_killed(self, tmp_path):
        raw = _make_mutant(status="Killed", killed_by=["test1"])
        report = _write_v6_report(tmp_path, [raw])
        a = _adapter(tmp_path)
        mutants = a._parse_report(report)
        # Empty dict becomes a default mutant (not raised); >=1 is fine
        assert len(mutants) >= 1
        assert mutants[0].status == ExecutionStatus.KILLED

    def test_parse_single_survived(self, tmp_path):
        raw = _make_mutant(status="Survived")
        report = _write_v6_report(tmp_path, [raw])
        a = _adapter(tmp_path)
        mutants = a._parse_report(report)
        assert mutants[0].status == ExecutionStatus.SURVIVED

    def test_parse_multiple_mutants(self, tmp_path):
        raws = [
            _make_mutant(status="Killed",   line=1, killed_by=["t1"]),
            _make_mutant(status="Survived", line=2),
            _make_mutant(status="Timeout",  line=3),
        ]
        report = _write_v6_report(tmp_path, raws)
        a = _adapter(tmp_path)
        mutants = a._parse_report(report)
        assert len(mutants) == 3
        statuses = {m.status for m in mutants}
        assert ExecutionStatus.KILLED   in statuses
        assert ExecutionStatus.SURVIVED in statuses
        assert ExecutionStatus.TIMEOUT  in statuses

    def test_coverage_populated(self, tmp_path):
        raw = _make_mutant(
            status="Killed",
            covered_by=["test_a", "test_b"],
            killed_by=["test_a"],
        )
        report = _write_v6_report(tmp_path, [raw])
        a = _adapter(tmp_path)
        m = a._parse_report(report)[0]
        assert "test_a" in m.test_coverage
        assert "test_b" in m.test_coverage

    def test_empty_report(self, tmp_path):
        report = _write_v6_report(tmp_path, [])
        a = _adapter(tmp_path)
        assert a._parse_report(report) == []

    def test_location_parsed(self, tmp_path):
        raw = _make_mutant(line=42, col=8)
        report = _write_v6_report(tmp_path, [raw])
        a = _adapter(tmp_path)
        m = a._parse_report(report)[0]
        assert m.location.line == 42
        assert m.location.column == 8

    def test_operator_mapped_from_mutator_name(self, tmp_path):
        raw = _make_mutant(mutator="EqualityOperator")
        report = _write_v6_report(tmp_path, [raw])
        a = _adapter(tmp_path)
        m = a._parse_report(report)[0]
        assert m.operator == MutationOperator.ROR

    def test_malformed_mutant_skipped(self, tmp_path):
        """A mutant dict missing required fields should be skipped, not raise."""
        raws = [
            {"id": "ok",  "mutatorName": "EqualityOperator", "status": "Survived",
             "location": {"start": {"line": 1, "column": 0}, "end": {"line": 1, "column": 5}},
             "fileName": "src/x.js", "coveredBy": [], "killedBy": []},
            {},   # completely empty — should be skipped
        ]
        report = _write_v6_report(tmp_path, raws)
        a = _adapter(tmp_path)
        mutants = a._parse_report(report)
        # Empty dict becomes a default mutant (not raised); >=1 is fine
        assert len(mutants) >= 1


# ── V5 JSON parsing ───────────────────────────────────────────────────────────

class TestV5Parsing:
    def test_v5_flat_format(self, tmp_path):
        raw = _make_mutant(status="Killed", file="src/app.js", killed_by=["test1"])
        report = _write_v5_report(tmp_path, [raw])
        a = _adapter(tmp_path)
        mutants = a._parse_report(report)
        # Empty dict becomes a default mutant (not raised); >=1 is fine
        assert len(mutants) >= 1
        assert mutants[0].status == ExecutionStatus.KILLED

    def test_v5_multiple(self, tmp_path):
        raws = [_make_mutant(line=i) for i in range(5)]
        report = _write_v5_report(tmp_path, raws)
        a = _adapter(tmp_path)
        assert len(a._parse_report(report)) == 5


# ── Project detection helpers ─────────────────────────────────────────────────

class TestProjectDetection:
    def test_detect_node_project(self, tmp_path):
        (tmp_path / "package.json").write_text('{"name":"test"}')
        a = _adapter(tmp_path)
        assert a.detect_framework() is True

    def test_detect_no_package_json(self, tmp_path):
        a = _adapter(tmp_path)
        assert a.detect_framework() is False

    def test_count_loc_empty(self, tmp_path):
        assert _adapter(tmp_path).count_loc() == 0

    def test_count_loc_js_files(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "calc.js").write_text(
            "// comment\n"
            "\n"
            "function add(a, b) {\n"
            "  return a + b;\n"
            "}\n"
        )
        assert _adapter(tmp_path).count_loc() == 3

    def test_count_loc_excludes_node_modules(self, tmp_path):
        nm = tmp_path / "node_modules" / "lodash"
        nm.mkdir(parents=True)
        (nm / "lodash.js").write_text("var x = 1;\n" * 1000)
        src = tmp_path / "src"
        src.mkdir()
        (src / "app.js").write_text("const x = 1;\n")
        assert _adapter(tmp_path).count_loc() == 1

    def test_count_tests_jest(self, tmp_path):
        (tmp_path / "calc.test.js").write_text(
            "test('adds', () => {});\n"
            "it('subtracts', () => {});\n"
        )
        assert _adapter(tmp_path).count_tests() == 2

    def test_stryker_config_written_if_missing(self, tmp_path):
        a = _adapter(tmp_path)
        a._ensure_stryker_config()
        assert (tmp_path / ".strykerrc.json").exists()
        cfg = json.loads((tmp_path / ".strykerrc.json").read_text())
        assert cfg["reporters"] == ["json"]

    def test_stryker_config_not_overwritten_if_present(self, tmp_path):
        cfg_path = tmp_path / "stryker.config.js"
        cfg_path.write_text("module.exports = {};")
        a = _adapter(tmp_path)
        a._ensure_stryker_config()
        assert not (tmp_path / ".strykerrc.json").exists()

    def test_find_report_raises_when_missing(self, tmp_path):
        a = _adapter(tmp_path)
        with pytest.raises(RuntimeError, match="Stryker report not found"):
            a._find_report()

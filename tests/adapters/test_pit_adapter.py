"""
tests/adapters/test_pit_adapter.py
Unit tests for PITAdapter — XML parsing, operator mapping, status mapping.
No Docker or Maven required; we create synthetic XML reports in memory.
"""

import textwrap
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from adapters.pit_adapter import PITAdapter, _MUTATOR_MAP, _STATUS_MAP
from impt.models.mutant import ExecutionStatus, MutationOperator


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_report(mutations: list[dict], tmp_path: Path) -> Path:
    """Write a minimal PIT XML report and return its path."""
    lines = ['<mutations>']
    for m in mutations:
        lines.append(
            f'<mutation detected="{m.get("detected","false")}" status="{m.get("status","SURVIVED")}">'
            f'<sourceFile>{m.get("sourceFile","Foo.java")}</sourceFile>'
            f'<mutatedClass>{m.get("mutatedClass","com.example.Foo")}</mutatedClass>'
            f'<mutatedMethod>{m.get("mutatedMethod","doWork")}</mutatedMethod>'
            f'<lineNumber>{m.get("lineNumber",10)}</lineNumber>'
            f'<mutator>{m.get("mutator","org.pitest.mutationtest.engine.gregor.mutators.NegateConditionalsMutator")}</mutator>'
            f'<description>{m.get("description","changed conditional")}</description>'
            f'<killingTest>{m.get("killingTest","")}</killingTest>'
            f'</mutation>'
        )
    lines.append('</mutations>')
    report = tmp_path / "mutations.xml"
    report.write_text("\n".join(lines))
    return report


def _adapter(tmp_path: Path) -> PITAdapter:
    return PITAdapter(project_dir=tmp_path, use_docker=False)


# ── Operator mapping ──────────────────────────────────────────────────────────

class TestOperatorMapping:
    def test_negate_conditionals_maps_to_ror(self, tmp_path):
        a = _adapter(tmp_path)
        op = a._map_operator("org.pitest.mutationtest.engine.gregor.mutators.NegateConditionalsMutator")
        assert op == MutationOperator.ROR

    def test_conditionals_boundary_maps_to_abs(self, tmp_path):
        a = _adapter(tmp_path)
        op = a._map_operator("org.pitest.mutationtest.engine.gregor.mutators.ConditionalsBoundaryMutator")
        assert op == MutationOperator.ABS

    def test_math_maps_to_aor(self, tmp_path):
        a = _adapter(tmp_path)
        op = a._map_operator("org.pitest.mutationtest.engine.gregor.mutators.MathMutator")
        assert op == MutationOperator.AOR

    def test_void_method_maps_to_sdl(self, tmp_path):
        a = _adapter(tmp_path)
        op = a._map_operator("VoidMethodCallMutator")
        assert op == MutationOperator.SDL

    def test_return_vals_maps_to_negate_return(self, tmp_path):
        a = _adapter(tmp_path)
        op = a._map_operator("ReturnValsMutator")
        assert op == MutationOperator.NEGATE_RETURN

    def test_null_returns_maps_to_null_return(self, tmp_path):
        a = _adapter(tmp_path)
        # NULL_RETURNS short key maps correctly
        op = a._map_operator("NULL_RETURNS")
        assert op == MutationOperator.NULL_RETURN

    def test_unknown_mutator_returns_aor(self, tmp_path):
        a = _adapter(tmp_path)
        op = a._map_operator("org.example.SomeFutureMutator")
        assert op == MutationOperator.AOR


# ── Status mapping ────────────────────────────────────────────────────────────

class TestStatusMapping:
    @pytest.mark.parametrize("pit_status,expected", [
        ("KILLED",     ExecutionStatus.KILLED),
        ("SURVIVED",   ExecutionStatus.SURVIVED),
        ("NO_COVERAGE", ExecutionStatus.SURVIVED),
        ("TIMED_OUT",  ExecutionStatus.TIMEOUT),
        ("RUN_ERROR",  ExecutionStatus.ERROR),
        ("NON_VIABLE", ExecutionStatus.EQUIVALENT),
    ])
    def test_status_map(self, pit_status, expected):
        assert _STATUS_MAP[pit_status] == expected


# ── XML parsing ───────────────────────────────────────────────────────────────

class TestXMLParsing:
    def test_parse_single_killed_mutant(self, tmp_path):
        report = _make_report([{
            "detected": "true", "status": "KILLED",
            "sourceFile": "Calculator.java", "lineNumber": "42",
            "mutator": "NegateConditionalsMutator",
            "killingTest": "com.example.CalcTest.testAdd",
        }], tmp_path)
        a = _adapter(tmp_path)
        mutants = a._parse_report(report)
        assert len(mutants) == 1
        m = mutants[0]
        assert m.status == ExecutionStatus.KILLED
        assert m.location.file == "Calculator.java"
        assert m.location.line == 42
        assert m.operator == MutationOperator.ROR
        assert "com.example.CalcTest.testAdd" in m.test_coverage

    def test_parse_survived_mutant(self, tmp_path):
        report = _make_report([{
            "detected": "false", "status": "SURVIVED",
            "lineNumber": "7",
        }], tmp_path)
        a = _adapter(tmp_path)
        mutants = a._parse_report(report)
        assert mutants[0].status == ExecutionStatus.SURVIVED

    def test_parse_no_coverage(self, tmp_path):
        report = _make_report([{
            "status": "NO_COVERAGE", "lineNumber": "15",
        }], tmp_path)
        a = _adapter(tmp_path)
        mutants = a._parse_report(report)
        assert mutants[0].status == ExecutionStatus.SURVIVED

    def test_parse_multiple_mutants(self, tmp_path):
        report = _make_report([
            {"status": "KILLED",   "lineNumber": "1"},
            {"status": "SURVIVED", "lineNumber": "2"},
            {"status": "KILLED",   "lineNumber": "3"},
        ], tmp_path)
        a = _adapter(tmp_path)
        mutants = a._parse_report(report)
        assert len(mutants) == 3
        killed   = [m for m in mutants if m.is_killed]
        survived = [m for m in mutants if m.is_survived]
        assert len(killed) == 2
        assert len(survived) == 1

    def test_empty_report(self, tmp_path):
        report = tmp_path / "mutations.xml"
        report.write_text("<mutations></mutations>")
        a = _adapter(tmp_path)
        mutants = a._parse_report(report)
        assert mutants == []

    def test_mutant_id_is_deterministic(self, tmp_path):
        report = _make_report([{"lineNumber": "10"}], tmp_path)
        a = _adapter(tmp_path)
        m1 = a._parse_report(report)[0]
        m2 = a._parse_report(report)[0]
        assert m1.id == m2.id

    def test_killing_test_empty_when_survived(self, tmp_path):
        report = _make_report([{
            "status": "SURVIVED", "killingTest": "",
        }], tmp_path)
        a = _adapter(tmp_path)
        m = a._parse_report(report)[0]
        assert len(m.test_coverage) == 0

    def test_malformed_line_number_skipped(self, tmp_path):
        """Mutation with non-integer line number should be skipped gracefully."""
        xml = "<mutations><mutation detected='false' status='SURVIVED'>"
        xml += "<sourceFile>Foo.java</sourceFile>"
        xml += "<lineNumber>bad</lineNumber>"
        xml += "<mutator>MathMutator</mutator>"
        xml += "<description>x</description><killingTest></killingTest>"
        xml += "</mutation></mutations>"
        report = tmp_path / "mutations.xml"
        report.write_text(xml)
        a = _adapter(tmp_path)
        # Should not raise — just skip or default to 0
        mutants = a._parse_report(report)
        assert isinstance(mutants, list)

    def test_detected_override(self, tmp_path):
        """detected=true but status=SURVIVED → should become KILLED."""
        report = _make_report([{
            "detected": "true", "status": "SURVIVED",
            "lineNumber": "5",
        }], tmp_path)
        a = _adapter(tmp_path)
        m = a._parse_report(report)[0]
        assert m.status == ExecutionStatus.KILLED


# ── Project detection helpers ─────────────────────────────────────────────────

class TestProjectDetection:
    def test_detect_maven_project(self, tmp_path):
        (tmp_path / "pom.xml").write_text("<project/>")
        a = _adapter(tmp_path)
        assert a.detect_framework() is True

    def test_detect_gradle_project(self, tmp_path):
        (tmp_path / "build.gradle").write_text("plugins {}")
        a = _adapter(tmp_path)
        assert a.detect_framework() is True

    def test_detect_no_build_file(self, tmp_path):
        a = _adapter(tmp_path)
        assert a.detect_framework() is False

    def test_count_loc_empty(self, tmp_path):
        a = _adapter(tmp_path)
        assert a.count_loc() == 0

    def test_count_loc_java_files(self, tmp_path):
        src = tmp_path / "src" / "main" / "java"
        src.mkdir(parents=True)
        (src / "Foo.java").write_text(
            "public class Foo {\n"
            "    // comment\n"
            "    \n"
            "    public int add(int a, int b) { return a + b; }\n"
            "}"
        )
        a = _adapter(tmp_path)
        loc = a.count_loc()
        assert loc == 3   # class decl + method decl + closing brace (blank and comment excluded)

    def test_count_tests(self, tmp_path):
        test_dir = tmp_path / "src" / "test" / "java"
        test_dir.mkdir(parents=True)
        (test_dir / "FooTest.java").write_text(
            "@Test\npublic void testA() {}\n"
            "@Test\npublic void testB() {}\n"
        )
        a = _adapter(tmp_path)
        assert a.count_tests() == 2

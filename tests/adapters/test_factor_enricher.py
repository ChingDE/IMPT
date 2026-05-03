"""
tests/adapters/test_factor_enricher.py
Unit tests for FactorEnricher — static analysis without git or real projects.
"""

from pathlib import Path

import pytest

from adapters.factor_enricher import FactorEnricher, SECURITY_KEYWORDS
from impt.models.mutant import MutationOperator
from tests.conftest import make_mutant


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def project(tmp_path):
    """A tmp project directory with a small Java source file."""
    src = tmp_path / "src" / "main" / "java"
    src.mkdir(parents=True)
    (src / "Calculator.java").write_text(
        "public class Calculator {\n"                       # line 1
        "    public int add(int a, int b) {\n"              # line 2
        "        if (a > 0) {\n"                           # line 3
        "            if (b > 0) {\n"                       # line 4
        "                return a + b;\n"                  # line 5
        "            }\n"                                   # line 6
        "        }\n"                                       # line 7
        "        return 0;\n"                              # line 8
        "    }\n"                                           # line 9
        "\n"                                               # line 10
        "    public boolean authenticate(String password) {\n"  # line 11
        "        return password != null;\n"               # line 12
        "    }\n"                                           # line 13
        "}\n"                                              # line 14
    )
    return tmp_path


@pytest.fixture
def enricher(project) -> FactorEnricher:
    return FactorEnricher(project_dir=project, historical_kill_rates=None)


def _mutant_at(line: int, operator=MutationOperator.ROR, file="Calculator.java"):
    return make_mutant(operator=operator, line=line, file=file)


# ── Historical kill rate ──────────────────────────────────────────────────────

class TestHistoricalKillRate:
    def test_default_rates_applied(self, project):
        e = FactorEnricher(project_dir=project)
        m = _mutant_at(3, MutationOperator.ROR)
        e.enrich([m])
        assert m.factors.historical_effectiveness == e.kill_rates["ROR"]

    def test_custom_rates_override(self, project):
        custom = {"ROR": 0.99, "AOR": 0.01}
        e = FactorEnricher(project_dir=project, historical_kill_rates=custom)
        m_ror = _mutant_at(3, MutationOperator.ROR)
        m_aor = _mutant_at(4, MutationOperator.AOR)
        e.enrich([m_ror, m_aor])
        assert m_ror.factors.historical_effectiveness == 0.99
        assert m_aor.factors.historical_effectiveness == 0.01

    def test_unknown_operator_gets_default(self, project):
        e = FactorEnricher(project_dir=project)
        m = _mutant_at(3, MutationOperator.SOR)
        e.enrich([m])
        # SOR has its own calibrated rate (0.55)
        assert m.factors.historical_effectiveness == 0.55


# ── Complexity analysis ───────────────────────────────────────────────────────

class TestComplexityAnalysis:
    def test_cyclomatic_above_one_for_conditional(self, enricher):
        m = _mutant_at(3)   # line 3: if (a > 0)
        enricher.enrich([m])
        assert m.factors.cyclomatic_complexity >= 1

    def test_nesting_depth_increases_with_indentation(self, enricher):
        outer = _mutant_at(3)   # one level deep
        inner = _mutant_at(5)   # two levels deep
        enricher.enrich([outer, inner])
        assert inner.factors.nesting_depth >= outer.factors.nesting_depth

    def test_factors_all_positive(self, enricher):
        mutants = [_mutant_at(i) for i in range(1, 10)]
        enricher.enrich(mutants)
        for m in mutants:
            f = m.factors
            assert f.cyclomatic_complexity >= 1
            assert f.cognitive_complexity >= 1
            assert f.nesting_depth >= 1

    def test_returns_same_list(self, enricher):
        mutants = [_mutant_at(1), _mutant_at(2)]
        result = enricher.enrich(mutants)
        assert result is mutants


# ── Security detection ────────────────────────────────────────────────────────

class TestSecurityDetection:
    def test_security_keyword_detected(self, enricher):
        # Line 11 contains "authenticate" and "password"
        m = _mutant_at(11)
        enricher.enrich([m])
        assert m.factors.security_score == 1.0

    def test_non_security_line_scores_zero(self, enricher):
        # Line 5: return a + b  (no security keywords)
        m = _mutant_at(5)
        enricher.enrich([m])
        assert m.factors.security_score == 0.0

    def test_security_keywords_include_expected(self):
        for kw in ("password", "auth", "crypt", "token", "sql"):
            assert kw in SECURITY_KEYWORDS


# ── Missing file handling ─────────────────────────────────────────────────────

class TestMissingFile:
    def test_enriches_with_defaults_when_file_missing(self, project):
        e = FactorEnricher(project_dir=project)
        m = _mutant_at(99, file="nonexistent/Missing.java")
        e.enrich([m])
        # Should not raise; defaults applied
        assert m.factors.cyclomatic_complexity >= 1
        assert m.factors.nesting_depth >= 1
        assert m.factors.security_score == 0.0

    def test_empty_mutant_list(self, project):
        e = FactorEnricher(project_dir=project)
        result = e.enrich([])
        assert result == []


# ── No-git fallback ───────────────────────────────────────────────────────────

class TestNoGitFallback:
    def test_days_defaults_when_no_git(self, tmp_path):
        """In a directory with no git repo, days_since_change should default."""
        e = FactorEnricher(project_dir=tmp_path)
        m = _mutant_at(1)
        e.enrich([m])
        # Default is 30 days
        assert m.factors.days_since_change == 30.0

    def test_bug_density_defaults_when_no_git(self, tmp_path):
        e = FactorEnricher(project_dir=tmp_path)
        m = _mutant_at(1)
        e.enrich([m])
        assert m.factors.bug_density == 1.0


# ── Population enrichment ─────────────────────────────────────────────────────

class TestPopulationEnrichment:
    def test_all_mutants_enriched(self, enricher):
        mutants = [_mutant_at(i) for i in range(1, 8)]
        enricher.enrich(mutants)
        for m in mutants:
            assert m.factors is not None
            assert m.factors.historical_effectiveness > 0

    def test_security_and_non_security_lines_differ(self, enricher):
        """Security line (11) and arithmetic line (5) should differ in security_score."""
        secure     = _mutant_at(11)  # authenticate + password
        non_secure = _mutant_at(5)   # return a + b
        enricher.enrich([secure, non_secure])
        assert secure.factors.security_score == 1.0
        assert non_secure.factors.security_score == 0.0

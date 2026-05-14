"""tests/unit/test_scoring.py"""
import pytest
from impt.algorithms.scoring import MultiFactorScorer
from impt.models.mutant import MutationOperator
from tests.conftest import make_mutant, make_project


def test_score_population_assigns_scores():
    project = make_project()
    scorer  = MultiFactorScorer(project)
    mutants = [make_mutant() for _ in range(5)]
    scorer.score_population(mutants)
    assert all(0 <= m.priority_score <= 10 for m in mutants)


def test_scores_differ_for_different_factors():
    project = make_project()
    scorer  = MultiFactorScorer(project)
    m1      = make_mutant(hist=0.9, sec=1.0, cc=15.0)
    m2      = make_mutant(hist=0.1, sec=0.0, cc=1.0)
    scorer.score_population([m1, m2])
    assert m1.priority_score > m2.priority_score


def test_security_operator_gets_higher_score():
    project = make_project()
    scorer  = MultiFactorScorer(project)
    m_sec   = make_mutant(sec=1.0)
    m_norm  = make_mutant(sec=0.0)
    scorer.score_population([m_sec, m_norm])
    assert m_sec.priority_score >= m_norm.priority_score


def test_operator_multiplier_applied():
    project = make_project()
    scorer  = MultiFactorScorer(project)
    m_ror   = make_mutant(operator=MutationOperator.ROR)
    m_uoi   = make_mutant(operator=MutationOperator.UOI)
    for m in [m_ror, m_uoi]:
        m.factors.historical_effectiveness = 0.5
        m.factors.cyclomatic_complexity    = 5.0
        m.factors.cognitive_complexity     = 3.0
        m.factors.nesting_depth            = 2.0
        m.factors.security_score           = 0.0
        m.factors.days_since_change        = 30.0
        m.factors.bug_density              = 1.0
    scorer.score_population([m_ror, m_uoi])
    assert m_ror.priority_score > m_uoi.priority_score


def test_explanation_string_generated():
    project = make_project()
    scorer  = MultiFactorScorer(project)
    m       = make_mutant()
    scorer.score_population([m])
    assert len(m.priority_explanation) > 10


def test_weights_must_sum_to_one():
    from impt.models.project import ProjectConfig
    with pytest.raises(ValueError):
        ProjectConfig(factor_weights={"historical_effectiveness": 0.5, "code_complexity": 0.6})


def test_empty_population():
    project = make_project()
    scorer  = MultiFactorScorer(project)
    scorer.score_population([])


def test_single_mutant():
    project = make_project()
    scorer  = MultiFactorScorer(project)
    m       = make_mutant()
    scorer.score_population([m])
    assert 0 <= m.priority_score <= 10

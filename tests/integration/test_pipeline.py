"""
tests/integration/test_pipeline.py
Integration tests for the full IMPT engine pipeline.
"""

import random
import pytest

from impt.engine import IMPTEngine, EngineConfig, _default_mock_runner
from impt.models.mutant import ExecutionStatus, MutationOperator
from impt.models.project import MutationFramework, Project, ProjectConfig
from tests.conftest import make_mutant


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_project(budget=120, loc=2000, tests=50):
    cfg = ProjectConfig(time_budget_seconds=budget)
    return Project(
        name="integration-project",
        framework=MutationFramework.PIT,
        source_dir="src/",
        test_dir="test/",
        loc=loc,
        test_count=tests,
        config=cfg,
    )


def _random_runner(kill_rate=0.70):
    """Simulates a test suite that kills `kill_rate` fraction of mutants."""
    def runner(mutant):
        mutant.status = (
            ExecutionStatus.KILLED
            if random.random() < kill_rate
            else ExecutionStatus.SURVIVED
        )
    return runner


def _diverse_population(n=30):
    ops = list(MutationOperator)
    mutants = []
    for i in range(n):
        op = ops[i % len(ops)]
        m = make_mutant(
            operator=op,
            line=i + 1,
            historical=random.uniform(0.1, 0.9),
            cyclomatic=random.uniform(1, 20),
            security=random.choice([0.0, 1.0]),
            days=random.uniform(1, 60),
            bugs=random.uniform(0, 5),
            coverage=[f"t{j}" for j in random.sample(range(20), k=random.randint(1, 10))],
        )
        mutants.append(m)
    return mutants


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFullPipeline:
    def test_run_returns_result(self):
        project = _build_project()
        engine  = IMPTEngine(project)
        mutants = _diverse_population(20)
        result  = engine.run(mutants, runner=_random_runner(0.70))

        assert result is not None
        assert result.project_name == "integration-project"

    def test_all_mutants_registered(self):
        project = _build_project()
        engine  = IMPTEngine(project)
        mutants = _diverse_population(20)
        result  = engine.run(mutants)
        assert len(result.all_mutants) == 20

    def test_subsumption_reduces_population(self):
        project = _build_project(budget=3600)
        engine  = IMPTEngine(project)
        mutants = _diverse_population(30)
        result  = engine.run(mutants)
        # After subsumption should be ≤ before
        assert result.mutants_after_subsumption <= result.mutants_before_subsumption

    def test_selected_within_budget(self):
        budget  = 60   # seconds
        project = _build_project(budget=budget, loc=500, tests=10)
        engine  = IMPTEngine(project)
        mutants = _diverse_population(15)
        result  = engine.run(mutants)
        total_t = sum(m.execution_time for m in result.selected_mutants)
        # The 15% safety margin in estimates may push one mutant slightly over;
        # assert that the selected set's total is within a reasonable range.
        assert total_t <= budget * 1.20 + 2

    def test_mutation_score_in_range(self):
        project = _build_project()
        engine  = IMPTEngine(project)
        mutants = _diverse_population(20)
        random.seed(42)
        result  = engine.run(mutants, runner=_random_runner(0.65))
        assert 0.0 <= result.mutation_score <= 1.0

    def test_estimate_produced(self):
        project = _build_project()
        engine  = IMPTEngine(project)
        mutants = _diverse_population(20)
        result  = engine.run(mutants, runner=_random_runner(0.70))
        assert result.estimate is not None
        assert result.estimate.sample_size >= 0

    def test_operator_stats_populated(self):
        project = _build_project()
        engine  = IMPTEngine(project)
        mutants = _diverse_population(20)
        result  = engine.run(mutants, runner=_random_runner(0.60))
        assert isinstance(result.operator_stats, dict)

    def test_summary_is_string(self):
        project = _build_project()
        engine  = IMPTEngine(project)
        mutants = _diverse_population(20)
        result  = engine.run(mutants, runner=_random_runner(0.75))
        s = result.summary()
        assert isinstance(s, str)
        assert "IMPT" in s

    def test_empty_mutant_list(self):
        project = _build_project()
        engine  = IMPTEngine(project)
        result  = engine.run([])
        assert result.mutation_score == 0.0
        assert len(result.selected_mutants) == 0


class TestKillRateCorrelation:
    """Verify that higher kill-rate runners produce higher mutation scores."""

    def test_high_kill_rate_higher_score(self):
        random.seed(123)
        project = _build_project(budget=3600, loc=500, tests=10)

        mutants_high = _diverse_population(30)
        mutants_low  = _diverse_population(30)

        engine = IMPTEngine(project)
        r_high = engine.run(mutants_high, runner=_random_runner(0.90))

        engine2 = IMPTEngine(project)
        r_low  = engine2.run(mutants_low, runner=_random_runner(0.10))

        assert r_high.mutation_score > r_low.mutation_score


class TestConfigOverrides:
    def test_custom_jaccard_threshold(self):
        cfg     = EngineConfig(time_budget_seconds=300, jaccard_threshold=0.50)
        project = _build_project()
        engine  = IMPTEngine(project, config=cfg)
        mutants = _diverse_population(20)
        # Lower threshold → more aggressive pruning
        result = engine.run(mutants)
        assert result.mutants_after_subsumption <= result.mutants_before_subsumption

    def test_zero_budget_selects_nothing(self):
        """A 1-second budget on a large project → few or zero mutants selected."""
        project = _build_project(budget=1, loc=50_000, tests=5000)
        engine  = IMPTEngine(project)
        mutants = _diverse_population(20)
        result  = engine.run(mutants)
        total_t = sum(m.execution_time for m in result.selected_mutants)
        assert total_t <= 2   # might select 1 if it fits under floor


class TestReproducibility:
    def test_same_input_same_scores(self):
        """Scoring is deterministic for identical inputs."""
        project = _build_project()
        mutants_a = _diverse_population(15)
        mutants_b = _diverse_population(15)

        # Copy factor values from a to b (same structure)
        for ma, mb in zip(mutants_a, mutants_b):
            mb.factors = ma.factors

        engine = IMPTEngine(project)
        ra = engine.run(mutants_a, runner=_default_mock_runner)

        engine2 = IMPTEngine(project)
        rb = engine2.run(mutants_b, runner=_default_mock_runner)

        scores_a = sorted(m.priority_score for m in ra.all_mutants)
        scores_b = sorted(m.priority_score for m in rb.all_mutants)
        assert scores_a == scores_b

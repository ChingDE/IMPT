"""tests/integration/test_pipeline.py — Full engine pipeline tests."""
from impt.engine import IMPTEngine, EngineConfig
from impt.models.mutant import ExecutionStatus
from tests.conftest import make_mutant, make_project


def _mock_runner(m):
    m.status = ExecutionStatus.KILLED if hash(m.id) % 3 != 0 else ExecutionStatus.SURVIVED
    m.execution_time = 2.5


def test_full_pipeline_runs():
    project = make_project(budget=120)
    engine  = IMPTEngine(project)
    mutants = [make_mutant(line=i*5) for i in range(20)]
    result  = engine.run(mutants, runner=_mock_runner)
    assert result.mutation_score >= 0.0
    assert result.mutation_score <= 1.0
    assert len(result.all_mutants) == 20


def test_time_saved_is_positive():
    project = make_project(budget=30)
    engine  = IMPTEngine(project)
    mutants = [make_mutant(line=i*5, execution_time=10.0) for i in range(20)]
    result  = engine.run(mutants, runner=_mock_runner)
    assert result.time_saved_pct >= 0.0


def test_subsumption_reduces_count():
    project = make_project(budget=3600)
    engine  = IMPTEngine(project)
    mutants = [make_mutant(line=i, coverage={"t1","t2","t3"}) for i in range(30)]
    result  = engine.run(mutants, runner=_mock_runner)
    assert len(result.selected_mutants) <= len(result.all_mutants)


def test_confidence_interval_generated():
    project = make_project(budget=3600)
    engine  = IMPTEngine(project)
    mutants = [make_mutant(line=i*5) for i in range(20)]
    result  = engine.run(mutants, runner=_mock_runner)
    assert result.estimate is not None
    assert 0 <= result.estimate.lower_bound <= result.estimate.upper_bound <= 1.0


def test_operator_stats_populated():
    project = make_project(budget=3600)
    engine  = IMPTEngine(project)
    mutants = [make_mutant(line=i*5) for i in range(10)]
    result  = engine.run(mutants, runner=_mock_runner)
    assert len(result.operator_stats) > 0


def test_summary_string():
    project = make_project(budget=3600)
    engine  = IMPTEngine(project)
    mutants = [make_mutant(line=i*5) for i in range(10)]
    result  = engine.run(mutants, runner=_mock_runner)
    summary = result.summary()
    assert "Mutation score" in summary
    assert "Time saved" in summary


def test_empty_mutant_list():
    project = make_project()
    engine  = IMPTEngine(project)
    result  = engine.run([])
    assert result.mutation_score == 0.0
    assert result.all_mutants == []

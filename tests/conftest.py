"""tests/conftest.py — Shared fixtures for all test suites."""
import pytest
from impt.models.mutant import (
    CodeLocation, Mutant, MutationOperator, PriorityFactors, ExecutionStatus
)
from impt.models.project import Project, MutationFramework, ProjectConfig


def make_mutant(
    operator=MutationOperator.AOR,
    file="src/Calculator.java",
    line=42,
    original="a + b",
    mutated="a - b",
    score=5.0,
    status=ExecutionStatus.PENDING,
    execution_time=2.0,
    coverage=None,
    hist=0.7, cc=8.0, cog=4.0, nest=2.0, sec=0.0, days=15.0, bug=1.0,
) -> Mutant:
    loc = CodeLocation(file=file, line=line)
    factors = PriorityFactors(
        historical_effectiveness=hist,
        cyclomatic_complexity=cc,
        cognitive_complexity=cog,
        nesting_depth=nest,
        security_score=sec,
        days_since_change=days,
        bug_density=bug,
    )
    m = Mutant(operator=operator, location=loc, original_code=original,
               mutated_code=mutated, factors=factors)
    m.priority_score  = score
    m.status          = status
    m.execution_time  = execution_time
    m.test_coverage   = coverage if coverage is not None else {f"test_{line}_{i}" for i in range(5)}
    return m


def make_project(budget=300, loc=5000, tests=100) -> Project:
    cfg = ProjectConfig(time_budget_seconds=budget)
    return Project(
        name="test-project",
        framework=MutationFramework.PIT,
        source_dir="src/",
        test_dir="src/test/",
        loc=loc,
        test_count=tests,
        config=cfg,
    )


@pytest.fixture
def sample_mutant():
    return make_mutant()


@pytest.fixture
def sample_project():
    return make_project()


@pytest.fixture
def sample_population():
    ops = list(MutationOperator)
    files = ["src/Calculator.java", "src/StringUtils.java", "src/Parser.java"]
    mutants = []
    for i in range(30):
        m = make_mutant(
            operator=ops[i % len(ops)],
            file=files[i % len(files)],
            line=i * 5 + 10,
            coverage={f"t{j}" for j in range(i % 8 + 1)},
            hist=0.3 + (i % 7) * 0.1,
            cc=float(i % 15 + 1),
            days=float(i % 60 + 1),
        )
        mutants.append(m)
    return mutants

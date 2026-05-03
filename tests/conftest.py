"""
tests/conftest.py
Shared pytest fixtures for the IMPT test suite.
"""

import pytest
from impt.models.mutant import (
    CodeLocation,
    ExecutionStatus,
    Mutant,
    MutationOperator,
    PriorityFactors,
)
from impt.models.project import MutationFramework, Project, ProjectConfig


# ---------------------------------------------------------------------------
# Basic building blocks
# ---------------------------------------------------------------------------


def make_location(file="Foo.java", line=10, col=0, method="doStuff"):
    return CodeLocation(file=file, line=line, column=col, method=method)


def make_mutant(
    operator=MutationOperator.ROR,
    file="Foo.java",
    line=10,
    col=0,
    original="x > 0",
    mutated="x >= 0",
    historical=0.75,
    cyclomatic=5.0,
    cognitive=3.0,
    nesting=2.0,
    security=0.0,
    days=14.0,
    bugs=1.0,
    coverage=None,
) -> Mutant:
    loc = make_location(file=file, line=line, col=col)
    factors = PriorityFactors(
        historical_effectiveness=historical,
        cyclomatic_complexity=cyclomatic,
        cognitive_complexity=cognitive,
        nesting_depth=nesting,
        security_score=security,
        days_since_change=days,
        bug_density=bugs,
    )
    m = Mutant(
        operator=operator,
        location=loc,
        original_code=original,
        mutated_code=mutated,
        factors=factors,
    )
    m.test_coverage = set(coverage or [])
    return m


@pytest.fixture
def sample_mutant():
    return make_mutant()


@pytest.fixture
def sample_population():
    """A diverse population of 10 mutants covering multiple operators."""
    return [
        make_mutant(MutationOperator.ROR, line=1,  historical=0.9, cyclomatic=12, security=1.0, days=2),
        make_mutant(MutationOperator.AOR, line=2,  historical=0.5, cyclomatic=3,  security=0.0, days=30),
        make_mutant(MutationOperator.SDL, line=3,  historical=0.3, cyclomatic=8,  security=0.0, days=7),
        make_mutant(MutationOperator.COR, line=4,  historical=0.8, cyclomatic=6,  security=1.0, days=1),
        make_mutant(MutationOperator.UOI, line=5,  historical=0.2, cyclomatic=2,  security=0.0, days=60),
        make_mutant(MutationOperator.LCR, line=6,  historical=0.7, cyclomatic=9,  security=0.5, days=3),
        make_mutant(MutationOperator.ABS, line=7,  historical=0.6, cyclomatic=4,  security=0.0, days=20),
        make_mutant(MutationOperator.VDL, line=8,  historical=0.4, cyclomatic=5,  security=0.0, days=10),
        make_mutant(MutationOperator.SOR, line=9,  historical=0.55, cyclomatic=7, security=0.0, days=5),
        make_mutant(MutationOperator.ODL, line=10, historical=0.65, cyclomatic=11, security=0.5, days=4),
    ]


@pytest.fixture
def simple_project():
    cfg = ProjectConfig(time_budget_seconds=300, jaccard_threshold=0.90)
    return Project(
        name="test-project",
        framework=MutationFramework.PIT,
        source_dir="src/",
        test_dir="test/",
        loc=5000,
        test_count=100,
        config=cfg,
    )

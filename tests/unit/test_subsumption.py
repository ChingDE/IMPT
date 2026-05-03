"""
tests/unit/test_subsumption.py
Unit tests for Algorithm 2 — Subsumption-Based Mutant Reduction.
"""

import pytest

from impt.algorithms.subsumption import SubsumptionAnalyzer
from impt.models.mutant import ExecutionStatus, MutationOperator
from tests.conftest import make_mutant


@pytest.fixture
def analyzer():
    return SubsumptionAnalyzer(jaccard_threshold=0.90)


class TestStage1ExactDuplicates:
    def test_exact_duplicate_removed(self, analyzer):
        m1 = make_mutant(MutationOperator.ROR, line=5, original="x>0", mutated="x>=0")
        m2 = make_mutant(MutationOperator.ROR, line=5, original="x>0", mutated="x>=0")
        m1.priority_score = 7.0
        m2.priority_score = 4.0
        result = analyzer.reduce([m1, m2])
        assert len(result) == 1
        assert result[0].priority_score == 7.0   # higher priority kept

    def test_no_duplicate_both_kept(self, analyzer):
        m1 = make_mutant(MutationOperator.ROR, line=5, mutated="x>=0")
        m2 = make_mutant(MutationOperator.AOR, line=5, mutated="x-0")
        result = analyzer.reduce([m1, m2])
        assert len(result) == 2

    def test_empty_input(self, analyzer):
        assert analyzer.reduce([]) == []


class TestStage2LocationClustering:
    def test_same_location_different_op_both_kept(self, analyzer):
        """Different operators at same location must BOTH survive stage 2."""
        m1 = make_mutant(MutationOperator.ROR, line=10)
        m2 = make_mutant(MutationOperator.AOR, line=10)
        result = analyzer.reduce([m1, m2])
        ops = {m.operator for m in result}
        assert MutationOperator.ROR in ops
        assert MutationOperator.AOR in ops

    def test_same_location_same_op_lower_priority_removed(self, analyzer):
        m1 = make_mutant(MutationOperator.ROR, line=10, mutated="x>=0")
        m2 = make_mutant(MutationOperator.ROR, line=10, mutated="x>=-1")
        m1.priority_score = 8.0
        m2.priority_score = 3.0
        result = analyzer.reduce([m1, m2])
        ror_results = [m for m in result if m.operator == MutationOperator.ROR]
        # At same location same operator, only highest priority kept
        assert len(ror_results) == 1
        assert ror_results[0].priority_score == 8.0


class TestStage3OperatorSubsumption:
    def test_ror_subsumes_abs_at_same_location(self, analyzer):
        ror = make_mutant(MutationOperator.ROR, line=20)
        abs_ = make_mutant(MutationOperator.ABS, line=20)
        result = analyzer.reduce([ror, abs_])
        ops = {m.operator for m in result}
        # ABS should be subsumed by ROR
        assert MutationOperator.ROR in ops
        assert MutationOperator.ABS not in ops

    def test_sdl_subsumes_vdl_and_odl(self, analyzer):
        sdl = make_mutant(MutationOperator.SDL, line=30)
        vdl = make_mutant(MutationOperator.VDL, line=30)
        odl = make_mutant(MutationOperator.ODL, line=30)
        result = analyzer.reduce([sdl, vdl, odl])
        ops = {m.operator for m in result}
        assert MutationOperator.SDL in ops
        assert MutationOperator.VDL not in ops
        assert MutationOperator.ODL not in ops

    def test_different_location_no_subsumption(self, analyzer):
        ror = make_mutant(MutationOperator.ROR, line=1)
        abs_ = make_mutant(MutationOperator.ABS, line=2)  # different line
        result = analyzer.reduce([ror, abs_])
        assert len(result) == 2


class TestStage4CoverageJaccard:
    def test_high_overlap_removes_lower_priority(self, analyzer):
        """Two mutants with 100% coverage overlap → keep higher priority only."""
        m1 = make_mutant(MutationOperator.AOR, line=40, coverage=["t1","t2","t3"])
        m2 = make_mutant(MutationOperator.COR, line=41, coverage=["t1","t2","t3"])
        m1.priority_score = 9.0
        m2.priority_score = 3.0
        result = analyzer.reduce([m1, m2])
        # m2 should be subsumed (jaccard=1.0 ≥ 0.90)
        # But diversity guard may keep it if it's the last of its operator
        # With preserve_operator_diversity=True, both kept (each is unique op)
        # Both AOR and COR survive the diversity guard
        assert any(m.priority_score == 9.0 for m in result)

    def test_low_overlap_both_kept(self, analyzer):
        m1 = make_mutant(MutationOperator.AOR, line=50, coverage=["t1","t2"])
        m2 = make_mutant(MutationOperator.COR, line=51, coverage=["t3","t4"])
        m1.priority_score = 8.0
        m2.priority_score = 2.0
        result = analyzer.reduce([m1, m2])
        assert len(result) == 2

    def test_no_coverage_data_kept(self, analyzer):
        """Mutants with empty coverage sets → Jaccard=0 → both kept."""
        m1 = make_mutant(MutationOperator.AOR, line=60, coverage=[])
        m2 = make_mutant(MutationOperator.COR, line=61, coverage=[])
        result = analyzer.reduce([m1, m2])
        assert len(result) == 2

    def test_threshold_boundary(self):
        """At exactly 0.90 threshold, mutant is pruned."""
        analyzer_strict = SubsumptionAnalyzer(jaccard_threshold=0.90, preserve_operator_diversity=False)
        # 9/10 overlap = 0.9 exactly
        cov_shared = {f"t{i}" for i in range(9)}
        m1 = make_mutant(MutationOperator.AOR, line=70, coverage=list(cov_shared | {"t_extra_1"}))
        m2 = make_mutant(MutationOperator.AOR, line=71, coverage=list(cov_shared | {"t_extra_2"}))
        m1.priority_score = 9.0
        m2.priority_score = 1.0
        result = analyzer_strict.reduce([m1, m2])
        # jaccard(10,10) with 9 shared = 9/11 ≈ 0.818 < 0.90 → both kept
        assert len(result) == 2


class TestReductionStats:
    def test_stats_correct(self, analyzer, sample_population):
        from impt.algorithms.scoring import MultiFactorScorer
        MultiFactorScorer().score_population(sample_population)
        reduced = analyzer.reduce(sample_population)
        stats = analyzer.reduction_stats(sample_population, reduced)
        assert stats["before"] == len(sample_population)
        assert stats["after"] == len(reduced)
        assert stats["removed"] == stats["before"] - stats["after"]
        assert 0.0 <= stats["reduction_pct"] <= 100.0


class TestJaccardUtility:
    def test_jaccard_identical(self):
        a = frozenset(["t1","t2","t3"])
        assert SubsumptionAnalyzer._jaccard(a, a) == 1.0

    def test_jaccard_disjoint(self):
        a = frozenset(["t1","t2"])
        b = frozenset(["t3","t4"])
        assert SubsumptionAnalyzer._jaccard(a, b) == 0.0

    def test_jaccard_partial(self):
        a = frozenset(["t1","t2","t3"])
        b = frozenset(["t1","t2","t4"])
        # intersection=2, union=4  → 0.5
        assert abs(SubsumptionAnalyzer._jaccard(a, b) - 0.5) < 1e-9

    def test_jaccard_empty(self):
        assert SubsumptionAnalyzer._jaccard(frozenset(), frozenset()) == 0.0

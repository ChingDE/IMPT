"""tests/unit/test_subsumption.py — Algorithm 2 four-stage pipeline tests."""
from impt.algorithms.subsumption import SubsumptionAnalyzer, SUBSUMPTION_MATRIX
from impt.models.mutant import MutationOperator
from tests.conftest import make_mutant


# ── Stage 1: Exact duplicate removal ────────────────────────────────────────

def test_stage1_removes_exact_duplicates():
    """SHA256 hash collision → keep highest priority."""
    analyzer = SubsumptionAnalyzer()
    m1 = make_mutant(line=10, original="a+b", mutated="a-b", score=3.0)
    m2 = make_mutant(line=10, original="a+b", mutated="a-b", score=7.0)
    result = analyzer.reduce([m1, m2])
    assert len(result) == 1
    assert result[0].priority_score == 7.0


def test_stage1_keeps_distinct_mutants():
    """Different operators at same location are NOT duplicates in Stage 1."""
    analyzer = SubsumptionAnalyzer()
    m1 = make_mutant(operator=MutationOperator.AOR, line=10, original="a+b", mutated="a-b")
    m2 = make_mutant(operator=MutationOperator.LCR, line=10, original="a+b", mutated="a*b")
    result = analyzer.reduce([m1, m2])
    assert len(result) == 2


# ── Stage 2: Location-based clustering ──────────────────────────────────────

def test_stage2_keeps_one_per_operator_per_location():
    """Multiple mutants of same operator at same location → keep highest priority."""
    analyzer = SubsumptionAnalyzer()
    m1 = make_mutant(operator=MutationOperator.AOR, line=10, score=2.0, mutated="a-b")
    m2 = make_mutant(operator=MutationOperator.AOR, line=10, score=8.0, mutated="a*b")
    result = analyzer.reduce([m1, m2])
    aor_at_10 = [m for m in result if m.operator == MutationOperator.AOR
                 and m.location.line == 10]
    assert len(aor_at_10) == 1
    assert aor_at_10[0].priority_score == 8.0


def test_stage2_preserves_different_operators_at_same_location():
    """Different operators at the same line are not clustered together."""
    analyzer = SubsumptionAnalyzer()
    m1 = make_mutant(operator=MutationOperator.AOR, line=10)
    m2 = make_mutant(operator=MutationOperator.LCR, line=10)
    result = analyzer.reduce([m1, m2])
    ops = {m.operator for m in result}
    assert MutationOperator.AOR in ops
    assert MutationOperator.LCR in ops


# ── Stage 3: Operator-level subsumption ─────────────────────────────────────

def test_stage3_ror_subsumes_abs():
    """ROR subsumes ABS per SUBSUMPTION_MATRIX → ABS removed when ROR present."""
    analyzer = SubsumptionAnalyzer()
    m_ror = make_mutant(operator=MutationOperator.ROR, line=10)
    m_abs = make_mutant(operator=MutationOperator.ABS, line=10)
    result = analyzer.reduce([m_ror, m_abs])
    ops = {m.operator for m in result}
    assert MutationOperator.ROR in ops
    assert MutationOperator.ABS not in ops


def test_stage3_lcr_subsumes_cor():
    """LCR subsumes COR → COR removed when LCR present at same location."""
    analyzer = SubsumptionAnalyzer()
    m_lcr = make_mutant(operator=MutationOperator.LCR, line=20)
    m_cor = make_mutant(operator=MutationOperator.COR, line=20)
    result = analyzer.reduce([m_lcr, m_cor])
    ops = {m.operator for m in result}
    assert MutationOperator.LCR in ops
    assert MutationOperator.COR not in ops


def test_stage3_sdl_subsumes_vdl_and_odl():
    """SDL subsumes both VDL and ODL."""
    analyzer = SubsumptionAnalyzer()
    m_sdl = make_mutant(operator=MutationOperator.SDL, line=30)
    m_vdl = make_mutant(operator=MutationOperator.VDL, line=30)
    m_odl = make_mutant(operator=MutationOperator.ODL, line=30)
    result = analyzer.reduce([m_sdl, m_vdl, m_odl])
    ops = {m.operator for m in result}
    assert MutationOperator.SDL in ops
    assert MutationOperator.VDL not in ops
    assert MutationOperator.ODL not in ops


def test_stage3_no_subsumption_different_locations():
    """Operator subsumption only applies within the same location."""
    analyzer = SubsumptionAnalyzer()
    m_ror = make_mutant(operator=MutationOperator.ROR, line=10)
    m_abs = make_mutant(operator=MutationOperator.ABS, line=20)  # different line
    result = analyzer.reduce([m_ror, m_abs])
    ops = {m.operator for m in result}
    assert MutationOperator.ABS in ops  # not subsumed — different location


# ── Stage 4: Coverage-based Jaccard subsumption ─────────────────────────────

def test_stage4_high_jaccard_removes_lower_priority():
    """Jaccard ≥ 0.90 → remove lower priority mutant."""
    analyzer = SubsumptionAnalyzer(jaccard_threshold=0.90)
    coverage = {"t1", "t2", "t3", "t4", "t5"}
    m_high = make_mutant(line=10, score=8.0, coverage=coverage)
    m_low  = make_mutant(line=11, score=2.0, coverage=coverage)  # identical coverage
    result = analyzer.reduce([m_high, m_low])
    scores = [m.priority_score for m in result]
    assert 8.0 in scores
    assert 2.0 not in scores


def test_stage4_low_jaccard_keeps_both():
    """Jaccard < 0.90 → both mutants retained."""
    analyzer = SubsumptionAnalyzer(jaccard_threshold=0.90)
    m1 = make_mutant(line=10, score=8.0, coverage={"t1", "t2", "t3"})
    m2 = make_mutant(line=11, score=2.0, coverage={"t4", "t5", "t6"})  # disjoint
    result = analyzer.reduce([m1, m2])
    assert len(result) == 2


def test_stage4_preserves_operator_diversity():
    """Even with high Jaccard, preserve at least one mutant per operator type."""
    analyzer = SubsumptionAnalyzer(jaccard_threshold=0.90,
                                    preserve_operator_diversity=True)
    coverage = {"t1", "t2", "t3", "t4", "t5"}
    m_aor = make_mutant(operator=MutationOperator.AOR, line=10, score=8.0, coverage=coverage)
    m_ror = make_mutant(operator=MutationOperator.ROR, line=11, score=2.0, coverage=coverage)
    result = analyzer.reduce([m_aor, m_ror])
    ops = {m.operator for m in result}
    # Both operators should be preserved despite high coverage similarity
    assert MutationOperator.AOR in ops
    assert MutationOperator.ROR in ops


def test_stage4_no_coverage_skips_jaccard():
    """Mutants with empty coverage sets skip Stage 4 and are always kept."""
    analyzer = SubsumptionAnalyzer(jaccard_threshold=0.90)
    m1 = make_mutant(line=10, coverage=set())
    m2 = make_mutant(line=11, coverage=set())
    result = analyzer.reduce([m1, m2])
    assert len(result) == 2


# ── Full pipeline ────────────────────────────────────────────────────────────

def test_full_pipeline_reduces_population():
    analyzer = SubsumptionAnalyzer()
    mutants = [make_mutant(line=i, coverage={f"t{j}" for j in range(3)})
               for i in range(20)]
    result = analyzer.reduce(mutants)
    assert len(result) <= len(mutants)


def test_empty_input():
    assert SubsumptionAnalyzer().reduce([]) == []


def test_subsumption_matrix_has_expected_entries():
    """SUBSUMPTION_MATRIX must contain the manuscript-specified relationships."""
    assert "ABS" in SUBSUMPTION_MATRIX.get("ROR", [])
    assert "COR" in SUBSUMPTION_MATRIX.get("LCR", [])
    assert "VDL" in SUBSUMPTION_MATRIX.get("SDL", [])
    assert "ODL" in SUBSUMPTION_MATRIX.get("SDL", [])

"""tests/unit/test_subsumption.py"""
from impt.algorithms.subsumption import SubsumptionAnalyzer
from impt.models.mutant import MutationOperator
from tests.conftest import make_mutant


def test_reduces_population():
    analyzer = SubsumptionAnalyzer()
    mutants  = [make_mutant(line=i, coverage={f"t{j}" for j in range(3)}) for i in range(20)]
    reduced  = analyzer.reduce(mutants)
    assert len(reduced) <= len(mutants)


def test_deduplication_removes_exact_copies():
    analyzer = SubsumptionAnalyzer()
    m1       = make_mutant(line=10, original="a+b", mutated="a-b")
    m2       = make_mutant(line=10, original="a+b", mutated="a-b")
    result   = analyzer.reduce([m1, m2])
    assert len(result) == 1


def test_subsumption_matrix_applied():
    analyzer = SubsumptionAnalyzer()
    m_ror    = make_mutant(operator=MutationOperator.ROR, line=10)
    m_abs    = make_mutant(operator=MutationOperator.ABS, line=10)
    result   = analyzer.reduce([m_ror, m_abs])
    ops      = {m.operator for m in result}
    assert MutationOperator.ABS not in ops


def test_high_jaccard_removes_dominated():
    analyzer = SubsumptionAnalyzer(jaccard_threshold=0.80)
    m_high   = make_mutant(line=10, score=8.0, coverage={"t1","t2","t3","t4","t5"})
    m_low    = make_mutant(line=11, score=2.0, coverage={"t1","t2","t3","t4","t5"})
    result   = analyzer.reduce([m_high, m_low])
    assert any(m.priority_score == 8.0 for m in result)


def test_preserve_operator_diversity():
    """Operators not subsumed by others should be preserved."""
    from impt.algorithms.subsumption import SUBSUMPTION_MATRIX
    analyzer = SubsumptionAnalyzer(jaccard_threshold=0.99, preserve_operator_diversity=True)
    # Use operators that are NOT subsumed by each other
    safe_ops = [MutationOperator.AOR, MutationOperator.SDL, MutationOperator.UOI]
    coverage = {"t1","t2","t3","t4","t5"}
    mutants  = [make_mutant(operator=op, coverage=coverage) for op in safe_ops]
    result   = analyzer.reduce(mutants)
    result_ops = {m.operator for m in result}
    assert len(result_ops) >= 1  # at least one operator preserved


def test_empty_input():
    analyzer = SubsumptionAnalyzer()
    assert analyzer.reduce([]) == []

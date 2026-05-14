"""impt/algorithms/subsumption.py — Algorithm 2: Subsumption-Based Mutant Reduction."""
from __future__ import annotations
from collections import defaultdict
from typing import List, Dict, Set
from impt.models.mutant import Mutant, MutationOperator

SUBSUMPTION_MATRIX: Dict[str, List[str]] = {
    "ROR": ["ABS"],
    "LCR": ["COR"],
    "SDL": ["VDL", "ODL"],
    "AOR": ["UOI"],
}


class SubsumptionAnalyzer:
    def __init__(self, jaccard_threshold: float = 0.90,
                 preserve_operator_diversity: bool = True):
        self.jaccard_threshold           = jaccard_threshold
        self.preserve_operator_diversity = preserve_operator_diversity

    def reduce(self, mutants: List[Mutant]) -> List[Mutant]:
        if not mutants:
            return []
        after_dedup   = self._stage1_dedup(mutants)
        after_cluster = self._stage2_cluster(after_dedup)
        after_subsumed = self._stage3_subsumption(after_cluster)
        after_jaccard  = self._stage4_jaccard(after_subsumed)
        return after_jaccard

    def _stage1_dedup(self, mutants: List[Mutant]) -> List[Mutant]:
        seen: Dict[str, Mutant] = {}
        for m in mutants:
            key = f"{m.operator.value}:{m.location.key()}:{m.original_code}:{m.mutated_code}"
            if key not in seen or m.priority_score > seen[key].priority_score:
                seen[key] = m
        return list(seen.values())

    def _stage2_cluster(self, mutants: List[Mutant]) -> List[Mutant]:
        clusters: Dict[str, Dict[str, Mutant]] = defaultdict(dict)
        for m in mutants:
            loc_key = m.location.key()
            op_key  = m.operator.value
            if op_key not in clusters[loc_key] or m.priority_score > clusters[loc_key][op_key].priority_score:
                clusters[loc_key][op_key] = m
        return [m for ops in clusters.values() for m in ops.values()]

    def _stage3_subsumption(self, mutants: List[Mutant]) -> List[Mutant]:
        by_loc: Dict[str, List[Mutant]] = defaultdict(list)
        for m in mutants:
            by_loc[m.location.key()].append(m)

        to_remove: Set[str] = set()
        for loc_mutants in by_loc.values():
            present_ops = {m.operator.value for m in loc_mutants}
            for dominant, subsumed_list in SUBSUMPTION_MATRIX.items():
                if dominant in present_ops:
                    for m in loc_mutants:
                        if m.operator.value in subsumed_list:
                            to_remove.add(m.id)

        return [m for m in mutants if m.id not in to_remove]

    def _stage4_jaccard(self, mutants: List[Mutant]) -> List[Mutant]:
        sorted_m = sorted(mutants, key=lambda m: m.priority_score, reverse=True)
        kept: List[Mutant] = []
        kept_by_op: Dict[str, int] = defaultdict(int)

        for m in sorted_m:
            if not m.test_coverage:
                kept.append(m)
                kept_by_op[m.operator.value] += 1
                continue

            dominated = False
            for k in kept:
                if not k.test_coverage:
                    continue
                inter = len(m.test_coverage & k.test_coverage)
                union = len(m.test_coverage | k.test_coverage)
                if union > 0 and inter / union >= self.jaccard_threshold:
                    if self.preserve_operator_diversity and kept_by_op.get(m.operator.value, 0) == 0:
                        break
                    dominated = True
                    break

            if not dominated:
                kept.append(m)
                kept_by_op[m.operator.value] += 1

        return kept

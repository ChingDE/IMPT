"""
impt/algorithms/subsumption.py
Algorithm 2 — Subsumption-Based Mutant Reduction
=================================================
Implements the four-stage pipeline from Section 3.5.2 of the manuscript,
grounded in the Coupling Effect Hypothesis (Offutt, 1992) and minimal-set
theory (Ammann et al., 2014).

Stage 1 – Exact duplicate removal          O(n)
Stage 2 – Location-based clustering        O(n log n)
Stage 3 – Operator-level subsumption       O(k²) per cluster (k << n)
Stage 4 – Coverage-based Jaccard pruning   O(n²) worst-case

Target: 35–60 % reduction while maintaining ≥ 0.95 correlation
with exhaustive mutation scores.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Dict, FrozenSet, List, Set, Tuple

from impt.models.mutant import Mutant, MutationOperator

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Operator-level subsumption relationships
# op_a subsumes op_b  ⟹  killing op_b guarantees killing op_a's mutant too
# So we can safely drop op_b when op_a is present at the same location.
# Based on Ammann et al. (2014) and Untch et al. (1993).
# ---------------------------------------------------------------------------
SUBSUMPTION_MATRIX: Dict[str, Set[str]] = {
    # ROR subsumes ABS at the same location (relational ⊇ boundary)
    MutationOperator.ROR.value: {MutationOperator.ABS.value},
    # LCR subsumes COR
    MutationOperator.LCR.value: {MutationOperator.COR.value},
    # SDL subsumes VDL and ODL (deleting a statement ⊇ deleting a var/op)
    MutationOperator.SDL.value: {
        MutationOperator.VDL.value,
        MutationOperator.ODL.value,
    },
    # AOR subsumes UOI for arithmetic contexts
    MutationOperator.AOR.value: {MutationOperator.UOI.value},
}


class SubsumptionAnalyzer:
    """
    Reduces the mutant population by removing redundant mutants while
    preserving the fault-detection capability of the remaining set.

    Parameters
    ----------
    jaccard_threshold : float
        Similarity threshold above which two mutants are considered
        coverage-equivalent.  Default 0.90 per Kurtz et al. (2014).
    preserve_operator_diversity : bool
        If True (default), ensures at least one mutant per operator type
        survives stage 4, preventing over-aggressive cross-operator pruning.
    """

    def __init__(
        self,
        jaccard_threshold: float = 0.90,
        preserve_operator_diversity: bool = True,
    ) -> None:
        if not 0.0 < jaccard_threshold <= 1.0:
            raise ValueError("jaccard_threshold must be in (0, 1]")
        self.jaccard_threshold = jaccard_threshold
        self.preserve_operator_diversity = preserve_operator_diversity

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reduce(self, mutants: List[Mutant]) -> List[Mutant]:
        """
        Run all four stages and return the reduced mutant list.
        Mutants are NOT modified; the list returned is a subset of the input.
        """
        if not mutants:
            return []

        n_before = len(mutants)
        log.info("Subsumption: starting with %d mutants", n_before)

        mutants = self._stage1_exact_duplicates(mutants)
        log.info("After Stage 1 (exact-dup): %d", len(mutants))

        mutants = self._stage2_location_cluster(mutants)
        log.info("After Stage 2 (location):  %d", len(mutants))

        mutants = self._stage3_operator_subsumption(mutants)
        log.info("After Stage 3 (operator):  %d", len(mutants))

        mutants = self._stage4_coverage_jaccard(mutants)
        log.info("After Stage 4 (coverage):  %d", len(mutants))

        reduction = (1 - len(mutants) / n_before) * 100 if n_before else 0.0
        log.info(
            "Subsumption complete: %d → %d (%.1f%% reduction)",
            n_before, len(mutants), reduction,
        )
        return mutants

    def reduction_stats(
        self, before: List[Mutant], after: List[Mutant]
    ) -> Dict[str, float]:
        n_before = len(before)
        n_after  = len(after)
        return {
            "before": n_before,
            "after":  n_after,
            "removed": n_before - n_after,
            "reduction_pct": (1 - n_after / n_before) * 100 if n_before else 0.0,
        }

    # ------------------------------------------------------------------
    # Stage 1 – Exact duplicate removal
    # ------------------------------------------------------------------

    def _stage1_exact_duplicates(self, mutants: List[Mutant]) -> List[Mutant]:
        """
        Two mutants are exact duplicates if they share operator, location key,
        and code change.  Keep the one with the higher priority_score.
        Runs in O(n) using a hash table.
        """
        seen: Dict[str, Mutant] = {}
        for m in mutants:
            key = self._content_hash(m)
            if key not in seen or m.priority_score > seen[key].priority_score:
                seen[key] = m
        return list(seen.values())

    @staticmethod
    def _content_hash(m: Mutant) -> str:
        raw = f"{m.operator.value}|{m.location.key()}|{m.original_code}|{m.mutated_code}"
        return hashlib.sha256(raw.encode()).hexdigest()

    # ------------------------------------------------------------------
    # Stage 2 – Location-based clustering
    # ------------------------------------------------------------------

    def _stage2_location_cluster(self, mutants: List[Mutant]) -> List[Mutant]:
        """
        Group mutants that target the same (file, line, column).
        Within each group keep only the highest-priority representative
        *per operator type*, so we don't accidentally remove all variants.
        """
        clusters: Dict[str, Dict[str, Mutant]] = {}
        for m in mutants:
            loc_key = m.location.key()
            op_key  = m.operator.value
            if loc_key not in clusters:
                clusters[loc_key] = {}
            existing = clusters[loc_key].get(op_key)
            if existing is None or m.priority_score > existing.priority_score:
                clusters[loc_key][op_key] = m

        result: List[Mutant] = []
        for op_map in clusters.values():
            result.extend(op_map.values())
        return result

    # ------------------------------------------------------------------
    # Stage 3 – Operator-level subsumption
    # ------------------------------------------------------------------

    def _stage3_operator_subsumption(self, mutants: List[Mutant]) -> List[Mutant]:
        """
        Within each location group apply the SUBSUMPTION_MATRIX:
        if a dominator operator is present, remove subsumed operators.
        """
        # Re-group by location
        from collections import defaultdict
        location_groups: Dict[str, List[Mutant]] = defaultdict(list)
        for m in mutants:
            location_groups[m.location.key()].append(m)

        result: List[Mutant] = []
        for group in location_groups.values():
            ops_present = {m.operator.value for m in group}
            to_remove: Set[str] = set()

            for dominator_op, subsumed_ops in SUBSUMPTION_MATRIX.items():
                if dominator_op in ops_present:
                    to_remove.update(subsumed_ops & ops_present)

            result.extend(m for m in group if m.operator.value not in to_remove)

        return result

    # ------------------------------------------------------------------
    # Stage 4 – Coverage-based Jaccard pruning
    # ------------------------------------------------------------------

    def _stage4_coverage_jaccard(self, mutants: List[Mutant]) -> List[Mutant]:
        """
        Sort mutants descending by priority_score.
        For each remaining mutant, remove lower-priority mutants whose
        test-coverage set has Jaccard similarity ≥ threshold to a
        higher-priority mutant already in the kept set.

        If preserve_operator_diversity is True, we never eliminate the *last*
        representative of any operator type.
        """
        # Sort descending priority
        sorted_m = sorted(mutants, key=lambda m: m.priority_score, reverse=True)

        # Track how many mutants remain per operator type
        if self.preserve_operator_diversity:
            op_counts: Dict[str, int] = {}
            for m in sorted_m:
                op_counts[m.operator.value] = op_counts.get(m.operator.value, 0) + 1
        else:
            op_counts = {}

        kept: List[Mutant] = []
        removed_ids: Set[str] = set()

        for i, candidate in enumerate(sorted_m):
            if candidate.id in removed_ids:
                continue
            kept.append(candidate)

            cov_i: FrozenSet[str] = frozenset(candidate.test_coverage)

            for j in range(i + 1, len(sorted_m)):
                lower = sorted_m[j]
                if lower.id in removed_ids:
                    continue

                # Diversity guard
                if self.preserve_operator_diversity:
                    if op_counts.get(lower.operator.value, 0) <= 1:
                        continue  # last survivor of this operator – keep it

                cov_j: FrozenSet[str] = frozenset(lower.test_coverage)
                sim = self._jaccard(cov_i, cov_j)
                if sim >= self.jaccard_threshold:
                    removed_ids.add(lower.id)
                    if self.preserve_operator_diversity:
                        op_counts[lower.operator.value] = (
                            op_counts.get(lower.operator.value, 1) - 1
                        )

        return kept

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _jaccard(a: FrozenSet[str], b: FrozenSet[str]) -> float:
        """
        Jaccard similarity coefficient.
        Returns 0.0 when both sets are empty (no coverage data → not similar).
        """
        if not a and not b:
            return 0.0          # no coverage data → treat as dissimilar
        union = a | b
        if not union:
            return 0.0
        return len(a & b) / len(union)

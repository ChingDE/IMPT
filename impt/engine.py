"""impt/engine.py — IMPTEngine: orchestrates all 5 algorithms."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, List, Optional

from impt.algorithms.scoring       import MultiFactorScorer
from impt.algorithms.subsumption   import SubsumptionAnalyzer
from impt.algorithms.optimization  import TimeBudgetOptimizer, SelectionStrategy
from impt.algorithms.extrapolation import StatisticalExtrapolator
from impt.algorithms.time_estimation import ExecutionTimeEstimator
from impt.models.mutant  import Mutant, ExecutionStatus
from impt.models.project import Project
from impt.models.result  import MutationTestResult


@dataclass
class EngineConfig:
    time_budget_seconds:        int              = 1200
    jaccard_threshold:          float            = 0.90
    confidence_level:           float            = 0.95
    dp_size_threshold:          int              = 1000
    optimizer_strategy:         SelectionStrategy = SelectionStrategy.AUTO
    preserve_operator_diversity: bool             = True


MutantRunner = Callable[[Mutant], None]


class IMPTEngine:
    def __init__(self, project: Project, config: Optional[EngineConfig] = None):
        self.project = project
        self.cfg     = config or EngineConfig(
            time_budget_seconds=project.config.time_budget_seconds,
            jaccard_threshold=project.config.jaccard_threshold,
            confidence_level=project.config.confidence_level,
        )
        self.scorer      = MultiFactorScorer(project)
        self.reducer     = SubsumptionAnalyzer(self.cfg.jaccard_threshold,
                                                self.cfg.preserve_operator_diversity)
        self.estimator   = ExecutionTimeEstimator(project)
        self.optimizer   = TimeBudgetOptimizer(self.cfg.time_budget_seconds,
                                               self.cfg.optimizer_strategy)
        self.extrapolator = StatisticalExtrapolator(self.cfg.confidence_level)

    def run(self, mutants: List[Mutant], runner: Optional[MutantRunner] = None) -> MutationTestResult:
        import time

        if not mutants:
            return MutationTestResult([], [], [], 0.0)

        # Step 1 — Score
        self.scorer.score_population(mutants)

        # Step 2 — Reduce
        reduced = self.reducer.reduce(mutants)
        sub_pct = (1 - len(reduced) / len(mutants)) * 100 if mutants else 0

        # Step 3 — Estimate execution times
        self.estimator.estimate_population(reduced)

        # Step 4 — Select within budget
        selected = self.optimizer.select(reduced)

        # Step 5 — Execute
        t0 = time.monotonic()
        if runner:
            for m in selected:
                t_start = time.monotonic()
                runner(m)
                actual = time.monotonic() - t_start
                m.execution_time = actual
                self.estimator.record_actual(m.execution_time, actual)
        total_time = time.monotonic() - t0

        # Step 6 — Extrapolate
        executed = [m for m in selected if m.status != ExecutionStatus.PENDING]
        estimate = self.extrapolator.estimate(executed) if executed else None

        # Score
        scored_m = [m for m in executed if m.counts_in_score]
        killed   = sum(1 for m in scored_m if m.is_killed)
        score    = (killed / len(scored_m)) if scored_m else 0.0

        # Time saved
        exhaustive_time = sum(m.execution_time for m in mutants)
        selected_time   = sum(m.execution_time for m in selected)
        time_saved      = (1 - selected_time / exhaustive_time) * 100 if exhaustive_time > 0 else 0.0

        # Operator stats
        from collections import defaultdict
        op_stats: dict = defaultdict(lambda: {"total": 0, "killed": 0})
        for m in executed:
            op = m.operator.value
            op_stats[op]["total"] += 1
            if m.is_killed:
                op_stats[op]["killed"] += 1

        return MutationTestResult(
            all_mutants              = mutants,
            selected_mutants         = selected,
            executed_mutants         = executed,
            mutation_score           = score,
            estimate                 = estimate,
            subsumption_reduction_pct = sub_pct,
            time_saved_pct           = time_saved,
            total_execution_time     = total_time,
            operator_stats           = dict(op_stats),
        )

#!/usr/bin/env python3
"""
cli/run_demo.py
IMPT Local Demo Runner
======================
Simulates a full IMPT session with a synthetic mutant population.
Use this during white-box testing to verify the pipeline end-to-end
without needing a real Java/JavaScript project.

Usage (from the impt/ project root):
    python cli/run_demo.py
    python cli/run_demo.py --mutants 50 --budget 120 --kill-rate 0.75
"""

import argparse
import logging
import random
import sys
import os

# Allow running from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from impt.engine import IMPTEngine, EngineConfig
from impt.models.mutant import ExecutionStatus, MutationOperator, PriorityFactors
from impt.models.project import MutationFramework, Project, ProjectConfig
from tests.conftest import make_mutant

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)


def build_synthetic_population(n: int, seed: int = 0) -> list:
    random.seed(seed)
    ops = list(MutationOperator)
    mutants = []
    for i in range(n):
        op = ops[i % len(ops)]
        coverage = [f"test_{j}" for j in random.sample(range(n * 2), k=random.randint(1, 8))]
        m = make_mutant(
            operator=op,
            line=i + 1,
            historical=round(random.uniform(0.1, 0.95), 2),
            cyclomatic=round(random.uniform(1.0, 25.0), 1),
            cognitive=round(random.uniform(1.0, 15.0), 1),
            nesting=round(random.uniform(1.0, 6.0), 1),
            security=random.choice([0.0, 0.0, 0.0, 1.0]),  # ~25% security-critical
            days=round(random.uniform(0.5, 90.0), 1),
            bugs=round(random.uniform(0.0, 8.0), 2),
            coverage=coverage,
        )
        mutants.append(m)
    return mutants


def make_runner(kill_rate: float):
    """Simulated runner: kills mutants with probability = kill_rate."""
    def runner(mutant):
        mutant.status = (
            ExecutionStatus.KILLED
            if random.random() < kill_rate
            else ExecutionStatus.SURVIVED
        )
    return runner


def main():
    parser = argparse.ArgumentParser(
        description="IMPT Local Demo — white-box testing runner"
    )
    parser.add_argument("--mutants",   type=int,   default=30,   help="Number of synthetic mutants")
    parser.add_argument("--budget",    type=int,   default=300,  help="Time budget in seconds")
    parser.add_argument("--kill-rate", type=float, default=0.70, help="Simulated kill rate [0..1]")
    parser.add_argument("--loc",       type=int,   default=5000, help="Project LOC")
    parser.add_argument("--tests",     type=int,   default=100,  help="Number of test cases")
    parser.add_argument("--seed",      type=int,   default=42,   help="Random seed")
    parser.add_argument("--strategy",  choices=["auto","dp","greedy"], default="auto")
    args = parser.parse_args()

    random.seed(args.seed)

    print("\n" + "═" * 60)
    print("  IMPT — Intelligent Mutation Prioritization Tool")
    print("  NovaSoft | FEU Institute of Technology")
    print("═" * 60)
    print(f"  Mutants    : {args.mutants}")
    print(f"  Budget     : {args.budget}s")
    print(f"  Kill rate  : {args.kill_rate:.0%}")
    print(f"  Strategy   : {args.strategy.upper()}")
    print("═" * 60 + "\n")

    # ── Project setup ─────────────────────────────────────────────────
    cfg = ProjectConfig(time_budget_seconds=args.budget)
    project = Project(
        name="demo-project",
        framework=MutationFramework.PIT,
        source_dir="src/main/java/",
        test_dir="src/test/java/",
        loc=args.loc,
        test_count=args.tests,
        config=cfg,
    )

    from impt.algorithms.optimization import SelectionStrategy
    strategy_map = {
        "auto":   SelectionStrategy.AUTO,
        "dp":     SelectionStrategy.DYNAMIC_PROGRAMMING,
        "greedy": SelectionStrategy.GREEDY,
    }

    engine_cfg = EngineConfig(
        time_budget_seconds=args.budget,
        optimizer_strategy=strategy_map[args.strategy],
        verbose=True,
    )

    # ── Mutant population ─────────────────────────────────────────────
    mutants = build_synthetic_population(args.mutants, seed=args.seed)
    runner  = make_runner(args.kill_rate)

    # ── Run ───────────────────────────────────────────────────────────
    engine = IMPTEngine(project, config=engine_cfg)
    result = engine.run(mutants, runner=runner)

    # ── Report ────────────────────────────────────────────────────────
    print("\n" + "═" * 60)
    print(result.summary())
    print("═" * 60)

    if result.operator_stats:
        print("\nOperator Breakdown:")
        for op, stats in sorted(result.operator_stats.items()):
            print(
                f"  {op:<20} total={stats['total']:>3}  "
                f"killed={stats['killed']:>3}  "
                f"kill_rate={stats['kill_rate']:.0%}"
            )

    if result.estimate:
        print(f"\n{result.estimate.as_percentage()}")

    print("\n✓ Demo complete.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

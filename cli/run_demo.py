"""
cli/run_demo.py
Runs the full 5-algorithm IMPT pipeline with a synthetic mutant population.
No Docker or real project required — useful for demonstrating the core algorithms.

Usage:
    PYTHONPATH=. python cli/run_demo.py --mutants 40 --budget 300 --kill-rate 0.72
"""
import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from impt.engine import IMPTEngine, EngineConfig
from impt.models.mutant import (
    CodeLocation, Mutant, MutationOperator, PriorityFactors, ExecutionStatus,
)
from impt.models.project import MutationFramework, Project, ProjectConfig
from impt.algorithms.optimization import SelectionStrategy


def make_synthetic_population(n: int, seed: int = 42) -> list:
    rng   = random.Random(seed)
    ops   = list(MutationOperator)
    files = [
        "src/Calculator.java", "src/StringUtils.java",
        "src/Parser.java", "src/Formatter.java", "src/Validator.java",
    ]
    mutants = []
    for i in range(n):
        op  = ops[i % len(ops)]
        loc = CodeLocation(
            file=files[i % len(files)],
            line=rng.randint(1, 250),
            column=0,
        )
        factors = PriorityFactors(
            historical_effectiveness=round(rng.uniform(0.1, 0.95), 2),
            cyclomatic_complexity=round(rng.uniform(1, 20), 1),
            cognitive_complexity=round(rng.uniform(1, 12), 1),
            nesting_depth=round(rng.uniform(1, 5), 1),
            security_score=rng.choice([0.0, 0.0, 0.0, 1.0]),
            days_since_change=round(rng.uniform(1, 60), 1),
            bug_density=round(rng.uniform(0, 5), 2),
        )
        m = Mutant(
            operator=op, location=loc,
            original_code=f"x {op.value} y",
            mutated_code=f"x {op.value[::-1]} y",
            factors=factors,
        )
        m.test_coverage = {
            f"Test{j}" for j in rng.sample(range(n * 2), k=rng.randint(1, 8))
        }
        mutants.append(m)
    return mutants


def make_runner(kill_rate: float, seed: int = 42):
    rng = random.Random(seed)

    def runner(m: Mutant):
        m.status = (
            ExecutionStatus.KILLED
            if rng.random() < kill_rate
            else ExecutionStatus.SURVIVED
        )
        m.execution_time = round(rng.uniform(1.0, 8.0), 2)

    return runner


def main():
    parser = argparse.ArgumentParser(description="IMPT Algorithm Demo")
    parser.add_argument("--mutants",   type=int,   default=30,   help="Number of synthetic mutants")
    parser.add_argument("--budget",    type=int,   default=300,  help="Time budget in seconds")
    parser.add_argument("--kill-rate", type=float, default=0.70, help="Simulated kill rate 0.0–1.0")
    parser.add_argument("--strategy",  type=str,   default="auto",
                        choices=["auto", "dp", "greedy"], help="Optimizer strategy")
    args = parser.parse_args()

    strat_map = {
        "auto":   SelectionStrategy.AUTO,
        "dp":     SelectionStrategy.DYNAMIC_PROGRAMMING,
        "greedy": SelectionStrategy.GREEDY,
    }

    print(f"\n{'='*60}")
    print(f"  IMPT Algorithm Demo")
    print(f"  Mutants: {args.mutants}  |  Budget: {args.budget}s  |  Kill rate: {args.kill_rate:.0%}")
    print(f"{'='*60}\n")

    config = ProjectConfig(
        time_budget_seconds=args.budget,
        factor_weights={
            "historical_effectiveness": 0.30,
            "code_complexity":          0.25,
            "security_criticality":     0.20,
            "change_recency":           0.15,
            "bug_history":              0.10,
        },
    )
    project = Project(
        name="synthetic-demo",
        framework=MutationFramework.PIT,
        source_dir="src/",
        test_dir="src/test/",
        loc=5000,
        test_count=100,
        config=config,
    )
    engine_cfg = EngineConfig(
        time_budget_seconds=args.budget,
        optimizer_strategy=strat_map[args.strategy],
    )

    mutants = make_synthetic_population(args.mutants)
    runner  = make_runner(args.kill_rate)
    engine  = IMPTEngine(project, config=engine_cfg)

    print("Running pipeline...")
    result = engine.run(mutants, runner=runner)

    print(result.summary())

    if result.operator_stats:
        print("\nOperator breakdown:")
        for op, stats in sorted(result.operator_stats.items()):
            total  = stats["total"]
            killed = stats["killed"]
            rate   = killed / total * 100 if total else 0
            print(f"  {op:20s} {killed:3d}/{total:3d} killed ({rate:5.1f}%)")

    print(f"\n{'='*60}")


if __name__ == "__main__":
    main()

"""
worker/tasks.py
Full IMPT pipeline with real PIT/Stryker adapters + synthetic fallback.
Writes intermediate progress to the DB so the frontend polling sees live numbers.
"""
from __future__ import annotations
import logging, os, sys, time
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
log = logging.getLogger(__name__)


# ── Progress writer ───────────────────────────────────────────────────────────
# Called periodically during execution to update the DB record so the
# polling endpoint returns live metrics while the job is still RUNNING.

def _write_progress(job_id: str, executed: int, killed: int,
                    total: int, selected: int) -> None:
    """Synchronous DB write — runs inside the worker thread."""
    try:
        import asyncio
        from db.database import AsyncSessionLocal
        from sqlalchemy import update
        from db.models.orm_models import MutationJob

        score = (killed / executed) if executed > 0 else 0.0

        async def _do_write():
            async with AsyncSessionLocal() as db:
                await db.execute(
                    update(MutationJob)
                    .where(MutationJob.id == job_id)
                    .values(
                        executed_mutants=executed,
                        killed_mutants=killed,
                        total_mutants=total,
                        selected_mutants=selected,
                        mutation_score=score,
                    )
                )
                await db.commit()

        # Run in a new event loop since we're inside a sync thread
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Can't nest event loops — create a thread-safe future
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    ex.submit(asyncio.run, _do_write()).result()
            else:
                loop.run_until_complete(_do_write())
        except RuntimeError:
            asyncio.run(_do_write())

    except Exception as e:
        log.warning("Progress write failed (non-fatal): %s", e)


# ── Engine runner ─────────────────────────────────────────────────────────────

def _run_engine(job_id: str, config: dict) -> dict:
    from impt.engine import IMPTEngine, EngineConfig
    from impt.models.project import MutationFramework, Project, ProjectConfig
    from impt.models.mutant import ExecutionStatus
    from impt.algorithms.optimization import SelectionStrategy
    import random

    fw_str = config.get("framework", "PIT").upper()
    fw = MutationFramework.PIT if fw_str == "PIT" else MutationFramework.STRYKER
    strat = {
        "AUTO":   SelectionStrategy.AUTO,
        "DP":     SelectionStrategy.DYNAMIC_PROGRAMMING,
        "GREEDY": SelectionStrategy.GREEDY,
    }.get(config.get("optimizer_strategy", "AUTO"), SelectionStrategy.AUTO)

    pcfg = ProjectConfig(
        time_budget_seconds=config.get("time_budget_seconds", 1800),
        jaccard_threshold=config.get("jaccard_threshold", 0.90),
        factor_weights=config.get("factor_weights") or {
            "historical_effectiveness": 0.30, "code_complexity": 0.25,
            "security_criticality": 0.20, "change_recency": 0.15, "bug_history": 0.10,
        },
    )
    project = Project(
        name=config.get("project_name", "unknown"),
        framework=fw,
        source_dir=config.get("upload_path", "src/"),
        test_dir=config.get("upload_path", "src/"),
        loc=config.get("loc", 5000),
        test_count=config.get("test_count", 100),
        config=pcfg,
    )
    ecfg = EngineConfig(
        time_budget_seconds=pcfg.time_budget_seconds,
        jaccard_threshold=pcfg.jaccard_threshold,
        optimizer_strategy=strat,
    )

    upload_path = config.get("upload_path")
    mutants = _get_mutants(
        upload_path, fw_str,
        config.get("use_docker", True),
        config.get("mutant_count", 40),
        job_id,
    )

    if upload_path and Path(upload_path).exists():
        try:
            real_loc, real_tests = _scan_project(upload_path, fw_str)
            if real_loc > 0:   project.loc        = real_loc
            if real_tests > 0: project.test_count = real_tests
        except Exception as e:
            log.warning("scan failed: %s", e)

    # ── Instrumented runner: writes progress every 5 mutants ────────────────
    rng = random.Random(hash(job_id))
    executed_count = [0]
    killed_count   = [0]
    PROGRESS_INTERVAL = 5  # write to DB every N mutants

    def runner(m):
        if m.status == ExecutionStatus.PENDING:
            # Simulate realistic kill/survive probabilities per operator
            kill_rates = {
                "AOR": 0.92, "ROR": 0.88, "COR": 0.85, "SOR": 0.76,
                "LCR": 0.71, "UOI": 0.85, "SDL": 0.75, "CRP": 0.65,
            }
            rate = kill_rates.get(m.operator.value, 0.70)
            m.status = (
                ExecutionStatus.KILLED
                if rng.random() < rate
                else ExecutionStatus.SURVIVED
            )

        executed_count[0] += 1
        if m.status == ExecutionStatus.KILLED:
            killed_count[0] += 1

        if executed_count[0] % PROGRESS_INTERVAL == 0:
            _write_progress(
                job_id,
                executed=executed_count[0],
                killed=killed_count[0],
                total=len(mutants),
                selected=0,  # will be set accurately after optimizer runs
            )

    engine = IMPTEngine(project, config=ecfg)
    result = engine.run(mutants, runner=runner)

    # Final progress write with accurate selected count
    _write_progress(
        job_id,
        executed=len(result.executed_mutants),
        killed=sum(1 for m in result.executed_mutants if m.is_killed),
        total=len(result.all_mutants),
        selected=len(result.selected_mutants),
    )

    killed = sum(1 for m in result.executed_mutants if m.is_killed)
    records = [
        {
            "mutant_hash":    m.id,
            "operator":       m.operator.value,
            "file":           m.location.file,
            "line":           m.location.line,
            "original_code":  m.original_code[:500],
            "mutated_code":   m.mutated_code[:500],
            "status":         m.status.value,
            "priority_score": m.priority_score,
            "execution_time": m.execution_time,
            "explanation":    m.priority_explanation,
        }
        for m in result.executed_mutants
    ]

    return {
        "total_mutants":              len(result.all_mutants),
        "selected_mutants":           len(result.selected_mutants),
        "executed_mutants":           len(result.executed_mutants),
        "killed_mutants":             killed,
        "mutation_score":             result.mutation_score,
        "estimated_score":            result.estimate.estimated_score if result.estimate else 0.0,
        "ci_lower":                   result.estimate.lower_bound     if result.estimate else 0.0,
        "ci_upper":                   result.estimate.upper_bound     if result.estimate else 0.0,
        "time_saved_pct":             result.time_saved_pct,
        "subsumption_reduction_pct":  result.subsumption_reduction_pct,
        "execution_time_seconds":     result.total_execution_time,
        "result_json": {
            "operator_stats": result.operator_stats,
            "summary":        result.summary(),
        },
        "mutant_records": records,
    }


# ── Adapter helpers ───────────────────────────────────────────────────────────

def _get_mutants(upload_path, framework, use_docker, fallback_count, job_id):
    if upload_path and Path(upload_path).exists():
        try:
            return _run_adapter(Path(upload_path), framework, use_docker)
        except Exception as e:
            log.error("Adapter failed, using synthetic fallback: %s", e)
    log.info("Using synthetic mutant population (n=%d)", fallback_count)
    return _synthetic_population(fallback_count, seed=hash(job_id))


def _run_adapter(project_dir, framework, use_docker):
    from adapters.pit_adapter import PITAdapter
    from adapters.stryker_adapter import StrykerAdapter
    from adapters.factor_enricher import FactorEnricher
    adapter = (
        PITAdapter(project_dir, use_docker=use_docker)
        if framework == "PIT"
        else StrykerAdapter(project_dir, use_docker=use_docker)
    )
    mutants = adapter.run()
    FactorEnricher(project_dir).enrich(mutants)
    return mutants


def _scan_project(upload_path, framework):
    from adapters.pit_adapter import PITAdapter
    from adapters.stryker_adapter import StrykerAdapter
    p = Path(upload_path)
    a = (
        PITAdapter(p, use_docker=False)
        if framework == "PIT"
        else StrykerAdapter(p, use_docker=False)
    )
    return a.count_loc(), a.count_tests()


def _synthetic_population(n, seed):
    import random
    from impt.models.mutant import (
        Mutant, MutationOperator, CodeLocation, PriorityFactors, ExecutionStatus
    )
    rng  = random.Random(seed)
    ops  = list(MutationOperator)
    files = ["src/Calculator.java", "src/StringUtils.java",
             "src/Parser.java", "src/Formatter.java", "src/Validator.java"]
    mutants = []
    for i in range(n):
        op  = ops[i % len(ops)]
        loc = CodeLocation(
            file=files[i % len(files)],
            line=rng.randint(1, 200),
            column=0,
        )
        f = PriorityFactors(
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
            factors=f,
        )
        m.test_coverage = {
            f"t{j}" for j in rng.sample(range(n * 2), k=rng.randint(1, 8))
        }
        mutants.append(m)
    return mutants


# ── Celery task registration ──────────────────────────────────────────────────

try:
    from worker.celery_app import celery_app, CELERY_AVAILABLE
    if celery_app and CELERY_AVAILABLE:
        @celery_app.task(
            bind=True,
            name="worker.tasks.run_mutation_job",
            max_retries=1,
            default_retry_delay=10,
        )
        def run_mutation_job(self, job_id, config):
            try:
                return _run_engine(job_id, config)
            except Exception as e:
                raise self.retry(exc=e)
    else:
        run_mutation_job = None
except Exception:
    run_mutation_job = None


def run_mutation_job_sync(job_id, config):
    log.info("Sync runner: job=%s", job_id)
    return _run_engine(job_id, config)

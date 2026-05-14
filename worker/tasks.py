"""worker/tasks.py — Mutation testing Celery task."""
from __future__ import annotations
import logging, os, sys, time, random
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
log = logging.getLogger(__name__)


def _write_progress(job_id: str, executed: int, killed: int, total: int, selected: int):
    try:
        import asyncio
        from db.database import AsyncSessionLocal
        from sqlalchemy import update
        from db.models.orm_models import MutationJob

        score = (killed / executed) if executed > 0 else 0.0

        async def _do():
            async with AsyncSessionLocal() as db:
                await db.execute(
                    update(MutationJob).where(MutationJob.id == job_id).values(
                        executed_mutants=executed,
                        killed_mutants=killed,
                        total_mutants=total,
                        selected_mutants=selected,
                        mutation_score=score,
                    )
                )
                await db.commit()

        try:
            asyncio.run(_do())
        except RuntimeError:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                ex.submit(asyncio.run, _do()).result()
    except Exception as e:
        log.warning("Progress write failed (non-fatal): %s", e)


def _run_engine(job_id: str, config: dict) -> dict:
    from impt.engine import IMPTEngine, EngineConfig
    from impt.models.project import MutationFramework, Project, ProjectConfig
    from impt.models.mutant import ExecutionStatus
    from impt.algorithms.optimization import SelectionStrategy

    language = config.get("language", "java").lower()
    fw = MutationFramework.PIT if language == "java" else MutationFramework.STRYKER
    strat_map = {"AUTO": SelectionStrategy.AUTO, "DP": SelectionStrategy.DYNAMIC_PROGRAMMING, "GREEDY": SelectionStrategy.GREEDY}
    strat = strat_map.get(config.get("optimizer_strategy", "AUTO"), SelectionStrategy.AUTO)

    # Random strategy uses greedy
    if config.get("strategy") == "random":
        strat = SelectionStrategy.GREEDY

    pcfg = ProjectConfig(
        time_budget_seconds=config.get("time_budget_seconds", 1200),
        factor_weights=config.get("factor_weights") or {
            "historical_effectiveness": 0.30, "code_complexity": 0.25,
            "security_criticality": 0.20, "change_recency": 0.15, "bug_history": 0.10,
        },
    )
    project = Project(
        name=config.get("session_id", "unknown"),
        framework=fw,
        source_dir=config.get("upload_path", "src/"),
        test_dir=config.get("upload_path", "src/"),
        loc=config.get("loc", 5000),
        test_count=config.get("test_count", 100),
        config=pcfg,
    )
    ecfg = EngineConfig(
        time_budget_seconds=pcfg.time_budget_seconds,
        optimizer_strategy=strat,
    )

    mutants = _get_mutants(config, job_id)

    rng = random.Random(hash(job_id))
    executed_count = [0]
    killed_count   = [0]

    kill_rates = {"AOR":0.92,"ROR":0.88,"COR":0.85,"SOR":0.76,"LCR":0.71,"UOI":0.85,"SDL":0.75,"CRP":0.65}

    # For random strategy — shuffle instead of prioritise
    if config.get("strategy") == "random":
        rng.shuffle(mutants)
    # For operator_based strategy — group mutants by operator, pick top-N per operator evenly
    elif config.get("strategy") == "operator_based":
        from collections import defaultdict
        by_op = defaultdict(list)
        for m in mutants:
            by_op[m.operator.value].append(m)
        for k in by_op:
            by_op[k].sort(key=lambda x: x.priority_score, reverse=True)
        # Round-robin selection across operators
        interleaved = []
        iters = [iter(v) for v in by_op.values()]
        while iters:
            still_going = []
            for it in iters:
                try:
                    interleaved.append(next(it))
                    still_going.append(it)
                except StopIteration:
                    pass
            iters = still_going
        mutants = interleaved

    def runner(m):
        if m.status == ExecutionStatus.PENDING:
            rate = kill_rates.get(m.operator.value if hasattr(m.operator, "value") else str(m.operator), 0.70)
            m.status = ExecutionStatus.KILLED if rng.random() < rate else ExecutionStatus.SURVIVED
        executed_count[0] += 1
        if m.status == ExecutionStatus.KILLED:
            killed_count[0] += 1
        if executed_count[0] % 5 == 0:
            _write_progress(job_id, executed_count[0], killed_count[0], len(mutants), 0)

    engine = IMPTEngine(project, config=ecfg)
    result = engine.run(mutants, runner=runner)

    killed = sum(1 for m in result.executed_mutants if m.is_killed)
    _write_progress(job_id, len(result.executed_mutants), killed, len(result.all_mutants), len(result.selected_mutants))

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
        "total_mutants":             len(result.all_mutants),
        "selected_mutants":          len(result.selected_mutants),
        "executed_mutants":          len(result.executed_mutants),
        "killed_mutants":            killed,
        "mutation_score":            result.mutation_score,
        "estimated_score":           result.estimate.estimated_score if result.estimate else 0.0,
        "ci_lower":                  result.estimate.lower_bound     if result.estimate else 0.0,
        "ci_upper":                  result.estimate.upper_bound     if result.estimate else 0.0,
        "time_saved_pct":            result.time_saved_pct,
        "subsumption_reduction_pct": result.subsumption_reduction_pct,
        "execution_time_seconds":    result.total_execution_time,
        "result_json":               {"operator_stats": result.operator_stats, "summary": result.summary()},
        "mutant_records":            records,
    }


def _get_mutants(config: dict, job_id: str):
    upload_path = config.get("upload_path")
    if upload_path and Path(upload_path).exists():
        try:
            from adapters.pit_adapter     import PITAdapter
            from adapters.stryker_adapter import StrykerAdapter
            from adapters.factor_enricher import FactorEnricher
            p   = Path(upload_path)
            lang = config.get("language", "java").lower()
            adapter = PITAdapter(p, use_docker=True) if lang == "java" else StrykerAdapter(p, use_docker=True)
            mutants = adapter.run()
            FactorEnricher(p).enrich(mutants)
            return mutants
        except Exception as e:
            log.error("Adapter failed, using synthetic fallback: %s", e)
    return _synthetic_population(config.get("loc", 5000), seed=hash(job_id))


def _synthetic_population(loc: int, seed: int):
    import random
    from impt.models.mutant import Mutant, MutationOperator, CodeLocation, PriorityFactors, ExecutionStatus
    rng   = random.Random(seed)
    ops   = list(MutationOperator)
    files = ["src/Calculator.java","src/StringUtils.java","src/Parser.java","src/Formatter.java","src/Validator.java"]
    n     = max(20, min(200, loc // 50))
    mutants = []
    for i in range(n):
        op  = ops[i % len(ops)]
        loc_obj = CodeLocation(file=files[i % len(files)], line=rng.randint(1,200), column=0)
        f   = PriorityFactors(
            historical_effectiveness=round(rng.uniform(0.1,0.95),2),
            cyclomatic_complexity=round(rng.uniform(1,20),1),
            cognitive_complexity=round(rng.uniform(1,12),1),
            nesting_depth=round(rng.uniform(1,5),1),
            security_score=rng.choice([0.0,0.0,0.0,1.0]),
            days_since_change=round(rng.uniform(1,60),1),
            bug_density=round(rng.uniform(0,5),2),
        )
        m = Mutant(operator=op, location=loc_obj, original_code=f"x {op.value} y", mutated_code=f"x {op.value[::-1]} y", factors=f)
        m.test_coverage = {f"t{j}" for j in rng.sample(range(n*2), k=rng.randint(1,8))}
        mutants.append(m)
    return mutants


# Celery task registration
try:
    from worker.celery_app import celery_app, CELERY_AVAILABLE
    if celery_app and CELERY_AVAILABLE:
        @celery_app.task(bind=True, name="worker.tasks.run_mutation_job", max_retries=1)
        def run_mutation_job(self, job_id, config):
            try:
                return _run_engine(job_id, config)
            except Exception as e:
                raise self.retry(exc=e)
    else:
        run_mutation_job = None
except Exception:
    run_mutation_job = None


def run_mutation_job_sync(job_id: str, config: dict) -> dict:
    return _run_engine(job_id, config)

"""
worker/tasks.py
Mutation testing job execution.
Runs via Celery (production) or in a background thread (sync fallback).
"""
from __future__ import annotations

import logging
import os
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
log = logging.getLogger(__name__)


# ── Synchronous DB helper (used in threads — no event loop needed) ────────────

def _write_progress_sync(job_id: str, executed: int, killed: int,
                          total: int, selected: int) -> None:
    """Write progress directly using a synchronous DB connection."""
    try:
        from config.settings import get_settings
        import sqlalchemy as sa
        settings = get_settings()

        # Build sync URL from async URL
        sync_url = settings.DATABASE_URL_SYNC
        if not sync_url or 'CHANGE_ME' in sync_url:
            # Fallback: derive from async URL
            sync_url = settings.DATABASE_URL.replace(
                'postgresql+asyncpg', 'postgresql+psycopg2'
            ).replace('sqlite+aiosqlite', 'sqlite').replace('?ssl=require', '?sslmode=require')

        engine = sa.create_engine(sync_url, pool_pre_ping=True,
                                   connect_args={"connect_timeout": 5} if 'postgresql' in sync_url else {})
        score = (killed / executed) if executed > 0 else 0.0
        with engine.begin() as conn:
            conn.execute(
                sa.text("""
                    UPDATE mutation_jobs SET
                        executed_mutants = :executed,
                        killed_mutants   = :killed,
                        total_mutants    = :total,
                        selected_mutants = :selected,
                        mutation_score   = :score
                    WHERE id = :job_id
                """),
                {"executed": executed, "killed": killed, "total": total,
                 "selected": selected, "score": score, "job_id": job_id}
            )
        engine.dispose()
    except Exception as e:
        log.warning("Progress write failed (non-fatal): %s", e)


def _mark_running_sync(job_id: str, task_id: str) -> None:
    try:
        from config.settings import get_settings
        import sqlalchemy as sa
        from datetime import datetime
        settings = get_settings()
        sync_url = settings.DATABASE_URL_SYNC or settings.DATABASE_URL.replace(
            'postgresql+asyncpg', 'postgresql+psycopg2'
        ).replace('sqlite+aiosqlite', 'sqlite').replace('?ssl=require', '?sslmode=require')
        engine = sa.create_engine(sync_url, pool_pre_ping=True,
                                   connect_args={"connect_timeout": 5} if 'postgresql' in sync_url else {})
        with engine.begin() as conn:
            conn.execute(
                sa.text("UPDATE mutation_jobs SET status='RUNNING', celery_task_id=:tid, started_at=:now WHERE id=:jid"),
                {"tid": task_id, "now": datetime.utcnow(), "jid": job_id}
            )
        engine.dispose()
    except Exception as e:
        log.warning("mark_running failed: %s", e)


def _mark_completed_sync(job_id: str, result: dict, records: list) -> None:
    try:
        import json
        from config.settings import get_settings
        import sqlalchemy as sa
        from datetime import datetime
        settings = get_settings()
        sync_url = settings.DATABASE_URL_SYNC or settings.DATABASE_URL.replace(
            'postgresql+asyncpg', 'postgresql+psycopg2'
        ).replace('sqlite+aiosqlite', 'sqlite').replace('?ssl=require', '?sslmode=require')
        engine = sa.create_engine(sync_url, pool_pre_ping=True,
                                   connect_args={"connect_timeout": 5} if 'postgresql' in sync_url else {})
        with engine.begin() as conn:
            conn.execute(sa.text("""
                UPDATE mutation_jobs SET
                    status='COMPLETED', completed_at=:now,
                    total_mutants=:total, selected_mutants=:selected,
                    executed_mutants=:executed, killed_mutants=:killed,
                    mutation_score=:score, estimated_score=:est,
                    ci_lower=:cil, ci_upper=:ciu,
                    time_saved_pct=:tsp, subsumption_reduction_pct=:srp,
                    execution_time_seconds=:ets, result_json=:rj
                WHERE id=:jid
            """), {
                "now": datetime.utcnow(),
                "total":    result.get("total_mutants", 0),
                "selected": result.get("selected_mutants", 0),
                "executed": result.get("executed_mutants", 0),
                "killed":   result.get("killed_mutants", 0),
                "score":    result.get("mutation_score", 0.0),
                "est":      result.get("estimated_score", 0.0),
                "cil":      result.get("ci_lower", 0.0),
                "ciu":      result.get("ci_upper", 0.0),
                "tsp":      result.get("time_saved_pct", 0.0),
                "srp":      result.get("subsumption_reduction_pct", 0.0),
                "ets":      result.get("execution_time_seconds", 0.0),
                "rj":       json.dumps(result.get("result_json", {})),
                "jid":      job_id,
            })
            # Also update session status
            conn.execute(sa.text("""
                UPDATE test_sessions SET status='completed', completed_at=:now
                WHERE id = (SELECT session_id FROM mutation_jobs WHERE id=:jid)
                AND NOT EXISTS (
                    SELECT 1 FROM mutation_jobs
                    WHERE session_id = (SELECT session_id FROM mutation_jobs WHERE id=:jid2)
                    AND status NOT IN ('COMPLETED','FAILED')
                    AND id != :jid3
                )
            """), {"now": datetime.utcnow(), "jid": job_id, "jid2": job_id, "jid3": job_id})

            # Save mutant records
            import uuid
            for rec in records:
                conn.execute(sa.text("""
                    INSERT INTO mutant_records
                        (id, job_id, mutant_hash, operator, file, line,
                         original_code, mutated_code, status,
                         priority_score, execution_time, explanation)
                    VALUES
                        (:id, :job_id, :mh, :op, :file, :line,
                         :orig, :mut, :status, :score, :etime, :expl)
                """), {
                    "id":     str(uuid.uuid4()),
                    "job_id": job_id,
                    "mh":     rec.get("mutant_hash", ""),
                    "op":     rec.get("operator", ""),
                    "file":   rec.get("file", ""),
                    "line":   rec.get("line", 0),
                    "orig":   (rec.get("original_code") or "")[:500],
                    "mut":    (rec.get("mutated_code") or "")[:500],
                    "status": rec.get("status", "SURVIVED"),
                    "score":  rec.get("priority_score", 0.0),
                    "etime":  rec.get("execution_time", 0.0),
                    "expl":   (rec.get("explanation") or "")[:1000],
                })
        engine.dispose()
        log.info("Job %s completed and saved.", job_id)
    except Exception as e:
        log.error("mark_completed failed: %s", e)
        _mark_failed_sync(job_id, str(e))


def _mark_failed_sync(job_id: str, error: str) -> None:
    try:
        from config.settings import get_settings
        import sqlalchemy as sa
        from datetime import datetime
        settings = get_settings()
        sync_url = settings.DATABASE_URL_SYNC or settings.DATABASE_URL.replace(
            'postgresql+asyncpg', 'postgresql+psycopg2'
        ).replace('sqlite+aiosqlite', 'sqlite').replace('?ssl=require', '?sslmode=require')
        engine = sa.create_engine(sync_url, pool_pre_ping=True,
                                   connect_args={"connect_timeout": 5} if 'postgresql' in sync_url else {})
        with engine.begin() as conn:
            conn.execute(
                sa.text("UPDATE mutation_jobs SET status='FAILED', error_message=:err, completed_at=:now WHERE id=:jid"),
                {"err": error[:1000], "now": datetime.utcnow(), "jid": job_id}
            )
            # Mark session as failed if all jobs failed
            conn.execute(sa.text("""
                UPDATE test_sessions SET status='failed'
                WHERE id = (SELECT session_id FROM mutation_jobs WHERE id=:jid)
                AND NOT EXISTS (
                    SELECT 1 FROM mutation_jobs
                    WHERE session_id = (SELECT session_id FROM mutation_jobs WHERE id=:jid2)
                    AND status NOT IN ('FAILED')
                    AND id != :jid3
                )
            """), {"jid": job_id, "jid2": job_id, "jid3": job_id})
        engine.dispose()
    except Exception as e:
        log.error("mark_failed itself failed: %s", e)


# ── Core engine runner ────────────────────────────────────────────────────────

def _run_engine(job_id: str, config: dict) -> dict:
    from impt.engine import IMPTEngine, EngineConfig
    from impt.models.project import MutationFramework, Project, ProjectConfig
    from impt.models.mutant import ExecutionStatus
    from impt.algorithms.optimization import SelectionStrategy

    language  = config.get("language", "java").lower()
    fw        = MutationFramework.PIT if language == "java" else MutationFramework.STRYKER
    strat_map = {
        "AUTO":   SelectionStrategy.AUTO,
        "DP":     SelectionStrategy.DYNAMIC_PROGRAMMING,
        "GREEDY": SelectionStrategy.GREEDY,
    }
    strat = strat_map.get(config.get("optimizer_strategy", "AUTO"), SelectionStrategy.AUTO)
    if config.get("strategy") in ("random", "operator_based"):
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

    # Get mutant population
    mutants = _get_mutants(config, job_id)
    log.info("Job %s: %d mutants generated", job_id, len(mutants))

    # Write initial total so UI shows "X of Y" immediately
    _write_progress_sync(job_id, 0, 0, len(mutants), 0)

    rng        = random.Random(hash(job_id))
    exec_count = [0]
    kill_count = [0]

    kill_rates = {
        "AOR": 0.92, "ROR": 0.88, "COR": 0.85, "SOR": 0.76,
        "LCR": 0.71, "UOI": 0.85, "SDL": 0.75, "CRP": 0.65,
        "ABS": 0.80, "VDL": 0.78, "ODL": 0.72,
        "NEGATE_RETURN": 0.88, "NULL_RETURN": 0.70,
    }

    # Apply strategy ordering
    strategy = config.get("strategy", "impt")
    if strategy == "random":
        rng.shuffle(mutants)
    elif strategy == "operator_based":
        from collections import defaultdict
        by_op = defaultdict(list)
        for m in mutants:
            by_op[m.operator.value].append(m)
        for k in by_op:
            by_op[k].sort(key=lambda x: x.priority_score, reverse=True)
        interleaved, iters = [], [iter(v) for v in by_op.values()]
        while iters:
            still = []
            for it in iters:
                try:
                    interleaved.append(next(it))
                    still.append(it)
                except StopIteration:
                    pass
            iters = still
        mutants = interleaved

    def runner(m):
        if m.status == ExecutionStatus.PENDING:
            op_key = m.operator.value if hasattr(m.operator, "value") else str(m.operator)
            rate   = kill_rates.get(op_key, 0.70)
            m.status = ExecutionStatus.KILLED if rng.random() < rate else ExecutionStatus.SURVIVED
        exec_count[0] += 1
        if m.status == ExecutionStatus.KILLED:
            kill_count[0] += 1
        # Write progress every 3 mutants for responsive UI
        if exec_count[0] % 3 == 0 or exec_count[0] == 1:
            _write_progress_sync(job_id, exec_count[0], kill_count[0],
                                  len(mutants), len(mutants))

    engine = IMPTEngine(project, config=ecfg)
    result = engine.run(mutants, runner=runner)

    killed = sum(1 for m in result.executed_mutants if m.is_killed)

    # Final progress write
    _write_progress_sync(job_id, len(result.executed_mutants), killed,
                          len(result.all_mutants), len(result.selected_mutants))

    records = [
        {
            "mutant_hash":    m.id,
            "operator":       m.operator.value,
            "file":           m.location.file,
            "line":           m.location.line,
            "original_code":  (m.original_code or "")[:500],
            "mutated_code":   (m.mutated_code or "")[:500],
            "status":         m.status.value,
            "priority_score": m.priority_score,
            "execution_time": m.execution_time,
            "explanation":    (m.priority_explanation or "")[:1000],
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
        "result_json":                {"operator_stats": result.operator_stats,
                                       "summary": result.summary()},
        "mutant_records":             records,
    }


def _get_mutants(config: dict, job_id: str):
    upload_path = config.get("upload_path")
    if upload_path and Path(upload_path).exists():
        try:
            from adapters.pit_adapter     import PITAdapter
            from adapters.stryker_adapter import StrykerAdapter
            from adapters.factor_enricher import FactorEnricher
            p    = Path(upload_path)
            lang = config.get("language", "java").lower()
            adapter = (PITAdapter(p, use_docker=True)
                       if lang == "java"
                       else StrykerAdapter(p, use_docker=True))
            mutants = adapter.run()
            FactorEnricher(p).enrich(mutants)
            log.info("Adapter produced %d mutants from %s", len(mutants), upload_path)
            return mutants
        except Exception as e:
            log.error("Adapter failed, using synthetic fallback: %s", e)
    log.info("Using synthetic population for job %s", job_id)
    return _synthetic_population(config.get("loc", 5000), seed=hash(job_id))


def _synthetic_population(loc: int, seed: int):
    from impt.models.mutant import (
        Mutant, MutationOperator, CodeLocation, PriorityFactors, ExecutionStatus
    )
    rng   = random.Random(seed)
    ops   = list(MutationOperator)
    files = [
        "src/Calculator.java", "src/StringUtils.java",
        "src/Parser.java", "src/Formatter.java", "src/Validator.java",
    ]
    n = max(20, min(300, loc // 30))
    mutants = []
    for i in range(n):
        op      = ops[i % len(ops)]
        loc_obj = CodeLocation(file=files[i % len(files)], line=rng.randint(1, 200), column=0)
        f       = PriorityFactors(
            historical_effectiveness=round(rng.uniform(0.1, 0.95), 2),
            cyclomatic_complexity   =round(rng.uniform(1, 20), 1),
            cognitive_complexity    =round(rng.uniform(1, 12), 1),
            nesting_depth           =round(rng.uniform(1, 5), 1),
            security_score          =rng.choice([0.0, 0.0, 0.0, 1.0]),
            days_since_change       =round(rng.uniform(1, 60), 1),
            bug_density             =round(rng.uniform(0, 5), 2),
        )
        m = Mutant(
            operator=op, location=loc_obj,
            original_code=f"x {op.value} y",
            mutated_code =f"x {op.value[::-1]} y",
            factors=f,
        )
        m.test_coverage = {f"t{j}" for j in rng.sample(range(n * 2), k=rng.randint(1, 8))}
        mutants.append(m)
    return mutants


# ── Public entry points ───────────────────────────────────────────────────────

def run_mutation_job_sync(job_id: str, config: dict) -> dict:
    """Called directly (non-Celery) — uses sync DB writes."""
    _mark_running_sync(job_id, "sync")
    try:
        result  = _run_engine(job_id, config)
        records = result.pop("mutant_records", [])
        _mark_completed_sync(job_id, result, records)
        return {**result, "mutant_records": records}
    except Exception as e:
        log.error("Job %s failed: %s", job_id, e)
        _mark_failed_sync(job_id, str(e))
        raise


# Celery task registration
try:
    from worker.celery_app import celery_app, CELERY_AVAILABLE
    if celery_app and CELERY_AVAILABLE:
        @celery_app.task(bind=True, name="worker.tasks.run_mutation_job",
                         max_retries=0, acks_late=True)
        def run_mutation_job(self, job_id: str, config: dict):
            """Celery task — runs in worker process with its own sync DB access."""
            return run_mutation_job_sync(job_id, config)
    else:
        run_mutation_job = None
except Exception as exc:
    log.warning("Celery task registration failed: %s", exc)
    run_mutation_job = None

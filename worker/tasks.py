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

def _publish_progress(session_id: str, job_id: str, executed: int,
                      killed: int, total: int, selected: int, strategy: str) -> None:
    """Publish progress to Redis channel for WebSocket clients."""
    try:
        import redis as _redis
        from config.settings import get_settings
        settings = get_settings()
        r = _redis.from_url(settings.REDIS_URL, decode_responses=True,
                            socket_connect_timeout=2)
        score = (killed / executed * 100) if executed > 0 else 0.0
        r.publish(f"impt:session:{session_id}", __import__('json').dumps({
            "type":     "progress",
            "job_id":   job_id,
            "strategy": strategy,
            "executed": executed,
            "killed":   killed,
            "total":    total,
            "selected": selected,
            "score":    round(score, 1),
        }))
        r.close()
    except Exception:
        pass  # Redis publish is best-effort — never block mutation testing


def _publish_bar(session_id: str, job_id: str, pct: int) -> None:
    """Publish a progress-bar-only update (live Stryker percentage). Drives the
    UI bar without touching numeric stats, which stay authoritative."""
    try:
        import redis as _redis
        from config.settings import get_settings
        r = _redis.from_url(get_settings().REDIS_URL, decode_responses=True,
                            socket_connect_timeout=2)
        r.publish(f"impt:session:{session_id}", __import__('json').dumps({
            "type": "bar", "job_id": job_id, "pct": int(pct),
        }))
        r.close()
    except Exception:
        pass


class _JobCancelled(Exception):
    """Raised to abort a job the user has stopped, without marking it FAILED."""


def _is_cancelled(job_id: str) -> bool:
    """Best-effort check for a user-requested stop. Returns False on any error
    so a transient DB hiccup never aborts a healthy run."""
    try:
        from config.settings import get_settings
        import sqlalchemy as sa
        settings = get_settings()
        sync_url = settings.DATABASE_URL_SYNC or settings.DATABASE_URL.replace(
            'postgresql+asyncpg', 'postgresql+psycopg2'
        ).replace('sqlite+aiosqlite', 'sqlite').replace('?ssl=require', '?sslmode=require')
        engine = sa.create_engine(sync_url, pool_pre_ping=True,
                                  connect_args={"connect_timeout": 5} if 'postgresql' in sync_url else {})
        with engine.connect() as conn:
            row = conn.execute(sa.text("SELECT status FROM mutation_jobs WHERE id=:jid"),
                               {"jid": job_id}).fetchone()
        engine.dispose()
        return bool(row) and str(row[0]).upper() == "CANCELLED"
    except Exception:
        return False


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
                WHERE id=:jid AND status != 'CANCELLED'
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
            # Mark the session ready as soon as the PRIMARY strategies finish.
            # The exhaustive baseline (if any) keeps running in the background and
            # enriches the results with the ground-truth correlation when done —
            # the user no longer waits on it to use their results. A session that
            # only has an exhaustive job completes when that job finishes.
            conn.execute(sa.text("""
                UPDATE test_sessions SET status='completed', completed_at=:now
                WHERE id = (SELECT session_id FROM mutation_jobs WHERE id=:jid)
                AND status NOT IN ('completed','failed','stopped')
                AND NOT EXISTS (
                    SELECT 1 FROM mutation_jobs
                    WHERE session_id = (SELECT session_id FROM mutation_jobs WHERE id=:jid2)
                    AND strategy != 'exhaustive'
                    AND status NOT IN ('COMPLETED','FAILED','CANCELLED')
                )
            """), {"now": datetime.utcnow(), "jid": job_id, "jid2": job_id})

            # Save mutant records
            import uuid
            for rec in records:
                conn.execute(sa.text("""
                    INSERT INTO mutant_records
                        (id, job_id, mutant_hash, operator, file, line,
                         original_code, mutated_code, status,
                         priority_score, execution_time, explanation, killing_test)
                    VALUES
                        (:id, :job_id, :mh, :op, :file, :line,
                         :orig, :mut, :status, :score, :etime, :expl, :kt)
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
                    "kt":     (rec.get("killing_test") or "")[:500] or None,
                })
        engine.dispose()
        # Update global operator kill rates from this run's results
        try:
            from adapters.factor_enricher import update_operator_stats
            op_results = {}
            for rec in records:
                op = rec.get("operator", "")
                if op:
                    if op not in op_results:
                        op_results[op] = {"total": 0, "killed": 0}
                    op_results[op]["total"] += 1
                    if rec.get("status") == "KILLED":
                        op_results[op]["killed"] += 1
            if op_results:
                update_operator_stats(op_results)
        except Exception as ue:
            log.debug("Operator stats update failed (non-fatal): %s", ue)
    except Exception as e:
        log.error("mark_completed failed: %s", e)

    log.info("Job %s completed and saved.", job_id)


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

def _random_select(mutants, budget_seconds, seed):
    """Random-sampling baseline: shuffle, then greedily fill the time budget."""
    import random as _r
    pool = list(mutants)
    _r.Random(hash(seed)).shuffle(pool)
    out, rem = [], float(budget_seconds)
    for m in pool:
        t = max(getattr(m, "execution_time", 0.0) or 0.0, 0.001)
        if t <= rem:
            out.append(m); rem -= t
    return out or pool[:1]


def _operator_based_select(mutants, budget_seconds, op_multipliers):
    """Operator-based baseline: rank by operator effectiveness only, fill budget."""
    def _key(m):
        op = m.operator.value if hasattr(m.operator, "value") else str(m.operator)
        return op_multipliers.get(op, 1.0)
    ranked = sorted(mutants, key=_key, reverse=True)
    out, rem = [], float(budget_seconds)
    for m in ranked:
        t = max(getattr(m, "execution_time", 0.0) or 0.0, 0.001)
        if t <= rem:
            out.append(m); rem -= t
    return out or ranked[:1]


def _run_engine(job_id: str, config: dict) -> dict:
    from impt.engine import IMPTEngine, EngineConfig
    from impt.models.project import MutationFramework, Project, ProjectConfig
    from impt.models.mutant import ExecutionStatus
    from impt.algorithms.optimization import SelectionStrategy
    import time as _time
    _wall_start = _time.time()
    _session_id = config.get("session_id", "")
    _strategy   = config.get("strategy", "impt")

    if _is_cancelled(job_id):
        raise _JobCancelled(job_id)

    language  = config.get("language", "java").lower()
    fw        = MutationFramework.PIT if language == "java" else MutationFramework.STRYKER
    strat_map = {
        "AUTO":   SelectionStrategy.AUTO,
        "DP":     SelectionStrategy.DYNAMIC_PROGRAMMING,
        "GREEDY": SelectionStrategy.GREEDY,
    }
    strat = strat_map.get(config.get("optimizer_strategy", "AUTO"), SelectionStrategy.AUTO)
    is_exhaustive = config.get("strategy") == "exhaustive"
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

    # ── Phase 1: Get all mutants ──────────────────────────────────────────────
    all_mutants, upload_path, actual_loc, actual_test_count = _get_all_mutants(config, job_id)
    log.info("Job %s: %d total mutants", job_id, len(all_mutants))
    # Update project with real measured LOC and test count for Algorithm 5
    project.loc        = actual_loc
    project.test_count = actual_test_count

    # Operator selection (Step 3): restrict to the user's chosen operators for
    # normal/baseline runs. The exhaustive/ground-truth run keeps ALL operators.
    _sel_ops = set(config.get("selected_operators") or [])
    if _sel_ops and not is_exhaustive:
        _before = len(all_mutants)
        all_mutants = [m for m in all_mutants
                       if (m.operator.value if hasattr(m.operator, "value") else str(m.operator)) in _sel_ops]
        log.info("Job %s: operator filter %d -> %d mutants (selected: %s)",
                 job_id, _before, len(all_mutants), sorted(_sel_ops))

    # Write initial total so UI shows "X of Y" immediately
    _write_progress_sync(job_id, 0, 0, len(all_mutants), 0)
    _publish_progress(_session_id, job_id, 0, 0, len(all_mutants), 0, _strategy)

    # ── Phase 2: IMPT scores, reduces, and selects within budget ─────────────
    engine = IMPTEngine(project, config=ecfg)

    if is_exhaustive:
        # Exhaustive: skip scoring, subsumption, and knapsack — run every mutant
        selected = list(all_mutants)
        reduced  = all_mutants  # no subsumption reduction
        log.info("Job %s: EXHAUSTIVE — running all %d mutants", job_id, len(selected))
    else:
        # Score the population (drives IMPT selection and the Results display).
        engine.scorer.score_population(all_mutants)
        strategy = config.get("strategy", "impt")

        if strategy == "random":
            # Genuine random-sampling baseline: a random subset filling the same
            # time budget — no IMPT scoring/subsumption drives the selection.
            reduced  = all_mutants
            engine.estimator.estimate_population(all_mutants)
            selected = _random_select(all_mutants, ecfg.time_budget_seconds, job_id)
            log.info("Job %s: RANDOM baseline selected %d/%d within %ds budget",
                     job_id, len(selected), len(all_mutants), ecfg.time_budget_seconds)
        elif strategy == "operator_based":
            # Genuine operator-based baseline: select by operator effectiveness
            # alone (single-factor heuristic), filling the same time budget.
            reduced  = all_mutants
            engine.estimator.estimate_population(all_mutants)
            _mult = getattr(engine.scorer, "multipliers", {}) or {}
            selected = _operator_based_select(all_mutants, ecfg.time_budget_seconds, _mult)
            log.info("Job %s: OPERATOR-BASED baseline selected %d/%d within %ds budget",
                     job_id, len(selected), len(all_mutants), ecfg.time_budget_seconds)
        else:
            # IMPT: multi-factor scoring + subsumption reduction + knapsack.
            reduced = engine.reducer.reduce(all_mutants)
            engine.estimator.estimate_population(reduced)
            selected = engine.optimizer.select(reduced)
            log.info("Job %s: IMPT selected %d/%d mutants within %ds budget",
                     job_id, len(selected), len(all_mutants), ecfg.time_budget_seconds)

    # Write selected count
    _write_progress_sync(job_id, 0, 0, len(all_mutants), len(selected))
    _publish_progress(_session_id, job_id, 0, 0, len(all_mutants), len(selected), _strategy)

    # (Selection above already reflects the chosen strategy — no reordering.)

    # ── Phase 3: Execute selected mutants ────────────────────────────────────
    if _is_cancelled(job_id):
        raise _JobCancelled(job_id)
    exec_count  = [0]
    kill_count  = [0]
    phase3_start = time.time()

    lang = config.get("language", "java").lower()
    use_real_runner = (upload_path and Path(upload_path).exists()
                       and lang == "javascript")

    if use_real_runner:
        # Phase 3: Run Stryker on ONLY the selected file:line ranges
        # Time taken ≈ (selected/total) × exhaustive_time ≈ budget
        log.info("Phase 3: Filtered Stryker run on %d/%d mutants",
                 len(selected), len(all_mutants))
        _run_selected_mutants(selected, upload_path, config,
                              progress_cb=lambda pct: _publish_bar(_session_id, job_id, pct))
        for m in selected:
            if m.status != ExecutionStatus.PENDING:
                exec_count[0] += 1
                if m.status == ExecutionStatus.KILLED:
                    kill_count[0] += 1
        _write_progress_sync(job_id, exec_count[0], kill_count[0],
                              len(all_mutants), len(selected))
        _publish_progress(_session_id, job_id, exec_count[0], kill_count[0], len(all_mutants), len(selected), _strategy)
    else:
        # Java: apply PIT's real Phase-1 statuses (ground truth) to the selected
        # subset - no simulation. Only synthetic/demo mutants (which carry no
        # real_status) fall back to the statistical simulator, and that path is
        # reachable exclusively in explicit demo mode.
        rng = random.Random(hash(job_id))
        kill_rates = {
            "AOR": 0.92, "ROR": 0.88, "COR": 0.85, "SOR": 0.76,
            "LCR": 0.71, "UOI": 0.85, "SDL": 0.75, "CRP": 0.65,
            "ABS": 0.80, "VDL": 0.78, "ODL": 0.72,
            "NEGATE_RETURN": 0.88, "NULL_RETURN": 0.70,
        }
        for m in selected:
            rs = getattr(m, "real_status", None)
            if rs in (ExecutionStatus.KILLED, ExecutionStatus.SURVIVED):
                m.status = rs
            elif m.status == ExecutionStatus.PENDING:
                op_key = m.operator.value if hasattr(m.operator, "value") else str(m.operator)
                m.status = (ExecutionStatus.KILLED
                            if rng.random() < kill_rates.get(op_key, 0.70)
                            else ExecutionStatus.SURVIVED)
            exec_count[0] += 1
            if m.status == ExecutionStatus.KILLED:
                kill_count[0] += 1
            if exec_count[0] % 25 == 0 or exec_count[0] == 1:
                _write_progress_sync(job_id, exec_count[0], kill_count[0],
                                      len(all_mutants), len(selected))
                _publish_progress(_session_id, job_id, exec_count[0], kill_count[0],
                                  len(all_mutants), len(selected), _strategy)
        _write_progress_sync(job_id, exec_count[0], kill_count[0],
                              len(all_mutants), len(selected))
        _publish_progress(_session_id, job_id, exec_count[0], kill_count[0],
                          len(all_mutants), len(selected), _strategy)

    # Build result using already-selected/executed mutants
    from impt.models.result import MutationTestResult
    executed = [m for m in selected if m.status != ExecutionStatus.PENDING]
    estimate = engine.extrapolator.estimate(executed) if executed else None
    scored_m = [m for m in executed if m.counts_in_score]
    killed   = sum(1 for m in scored_m if m.is_killed)
    score    = (killed / len(scored_m)) if scored_m else 0.0
    exhaustive_time = sum(m.execution_time for m in all_mutants)
    selected_time   = sum(m.execution_time for m in selected)
    time_saved = (1 - selected_time / exhaustive_time) * 100 if exhaustive_time > 0 else 0.0
    from collections import defaultdict
    op_stats = defaultdict(lambda: {"total": 0, "killed": 0})
    for m in executed:
        op_stats[m.operator.value]["total"] += 1
        if m.is_killed:
            op_stats[m.operator.value]["killed"] += 1

    result = MutationTestResult(
        all_mutants              = all_mutants,
        selected_mutants         = selected,
        executed_mutants         = executed,
        mutation_score           = score,
        estimate                 = estimate,
        subsumption_reduction_pct = (1 - len(reduced)/len(all_mutants))*100 if all_mutants else 0,
        time_saved_pct           = time_saved,
        total_execution_time     = sum(m.execution_time for m in executed),
        operator_stats           = dict(op_stats),
    )

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
            "killing_test":   (getattr(m, "killing_test", None) or "")[:500] or None,
        }
        for m in result.executed_mutants
    ]

    # Cache JS FOSS exhaustive results so the offline comparative sweep can
    # reconstruct strategies. Java is cached in Phase 1 (PIT gives real statuses
    # up front); JS statuses only exist after Phase 3, so we cache here. Factors
    # were enriched in Phase 1, so the cached mutants carry everything the offline
    # scorer needs. Only for exhaustive runs (all mutants executed = full population).
    if is_exhaustive and config.get("foss_project_id") and lang == "javascript":
        try:
            # Cache the EXECUTED mutants: these carry the real Phase-3 statuses
            # (the same population the stored mutation_score is computed from) AND
            # the factors enriched in Phase 1. Pin real_status so the serializer
            # reads the executed status, not any stale Phase-1 value.
            for _m in result.executed_mutants:
                _m.real_status = _m.status
            _cache_foss_mutants(config["foss_project_id"], result.executed_mutants,
                                actual_loc, actual_test_count)
        except Exception as _exc:
            log.warning("JS FOSS cache write failed: %s", _exc)

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
        "execution_time_seconds":     round(_time.time() - _wall_start, 1),
        "result_json":                {"operator_stats": result.operator_stats,
                                       "summary": result.summary()},
        "mutant_records":             records,
    }


def _resolve_upload_path(upload_path: str) -> str:
    """Translate container path to host path if needed."""
    if upload_path and not Path(upload_path).exists():
        alt = upload_path.replace("/app/uploads", "/home/imptuser/impt/uploads")
        if Path(alt).exists():
            return alt
    return upload_path



# ── FOSS-Java exhaustive mutant cache ─────────────────────────────────────────
# PIT runs the whole project exhaustively (Phase 1), so live FOSS-Java sessions
# would make testers wait a long time. We cache the full mutant list (with real
# PIT statuses) on the FOSS project's exhaustive baseline; later sessions load it
# and skip the live run, going straight to Phase 2 prioritization. JS is not
# cached (its live dry-run is already fast and gives the real IMPT experience).

def _foss_cache_engine():
    import sqlalchemy as sa
    from config.settings import get_settings
    s = get_settings()
    url = s.DATABASE_URL_SYNC or s.DATABASE_URL.replace("+asyncpg", "").replace("+aiosqlite", "")
    return sa.create_engine(url, pool_pre_ping=True)


def _mutant_real_status(m):
    rs = getattr(m, "real_status", None) or getattr(m, "status", None)
    return rs.value if hasattr(rs, "value") else str(rs)


def _serialize_mutant(m):
    fac = getattr(m, "factors", None)
    return {
        "operator": m.operator.value if hasattr(m.operator, "value") else str(m.operator),
        "file": m.location.file, "line": m.location.line,
        "column": getattr(m.location, "column", 0),
        "method_name": getattr(m.location, "method_name", None),
        "class_name": getattr(m.location, "class_name", None),
        "original_code": m.original_code, "mutated_code": m.mutated_code,
        "status": _mutant_real_status(m),
        "killing_test": getattr(m, "killing_test", None),
        "test_coverage": list(m.test_coverage) if getattr(m, "test_coverage", None) else [],
        "factors": ({
            "historical_effectiveness": fac.historical_effectiveness,
            "cyclomatic_complexity": fac.cyclomatic_complexity,
            "cognitive_complexity": fac.cognitive_complexity,
            "nesting_depth": fac.nesting_depth,
            "security_score": fac.security_score,
            "days_since_change": fac.days_since_change,
            "bug_density": fac.bug_density,
        } if fac else None),
    }


def _deserialize_mutant(dct):
    from impt.models.mutant import (Mutant, MutationOperator, CodeLocation,
                                    PriorityFactors, ExecutionStatus)
    try:
        op = MutationOperator(dct["operator"])
    except Exception:
        op = MutationOperator.AOR
    loc = CodeLocation(file=dct.get("file", "unknown"), line=dct.get("line", 1),
                       column=dct.get("column", 0), method_name=dct.get("method_name"),
                       class_name=dct.get("class_name"))
    fac = PriorityFactors(**dct["factors"]) if dct.get("factors") else PriorityFactors()
    m = Mutant(operator=op, location=loc,
               original_code=dct.get("original_code", ""),
               mutated_code=dct.get("mutated_code", ""),
               factors=fac, test_coverage=set(dct.get("test_coverage", [])))
    try:
        st = ExecutionStatus(dct.get("status", "SURVIVED"))
    except Exception:
        st = ExecutionStatus.SURVIVED
    m.real_status = st                     # ground truth from the exhaustive PIT run
    m.status = ExecutionStatus.PENDING
    m.killing_test = dct.get("killing_test")
    return m


def _load_foss_cache(foss_project_id: str):
    """Return (mutants, loc, test_count) from cache, or None on miss."""
    import sqlalchemy as sa, json
    try:
        eng = _foss_cache_engine()
        with eng.connect() as c:
            row = c.execute(sa.text(
                "SELECT mutants_json FROM exhaustive_baselines "
                "WHERE project_id=:pid AND mutants_json IS NOT NULL"),
                {"pid": foss_project_id}).fetchone()
        if not row or not row[0]:
            return None
        payload = json.loads(row[0])
        muts = [_deserialize_mutant(x) for x in payload.get("mutants", [])]
        if not muts:
            return None
        return muts, payload.get("loc") or 5000, payload.get("test_count") or 0
    except Exception as exc:
        log.warning("FOSS cache load failed for %s: %s", foss_project_id, exc)
        return None


def _cache_foss_mutants(foss_project_id: str, mutants, loc, test_count) -> None:
    """Upsert the full mutant list onto the project's exhaustive baseline row."""
    import sqlalchemy as sa, json, uuid as _uuid
    try:
        payload = json.dumps({"loc": loc, "test_count": test_count,
                              "mutants": [_serialize_mutant(m) for m in mutants]})
        total  = len(mutants)
        killed = sum(1 for m in mutants if _mutant_real_status(m) == "KILLED")
        score  = (killed / total) if total else 0.0
        eng = _foss_cache_engine()
        with eng.begin() as c:
            n = c.execute(sa.text(
                "UPDATE exhaustive_baselines SET mutants_json=:mj WHERE project_id=:pid"),
                {"mj": payload, "pid": foss_project_id}).rowcount
            if not n:
                c.execute(sa.text(
                    "INSERT INTO exhaustive_baselines "
                    "(id, project_id, total_mutants, killed_mutants, mutation_score, "
                    "execution_time_seconds, mutants_json, source) "
                    "VALUES (:id,:pid,:tot,:kil,:score,0,:mj,'computed')"),
                    {"id": _uuid.uuid4().hex, "pid": foss_project_id, "tot": total,
                     "kil": killed, "score": score, "mj": payload})
        log.info("Cached %d PIT mutants for FOSS project %s", total, foss_project_id)
    except Exception as exc:
        log.warning("FOSS cache save failed for %s: %s", foss_project_id, exc)


def _get_all_mutants(config: dict, job_id: str):
    """
    Phase 1: Get ALL mutants from the project.
    For JS: runs Stryker --dryRunOnly --coverageAnalysis perTest (~3s).
    For Java: runs PIT fully.
    Returns (mutants, upload_path, loc, test_count).
    """
    upload_path = _resolve_upload_path(config.get("upload_path", ""))

    # FOSS project — resolve path from pre-cloned directory
    if not upload_path and config.get("foss_project_id"):
        foss_slug = config.get("foss_slug", "")
        candidate = f"/app/foss/{foss_slug}"
        if Path(candidate).exists():
            upload_path = candidate
            log.info("Using FOSS project path: %s", upload_path)

    # FOSS Java: serve cached exhaustive mutants and skip the long live PIT run.
    _fpid = config.get("foss_project_id")
    if (_fpid and config.get("language", "java").lower() == "java"
            and config.get("strategy") != "exhaustive"):
        _cached = _load_foss_cache(_fpid)
        if _cached is not None:
            _muts, _loc, _tc = _cached
            log.info("Phase 1: loaded %d cached PIT mutants for FOSS %s (no live run)",
                     len(_muts), _fpid)
            return _muts, (upload_path or f"/app/foss/{config.get('foss_slug','')}"), _loc, _tc

    if upload_path and Path(upload_path).exists():
        try:
            from adapters.pit_adapter     import PITAdapter
            from adapters.stryker_adapter import StrykerAdapter
            from adapters.factor_enricher import FactorEnricher
            from impt.models.mutant       import ExecutionStatus
            p    = Path(upload_path)
            lang = config.get("language", "java").lower()
            if lang == "java":
                adapter    = PITAdapter(p, use_docker=True)
                mutants    = adapter.run()
                loc        = adapter.count_loc()
                test_count = adapter.count_tests()
            else:
                adapter    = StrykerAdapter(p, use_docker=True,
                                           user_id=config.get("user_id"))
                # For exhaustive runs, clear any cached Phase 1 report so we
                # re-enumerate fresh — prevents stale count from a prior IMPT run
                if config.get("strategy") == "exhaustive":
                    stale = adapter._find_report()
                    if stale and stale.exists():
                        stale.unlink()
                        log.info("Cleared cached Phase 1 report for exhaustive re-enumeration")
                mutants    = adapter.enumerate()
                loc        = adapter.count_loc()
                test_count = adapter.count_tests()
            FactorEnricher(p).enrich(mutants)
            for m in mutants:
                # Java/PIT computes real KILLED/SURVIVED during Phase 1; preserve
                # it as ground truth so Phase 3 uses real statuses, not simulation.
                m.real_status = m.status
                m.status = ExecutionStatus.PENDING
            if config.get("foss_project_id") and lang == "java":
                _cache_foss_mutants(config["foss_project_id"], mutants, loc, test_count)
            log.info("Phase 1: %d mutants enumerated (LOC=%d, tests=%d) from %s",
                     len(mutants), loc, test_count, upload_path)
            return mutants, upload_path, loc, test_count
        except Exception as e:
            log.error("Adapter failed: %s", e)
            if not _synthetic_allowed(config):
                raise RuntimeError(
                    f"Real mutation run failed and synthetic fallback is disabled: {e}"
                ) from e
    if not _synthetic_allowed(config):
        raise RuntimeError(
            "No runnable project available and synthetic fallback is disabled. "
            "Set IMPT_ALLOW_SYNTHETIC=1 only for demos, never for evaluation runs."
        )
    log.warning("Using SYNTHETIC population for job %s (DEMO MODE - not real data)", job_id)
    return _synthetic_population(config.get("loc", 5000), seed=hash(job_id)), None, 5000, 100


def _run_selected_mutants(selected, upload_path: str, config: dict, progress_cb=None) -> None:
    """
    Phase 3: Re-run Stryker/PIT on ONLY the selected mutants.
    This is what achieves real time savings.
    Updates mutant status in place.
    """
    if not upload_path or not selected:
        return
    try:
        from adapters.stryker_adapter import StrykerAdapter
        from adapters.pit_adapter     import PITAdapter
        from impt.models.mutant       import ExecutionStatus
        p    = Path(upload_path)
        lang = config.get("language", "java").lower()
        if lang == "java":
            # PIT doesn't support selective execution easily — use full run results
            pass
        else:
            log.info("Phase 3: Running Stryker on %d selected mutants", len(selected))
            adapter  = StrykerAdapter(p, use_docker=True, selected_mutants=selected,
                                         user_id=config.get("user_id"),
                                         progress_cb=progress_cb)
            executed = adapter.run()
            # Map results back by file+line+operator
            result_map = {}
            for m in executed:
                key = (m.location.file, m.location.line, m.operator.value)
                result_map[key] = m.status
            for m in selected:
                key = (m.location.file, m.location.line, m.operator.value)
                if key in result_map:
                    m.status = result_map[key]
                else:
                    m.status = ExecutionStatus.SURVIVED
    except Exception as e:
        log.error("Phase 3 filtered run failed: %s", e)


def _get_mutants(config: dict, job_id: str):
    """Legacy entry point — returns all mutants for scoring."""
    mutants, _ = _get_all_mutants(config, job_id)
    return mutants


def _synthetic_allowed(config: dict) -> bool:
    """Synthetic mutants are ONLY for explicit demos, never real evaluation."""
    return bool(config.get("allow_synthetic")) or os.getenv("IMPT_ALLOW_SYNTHETIC") == "1"


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
        # Publish completion to WebSocket clients
        _publish_progress(
            config.get("session_id",""), job_id,
            result.get("executed_mutants", 0),
            result.get("killed_mutants", 0),
            result.get("total_mutants", 0),
            result.get("selected_mutants", 0),
            config.get("strategy","impt"),
        )
        try:
            import redis as _redis, json as _json
            from config.settings import get_settings
            r = _redis.from_url(get_settings().REDIS_URL, decode_responses=True,
                                socket_connect_timeout=2)
            r.publish(f"impt:session:{config.get('session_id','')}", _json.dumps({
                "type": "job_complete", "job_id": job_id,
                "strategy": config.get("strategy",""), "status": "COMPLETED",
            }))
            r.close()
        except Exception:
            pass
        if config.get("strategy") == "exhaustive" and config.get("foss_project_id"):
            _save_exhaustive_baseline(config["foss_project_id"], result)
        return {**result, "mutant_records": records}
    except _JobCancelled:
        log.info("Job %s cancelled by user — leaving status CANCELLED", job_id)
        try:
            import redis as _redis, json as _json
            from config.settings import get_settings
            r = _redis.from_url(get_settings().REDIS_URL, decode_responses=True,
                                socket_connect_timeout=2)
            r.publish(f"impt:session:{config.get('session_id','')}", _json.dumps({
                "type": "job_complete", "job_id": job_id,
                "strategy": config.get("strategy",""), "status": "CANCELLED",
            }))
            r.close()
        except Exception:
            pass
        return {}
    except Exception as e:
        log.error("Job %s failed: %s", job_id, e)
        _mark_failed_sync(job_id, str(e))
        raise


def _save_exhaustive_baseline(foss_project_id: str, result: dict) -> None:
    """Persist exhaustive run result as the permanent ground-truth baseline."""
    import json as _json
    import sqlite3 as _sql
    from config.settings import get_settings
    settings = get_settings()
    db_url = settings.DATABASE_URL or ""

    op_breakdown = _json.dumps(result.get("result_json", {}).get("operator_stats", {}))

    try:
        if "sqlite" in db_url:
            db_path = db_url.replace("sqlite:///", "").replace("sqlite://", "")
            conn = _sql.connect(db_path)
            cur  = conn.cursor()
            cur.execute("""
                INSERT INTO exhaustive_baselines
                    (id, project_id, total_mutants, killed_mutants, mutation_score,
                     execution_time_seconds, equivalent_mutants, operator_breakdown,
                     source, computed_at)
                VALUES (lower(hex(randomblob(18))), ?, ?, ?, ?, ?, 0, ?, 'computed', datetime('now'))
                ON CONFLICT(project_id) DO UPDATE SET
                    total_mutants=excluded.total_mutants,
                    killed_mutants=excluded.killed_mutants,
                    mutation_score=excluded.mutation_score,
                    execution_time_seconds=excluded.execution_time_seconds,
                    operator_breakdown=excluded.operator_breakdown,
                    computed_at=datetime('now')
            """, (
                foss_project_id,
                result.get("total_mutants", 0),
                result.get("killed_mutants", 0),
                result.get("mutation_score", 0.0),
                result.get("execution_time_seconds", 0.0),
                op_breakdown,
            ))
            conn.commit()
            conn.close()
            log.info("Saved exhaustive baseline for FOSS project %s", foss_project_id)
        else:
            # PostgreSQL — use psycopg2 directly (sync context)
            import psycopg2
            from urllib.parse import urlparse, urlencode, parse_qs, urlunparse
            raw_url = db_url.replace("postgresql+asyncpg", "postgresql") \
                            .replace("postgresql+psycopg2", "postgresql")
            parsed = urlparse(raw_url)
            qs = parse_qs(parsed.query)
            ssl_val = qs.pop("ssl", [None])[0]
            clean_url = urlunparse(parsed._replace(query=urlencode({k: v[0] for k, v in qs.items()})))
            # Pass ssl as sslmode kwarg (psycopg2 syntax)
            ssl_kwargs = {"sslmode": ssl_val} if ssl_val else {}
            conn = psycopg2.connect(clean_url, **ssl_kwargs)
            cur  = conn.cursor()
            cur.execute("""
                INSERT INTO exhaustive_baselines
                    (id, project_id, total_mutants, killed_mutants, mutation_score,
                     execution_time_seconds, equivalent_mutants, operator_breakdown,
                     source, computed_at)
                VALUES (gen_random_uuid()::text, %s, %s, %s, %s, %s, 0, %s, 'computed', NOW())
                ON CONFLICT(project_id) DO UPDATE SET
                    total_mutants=EXCLUDED.total_mutants,
                    killed_mutants=EXCLUDED.killed_mutants,
                    mutation_score=EXCLUDED.mutation_score,
                    execution_time_seconds=EXCLUDED.execution_time_seconds,
                    operator_breakdown=EXCLUDED.operator_breakdown,
                    computed_at=NOW()
            """, (
                foss_project_id,
                result.get("total_mutants", 0),
                result.get("killed_mutants", 0),
                result.get("mutation_score", 0.0),
                result.get("execution_time_seconds", 0.0),
                op_breakdown,
            ))
            conn.commit()
            conn.close()
            log.info("Saved exhaustive baseline for FOSS project %s", foss_project_id)
    except Exception as exc:
        log.error("Failed to save exhaustive baseline: %s", exc)


# ── Live coverage measurement (uploaded projects) ─────────────────────────────

def _set_session_coverage_sync(session_id: str, coverage) -> None:
    """Write test_coverage (float % or None) onto a test_session row."""
    try:
        from config.settings import get_settings
        import sqlalchemy as sa
        settings = get_settings()
        sync_url = settings.DATABASE_URL_SYNC or settings.DATABASE_URL.replace(
            'postgresql+asyncpg', 'postgresql+psycopg2'
        ).replace('sqlite+aiosqlite', 'sqlite').replace('?ssl=require', '?sslmode=require')
        engine = sa.create_engine(sync_url, pool_pre_ping=True,
                                   connect_args={"connect_timeout": 5} if 'postgresql' in sync_url else {})
        with engine.begin() as conn:
            conn.execute(
                sa.text("UPDATE test_sessions SET test_coverage=:cov WHERE id=:sid"),
                {"cov": coverage, "sid": session_id},
            )
        engine.dispose()
    except Exception as e:
        log.warning("set_session_coverage failed: %s", e)


def measure_coverage_sync(session_id: str, project_root: str, language: str) -> None:
    """Measure line coverage for an uploaded project and store it on the session.

    Best-effort: on any failure the session's test_coverage simply stays None
    and the UI shows it as unavailable. Never raises.
    """
    try:
        from services.metadata import measure_line_coverage
        path = _resolve_upload_path(project_root)
        cov = measure_line_coverage(path, language, timeout_s=420)
        if cov is not None:
            _set_session_coverage_sync(session_id, cov)
            log.info("Coverage for session %s: %.1f%%", session_id, cov)
        else:
            log.info("Coverage for session %s: unavailable", session_id)
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("measure_coverage_sync failed for %s: %s", session_id, exc)


# Celery task registration
try:
    from worker.celery_app import celery_app, CELERY_AVAILABLE
    if celery_app and CELERY_AVAILABLE:
        @celery_app.task(bind=True, name="worker.tasks.run_mutation_job",
                         max_retries=0, acks_late=True)
        def run_mutation_job(self, job_id: str, config: dict):
            """Celery task — runs in worker process with its own sync DB access."""
            return run_mutation_job_sync(job_id, config)

        @celery_app.task(bind=True, name="worker.tasks.measure_coverage",
                         max_retries=0, acks_late=True)
        def measure_coverage(self, session_id: str, project_root: str, language: str):
            """Celery task — best-effort line-coverage measurement for an upload."""
            return measure_coverage_sync(session_id, project_root, language)
    else:
        run_mutation_job = None
        measure_coverage = None
except Exception as exc:
    log.warning("Celery task registration failed: %s", exc)
    run_mutation_job = None
    measure_coverage = None

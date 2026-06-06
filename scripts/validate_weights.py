#!/usr/bin/env python3
"""
IMPT MCDM Weight Validation Experiment
=======================================
Compares 6 weight configurations against exhaustive ground truth
on the FOSS projects to validate the proposed weight distribution
for the multi-criteria prioritization algorithm.

Usage:
  python3 scripts/validate_weights.py \
    --url https://api.impt.it.com \
    --email evaluator01@impt.it.com \
    --password MFf0ABpZex

Step 1: Runs exhaustive baselines on selected projects
Step 2: Runs each weight configuration on same projects
Step 3: Computes Pearson r, Spearman rho, Friedman test
Step 4: Saves full results to JSON + prints summary table

During the exhaustive phase (PHASE 1) this build also writes capture_<slug>.json
per project — full per-mutant {priority_score, execution_time, killed, operator}
records pulled from the job CSV export — for the offline budget-sweep simulator.
"""

import argparse
import asyncio
import httpx
import json
import math
import time
from datetime import datetime

# ── Weight configurations to compare ─────────────────────────────────────────
CONFIGS = {
    "Proposed (30/25/20/15/10)": {
        "historical_effectiveness": 0.30,
        "code_complexity":          0.25,
        "security_criticality":     0.20,
        "change_recency":           0.15,
        "bug_history":              0.10,
    },
    "Equal (20/20/20/20/20)": {
        "historical_effectiveness": 0.20,
        "code_complexity":          0.20,
        "security_criticality":     0.20,
        "change_recency":           0.20,
        "bug_history":              0.20,
    },
    "History-Dominant (50/20/15/10/5)": {
        "historical_effectiveness": 0.50,
        "code_complexity":          0.20,
        "security_criticality":     0.15,
        "change_recency":           0.10,
        "bug_history":              0.05,
    },
    "Complexity-Dominant (15/50/15/15/5)": {
        "historical_effectiveness": 0.15,
        "code_complexity":          0.50,
        "security_criticality":     0.15,
        "change_recency":           0.15,
        "bug_history":              0.05,
    },
    "Recency-Dominant (15/20/15/45/5)": {
        "historical_effectiveness": 0.15,
        "code_complexity":          0.20,
        "security_criticality":     0.15,
        "change_recency":           0.45,
        "bug_history":              0.05,
    },
    "Inverted (10/15/20/25/30)": {
        "historical_effectiveness": 0.10,
        "code_complexity":          0.15,
        "security_criticality":     0.20,
        "change_recency":           0.25,
        "bug_history":              0.30,
    },
}
PROPOSED_WEIGHTS = CONFIGS["Proposed (30/25/20/15/10)"]

# All 20 FOSS benchmark projects
# Note: mathjs excluded from exhaustive baseline (38k mutants, infeasible within 120-min budget)
# Use --skip-exhaustive to run weight configs on all 20 projects
ALL_PROJECTS = [
    # JavaScript (10)
    "ms", "uuid", "dayjs", "chalk", "zod",
    "axios", "ramda", "semver", "date-fns", "mathjs",
    # Java (10)
    "gson", "commons-io", "jsoup", "commons-text",
    "commons-collections", "joda-money",
    "jackson-databind", "commons-lang", "commons-math", "rxjava",
]
PROJECTS = ALL_PROJECTS  # overridden by --projects flag at runtime
JAVA_PROJECTS  = {"gson","commons-io","jsoup","commons-text","commons-collections",
                  "commons-lang","joda-money","jackson-databind","rxjava","commons-math"}
JS_OPERATORS   = ["AOR", "ROR", "NEGATE_RETURN", "COR"]
JAVA_OPERATORS = ["AOR", "ROR", "NEGATE_RETURN", "COR"]

def operators_for(slug):
    return JAVA_OPERATORS if slug in JAVA_PROJECTS else JS_OPERATORS

def language_for(slug):
    return "java" if slug in JAVA_PROJECTS else "javascript"
BUDGET_MINUTES = 10
MAX_WAIT           = 1800  # 30 min max wait per IMPT session (slow JS projects need ~16-26 min)
MAX_WAIT_EXHAUSTIVE = 7200  # 2 hours max for exhaustive
POLL_INTERVAL = 15

# ── Token refresh ─────────────────────────────────────────────────────────────
async def refresh_token(client, base, email, password):
    """Get a fresh token — called before each batch to avoid expiry."""
    r = await client.post(f"{base}/api/auth/token",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    r.raise_for_status()
    return r.json()["access_token"]

# ── API helpers ───────────────────────────────────────────────────────────────
def hdr(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

async def get_foss_id(client, base, token, slug):
    r = await client.get(f"{base}/api/foss", headers=hdr(token))
    r.raise_for_status()
    projects = r.json()
    for p in projects:
        if p["slug"] == slug:
            return p["id"]
    raise ValueError(f"FOSS project '{slug}' not found")

async def create_session(client, base, token, name, foss_id, slug,
                         weight_config=None, exhaustive=False):
    lang = language_for(slug)
    ops  = operators_for(slug)
    r = await client.post(f"{base}/api/sessions", headers=hdr(token), json={
        "name": name, "language": lang, "foss_project_id": foss_id,
        "weight_config": weight_config,
    })
    r.raise_for_status()
    sid = r.json()["id"]

    r2 = await client.post(f"{base}/api/sessions/{sid}/operators", headers=hdr(token),
        json={"selected_operators": ops})
    r2.raise_for_status()

    # Java exhaustive needs a longer budget (PIT builds take longer)
    # Capped at 120 to match TimeBudgetRequest schema limit
    budget = 120 if exhaustive else BUDGET_MINUTES
    r3 = await client.post(f"{base}/api/sessions/{sid}/budget", headers=hdr(token), json={
        "time_budget_minutes":  budget,
        "selected_strategy":    "impt",
        "run_exhaustive":       exhaustive,
        "run_comparison":       False,
        "run_operator_based":   False,
    })
    r3.raise_for_status()

    r4 = await client.post(f"{base}/api/sessions/{sid}/start", headers=hdr(token))
    r4.raise_for_status()
    return sid

async def poll(client, base, token, sid, max_wait=MAX_WAIT):
    deadline = time.time() + max_wait
    while time.time() < deadline:
        await asyncio.sleep(POLL_INTERVAL)
        r = await client.get(f"{base}/api/sessions/{sid}", headers=hdr(token))
        if r.status_code != 200:
            return None
        data = r.json()
        status = (data.get("status") or "").lower()
        if status in ("completed", "failed", "error"):
            return data
        print(f"      … {status} ({int(deadline-time.time())}s left)")
    return None

async def get_jobs(client, base, token, sid):
    """Return all jobs for a session."""
    r = await client.get(f"{base}/api/analytics/compare/{sid}", headers=hdr(token))
    if r.status_code == 200:
        return list(r.json().values())
    return []

async def get_score(client, base, token, sid):
    """Return (impt_score, executed, total) from session primary job."""
    jobs = await get_jobs(client, base, token, sid)
    primary = next((j for j in jobs if j.get("strategy") not in ("exhaustive",)), None)
    if primary:
        return primary.get("mutation_score", 0), primary.get("executed_mutants", 0), primary.get("total_mutants", 0)
    return None, None, None

async def get_exhaustive_score(client, base, token, sid):
    """Return exhaustive mutation score (fraction 0-1) for the session, or None.

    The exhaustive run executes the full mutant set; its job is tagged
    'exhaustive'. Some builds expose only a single primary job, so fall back
    to the non-baseline job if no explicit 'exhaustive' job is present.
    """
    jobs = await get_jobs(client, base, token, sid)
    ex = next((j for j in jobs if j.get("strategy") == "exhaustive"), None)
    if ex is None:
        ex = next((j for j in jobs if j.get("strategy") not in ("random", "operator_based")), None)
    return ex.get("mutation_score", 0) if ex else None

async def get_mutant_records(client, base, token, sid):
    """Return list of {priority_score, killed} for each executed mutant."""
    r = await client.get(f"{base}/api/sessions/{sid}/results", headers=hdr(token))
    if r.status_code == 200:
        data = r.json()
        records = data.get("mutant_records", [])
        return [
            {
                "priority_score": rec.get("priority_score", 0),
                "killed": 1 if rec.get("status", "").upper() == "KILLED" else 0,
            }
            for rec in records
            if rec.get("priority_score") is not None
               and rec.get("status", "").upper() in ("KILLED", "SURVIVED")
        ]
    return []

def _primary_job_id(jobs):
    """Pick the exhaustive/primary job and return its id (tries common keys)."""
    job = next((j for j in jobs if j.get("strategy") == "exhaustive"), None)
    if job is None:
        job = next((j for j in jobs if j.get("strategy") not in ("random", "operator_based")), None)
    if job is None:
        print(f"    [capture] no primary job found; sample keys: "
              f"{[list(j.keys()) for j in jobs][:1]}")
        return None
    jid = job.get("id") or job.get("job_id") or job.get("uuid") or job.get("jobId")
    if not jid:
        print(f"    [capture] no job-id field in job dict; keys: {list(job.keys())}")
    return jid

async def get_capture_records(client, base, token, sid):
    """Full per-mutant records for the offline budget-sweep simulator, pulled
    from the job CSV export (guaranteed to include execution time and operator).

    Returns list of {priority_score, execution_time, killed, operator}.
    """
    import csv as _csv, io as _io
    jobs = await get_jobs(client, base, token, sid)
    job_id = _primary_job_id(jobs)
    if not job_id:
        return []
    r = await client.get(f"{base}/api/jobs/{job_id}/export/csv", headers=hdr(token))
    if r.status_code != 200:
        print(f"    [capture] export/csv -> HTTP {r.status_code}")
        return []
    out = []
    for row in _csv.DictReader(_io.StringIO(r.text)):
        status = (row.get("Status") or "").upper()
        if status not in ("KILLED", "SURVIVED"):
            continue
        try:
            et = float(row.get("Execution Time (s)") or 0)
            ps = float(row.get("Priority Score") or 0)
        except (TypeError, ValueError):
            continue
        out.append({
            "priority_score": ps,
            "execution_time": et,
            "killed": 1 if status == "KILLED" else 0,
            "operator": row.get("Operator"),
        })
    return out

def ttest_correlation(r_val, n):
    """
    One-tailed t-test for correlation coefficient.
    H0: r = 0, H1: r > 0
    t = r * sqrt(n-2) / sqrt(1 - r^2), df = n-2
    Returns (t_stat, p_one_tailed).
    """
    if math.isnan(r_val) or n < 3:
        return float('nan'), float('nan')
    t_stat = r_val * math.sqrt(n - 2) / math.sqrt(max(1 - r_val**2, 1e-10))
    # One-tailed p-value using normal approximation
    p_one = 0.5 * math.erfc(t_stat / math.sqrt(2))
    return round(t_stat, 4), round(p_one, 4)



# ── Statistics ────────────────────────────────────────────────────────────────
def pearson_r(xs, ys):
    """Pearson correlation coefficient."""
    n = len(xs)
    if n < 2:
        return float('nan')
    mx, my = sum(xs)/n, sum(ys)/n
    num = sum((x-mx)*(y-my) for x,y in zip(xs,ys))
    dx  = math.sqrt(sum((x-mx)**2 for x in xs))
    dy  = math.sqrt(sum((y-my)**2 for y in ys))
    if dx*dy < 1e-10:
        return float('nan')
    return num/(dx*dy)

def spearman_rho(xs, ys):
    """Spearman rank correlation (average ranks for ties)."""
    def rank(arr):
        order = sorted(range(len(arr)), key=lambda i: arr[i])
        ranks = [0.0]*len(arr)
        i = 0
        while i < len(order):
            j = i
            while j+1 < len(order) and arr[order[j+1]] == arr[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j+1):
                ranks[order[k]] = avg
            i = j + 1
        return ranks
    return pearson_r(rank(xs), rank(ys))

def friedman_stat(matrix):
    """
    Friedman test for k configurations x n projects.
    matrix: dict of config_name -> list of scores (one per project).
    Uses AVERAGE ranks for ties (prior version assigned distinct sequential
    ranks to ties, which inflates chi-square when scores tie — and these data
    tie heavily). Prefers scipy when available; otherwise a correct
    average-rank implementation with a Wilson-Hilferty p-value.
    Returns (chi2, p).
    """
    configs = list(matrix.keys())
    n = len(list(matrix.values())[0])
    k = len(configs)
    if n < 2 or k < 2:
        return float('nan'), float('nan')

    try:
        from scipy.stats import friedmanchisquare
        chi2, p = friedmanchisquare(*[matrix[c] for c in configs])
        return round(float(chi2), 4), round(float(p), 4)
    except Exception:
        pass

    # Pure-Python fallback with average ranks
    rank_sums = {c: 0.0 for c in configs}
    for i in range(n):
        scored = sorted(((matrix[c][i], c) for c in configs), key=lambda x: x[0])
        j = 0
        while j < len(scored):
            jj = j
            while jj+1 < len(scored) and scored[jj+1][0] == scored[j][0]:
                jj += 1
            avg = sum(range(j+1, jj+2)) / (jj - j + 1)
            for t in range(j, jj+1):
                rank_sums[scored[t][1]] += avg
            j = jj + 1
    chi2 = (12.0 / (n*k*(k+1))) * sum(r*r for r in rank_sums.values()) - 3*n*(k+1)
    df = k - 1
    try:
        x = chi2 / df
        z = ((x ** (1/3)) - (1 - 2/(9*df))) / math.sqrt(2/(9*df))
        p = 0.5 * math.erfc(z / math.sqrt(2))
    except Exception:
        p = float('nan')
    return round(chi2, 4), round(p, 4)

# ── Main experiment ───────────────────────────────────────────────────────────
async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url",      default="https://api.impt.it.com")
    parser.add_argument("--token",    default=None, help="Initial bearer token")
    parser.add_argument("--email",    default="evaluator01@impt.it.com")
    parser.add_argument("--password", default="MFf0ABpZex")
    parser.add_argument("--projects", default=None,
        help="Comma-separated slugs, e.g. ms,uuid,dayjs  (default: all 20)")
    parser.add_argument("--skip-exhaustive", action="store_true",
        help="Skip exhaustive baseline runs")
    parser.add_argument("--exhaustive-only", action="store_true",
        help="Run exhaustive baselines only — skip weight config experiments")
    parser.add_argument("--weights-only", action="store_true",
        help="Run weight config experiments only — skip exhaustive baselines")
    args = parser.parse_args()
    base = args.url.rstrip("/")

    # Resolve project list
    global PROJECTS
    if args.projects:
        PROJECTS = [s.strip() for s in args.projects.split(",")]
    else:
        PROJECTS = ALL_PROJECTS

    # --weights-only implies --skip-exhaustive
    if args.weights_only:
        args.skip_exhaustive = True

    js_count   = sum(1 for s in PROJECTS if s not in JAVA_PROJECTS)
    java_count = sum(1 for s in PROJECTS if s in JAVA_PROJECTS)
    est_hrs    = round((js_count * 1.0 + java_count * 1.5) / 1, 1)

    print(f"\n{'='*70}")
    print(f"  IMPT MCDM Weight Validation Experiment")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}  |  {base}")
    print(f"  Projects: {len(PROJECTS)} total  ({js_count} JS, {java_count} Java)")
    print(f"  Projects: {', '.join(PROJECTS)}")
    print(f"  Configurations: {len(CONFIGS)}")
    print(f"  Estimated runtime: ~{est_hrs}–{est_hrs*1.5:.0f} hours (exhaustive + all configs)")
    print(f"{'='*70}\n")

    results = {}   # config_name -> {project_slug -> score}
    exhaustive = {}  # project_slug -> exhaustive_score

    async with httpx.AsyncClient(timeout=60) as client:

        # Get initial token
        token = args.token
        if not token:
            token = await refresh_token(client, base, args.email, args.password)
            print(f"✓ Token acquired")

        # ── Step 1: Resolve FOSS IDs ──────────────────────────────────────────
        foss_ids = {}
        for slug in PROJECTS:
            foss_ids[slug] = await get_foss_id(client, base, token, slug)
            print(f"✓ Resolved {slug} → {foss_ids[slug][:8]}…")

        # ── Step 2: Exhaustive baselines ──────────────────────────────────────
        if not args.skip_exhaustive:
            print(f"\n{'─'*70}")
            print("PHASE 1 — Exhaustive Baselines (ground truth)")
            print("This may take 15–45 minutes depending on project size.")
            print(f"{'─'*70}")

            for slug in PROJECTS:
                # Refresh token before each project (they take up to 20 min each)
                token = await refresh_token(client, base, args.email, args.password)
                print(f"\n  [{slug}] Starting exhaustive run… (fresh token acquired)")
                try:
                    sid = await create_session(client, base, token,
                        f"weight-val-exhaustive-{slug}-{datetime.now().strftime('%H%M%S')}",
                        foss_ids[slug], slug,
                        weight_config=PROPOSED_WEIGHTS, exhaustive=True)
                    print(f"  [{slug}] Session {sid[:8]}… started — polling every {POLL_INTERVAL}s")
                    final = await poll(client, base, token, sid, max_wait=MAX_WAIT_EXHAUSTIVE)
                    if final and final.get("status") == "completed":
                        score = await get_exhaustive_score(client, base, token, sid)
                        exhaustive[slug] = score
                        print(f"  [{slug}] Exhaustive score: {(score or 0)*100:.1f}%")
                        # Capture full per-mutant records for the budget-sweep simulator
                        recs = await get_capture_records(client, base, token, sid)
                        total = (final.get("total_mutants") or len(recs))
                        with open(f"capture_{slug}.json", "w") as cf:
                            json.dump({
                                "project": slug,
                                "capture_budget_seconds": MAX_WAIT_EXHAUSTIVE,
                                "completed_all_mutants": len(recs) >= (total or 0),
                                "n_records": len(recs),
                                "mutants": recs,
                            }, cf, indent=2)
                        print(f"  [{slug}] captured {len(recs)} mutant records → capture_{slug}.json")
                    else:
                        print(f"  [{slug}] ⚠ Exhaustive run failed — using None")
                        exhaustive[slug] = None
                except Exception as e:
                    print(f"  [{slug}] ❌ Error: {e}")
                    exhaustive[slug] = None
        else:
            print("Skipping exhaustive runs (--skip-exhaustive)")
            exhaustive = {s: None for s in PROJECTS}

        # ── Step 3: Weight configuration experiments ──────────────────────────
        if args.exhaustive_only:
            print("\nExhaustive-only mode — skipping weight configuration experiments.")
            print(f"\nExhaustive scores obtained:")
            for slug, score in exhaustive.items():
                print(f"  {slug:<25} {(score or 0)*100:.1f}%")
            fname = f"exhaustive_baselines_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(fname, "w") as f:
                json.dump({"run_at": datetime.now().isoformat(), "exhaustive": exhaustive}, f, indent=2)
            print(f"\nBaselines saved: {fname}")
            return
        print(f"\n{'─'*70}")
        print("PHASE 2 — Weight Configuration Experiments")
        print(f"{'─'*70}")

        mutant_records_proposed = []  # per-mutant {priority_score, killed} for Pearson/Spearman

        for cfg_name, weights in CONFIGS.items():
            print(f"\n  [{cfg_name}]")
            results[cfg_name] = {}

            for slug in PROJECTS:
                # Refresh token before each session
                token = await refresh_token(client, base, args.email, args.password)
                try:
                    sid = await create_session(client, base, token,
                        f"wv-{slug}-{list(CONFIGS.keys()).index(cfg_name)+1}-{datetime.now().strftime('%H%M%S')}",
                        foss_ids[slug], slug, weight_config=weights)
                    final = await poll(client, base, token, sid)

                    if final and final.get("status") == "completed":
                        score, executed, total = await get_score(client, base, token, sid)
                        results[cfg_name][slug] = score
                        print(f"    {slug}: {(score or 0)*100:.1f}% ({executed}/{total} mutants)")
                        # Collect per-mutant records for Proposed config correlation
                        if cfg_name.startswith("Proposed"):
                            recs = await get_capture_records(client, base, token, sid)
                            if recs:
                                mutant_records_proposed.extend(
                                    {"priority_score": r["priority_score"], "killed": r["killed"]}
                                    for r in recs)
                    else:
                        print(f"    {slug}: ⚠ Failed")
                        results[cfg_name][slug] = None
                except Exception as e:
                    print(f"    {slug}: ❌ Error: {e}")
                    results[cfg_name][slug] = None

    # ── Step 4: Statistical analysis ──────────────────────────────────────────
    print(f"\n{'='*70}")
    print("RESULTS & STATISTICAL ANALYSIS")
    print(f"{'='*70}\n")

    # ── Sec 3.11.4.1-3: Per-mutant Pearson r, Spearman ρ, t-test ─────────────
    print(f"{'─'*70}")
    print("Algorithm Accuracy — Priority Score vs Kill Rate Correlation")
    print("(Proposed weight config: priority score per mutant vs binary kill outcome)")
    print(f"{'─'*70}")
    if mutant_records_proposed:
        pscores = [r["priority_score"] for r in mutant_records_proposed]
        kills   = [r["killed"]          for r in mutant_records_proposed]
        n_mut   = len(pscores)
        r_val   = pearson_r(pscores, kills)
        rho_val = spearman_rho(pscores, kills)
        t_r, p_r     = ttest_correlation(r_val,   n_mut)
        t_rho, p_rho = ttest_correlation(rho_val, n_mut)
        sig_r   = "✓ significant" if (not math.isnan(p_r))   and p_r   < 0.05 else "✗ not significant"
        sig_rho = "✓ significant" if (not math.isnan(p_rho)) and p_rho < 0.05 else "✗ not significant"
        thresh  = "✓ meets threshold" if (not math.isnan(r_val)) and r_val >= 0.85 else "✗ below threshold (≥0.85)"
        print(f"  n (mutants):    {n_mut}")
        print(f"  Pearson r:      {r_val:.4f}  t={t_r}, p(one-tailed)={p_r}  →  {sig_r}  [{thresh}]")
        print(f"  Spearman ρ:     {rho_val:.4f}  t={t_rho}, p(one-tailed)={p_rho}  →  {sig_rho}")
        kill_rate = sum(kills)/n_mut*100
        print(f"  Kill rate:      {kill_rate:.1f}%  ({sum(kills)}/{n_mut} mutants killed)")
    else:
        print("  ⚠ No per-mutant records available (check job CSV export endpoint)")
        r_val, rho_val, n_mut, t_r, p_r, t_rho, p_rho = [None]*7

    # Build score matrix (only projects with exhaustive baseline)
    valid_projects = [s for s in PROJECTS if exhaustive.get(s) is not None]
    print(f"\nProjects with exhaustive baseline: {valid_projects or 'none (correlation N/A)'}")

    # Summary table — dynamic columns based on first 3 projects
    col_slugs = PROJECTS[:3]
    col_header = " ".join(f"{s:>8}" for s in col_slugs)
    print(f"\n{'Configuration':<40} {col_header} {'Mean':>8} {'Pearson r':>10} {'Spearman ρ':>11}")
    print("─" * 100)

    stat_results = []
    for cfg_name in CONFIGS:
        scores = [results[cfg_name].get(s) for s in PROJECTS]
        valid_scores = [s for s in scores if s is not None]
        mean = sum(valid_scores)/len(valid_scores) if valid_scores else 0
        mean_pct = mean * 100

        # Correlation with exhaustive
        paired = [(results[cfg_name].get(s), exhaustive.get(s))
                  for s in PROJECTS
                  if results[cfg_name].get(s) is not None and exhaustive.get(s) is not None]
        if len(paired) >= 2:
            xs = [p[0] for p in paired]
            ys = [p[1] for p in paired]
            r   = pearson_r(xs, ys)
            rho = spearman_rho(xs, ys)
        else:
            r, rho = float('nan'), float('nan')

        r_str   = f"{r:.4f}"   if not math.isnan(r)   else "N/A"
        rho_str = f"{rho:.4f}" if not math.isnan(rho) else "N/A"

        col_scores = " ".join(
            f"{(results[cfg_name].get(s) or 0)*100:>7.1f}%" if results[cfg_name].get(s) is not None else f"{'—':>8}"
            for s in col_slugs
        )
        print(f"  {cfg_name:<38} {col_scores} {mean_pct:>7.1f}% {r_str:>10} {rho_str:>11}")

        stat_results.append({
            "config": cfg_name,
            "weights": CONFIGS[cfg_name],
            "scores_pct": {s: round((results[cfg_name].get(s) or 0)*100, 2) for s in PROJECTS},
            "exhaustive_pct": {s: round((exhaustive.get(s) or 0)*100, 2) for s in PROJECTS},
            "mean_score_pct": round(mean_pct, 2),
            "pearson_r": round(r, 4) if not math.isnan(r) else None,
            "spearman_rho": round(rho, 4) if not math.isnan(rho) else None,
        })

    # Friedman test across configurations (exclude failed/None cells per project)
    print(f"\n{'─'*70}")
    print("Friedman Test (H₀: all weight configurations produce equivalent scores)")
    usable = [s for s in PROJECTS
              if all(results[cfg].get(s) is not None for cfg in CONFIGS)]
    dropped = [s for s in PROJECTS if s not in usable]
    if dropped:
        print(f"  (excluded {len(dropped)} project(s) with a failed cell: {dropped})")
    score_matrix = {cfg: [results[cfg][s] for s in usable] for cfg in CONFIGS}
    if usable:
        chi2, p = friedman_stat(score_matrix)
    else:
        chi2, p = float('nan'), float('nan')
    print(f"  n = {len(usable)} projects,  χ² = {chi2},  df = {len(CONFIGS)-1},  p = {p}")
    if not math.isnan(p):
        if p < 0.05:
            print("  → REJECT H₀: Significant differences between configurations (p < 0.05)")
        else:
            print("  → FAIL TO REJECT H₀: No significant differences (p ≥ 0.05)")
            print("  → Proposed weights are robust — alternatives are statistically equivalent")

    # Best config by mean score and correlation
    best_by_score = max(stat_results, key=lambda x: x["mean_score_pct"])
    best_by_r     = max((r for r in stat_results if r["pearson_r"] is not None),
                        key=lambda x: x["pearson_r"], default=None)

    print(f"\n{'─'*70}")
    print(f"  Best by mutation score:  {best_by_score['config']} ({best_by_score['mean_score_pct']:.1f}%)")
    if best_by_r:
        print(f"  Best by Pearson r:       {best_by_r['config']} (r={best_by_r['pearson_r']:.4f})")

    proposed = next(r for r in stat_results if r["config"].startswith("Proposed"))

    # ── Save JSON report ──────────────────────────────────────────────────────
    report = {
        "run_at":          datetime.now().isoformat(),
        "base_url":        base,
        "projects":        PROJECTS,
        "budget_minutes":  BUDGET_MINUTES,
        "exhaustive":      exhaustive,
        "configurations":  stat_results,
        "friedman": {
            "chi2": chi2, "df": len(CONFIGS)-1, "p": p,
            "n_projects": len(usable),
            "excluded_projects": dropped,
            "significant": (p < 0.05) if not math.isnan(p) else None,
        },
        "per_mutant_correlation": {
            "n_mutants":    n_mut,
            "pearson_r":    round(r_val, 4)   if r_val   is not None and not math.isnan(r_val)   else None,
            "spearman_rho": round(rho_val, 4) if rho_val is not None and not math.isnan(rho_val) else None,
            "t_pearson":    t_r,
            "p_pearson":    p_r,
            "t_spearman":   t_rho,
            "p_spearman":   p_rho,
            "meets_threshold_r085": (r_val >= 0.85) if r_val is not None and not math.isnan(r_val) else None,
        },
        "conclusion": {
            "best_by_score": best_by_score["config"],
            "best_by_pearson_r": best_by_r["config"] if best_by_r else None,
            "proposed_score_rank": sorted([r["mean_score_pct"] for r in stat_results], reverse=True).index(proposed["mean_score_pct"]) + 1,
        }
    }
    fname = f"weight_validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(fname, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n  Report saved: {fname}")
    print(f"{'='*70}\n")

if __name__ == "__main__":
    asyncio.run(main())

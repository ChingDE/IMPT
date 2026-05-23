#!/usr/bin/env python3
"""
IMPT MCDM Weight Validation Experiment
=======================================
Compares 6 weight configurations against exhaustive ground truth
on 3 FOSS projects (ms, uuid, dayjs) to validate the proposed
weight distribution for the multi-criteria prioritization algorithm.

Usage:
  python3 scripts/validate_weights.py \
    --url https://api.impt.it.com \
    --token YOUR_TOKEN

Step 1: Runs exhaustive baselines on ms, uuid, dayjs
Step 2: Runs each weight configuration on same projects
Step 3: Computes Pearson r, Spearman rho, Friedman test
Step 4: Saves full results to JSON + prints summary table
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

# Default 15 projects for full validation (mathjs excluded — 38k mutants not feasible exhaustively)
ALL_PROJECTS = [
    # JavaScript (9 — excl. mathjs)
    "ms", "uuid", "dayjs", "validator-js", "zod", "axios", "ramda", "faker-js", "date-fns",
    # Java (6)
    "gson", "commons-io", "jsoup", "mockito", "commons-collections", "joda-time",
]
PROJECTS = ALL_PROJECTS  # overridden by --projects flag at runtime
JAVA_PROJECTS  = {"gson","commons-io","jsoup","mockito","commons-collections","commons-lang",
                  "joda-time","assertj","rxjava","commons-math"}
JS_OPERATORS   = ["AOR", "ROR", "NEGATE_RETURN", "COR"]
JAVA_OPERATORS = ["AOR", "ROR", "NEGATE_RETURN", "COR"]

def operators_for(slug):
    return JAVA_OPERATORS if slug in JAVA_PROJECTS else JS_OPERATORS

def language_for(slug):
    return "java" if slug in JAVA_PROJECTS else "javascript"
BUDGET_MINUTES = 10
MAX_WAIT           = 900   # 15 min max wait per IMPT session
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
    budget = 180 if (exhaustive and lang == "java") else \
             120 if exhaustive else \
             BUDGET_MINUTES
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
    """Return exhaustive mutation score from same session."""
    jobs = await get_jobs(client, base, token, sid)
    ex = next((j for j in jobs if j.get("strategy") == "exhaustive"), None)
    return ex.get("mutation_score", 0) if ex else None

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
    """Spearman rank correlation."""
    def rank(arr):
        s = sorted(enumerate(arr), key=lambda x: x[1])
        r = [0]*len(arr)
        for rank_i, (orig_i, _) in enumerate(s):
            r[orig_i] = rank_i + 1
        return r
    rx, ry = rank(xs), rank(ys)
    return pearson_r(rx, ry)

def friedman_stat(matrix):
    """
    Friedman test statistic for k configurations × n projects.
    matrix: dict of config_name -> list of scores (one per project).
    Returns chi-squared statistic and p-value approximation.
    """
    configs = list(matrix.keys())
    n = len(list(matrix.values())[0])  # number of projects
    k = len(configs)
    if n < 2 or k < 2:
        return float('nan'), float('nan')

    # Rank within each project (row)
    project_ranks = []
    for proj_i in range(n):
        scores = [(matrix[cfg][proj_i], cfg) for cfg in configs]
        sorted_scores = sorted(scores, key=lambda x: x[0], reverse=True)
        ranks = {cfg: rank+1 for rank, (_, cfg) in enumerate(sorted_scores)}
        project_ranks.append(ranks)

    # Friedman statistic
    rank_sums = {cfg: sum(project_ranks[i][cfg] for i in range(n)) for cfg in configs}
    chi2 = (12.0 / (n * k * (k+1))) * sum(r**2 for r in rank_sums.values()) - 3*n*(k+1)

    # Approximate p-value using chi-squared distribution (df=k-1)
    df = k - 1
    # Approximate using Wilson-Hilferty
    try:
        x = chi2 / df
        z = ((x ** (1/3)) - (1 - 2/(9*df))) / math.sqrt(2/(9*df))
        # Standard normal CDF approximation (upper tail)
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
        help="Comma-separated slugs, e.g. ms,uuid,dayjs  (default: all 15)")
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
                        foss_ids[slug], slug, exhaustive=True)
                    print(f"  [{slug}] Session {sid[:8]}… started — polling every {POLL_INTERVAL}s")
                    final = await poll(client, base, token, sid, max_wait=MAX_WAIT_EXHAUSTIVE)
                    if final and final.get("status") == "completed":
                        score = await get_exhaustive_score(client, base, token, sid)
                        exhaustive[slug] = score
                        print(f"  [{slug}] Exhaustive score: {(score or 0)*100:.1f}%")
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

    # Build score matrix (only projects with exhaustive baseline)
    valid_projects = [s for s in PROJECTS if exhaustive.get(s) is not None]
    print(f"Projects with exhaustive baseline: {valid_projects or 'none (correlation N/A)'}")

    # Summary table
    print(f"\n{'Configuration':<40} {'ms':>8} {'uuid':>8} {'dayjs':>8} {'Mean':>8} {'Pearson r':>10} {'Spearman ρ':>11}")
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

        s0 = f"{(scores[0] or 0)*100:.1f}%" if scores[0] is not None else "—"
        s1 = f"{(scores[1] or 0)*100:.1f}%" if scores[1] is not None else "—"
        s2 = f"{(scores[2] or 0)*100:.1f}%" if scores[2] is not None else "—"

        print(f"  {cfg_name:<38} {s0:>8} {s1:>8} {s2:>8} {mean_pct:>7.1f}% {r_str:>10} {rho_str:>11}")

        stat_results.append({
            "config": cfg_name,
            "weights": CONFIGS[cfg_name],
            "scores_pct": {s: round((results[cfg_name].get(s) or 0)*100, 2) for s in PROJECTS},
            "exhaustive_pct": {s: round((exhaustive.get(s) or 0)*100, 2) for s in PROJECTS},
            "mean_score_pct": round(mean_pct, 2),
            "pearson_r": round(r, 4) if not math.isnan(r) else None,
            "spearman_rho": round(rho, 4) if not math.isnan(rho) else None,
        })

    # Friedman test across configurations
    print(f"\n{'─'*70}")
    print("Friedman Test (H₀: all weight configurations produce equivalent scores)")
    score_matrix = {cfg: [results[cfg].get(s, 0) or 0 for s in PROJECTS] for cfg in CONFIGS}
    chi2, p = friedman_stat(score_matrix)
    print(f"  χ² = {chi2},  df = {len(CONFIGS)-1},  p = {p}")
    if not math.isnan(p):
        if p < 0.05:
            print("  → REJECT H₀: Significant differences between configurations (p < 0.05)")
            print("  → Post-hoc: Proposed configuration comparison with each alternative")
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
    print(f"\n  Proposed weights ranking:")
    sorted_by_r = sorted(stat_results, key=lambda x: x.get("pearson_r") or -99, reverse=True)
    for i, r in enumerate(sorted_by_r, 1):
        marker = " ← PROPOSED" if r["config"].startswith("Proposed") else ""
        print(f"    {i}. {r['config']:<45} r={r['pearson_r'] or 'N/A'}{marker}")

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
            "significant": (p < 0.05) if not math.isnan(p) else None,
        },
        "conclusion": {
            "best_by_score": best_by_score["config"],
            "best_by_pearson_r": best_by_r["config"] if best_by_r else None,
            "proposed_score_rank": sorted_by_score.index(proposed) + 1,
        }
    }
    fname = f"weight_validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(fname, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n  Report saved: {fname}")
    print(f"{'='*70}\n")

if __name__ == "__main__":
    asyncio.run(main())

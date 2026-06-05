#!/usr/bin/env python3
"""
IMPT Comparative Performance Analysis
======================================
Compares three mutation testing strategies across 15 FOSS projects:
  1. IMPT      — Intelligent prioritization (proposed)
  2. Random    — Random mutant selection
  3. Operator  — Operator-based selection (no MCDM scoring)

Uses paired Wilcoxon signed-rank test (non-parametric) and effect size
to determine whether IMPT significantly outperforms alternatives.

Usage:
  python3 scripts/compare_strategies.py \
    --email evaluator01@impt.it.com \
    --password MFf0ABpZex

Flags:
  --projects  Comma-separated slugs (default: all 15)
  --skip-impt Use already-collected IMPT scores (saves time)
  --impt-only Run only IMPT sessions
"""

import argparse
import asyncio
import httpx
import json
import math
import time
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────
ALL_PROJECTS = [
    # JavaScript (6 fast projects — dayjs/semver/date-fns excluded due to >15min runtime)
    "ms", "uuid", "chalk", "zod", "axios", "ramda",
    # Java (10)
    "gson", "commons-io", "jsoup", "commons-text",
    "commons-collections", "joda-money",
    "jackson-databind", "commons-lang", "commons-math", "rxjava",
]
JAVA_PROJECTS  = {"gson","commons-io","jsoup","commons-text","commons-collections",
                  "commons-lang","joda-money","jackson-databind","rxjava","commons-math"}
JS_OPERATORS   = ["AOR", "ROR", "NEGATE_RETURN", "COR"]
JAVA_OPERATORS = ["AOR", "ROR", "NEGATE_RETURN", "COR"]
BUDGET_MINUTES = 10
MAX_WAIT       = 1800  # 30 min — accommodates slow JS projects (~16-26 min)
POLL_INTERVAL  = 15

STRATEGIES = ["impt", "random", "operator_based"]
STRATEGY_LABELS = {
    "impt":           "IMPT (Proposed)",
    "random":         "Random Selection",
    "operator_based": "Operator-Based",
}

# KNOWN_IMPT_SCORES: populated after weight validation with real data
# Previous scores were from synthetic fallback and are invalid
KNOWN_IMPT_SCORES = {}

# ── Helpers ───────────────────────────────────────────────────────────────────
def hdr(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

def language_for(slug):
    return "java" if slug in JAVA_PROJECTS else "javascript"

def operators_for(slug):
    return JAVA_OPERATORS if slug in JAVA_PROJECTS else JS_OPERATORS

async def refresh_token(client, base, email, password):
    r = await client.post(f"{base}/api/auth/token",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    r.raise_for_status()
    return r.json()["access_token"]

async def get_foss_id(client, base, token, slug):
    r = await client.get(f"{base}/api/foss", headers=hdr(token))
    r.raise_for_status()
    for p in r.json():
        if p["slug"] == slug:
            return p["id"]
    raise ValueError(f"FOSS project '{slug}' not found")

async def run_session(client, base, token, name, foss_id, slug, strategy):
    lang = language_for(slug)
    ops  = operators_for(slug)

    r = await client.post(f"{base}/api/sessions", headers=hdr(token),
        json={"name": name, "language": lang, "foss_project_id": foss_id})
    r.raise_for_status()
    sid = r.json()["id"]

    r2 = await client.post(f"{base}/api/sessions/{sid}/operators",
        headers=hdr(token), json={"selected_operators": ops})
    r2.raise_for_status()

    r3 = await client.post(f"{base}/api/sessions/{sid}/budget",
        headers=hdr(token), json={
            "time_budget_minutes":  BUDGET_MINUTES,
            "selected_strategy":    strategy,
            "run_exhaustive":       False,
            "run_comparison":       False,
            "run_operator_based":   False,
        })
    r3.raise_for_status()

    r4 = await client.post(f"{base}/api/sessions/{sid}/start", headers=hdr(token))
    r4.raise_for_status()
    return sid

async def poll(client, base, token, sid):
    deadline = time.time() + MAX_WAIT
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

async def get_score(client, base, token, sid):
    r = await client.get(f"{base}/api/analytics/compare/{sid}", headers=hdr(token))
    if r.status_code == 200:
        jobs = list(r.json().values())
        primary = next((j for j in jobs if j.get("strategy") not in ("exhaustive",)), None)
        if primary:
            return primary.get("mutation_score", 0) * 100
    return None

# ── Statistics ────────────────────────────────────────────────────────────────
def wilcoxon_signed_rank(xs, ys):
    """
    Wilcoxon signed-rank test (two-tailed).
    Tests H0: median difference = 0.
    Returns (W+, W-, p_approx, n_effective).
    """
    diffs = [x - y for x, y in zip(xs, ys) if x != y]
    n = len(diffs)
    if n < 2:
        return None, None, float('nan'), n

    abs_diffs = sorted(enumerate(diffs), key=lambda x: abs(x[1]))
    ranks = {}
    i = 0
    while i < n:
        j = i
        while j < n - 1 and abs(abs_diffs[j][1]) == abs(abs_diffs[j+1][1]):
            j += 1
        avg_rank = (i + j) / 2 + 1
        for k in range(i, j+1):
            ranks[abs_diffs[k][0]] = avg_rank
        i = j + 1

    W_pos = sum(ranks[i] for i, d in enumerate(diffs) if d > 0)
    W_neg = sum(ranks[i] for i, d in enumerate(diffs) if d < 0)
    W = min(W_pos, W_neg)

    # Normal approximation (valid for n >= 10; use with caution for n=15)
    mu    = n * (n + 1) / 4
    sigma = math.sqrt(n * (n + 1) * (2*n + 1) / 24)
    z     = (W - mu) / sigma if sigma > 0 else 0
    p     = 2 * (0.5 * math.erfc(abs(z) / math.sqrt(2)))

    return round(W_pos, 2), round(W_neg, 2), round(p, 4), n

def cohens_d(xs, ys):
    """Cohen's d effect size for paired samples."""
    diffs = [x - y for x, y in zip(xs, ys)]
    n = len(diffs)
    if n < 2:
        return float('nan')
    mean_d = sum(diffs) / n
    sd_d   = math.sqrt(sum((d - mean_d)**2 for d in diffs) / (n - 1))
    return round(mean_d / sd_d, 4) if sd_d > 0 else float('nan')

def effect_label(d):
    d = abs(d)
    if math.isnan(d): return "N/A"
    if d < 0.2: return "negligible"
    if d < 0.5: return "small"
    if d < 0.8: return "medium"
    return "large"

def mean(xs):
    return sum(xs) / len(xs) if xs else 0

# ── Main ──────────────────────────────────────────────────────────────────────
async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url",       default="https://api.impt.it.com")
    parser.add_argument("--email",     default="evaluator01@impt.it.com")
    parser.add_argument("--password",  default="MFf0ABpZex")
    parser.add_argument("--projects",  default=None)
    parser.add_argument("--skip-impt", action="store_true",
        help="Use pre-collected IMPT scores from weight validation run")
    parser.add_argument("--impt-only", action="store_true",
        help="Run IMPT sessions only")
    args = parser.parse_args()
    base = args.url.rstrip("/")

    projects = [s.strip() for s in args.projects.split(",")] \
               if args.projects else ALL_PROJECTS

    print(f"\n{'='*70}")
    print(f"  IMPT Comparative Performance Analysis")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}  |  {base}")
    print(f"  Projects: {len(projects)}  |  Budget: {BUDGET_MINUTES} min/project")
    print(f"  Strategies: IMPT vs Random vs Operator-Based")
    print(f"{'='*70}\n")

    scores = {s: {} for s in STRATEGIES}

    # Pre-load known IMPT scores if skipping
    if args.skip_impt:
        print("Using pre-collected IMPT scores from weight validation run.")
        for slug in projects:
            if slug in KNOWN_IMPT_SCORES:
                scores["impt"][slug] = KNOWN_IMPT_SCORES[slug]
        print(f"Loaded {len(scores['impt'])} IMPT scores.\n")

    strategies_to_run = []
    if not args.skip_impt:
        strategies_to_run.append("impt")
    if not args.impt_only:
        strategies_to_run.extend(["random", "operator_based"])

    async with httpx.AsyncClient(timeout=60) as client:

        token = await refresh_token(client, base, args.email, args.password)
        print("✓ Token acquired")

        foss_ids = {}
        for slug in projects:
            foss_ids[slug] = await get_foss_id(client, base, token, slug)
        print(f"✓ Resolved {len(projects)} FOSS project IDs\n")

        for strategy in strategies_to_run:
            label = STRATEGY_LABELS[strategy]
            print(f"{'─'*70}")
            print(f"  Running: {label}")
            print(f"{'─'*70}")

            for slug in projects:
                token = await refresh_token(client, base, args.email, args.password)
                ts    = datetime.now().strftime('%H%M%S')
                try:
                    sid = await run_session(client, base, token,
                        f"cpa-{strategy[:3]}-{slug}-{ts}",
                        foss_ids[slug], slug, strategy)
                    final = await poll(client, base, token, sid)

                    if final and final.get("status") == "completed":
                        score = await get_score(client, base, token, sid)
                        scores[strategy][slug] = score
                        print(f"  {slug:<25} {score:.1f}%")
                    else:
                        print(f"  {slug:<25} ⚠ Failed")
                        scores[strategy][slug] = None
                except Exception as e:
                    print(f"  {slug:<25} ❌ {e}")
                    scores[strategy][slug] = None
            print()

    # ── Statistical Analysis ──────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print("  RESULTS & STATISTICAL ANALYSIS")
    print(f"{'='*70}\n")

    # Project-level score table
    print(f"  {'Project':<25} {'IMPT':>8} {'Random':>8} {'Operator':>10}")
    print(f"  {'─'*55}")
    for slug in projects:
        i = scores['impt'].get(slug)
        r = scores['random'].get(slug)
        o = scores['operator_based'].get(slug)
        fmt = lambda x: f"{x:.1f}%" if x is not None else "—"
        print(f"  {slug:<25} {fmt(i):>8} {fmt(r):>8} {fmt(o):>10}")

    # Means
    impt_scores = [scores['impt'][s] for s in projects if scores['impt'].get(s) is not None]
    rand_scores = [scores['random'][s] for s in projects if scores['random'].get(s) is not None]
    op_scores   = [scores['operator_based'][s] for s in projects if scores['operator_based'].get(s) is not None]

    print(f"\n  {'Mean':<25} {mean(impt_scores):>7.2f}% {mean(rand_scores):>7.2f}% {mean(op_scores):>9.2f}%")

    # Paired comparisons (IMPT vs each alternative)
    # Use projects where all three have valid scores
    valid = [s for s in projects
             if scores['impt'].get(s) is not None
             and scores['random'].get(s) is not None
             and scores['operator_based'].get(s) is not None]
    n = len(valid)

    xi = [scores['impt'][s]           for s in valid]
    xr = [scores['random'][s]         for s in valid]
    xo = [scores['operator_based'][s] for s in valid]

    print(f"\n{'─'*70}")
    print(f"  Paired Statistical Comparisons (n={n} projects with all three scores)")
    print(f"  Wilcoxon Signed-Rank Test (two-tailed, α=0.05)")
    print(f"{'─'*70}")

    comparisons = [
        ("IMPT vs Random",        xi, xr),
        ("IMPT vs Operator-Based", xi, xo),
    ]

    stat_results = []
    for label, a, b in comparisons:
        Wp, Wn, p, n_eff = wilcoxon_signed_rank(a, b)
        d = cohens_d(a, b)
        sig = "✓ significant" if p < 0.05 else "✗ not significant"
        direction = "IMPT better" if mean(a) > mean(b) else "Alternative better"
        print(f"\n  {label}")
        print(f"    Mean diff:  {mean(a)-mean(b):+.2f} percentage points  ({direction})")
        print(f"    W+ = {Wp},  W- = {Wn},  p = {p}  →  {sig}")
        print(f"    Cohen's d = {d}  ({effect_label(d)} effect)")
        stat_results.append({
            "comparison": label, "mean_impt": mean(a), "mean_alt": mean(b),
            "mean_diff": round(mean(a)-mean(b), 2),
            "W_pos": Wp, "W_neg": Wn, "p": p, "significant": p < 0.05,
            "cohens_d": d, "effect": effect_label(d),
        })

    print(f"\n{'─'*70}")
    print(f"  Summary:")
    print(f"    IMPT mean score:          {mean(impt_scores):.2f}%")
    print(f"    Random mean score:        {mean(rand_scores):.2f}%")
    print(f"    Operator-Based mean:      {mean(op_scores):.2f}%")
    print(f"    IMPT vs Random diff:      {mean(impt_scores)-mean(rand_scores):+.2f} pp")
    print(f"    IMPT vs Operator diff:    {mean(impt_scores)-mean(op_scores):+.2f} pp")
    print(f"{'='*70}")

    # Save
    report = {
        "run_at": datetime.now().isoformat(),
        "projects": projects,
        "budget_minutes": BUDGET_MINUTES,
        "scores": scores,
        "means": {
            "impt": round(mean(impt_scores), 2),
            "random": round(mean(rand_scores), 2),
            "operator_based": round(mean(op_scores), 2),
        },
        "comparisons": stat_results,
    }
    fname = f"comparative_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(fname, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n  Report saved: {fname}\n")

if __name__ == "__main__":
    asyncio.run(main())

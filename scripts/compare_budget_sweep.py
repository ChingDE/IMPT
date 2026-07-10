#!/usr/bin/env python3
"""
compare_budget_sweep.py — OFFLINE comparative budget sweep against exhaustive
ground truth, for every FOSS project that has a cached exhaustive baseline
(mutants_json). Reconstructs each selection strategy at multiple budgets from the
real per-mutant data and measures how well each subset predicts the true
exhaustive mutation score.

This answers the panel directly:
  • "adaptive budgets, not a fixed 10 min"  -> budget is a FRACTION of the mutant
     population (5/10/20/40/70/100%), swept per project.
  • "no advantage / compare stronger baselines" -> IMPT vs random vs
     operator-based vs Offutt's SUFFICIENT operator set, with the HEADLINE being
     correlation-to-ground-truth (accuracy of the selected subset), not raw score.

Run INSIDE the container (needs the impt package + DB env):
  docker compose exec -T worker python scripts/compare_budget_sweep.py
  # optional: --budgets 5,10,20,40,70,100  --out /tmp/sweep

Outputs two CSVs:
  sweep_rows.csv     one row per (project, strategy, budget)
  sweep_summary.csv  per (strategy, budget): mean accuracy + cross-project
                     Pearson/Spearman correlation (when >=3 projects)
"""
import argparse, csv, json, math, os, random, sys

import sqlalchemy as sa

# --- IMPT engine pieces (faithful reuse of the defended scoring/subsumption) ---
from impt.models.mutant import (Mutant, MutationOperator, CodeLocation,
                                 PriorityFactors, ExecutionStatus)
from impt.models.project import Project, ProjectConfig, MutationFramework
from impt.algorithms.scoring import MultiFactorScorer
from impt.algorithms.subsumption import SubsumptionAnalyzer

# Offutt et al. sufficient mutation-operator set (Mothra), mapped to our operators
SUFFICIENT_OPS = {"ABS", "AOR", "LCR", "ROR", "UOI"}
STRATEGIES = ["impt", "random", "operator_based", "offutt_sufficient"]


def _sync_url():
    s = os.environ.get("DATABASE_URL_SYNC")
    if s:
        return s
    return os.environ["DATABASE_URL"].replace("+asyncpg", "").replace("+aiosqlite", "")


def _op(m):
    return m.operator.value if hasattr(m.operator, "value") else str(m.operator)


def _mk_mutant(d):
    try:
        op = MutationOperator(d["operator"])
    except Exception:
        op = MutationOperator.AOR
    loc = CodeLocation(file=d.get("file", "x"), line=d.get("line", 1),
                       column=d.get("column", 0), method_name=d.get("method_name"),
                       class_name=d.get("class_name"))
    fac = PriorityFactors(**d["factors"]) if d.get("factors") else PriorityFactors()
    m = Mutant(operator=op, location=loc, original_code=d.get("original_code", ""),
               mutated_code=d.get("mutated_code", ""), factors=fac,
               test_coverage=set(d.get("test_coverage", [])))
    m._real = (d.get("status") or "SURVIVED").upper()   # ground-truth PIT status
    return m


def _countable(m):
    return m._real not in ("EQUIVALENT", "ERROR", "PENDING", "NON_VIABLE")


def _killed(m):
    return m._real == "KILLED"


def _score(mutants):
    """Mutation score = killed / countable over a mutant list."""
    cnt = [m for m in mutants if _countable(m)]
    if not cnt:
        return None
    return sum(1 for m in cnt if _killed(m)) / len(cnt)


def _select(strategy, mutants, k, reducer, multipliers, seed):
    """Return up to k mutants chosen by the given strategy."""
    if strategy == "impt":
        reduced = reducer.reduce(list(mutants))               # subsumption is part of IMPT
        ranked  = sorted(reduced, key=lambda m: m.priority_score, reverse=True)
        return ranked[:k]
    if strategy == "random":
        pool = list(mutants); random.Random(seed).shuffle(pool)
        return pool[:k]
    if strategy == "operator_based":
        ranked = sorted(mutants, key=lambda m: multipliers.get(_op(m), 1.0), reverse=True)
        return ranked[:k]
    if strategy == "offutt_sufficient":
        suff  = [m for m in mutants if _op(m) in SUFFICIENT_OPS]
        other = [m for m in mutants if _op(m) not in SUFFICIENT_OPS]
        random.Random(seed).shuffle(suff); random.Random(seed + 1).shuffle(other)
        return (suff + other)[:k]                             # sufficient-set first, then fill
    raise ValueError(strategy)


def _pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return (num / (dx * dy)) if dx and dy else None


def _spearman(xs, ys):
    if len(xs) < 3:
        return None
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0] * len(v)
        for rank, i in enumerate(order):
            r[i] = rank
        return r
    return _pearson(ranks(xs), ranks(ys))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--budgets", default="5,10,20,40,70,100")
    ap.add_argument("--out", default="/tmp")
    a = ap.parse_args()
    fracs = [int(x) / 100.0 for x in a.budgets.split(",")]

    eng = sa.create_engine(_sync_url(), pool_pre_ping=True)
    with eng.connect() as c:
        cached = [(r[0], r[1], r[2]) for r in c.execute(sa.text(
            "SELECT project_id, mutation_score, mutants_json "
            "FROM exhaustive_baselines WHERE mutants_json IS NOT NULL"))]
        slugs = {r[0]: r[1] for r in c.execute(sa.text("SELECT id, slug FROM foss_projects"))}

    if not cached:
        sys.exit("No cached baselines (mutants_json) found. Cache Java (and JS) exhaustive runs first.")

    print(f"Found {len(cached)} cached baseline(s): "
          f"{', '.join(slugs.get(pid, pid[:8]) for pid, _, _ in cached)}\n")

    rows = []
    for pid, stored_score, mj in cached:
        slug = slugs.get(pid, pid[:8])
        payload = json.loads(mj)
        mutants = [_mk_mutant(d) for d in payload.get("mutants", [])]
        if not mutants:
            print(f"  {slug}: empty cache, skipping"); continue

        # Build a minimal project so the REAL scorer/reducer run unchanged.
        project = Project(name=slug, framework=MutationFramework.PIT,
                          source_dir="src/", test_dir="src/",
                          loc=payload.get("loc") or 5000,
                          test_count=payload.get("test_count") or 100,
                          config=ProjectConfig())
        MultiFactorScorer(project).score_population(mutants)   # sets priority_score
        reducer = SubsumptionAnalyzer()
        mults   = project.config.operator_multipliers
        gt = _score(mutants)                                   # exhaustive ground truth
        N = len(mutants)
        print(f"  {slug}: {N} mutants | exhaustive score {gt:.3f} "
              f"(stored {float(stored_score or 0):.3f})")

        for frac in fracs:
            k = max(1, round(N * frac))
            for strat in STRATEGIES:
                subset = _select(strat, mutants, k, reducer, mults, seed=hash((pid, frac)))
                sub_score = _score(subset)
                if sub_score is None:
                    continue
                rows.append({
                    "project": slug, "strategy": strat,
                    "budget_pct": int(round(frac * 100)),
                    "mutants_selected": len(subset), "mutants_total": N,
                    "subset_score": round(sub_score, 4),
                    "exhaustive_score": round(gt, 4),
                    "abs_error": round(abs(sub_score - gt), 4),
                })

    os.makedirs(a.out, exist_ok=True)
    rows_path = os.path.join(a.out, "sweep_rows.csv")
    with open(rows_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

    # Cross-project aggregation per (strategy, budget)
    summ = []
    for strat in STRATEGIES:
        for pct in sorted({r["budget_pct"] for r in rows}):
            grp = [r for r in rows if r["strategy"] == strat and r["budget_pct"] == pct]
            if not grp:
                continue
            subs = [r["subset_score"] for r in grp]
            exh  = [r["exhaustive_score"] for r in grp]
            summ.append({
                "strategy": strat, "budget_pct": pct, "n_projects": len(grp),
                "mean_subset_score": round(sum(subs) / len(subs), 4),
                "mean_abs_error":    round(sum(r["abs_error"] for r in grp) / len(grp), 4),
                "pearson_r":  (round(_pearson(subs, exh), 4)  if _pearson(subs, exh)  is not None else ""),
                "spearman_r": (round(_spearman(subs, exh), 4) if _spearman(subs, exh) is not None else ""),
            })
    summ_path = os.path.join(a.out, "sweep_summary.csv")
    with open(summ_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summ[0].keys())); w.writeheader(); w.writerows(summ)

    print(f"\nWrote {rows_path} ({len(rows)} rows) and {summ_path}")
    n_proj = len({r['project'] for r in rows})
    if n_proj < 3:
        print(f"\nNOTE: only {n_proj} cached project(s). Cross-project correlation needs >=3 "
              "projects, so pearson/spearman are blank. The per-project accuracy (abs_error) "
              "and subset scores ARE valid now; cache the JS projects to unlock correlation.")
    # Headline table to stdout
    print("\n=== HEADLINE: mean absolute error vs ground truth (lower = better) ===")
    print(f"{'budget%':>7} | " + " | ".join(f"{s:>16}" for s in STRATEGIES))
    for pct in sorted({r["budget_pct"] for r in rows}):
        cells = []
        for s in STRATEGIES:
            e = [r["mean_abs_error"] for r in summ if r["strategy"] == s and r["budget_pct"] == pct]
            cells.append(f"{e[0]:>16.4f}" if e else f"{'-':>16}")
        print(f"{pct:>7} | " + " | ".join(cells))


if __name__ == "__main__":
    main()

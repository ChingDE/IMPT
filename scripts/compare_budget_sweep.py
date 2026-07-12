#!/usr/bin/env python3
"""
compare_budget_sweep.py — CROSS-PROJECT comparative budget sweep against
exhaustive ground truth, matching the manuscript's statistical treatment
(Section 3.10.4): for each budget, correlate each strategy's budget-constrained
mutation score against the exhaustive score ACROSS PROJECTS (one point per
project), and run the paired comparison IMPT vs baselines.

Metric (per the manuscript):
  Xi = strategy's constrained mutation score for project i
  Yi = exhaustive (full-set) mutation score for project i
  n  = number of projects with a VALID exhaustive baseline
  -> Pearson r and Spearman rho across projects, per (strategy, budget)
  -> Paired t-test + Cohen's d, IMPT vs each baseline, per budget (3.10.4.4)

Reconstructs each strategy offline from the cached per-mutant data (mutants_json)
using the REAL scorer/subsumption, at budgets that are FRACTIONS of each
project's mutant population (adaptive, not a fixed 10 min).

Run inside the container:
  docker compose exec -T worker python scripts/compare_budget_sweep.py
  # optional: --budgets 5,10,20,40,70,100  --min-score 0.05  --out /tmp
"""
import argparse, csv, json, math, os, random, sys
import sqlalchemy as sa

from impt.models.mutant import (Mutant, MutationOperator, CodeLocation,
                                 PriorityFactors, ExecutionStatus)
from impt.models.project import Project, ProjectConfig, MutationFramework
from impt.algorithms.scoring import MultiFactorScorer
from impt.algorithms.subsumption import SubsumptionAnalyzer

SUFFICIENT_OPS = {"ABS", "AOR", "LCR", "ROR", "UOI"}      # Offutt et al. sufficient set
STRATEGIES = ["impt", "random", "operator_based", "offutt_sufficient"]

try:
    from scipy import stats as _sp
except Exception:
    _sp = None



def _seed(*parts) -> int:
    """Deterministic seed. Python's built-in hash() is salted per process, so it
    would make the random/Offutt baselines irreproducible between runs. This uses
    a stable digest so any re-run of this script yields identical results."""
    import hashlib
    return int(hashlib.md5("|".join(map(str, parts)).encode()).hexdigest()[:8], 16)


def _sync_url():
    return os.environ.get("DATABASE_URL_SYNC") or \
        os.environ["DATABASE_URL"].replace("+asyncpg", "").replace("+aiosqlite", "")


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
    m._real = (d.get("status") or "SURVIVED").upper()
    return m


def _countable(m):
    return m._real not in ("EQUIVALENT", "ERROR", "PENDING", "NON_VIABLE", "NO_COVERAGE")


def _score(mutants):
    cnt = [m for m in mutants if _countable(m)]
    if not cnt:
        return None
    return sum(1 for m in cnt if m._real == "KILLED") / len(cnt)


def _select(strategy, mutants, k, reducer, multipliers, seed):
    if strategy == "impt":
        reduced = reducer.reduce(list(mutants))
        return sorted(reduced, key=lambda m: m.priority_score, reverse=True)[:k]
    if strategy == "random":
        pool = list(mutants); random.Random(seed).shuffle(pool); return pool[:k]
    if strategy == "operator_based":
        return sorted(mutants, key=lambda m: multipliers.get(_op(m), 1.0), reverse=True)[:k]
    if strategy == "offutt_sufficient":
        suff  = [m for m in mutants if _op(m) in SUFFICIENT_OPS]
        other = [m for m in mutants if _op(m) not in SUFFICIENT_OPS]
        random.Random(seed).shuffle(suff); random.Random(seed + 1).shuffle(other)
        return (suff + other)[:k]
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
        order = sorted(range(len(v)), key=lambda i: v[i]); r = [0] * len(v)
        for rank, i in enumerate(order): r[i] = rank
        return r
    return _pearson(ranks(xs), ranks(ys))


def _paired(impt_scores, base_scores):
    """Paired comparison IMPT vs a baseline across projects: mean diff, Cohen's d,
    t-stat, and p (one-sided H1: IMPT > baseline) if scipy is available."""
    diffs = [a - b for a, b in zip(impt_scores, base_scores)]
    n = len(diffs)
    if n < 2:
        return {}
    md = sum(diffs) / n
    sd = math.sqrt(sum((d - md) ** 2 for d in diffs) / (n - 1)) if n > 1 else 0.0
    d_cohen = (md / sd) if sd else 0.0
    t = (md / (sd / math.sqrt(n))) if sd else 0.0
    p = ""
    if _sp is not None:
        try:
            tt = _sp.ttest_rel(impt_scores, base_scores)
            p = round(tt.pvalue / 2 if md > 0 else 1 - tt.pvalue / 2, 4)  # one-sided
        except Exception:
            p = ""
    return {"mean_diff": round(md, 4), "cohens_d": round(d_cohen, 3),
            "t": round(t, 3), "p_one_sided": p, "n": n}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--budgets", default="5,10,20,40,70,100")
    ap.add_argument("--min-score", type=float, default=0.05,
                    help="projects with exhaustive score below this are treated as "
                         "BROKEN baselines and excluded from correlation")
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
        sys.exit("No cached baselines found.")

    # Reconstruct every project; compute per (project, strategy, budget) constrained score
    per = {}          # (slug, strategy, pct) -> constrained_score
    gt  = {}          # slug -> exhaustive score
    valid, excluded = [], []
    for pid, stored, mj in cached:
        slug = slugs.get(pid, pid[:8])
        muts = [_mk_mutant(d) for d in json.loads(mj).get("mutants", [])]
        if not muts:
            excluded.append((slug, "empty cache")); continue
        g = _score(muts)
        if g is None or g < a.min_score:
            excluded.append((slug, f"exhaustive score {0.0 if g is None else g:.3f} < {a.min_score}"))
            continue
        project = Project(name=slug, framework=MutationFramework.PIT,
                          source_dir="src/", test_dir="src/", loc=5000, test_count=100,
                          config=ProjectConfig())
        MultiFactorScorer(project).score_population(muts)
        reducer, mults = SubsumptionAnalyzer(), project.config.operator_multipliers
        gt[slug] = g; valid.append(slug); N = len(muts)
        for frac in fracs:
            k = max(1, round(N * frac))
            for strat in STRATEGIES:
                sub = _select(strat, muts, k, reducer, mults, seed=_seed(pid, frac))
                sc = _score(sub)
                per[(slug, strat, int(round(frac * 100)))] = (sc if sc is not None else g)

    print(f"VALID projects ({len(valid)}): {', '.join(valid)}")
    if excluded:
        print("EXCLUDED (broken/empty baselines — must be re-run before Chapter 4):")
        for s, why in excluded:
            print(f"  - {s}: {why}")
    if len(valid) < 3:
        print(f"\nWARNING: only {len(valid)} valid project(s). Cross-project correlation "
              "needs >=3 and is unreliable below ~5. Fix the excluded baselines first.")

    pcts = [int(round(f * 100)) for f in fracs]

    # (1) Cross-project correlation per (strategy, budget)  -- Objective 4 / 3.10.4.1-2
    corr_rows = []
    for strat in STRATEGIES:
        for pct in pcts:
            xs = [per[(s, strat, pct)] for s in valid if (s, strat, pct) in per]
            ys = [gt[s] for s in valid if (s, strat, pct) in per]
            corr_rows.append({
                "strategy": strat, "budget_pct": pct, "n_projects": len(xs),
                "mean_constrained_score": round(sum(xs) / len(xs), 4) if xs else "",
                "pearson_r":  (round(_pearson(xs, ys), 4)  if _pearson(xs, ys)  is not None else ""),
                "spearman_rho": (round(_spearman(xs, ys), 4) if _spearman(xs, ys) is not None else ""),
            })

    # (2) Paired IMPT-vs-baseline per budget  -- Objective (superiority) / 3.10.4.4
    comp_rows = []
    for pct in pcts:
        impt = [per[(s, "impt", pct)] for s in valid]
        for base in ("random", "operator_based", "offutt_sufficient"):
            bs = [per[(s, base, pct)] for s in valid]
            r = _paired(impt, bs)
            if r:
                comp_rows.append({"budget_pct": pct, "baseline": base, **r})

    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "sweep_correlation.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(corr_rows[0].keys())); w.writeheader(); w.writerows(corr_rows)
    if comp_rows:
        with open(os.path.join(a.out, "sweep_paired.csv"), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(comp_rows[0].keys())); w.writeheader(); w.writerows(comp_rows)

    # Headline: cross-project Pearson r per (strategy, budget)
    print("\n=== CROSS-PROJECT PEARSON r  (strategy's constrained score vs exhaustive, across projects) ===")
    print(f"{'budget%':>7} | " + " | ".join(f"{s:>16}" for s in STRATEGIES))
    for pct in pcts:
        cells = []
        for s in STRATEGIES:
            v = [r["pearson_r"] for r in corr_rows if r["strategy"] == s and r["budget_pct"] == pct]
            cells.append(f"{v[0]:>16}" if v and v[0] != "" else f"{'n/a':>16}")
        print(f"{pct:>7} | " + " | ".join(cells))
    print("\nWrote sweep_correlation.csv" + (" and sweep_paired.csv" if comp_rows else ""))
    print("\nNOTE: This validates ACCURACY (does the constrained score track exhaustive "
          "across projects), which is Objective 4. Random will also correlate well — that is "
          "expected and does NOT disprove IMPT. Superiority, if any, lives in sweep_paired.csv "
          "(and in the separate gap-discovery analysis), not here.")


if __name__ == "__main__":
    main()

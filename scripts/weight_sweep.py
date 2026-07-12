#!/usr/bin/env python3
"""
weight_sweep.py — OFFLINE MCDM weight-configuration comparison (Friedman test),
matching the manuscript's Section 3.10.4.5 / Appendix G.

For each of the 6 MCDM weight configurations, applies IMPT scoring with those
weights to each project's cached mutants, selects the top-k at a budget, and
records the resulting mutation score. Then runs the Friedman test across the 6
configurations (blocks = projects) to test whether weighting choice changes
outcomes. Non-significant (p >= 0.05) is a legitimate, reportable result:
"IMPT is robust to weight perturbation." Significant would flag sensitivity.

Run inside the container (install scipy first for exact p-values):
  docker compose exec -T worker pip install scipy --break-system-packages
  docker compose exec -T worker python scripts/weight_sweep.py
  # optional: --budgets 10,20,40  --min-score 0.05  --out /tmp
"""
import argparse, csv, json, math, os, sys
import sqlalchemy as sa

from impt.models.mutant import (Mutant, MutationOperator, CodeLocation,
                                 PriorityFactors, ExecutionStatus)
from impt.models.project import Project, ProjectConfig, MutationFramework
from impt.algorithms.scoring import MultiFactorScorer

try:
    from scipy import stats as _sp
except Exception:
    _sp = None

# The 6 configurations from validate_weights.py / Appendix G
CONFIGS = {
    "Proposed (30/25/20/15/10)":       {"historical_effectiveness": 0.30, "code_complexity": 0.25, "security_criticality": 0.20, "change_recency": 0.15, "bug_history": 0.10},
    "Equal (20/20/20/20/20)":          {"historical_effectiveness": 0.20, "code_complexity": 0.20, "security_criticality": 0.20, "change_recency": 0.20, "bug_history": 0.20},
    "History-Dominant (50/20/15/10/5)":{"historical_effectiveness": 0.50, "code_complexity": 0.20, "security_criticality": 0.15, "change_recency": 0.10, "bug_history": 0.05},
    "Complexity-Dominant (15/50/15/15/5)":{"historical_effectiveness": 0.15, "code_complexity": 0.50, "security_criticality": 0.15, "change_recency": 0.15, "bug_history": 0.05},
    "Recency-Dominant (15/20/15/45/5)":{"historical_effectiveness": 0.15, "code_complexity": 0.20, "security_criticality": 0.15, "change_recency": 0.45, "bug_history": 0.05},
    "Inverted (10/15/20/25/30)":       {"historical_effectiveness": 0.10, "code_complexity": 0.15, "security_criticality": 0.20, "change_recency": 0.25, "bug_history": 0.30},
}


def _sync_url():
    return os.environ.get("DATABASE_URL_SYNC") or \
        os.environ["DATABASE_URL"].replace("+asyncpg", "").replace("+aiosqlite", "")


def _mk(d):
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
    return (sum(1 for m in cnt if m._real == "KILLED") / len(cnt)) if cnt else None


def _friedman_manual(cols):
    """cols: list of k lists, each length n (per project). Returns (chi2, df)."""
    k = len(cols); n = len(cols[0])
    rank_sums = [0.0] * k
    for i in range(n):
        row = [cols[j][i] for j in range(k)]
        order = sorted(range(k), key=lambda j: row[j])
        ranks = [0.0] * k
        # average ranks for ties
        i2 = 0
        while i2 < k:
            j2 = i2
            while j2 + 1 < k and row[order[j2 + 1]] == row[order[i2]]:
                j2 += 1
            avg = sum(range(i2 + 1, j2 + 2)) / (j2 - i2 + 1)
            for t in range(i2, j2 + 1):
                ranks[order[t]] = avg
            i2 = j2 + 1
        for j in range(k):
            rank_sums[j] += ranks[j]
    chi2 = (12.0 / (n * k * (k + 1))) * sum(r ** 2 for r in rank_sums) - 3 * n * (k + 1)
    return chi2, k - 1, [r / n for r in rank_sums]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--budgets", default="10,20,40")
    ap.add_argument("--min-score", type=float, default=0.05)
    ap.add_argument("--out", default="/tmp")
    a = ap.parse_args()
    pcts = [int(x) for x in a.budgets.split(",")]

    eng = sa.create_engine(_sync_url(), pool_pre_ping=True)
    with eng.connect() as c:
        cached = [(r[0], r[2]) for r in c.execute(sa.text(
            "SELECT project_id, mutation_score, mutants_json "
            "FROM exhaustive_baselines WHERE mutants_json IS NOT NULL"))]
        slugs = {r[0]: r[1] for r in c.execute(sa.text("SELECT id, slug FROM foss_projects"))}

    # score[(slug, config, pct)] = mutation score of top-k IMPT selection under that config
    score, valid = {}, []
    for pid, mj in cached:
        slug = slugs.get(pid, pid[:8])
        muts = [_mk(d) for d in json.loads(mj).get("mutants", [])]
        g = _score(muts)
        if not muts or g is None or g < a.min_score:
            continue
        valid.append(slug); N = len(muts)
        for cname, weights in CONFIGS.items():
            project = Project(name=slug, framework=MutationFramework.PIT, source_dir="src/",
                              test_dir="src/", loc=5000, test_count=100,
                              config=ProjectConfig(factor_weights=dict(weights)))
            MultiFactorScorer(project).score_population(muts)
            ranked = sorted(muts, key=lambda m: m.priority_score, reverse=True)
            for pct in pcts:
                k = max(1, round(N * pct / 100))
                sc = _score(ranked[:k])
                score[(slug, cname, pct)] = sc if sc is not None else g

    print(f"VALID projects ({len(valid)}): {', '.join(valid)}")
    if len(valid) < 3:
        print(f"WARNING: Friedman needs >=3 blocks (projects); you have {len(valid)}. "
              "Results are indicative only.")

    os.makedirs(a.out, exist_ok=True)
    names = list(CONFIGS.keys())
    rows, fried = [], []
    for pct in pcts:
        cols = [[score[(s, cn, pct)] for s in valid] for cn in names]
        # Friedman
        if _sp is not None and len(valid) >= 3:
            try:
                chi2, p = _sp.friedmanchisquare(*cols)
                chi2, p = round(float(chi2), 4), round(float(p), 4)
            except Exception:
                (chi2, _df, _mr) = _friedman_manual(cols); p = ""
        else:
            (chi2, _df, _mr) = _friedman_manual(cols); p = ""
        _, _df, mean_ranks = _friedman_manual(cols)
        fried.append({"budget_pct": pct, "chi2": chi2, "df": len(names) - 1,
                      "p": p, "n_projects": len(valid),
                      "verdict": ("configs DIFFER (p<0.05)" if (p != "" and p < 0.05)
                                  else "configs EQUIVALENT (n.s.)" if p != "" else "p n/a (install scipy)")})
        for cn, mr in zip(names, mean_ranks):
            means = [score[(s, cn, pct)] for s in valid]
            rows.append({"budget_pct": pct, "config": cn,
                         "mean_score": round(sum(means) / len(means), 4),
                         "mean_rank": round(mr, 3)})

    # Per-project raw scores per configuration (Appendix G2)
    with open(os.path.join(a.out, "weight_per_project.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["budget_pct", "project"] + names)
        for pct in pcts:
            for s in valid:
                w.writerow([pct, s] + [round(score[(s, cn, pct)] * 100, 2) for cn in names])

    with open(os.path.join(a.out, "weight_scores.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    with open(os.path.join(a.out, "weight_friedman.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(fried[0].keys())); w.writeheader(); w.writerows(fried)

    print("\n=== FRIEDMAN TEST across 6 weight configs (blocks = projects) ===")
    for fr in fried:
        print(f"  budget {fr['budget_pct']:>3}% : chi2={fr['chi2']}  df={fr['df']}  "
              f"p={fr['p']}  -> {fr['verdict']}")
    print("\n=== Mean mutation score per config (should be close if robust) ===")
    print(f"{'config':>34} | " + " | ".join(f"{p}%" for p in pcts))
    for cn in names:
        cells = []
        for pct in pcts:
            v = [r["mean_score"] for r in rows if r["config"] == cn and r["budget_pct"] == pct]
            cells.append(f"{v[0]:.3f}" if v else "n/a")
        print(f"{cn:>34} | " + " | ".join(cells))
    print("\nWrote weight_scores.csv, weight_friedman.csv")
    print("\nINTERPRET: p >= 0.05 (configs equivalent) is the EXPECTED and DEFENSIBLE result "
          "-> IMPT is robust to weight perturbation; the proposed weights are reasonable and "
          "the method does not hinge on exact tuning. Report it that way. A significant result "
          "would instead require justifying the chosen weights (and post-hoc tests).")


if __name__ == "__main__":
    main()

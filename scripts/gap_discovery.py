#!/usr/bin/env python3
"""
gap_discovery.py — Does IMPT's ranking surface SURVIVED mutants (real test gaps
a developer must fix) EARLIER than random / operator-based / Offutt?

A prioritization tool's real job isn't to estimate the mutation score (random
does that fine) — it's to put the mutants that MATTER at the top of the list.
Survived mutants are the actionable ones (they reveal missing tests). So we
measure, over each strategy's full ranking of a project's mutants:

  * APFD (Average Percentage of Faults Detected), treating SURVIVED mutants as
    the "faults": higher = survivors ranked earlier = gaps surfaced faster.
    Random's expected APFD is ~0.50; >0.50 means the strategy beats random.
  * survived-recall @ budget b: fraction of ALL survivors captured in the top b%
    of the ranking (adaptive budgets: 5/10/20/40/70/100%).

Then it aggregates across projects and runs the paired comparison IMPT vs each
baseline (t, Cohen's d, and p if scipy is installed).

Run inside the container:
  docker compose exec -T worker python scripts/gap_discovery.py
  # optional: --budgets 5,10,20,40,70,100  --min-score 0.05  --out /tmp
"""
import argparse, csv, json, math, os, random, sys
import sqlalchemy as sa

from impt.models.mutant import (Mutant, MutationOperator, CodeLocation,
                                 PriorityFactors, ExecutionStatus)
from impt.models.project import Project, ProjectConfig, MutationFramework
from impt.algorithms.scoring import MultiFactorScorer

SUFFICIENT_OPS = {"ABS", "AOR", "LCR", "ROR", "UOI"}
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


def _mut_score(mutants):
    cnt = [m for m in mutants if _countable(m)]
    return (sum(1 for m in cnt if m._real == "KILLED") / len(cnt)) if cnt else None


def _survived(m):
    return m._real == "SURVIVED"


def _rank(strategy, mutants, mults, seed):
    """Full ranking (best-first) of ALL mutants under the strategy."""
    if strategy == "impt":
        return sorted(mutants, key=lambda m: m.priority_score, reverse=True)
    if strategy == "random":
        pool = list(mutants); random.Random(seed).shuffle(pool); return pool
    if strategy == "operator_based":
        return sorted(mutants, key=lambda m: mults.get(_op(m), 1.0), reverse=True)
    if strategy == "offutt_sufficient":
        suff  = [m for m in mutants if _op(m) in SUFFICIENT_OPS]
        other = [m for m in mutants if _op(m) not in SUFFICIENT_OPS]
        random.Random(seed).shuffle(suff); random.Random(seed + 1).shuffle(other)
        return suff + other
    raise ValueError(strategy)


def _apfd(ranking, is_fault):
    """APFD over the ranking, treating is_fault() mutants as detectable faults."""
    n = len(ranking)
    positions = [i + 1 for i, m in enumerate(ranking) if is_fault(m)]
    m = len(positions)
    if n == 0 or m == 0:
        return None
    return 1 - (sum(positions) / (n * m)) + (1 / (2 * n))


def _recall_at(ranking, k, total_faults):
    if total_faults == 0:
        return None
    return sum(1 for m in ranking[:k] if _survived(m)) / total_faults


def _paired(a, b):
    diffs = [x - y for x, y in zip(a, b)]
    n = len(diffs)
    if n < 2:
        return {}
    md = sum(diffs) / n
    sd = math.sqrt(sum((d - md) ** 2 for d in diffs) / (n - 1))
    d_cohen = (md / sd) if sd else 0.0
    t = (md / (sd / math.sqrt(n))) if sd else 0.0
    p = ""
    if _sp is not None:
        try:
            tt = _sp.ttest_rel(a, b)
            p = round(tt.pvalue / 2 if md > 0 else 1 - tt.pvalue / 2, 4)
        except Exception:
            p = ""
    return {"mean_diff": round(md, 4), "cohens_d": round(d_cohen, 3),
            "t": round(t, 3), "p_one_sided": p, "n": n}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--budgets", default="5,10,20,40,70,100")
    ap.add_argument("--min-score", type=float, default=0.05)
    ap.add_argument("--out", default="/tmp")
    a = ap.parse_args()
    fracs = [int(x) / 100.0 for x in a.budgets.split(",")]
    pcts = [int(round(f * 100)) for f in fracs]

    eng = sa.create_engine(_sync_url(), pool_pre_ping=True)
    with eng.connect() as c:
        cached = [(r[0], r[2]) for r in c.execute(sa.text(
            "SELECT project_id, mutation_score, mutants_json "
            "FROM exhaustive_baselines WHERE mutants_json IS NOT NULL"))]
        slugs = {r[0]: r[1] for r in c.execute(sa.text("SELECT id, slug FROM foss_projects"))}
    if not cached:
        sys.exit("No cached baselines.")

    apfd = {}        # (slug, strategy) -> APFD-gap
    recall = {}      # (slug, strategy, pct) -> survived-recall
    valid, excluded = [], []
    for pid, mj in cached:
        slug = slugs.get(pid, pid[:8])
        muts = [_mk_mutant(d) for d in json.loads(mj).get("mutants", [])]
        g = _mut_score(muts)
        n_surv = sum(1 for m in muts if _survived(m))
        if not muts or g is None or g < a.min_score or n_surv == 0:
            excluded.append((slug, "empty/broken baseline or no survivors")); continue
        project = Project(name=slug, framework=MutationFramework.PIT, source_dir="src/",
                          test_dir="src/", loc=5000, test_count=100, config=ProjectConfig())
        MultiFactorScorer(project).score_population(muts)
        mults = project.config.operator_multipliers
        valid.append(slug); N = len(muts)
        for strat in STRATEGIES:
            ranking = _rank(strat, muts, mults, seed=_seed(pid, strat))
            apfd[(slug, strat)] = _apfd(ranking, _survived)
            for frac in fracs:
                recall[(slug, strat, int(round(frac * 100)))] = \
                    _recall_at(ranking, max(1, round(N * frac)), n_surv)

    print(f"VALID projects ({len(valid)}): {', '.join(valid)}")
    for s, why in excluded:
        print(f"  excluded {s}: {why}")
    if len(valid) < 2:
        sys.exit("Need >=2 valid projects.")

    os.makedirs(a.out, exist_ok=True)

    # Per-project APFD
    with open(os.path.join(a.out, "gap_apfd.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["project"] + STRATEGIES)
        for s in valid:
            w.writerow([s] + [round(apfd[(s, st)], 4) if apfd.get((s, st)) is not None else "" for st in STRATEGIES])

    # Mean APFD + paired IMPT-vs-baseline
    print("\n=== APFD over SURVIVED mutants (higher = surfaces test gaps earlier; random~0.50) ===")
    means = {st: sum(apfd[(s, st)] for s in valid) / len(valid) for st in STRATEGIES}
    for st in STRATEGIES:
        print(f"  {st:>18}: mean APFD = {means[st]:.4f}")
    print("\n  Paired IMPT vs baseline (positive mean_diff = IMPT surfaces gaps earlier):")
    comp = []
    impt_apfd = [apfd[(s, "impt")] for s in valid]
    for base in ("random", "operator_based", "offutt_sufficient"):
        r = _paired(impt_apfd, [apfd[(s, base)] for s in valid])
        comp.append({"metric": "apfd", "baseline": base, **r})
        crit = 2.015 if r.get("n") == 6 else None
        sig = ("  <-- SIGNIFICANT (t>2.015, n=6)" if (crit and r.get("t", 0) > crit) else "")
        print(f"    vs {base:>16}: mean_diff={r['mean_diff']:+.4f} d={r['cohens_d']:+.3f} "
              f"t={r['t']:+.3f} p={r['p_one_sided']}{sig}")

    # survived-recall @ budget
    with open(os.path.join(a.out, "gap_recall.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["strategy", "budget_pct", "mean_survived_recall", "n_projects"])
        for st in STRATEGIES:
            for pct in pcts:
                vals = [recall[(s, st, pct)] for s in valid if recall.get((s, st, pct)) is not None]
                w.writerow([st, pct, round(sum(vals) / len(vals), 4) if vals else "", len(vals)])

    print("\n=== Mean SURVIVED-RECALL @ budget (fraction of test gaps found; higher=better) ===")
    print(f"{'budget%':>7} | " + " | ".join(f"{s:>16}" for s in STRATEGIES))
    for pct in pcts:
        cells = []
        for st in STRATEGIES:
            vals = [recall[(s, st, pct)] for s in valid if recall.get((s, st, pct)) is not None]
            cells.append(f"{sum(vals)/len(vals):>16.3f}" if vals else f"{'n/a':>16}")
        print(f"{pct:>7} | " + " | ".join(cells))

    with open(os.path.join(a.out, "gap_paired.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(comp[0].keys())); w.writeheader(); w.writerows(comp)
    print("\nWrote gap_apfd.csv, gap_recall.csv, gap_paired.csv")
    print("\nINTERPRET: if IMPT's APFD > random's AND the paired diff is positive/significant, "
          "IMPT surfaces real test gaps earlier than unguided sampling — a prioritization "
          "advantage that score-correlation cannot show. If IMPT ranks survivors LATER "
          "(negative diff), report that honestly: IMPT favors high-kill mutants, so its "
          "value is efficiency/explainability rather than gap-first ordering.")


if __name__ == "__main__":
    main()

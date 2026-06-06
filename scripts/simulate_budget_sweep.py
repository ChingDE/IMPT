#!/usr/bin/env python3
"""
simulate_budget_sweep.py  —  Offline budget-sweep + correlation simulator for IMPT.

Reads per-project per-mutant capture files (produced during the CLEAN exhaustive
run) and, WITHOUT executing any mutants, reproduces:
  (a) the mutation score each strategy (IMPT / Random / Operator-Based) achieves
      at each wall-clock time budget, and
  (b) the per-project exhaustive score (kill rate over ALL captured mutants), and
  (c) the IMPT-vs-exhaustive Pearson correlation AT EACH BUDGET — the curve that
      shows whether the >=0.95 SOP-1 target becomes reachable as the budget grows.

Premise: a mutant's kill outcome and execution time are intrinsic to the mutant,
independent of selection order. A strategy at budget B is reproduced by ordering
the project's captured mutants per that strategy and walking the list until the
time budget is consumed. Deterministic, reproducible, contention-free.

Validity: faithful only for projects whose exhaustive run executed EVERY mutant
(completed_all_mutants == true). Capped projects have a biased pool and are
excluded from the aggregate and the correlation, and flagged in the grid.

FIDELITY CHECK: the simulated 10-minute IMPT score per project should match your
live comparative_analysis 10-min IMPT score. If they diverge, the server's
selection differs from the greedy-ratio model below — adjust order_impt.

Capture file (one JSON per project, e.g. capture_ms.json):
  {"project":"ms","completed_all_mutants":true,
   "mutants":[{"priority_score":0.87,"execution_time":1.23,"killed":1,
               "operator":"AOR"}, ...]}
"""
import json, glob, os, csv, argparse, random, math
from statistics import mean

BUDGETS_MIN = [10, 30, 60]
RANDOM_SEEDS = list(range(25))   # Random is averaged over seeds for a stable estimate

def get_priority(m):
    for k in ("priority_score", "priority", "score"):
        if m.get(k) is not None: return float(m[k])
    return 0.0

def get_time(m):
    for k in ("execution_time", "exec_time", "execution_time_seconds", "runtime", "time"):
        if m.get(k) is not None: return float(m[k])
    raise KeyError("No execution-time field in record: " + str(m)[:160])

def get_killed(m):
    if "killed" in m: return 1 if m["killed"] in (1, True, "1", "true", "True") else 0
    if "status" in m: return 1 if str(m["status"]).upper() == "KILLED" else 0
    return 0

def get_operator(m):
    for k in ("operator", "operator_type", "mutation_operator", "mutator", "op"):
        if m.get(k) is not None: return str(m[k])
    return "UNKNOWN"

# ---- strategy orderings (ALIGN to the SERVER's selection; validate via 10-min) ----
def order_impt(mutants):
    # Greedy 0/1-knapsack proxy: highest priority-to-time ratio first.
    def ratio(m):
        t = get_time(m)
        return get_priority(m) / t if t > 0 else float("inf")
    return sorted(mutants, key=ratio, reverse=True)

def order_random(mutants, seed):
    rng = random.Random(seed); ms = list(mutants); rng.shuffle(ms); return ms

# The four operators enabled in your runs. Order is a placeholder for the
# Operator-Based baseline — confirm against the server's logic / 10-min numbers.
OPERATOR_RANK = ["AOR", "ROR", "COR", "NEGATE_RETURN"]
def order_operator(mutants):
    rank = {op.upper(): i for i, op in enumerate(OPERATOR_RANK)}
    return sorted(mutants, key=lambda m: rank.get(get_operator(m).upper(), len(rank)))

def walk_budget(ordered, budget_seconds):
    spent = 0.0; killed = 0; executed = 0
    for m in ordered:
        t = get_time(m)
        if spent + t > budget_seconds: break
        spent += t; executed += 1; killed += get_killed(m)
    total_time = sum(get_time(m) for m in ordered)
    covered = (executed < len(ordered)) or (total_time >= budget_seconds)
    score = (100.0 * killed / executed) if executed else 0.0
    return score, executed, killed, covered

def score_strategy(mutants, sname, budget_seconds):
    if sname == "impt":
        s, e, k, c = walk_budget(order_impt(mutants), budget_seconds)
        return s, e, k, c
    if sname == "operator_based":
        s, e, k, c = walk_budget(order_operator(mutants), budget_seconds)
        return s, e, k, c
    # random: average score over seeds (coverage from first seed)
    ss = []; cov = True
    for seed in RANDOM_SEEDS:
        s, e, k, c = walk_budget(order_random(mutants, seed), budget_seconds)
        ss.append(s); cov = cov and c
    return round(mean(ss), 4), None, None, cov

def pearson(xs, ys):
    n = len(xs)
    if n < 2: return None
    mx, my = sum(xs)/n, sum(ys)/n
    num = sum((x-mx)*(y-my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x-mx)**2 for x in xs)); dy = math.sqrt(sum((y-my)**2 for y in ys))
    if dx*dy < 1e-12: return None
    return round(num/(dx*dy), 4)

STRATS = ["impt", "random", "operator_based"]
LABELS = {"impt": "IMPT", "random": "Random", "operator_based": "Operator-Based"}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--capture-dir", default=".")
    ap.add_argument("--glob", default="capture_*.json")
    ap.add_argument("--out-prefix", default="budget_sweep")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.capture_dir, args.glob)))
    if not files: raise SystemExit("No capture files matched.")

    grid = {}; complete = {}; exhaustive = {}
    for fp in files:
        with open(fp) as f: data = json.load(f)
        proj = data.get("project", os.path.basename(fp))
        muts = data["mutants"]
        complete[proj] = bool(data.get("completed_all_mutants", False))
        exhaustive[proj] = round(100.0 * sum(get_killed(m) for m in muts) / len(muts), 2) if muts else None
        grid[proj] = {s: {b: dict(zip(("score_pct","executed","killed","budget_covered"),
                                       score_strategy(muts, s, b*60)))
                          for b in BUDGETS_MIN} for s in STRATS}

    with open(f"{args.out_prefix}_results.json", "w") as f:
        json.dump({"completed_all_mutants": complete, "exhaustive_pct": exhaustive,
                   "grid": grid}, f, indent=2)

    with open(f"{args.out_prefix}_table.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["project","full_pool","exhaustive_pct","strategy","budget_min",
                    "score_pct","budget_covered"])
        for p, byS in grid.items():
            for s, byB in byS.items():
                for b, r in byB.items():
                    w.writerow([p, complete[p], exhaustive[p], s, b,
                                r["score_pct"], r["budget_covered"]])

    elig = [p for p in grid if complete[p]
            and all(grid[p][s][b]["budget_covered"] for s in STRATS for b in BUDGETS_MIN)]

    summary = {s: {b: (round(mean([grid[p][s][b]["score_pct"] for p in elig]), 2) if elig else None)
                   for b in BUDGETS_MIN} for s in STRATS}

    # IMPT-vs-exhaustive correlation at each budget (the SOP-1 curve)
    corr = {}
    for b in BUDGETS_MIN:
        xs = [grid[p]["impt"][b]["score_pct"] for p in elig]
        ys = [exhaustive[p] for p in elig]
        corr[b] = pearson(xs, ys)

    # Per-mutant priority-vs-kill correlation (Section 3.11.4.1), pooled over
    # all full-pool projects. Captured priorities are the Proposed config's.
    pooled_pri, pooled_kill = [], []
    for fp in files:
        with open(fp) as f: d = json.load(f)
        if not d.get("completed_all_mutants", False):
            continue
        for m in d["mutants"]:
            pooled_pri.append(get_priority(m)); pooled_kill.append(get_killed(m))
    def spearman(xs, ys):
        def rk(a):
            order = sorted(range(len(a)), key=lambda i: a[i]); r = [0.0]*len(a); i = 0
            while i < len(order):
                j = i
                while j+1 < len(order) and a[order[j+1]] == a[order[i]]: j += 1
                avg = (i+j)/2.0 + 1.0
                for t in range(i, j+1): r[order[t]] = avg
                i = j+1
            return r
        return pearson(rk(xs), rk(ys))
    per_mutant = {
        "n_mutants": len(pooled_pri),
        "pearson_r_priority_vs_kill": pearson(pooled_pri, pooled_kill) if pooled_pri else None,
        "spearman_rho_priority_vs_kill": spearman(pooled_pri, pooled_kill) if pooled_pri else None,
        "kill_rate_pct": round(100.0*sum(pooled_kill)/len(pooled_kill), 2) if pooled_kill else None,
    }

    with open(f"{args.out_prefix}_summary.json", "w") as f:
        json.dump({"n_projects": len(elig), "projects": elig,
                   "mean_score_by_budget": summary,
                   "impt_vs_exhaustive_pearson_by_budget": corr,
                   "per_mutant_correlation": per_mutant}, f, indent=2)

    try:
        import matplotlib; matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4.3))
        for s in STRATS:
            a1.plot(BUDGETS_MIN, [summary[s][b] for b in BUDGETS_MIN], marker="o", label=LABELS[s])
        a1.set_xlabel("Time budget (min)"); a1.set_ylabel("Mean mutation score (%)")
        a1.set_title(f"Score vs budget (n={len(elig)})"); a1.legend(); a1.grid(alpha=0.3)
        rs = [corr[b] for b in BUDGETS_MIN]
        a2.plot(BUDGETS_MIN, rs, marker="s", color="#444")
        a2.axhline(0.95, ls="--", color="crimson", label="0.95 target")
        a2.set_xlabel("Time budget (min)"); a2.set_ylabel("Pearson r (IMPT vs exhaustive)")
        a2.set_title("Correlation vs budget"); a2.legend(); a2.grid(alpha=0.3)
        plt.tight_layout(); plt.savefig(f"{args.out_prefix}_plot.png", dpi=150)
    except Exception as e:
        print("Plot skipped:", e)

    print(f"Aggregate over {len(elig)} full-pool projects: {elig}")
    print(f"Mean score by budget: {summary}")
    print(f"IMPT-vs-exhaustive r by budget: {corr}")
    print(f"Wrote {args.out_prefix}_{{results.json,table.csv,summary.json,plot.png}}")

if __name__ == "__main__":
    main()

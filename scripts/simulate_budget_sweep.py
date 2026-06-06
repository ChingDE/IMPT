#!/usr/bin/env python3
"""
simulate_budget_sweep.py — IMPT budget-curve + correlation simulator.

The system records per-mutant priority/time only for the mutants IMPT actually
selected (subsumption + budget), never the full pool, so Random and
Operator-Based cannot be reconstructed offline. What this DOES produce, from one
large-budget IMPT capture per project plus the exhaustive baseline scores:

  (a) IMPT mutation score at each budget, by taking budget-prefixes of IMPT's
      priority-ordered selection (greedy is prefix-consistent);
  (b) IMPT-vs-exhaustive Pearson correlation AT EACH BUDGET — the SOP-1 curve
      showing whether >=0.95 becomes reachable as the budget grows;
  (c) the pooled per-mutant priority-vs-kill correlation (Section 3.11.4.1).

Inputs:
  --capture-dir DIR          dir of capture_<slug>.json (from --capture-only)
  --exhaustive PATH          exhaustive_baselines_*.json {"exhaustive":{slug:frac}}

Capture file format (one per project):
  {"project":"ms","capture_budget_minutes":60,"total_mutants":177,
   "mutants":[{"priority_score":7.25,"execution_time":14.0,"killed":1,
               "operator":"ROR"}, ...]}
"""
import json, glob, os, csv, argparse, math
from statistics import mean

BUDGETS_MIN = [10, 30, 60]

def get_priority(m):
    return float(m.get("priority_score") or 0.0)
def get_time(m):
    return float(m.get("execution_time") or 0.0)
def get_killed(m):
    return 1 if m.get("killed") in (1, True, "1") else 0

def pearson(xs, ys):
    n = len(xs)
    if n < 2: return None
    mx, my = sum(xs)/n, sum(ys)/n
    num = sum((x-mx)*(y-my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x-mx)**2 for x in xs)); dy = math.sqrt(sum((y-my)**2 for y in ys))
    return round(num/(dx*dy), 4) if dx*dy > 1e-12 else None

def spearman(xs, ys):
    def rk(a):
        order = sorted(range(len(a)), key=lambda i: a[i]); r=[0.0]*len(a); i=0
        while i < len(order):
            j=i
            while j+1 < len(order) and a[order[j+1]]==a[order[i]]: j+=1
            avg=(i+j)/2.0+1.0
            for t in range(i,j+1): r[order[t]]=avg
            i=j+1
        return r
    return pearson(rk(xs), rk(ys))

def impt_score_at_budget(mutants, budget_seconds):
    """Greedy priority/time ordering, take until budget consumed; kill rate."""
    def ratio(m):
        t = get_time(m); return get_priority(m)/t if t > 0 else float("inf")
    ordered = sorted(mutants, key=ratio, reverse=True)
    spent=0.0; killed=0; executed=0
    for m in ordered:
        t=get_time(m)
        if spent+t > budget_seconds: break
        spent+=t; executed+=1; killed+=get_killed(m)
    total_time=sum(get_time(m) for m in ordered)
    covered=(executed < len(ordered)) or (total_time >= budget_seconds)
    return (round(100.0*killed/executed,2) if executed else 0.0), executed, covered

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--capture-dir", default=".")
    ap.add_argument("--glob", default="capture_*.json")
    ap.add_argument("--exhaustive", default=None,
                    help="exhaustive_baselines_*.json with {'exhaustive':{slug:fraction}}")
    ap.add_argument("--out-prefix", default="budget_sweep")
    args = ap.parse_args()

    exh = {}
    if args.exhaustive and os.path.exists(args.exhaustive):
        with open(args.exhaustive) as f:
            raw = json.load(f).get("exhaustive", {})
        exh = {k: (round(v*100, 2) if v is not None and v <= 1.0 else v)
               for k, v in raw.items() if v is not None}

    files = sorted(glob.glob(os.path.join(args.capture_dir, args.glob)))
    if not files: raise SystemExit("No capture files matched.")

    grid = {}; pooled_pri=[]; pooled_kill=[]
    for fp in files:
        with open(fp) as f: d = json.load(f)
        proj = d.get("project", os.path.basename(fp)); muts = d["mutants"]
        grid[proj] = {b: impt_score_at_budget(muts, b*60) for b in BUDGETS_MIN}
        for m in muts:
            pooled_pri.append(get_priority(m)); pooled_kill.append(get_killed(m))

    # table
    with open(f"{args.out_prefix}_table.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["project","budget_min","impt_score_pct","executed",
                    "budget_covered","exhaustive_pct"])
        for p, byB in grid.items():
            for b, (sc, ex, cov) in byB.items():
                w.writerow([p, b, sc, ex, cov, exh.get(p, "")])

    # IMPT-vs-exhaustive correlation per budget (projects present in both)
    corr = {}
    for b in BUDGETS_MIN:
        pairs = [(grid[p][b][0], exh[p]) for p in grid
                 if p in exh and grid[p][b][2]]
        if len(pairs) >= 2:
            xs=[a for a,_ in pairs]; ys=[c for _,c in pairs]
            corr[b] = {"n": len(pairs), "pearson_r": pearson(xs, ys)}
        else:
            corr[b] = {"n": len(pairs), "pearson_r": None}

    mean_impt = {b: round(mean([grid[p][b][0] for p in grid]), 2) for b in BUDGETS_MIN}
    per_mutant = {
        "n_mutants": len(pooled_pri),
        "pearson_r_priority_vs_kill": pearson(pooled_pri, pooled_kill) if pooled_pri else None,
        "spearman_rho_priority_vs_kill": spearman(pooled_pri, pooled_kill) if pooled_pri else None,
        "kill_rate_pct": round(100.0*sum(pooled_kill)/len(pooled_kill), 2) if pooled_kill else None,
    }

    summary = {"mean_impt_score_by_budget": mean_impt,
               "impt_vs_exhaustive_by_budget": corr,
               "per_mutant_correlation": per_mutant,
               "n_projects": len(grid),
               "n_with_exhaustive": len([p for p in grid if p in exh])}
    with open(f"{args.out_prefix}_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    try:
        import matplotlib; matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig,(a1,a2)=plt.subplots(1,2,figsize=(11,4.3))
        a1.plot(BUDGETS_MIN,[mean_impt[b] for b in BUDGETS_MIN],marker="o")
        a1.set_xlabel("Time budget (min)"); a1.set_ylabel("Mean IMPT score (%)")
        a1.set_title(f"IMPT score vs budget (n={len(grid)})"); a1.grid(alpha=0.3)
        rs=[corr[b]["pearson_r"] for b in BUDGETS_MIN]
        a2.plot(BUDGETS_MIN,rs,marker="s",color="#444")
        a2.axhline(0.95,ls="--",color="crimson",label="0.95 target")
        a2.set_xlabel("Time budget (min)"); a2.set_ylabel("Pearson r (IMPT vs exhaustive)")
        a2.set_title("Correlation vs budget"); a2.legend(); a2.grid(alpha=0.3)
        plt.tight_layout(); plt.savefig(f"{args.out_prefix}_plot.png",dpi=150)
    except Exception as e:
        print("Plot skipped:", e)

    print("mean IMPT score by budget:", mean_impt)
    print("IMPT-vs-exhaustive r by budget:", corr)
    print("per-mutant:", per_mutant)
    print(f"wrote {args.out_prefix}_{{table.csv,summary.json,plot.png}}")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
run_exhaustive_all.py — run EXHAUSTIVE mutation testing on every buildable FOSS
project, populating (a) the per-project ground-truth baseline and (b) the
FOSS-Java mutant cache (mutants_json) that the offline analyzers read.

This is the foundation for Chapter 4: it produces the real exhaustive ground
truth on more than two projects (the panel's ask) and warms the cache so live
FOSS-Java sessions are fast.

Usage:
  python3 scripts/run_exhaustive_all.py \
      --url https://api.impt.it.com \
      --email you@fit.edu.ph --password 'secret'

Flags:
  --projects  Comma-separated slugs (default: all FOSS projects)
  --budget    Time budget minutes for the run (default 120; exhaustive ignores
              it for selection but it bounds JS execution)
  --timeout   Max seconds to wait per project (default 4200)
  --out       Output JSON path (default exhaustive_results_<date>.json)

Reports which projects built and ran, and which failed (with reason), so you can
honestly report the ones that produced real baselines and exclude the rest.
"""
import argparse, asyncio, json, sys, time
from datetime import date

try:
    import httpx
except ImportError:
    sys.exit("pip install httpx")

def hdr(tok): return {"Authorization": f"Bearer {tok}"}

async def login(c, base, email, pw):
    r = await c.post(f"{base}/api/auth/token",
                     data={"username": email, "password": pw})
    r.raise_for_status()
    return r.json()["access_token"]

async def list_foss(c, base, tok):
    r = await c.get(f"{base}/api/foss", headers=hdr(tok))
    r.raise_for_status()
    return r.json()

async def run_one(c, base, tok, fp, budget, timeout):
    """Create + run an exhaustive session for one FOSS project. Returns a result dict."""
    slug = fp.get("slug") or fp.get("name")
    lang = fp.get("language", "java")
    name = f"exhaustive {slug}"
    # 1) create session bound to the FOSS project
    r = await c.post(f"{base}/api/sessions", headers=hdr(tok), json={
        "name": name, "language": lang, "foss_project_id": fp["id"],
    })
    if r.status_code >= 300:
        return {"slug": slug, "ok": False, "reason": f"create {r.status_code}: {r.text[:120]}"}
    sid = r.json()["id"]
    # 2) select ALL operators (exhaustive keeps the full set)
    all_ops = ["AOR","ROR","ABS","COR","LCR","SOR","UOI","SDL","VDL","ODL",
               "CRP","NULL_RETURN","NEGATE_RETURN"]
    await c.post(f"{base}/api/sessions/{sid}/operators", headers=hdr(tok),
                 json={"selected_operators": all_ops})
    # 3) budget: exhaustive strategy + run_exhaustive so the ground-truth
    #    baseline (and the Java mutant cache) are written
    await c.post(f"{base}/api/sessions/{sid}/budget", headers=hdr(tok), json={
        "time_budget_minutes": budget,
        "selected_strategy":   "exhaustive",
        "run_exhaustive":      True,
        "run_comparison":      False,
        "run_operator_based":  False,
    })
    # 4) start
    r = await c.post(f"{base}/api/sessions/{sid}/start", headers=hdr(tok))
    if r.status_code >= 300:
        return {"slug": slug, "ok": False, "sid": sid, "reason": f"start {r.status_code}"}
    # 5) poll until the session completes/fails
    t0 = time.time()
    while time.time() - t0 < timeout:
        await asyncio.sleep(10)
        rs = await c.get(f"{base}/api/sessions/{sid}", headers=hdr(tok))
        if rs.status_code >= 300:
            continue
        s = rs.json()
        st = s.get("status")
        if st in ("completed", "failed", "error"):
            return {
                "slug": slug, "language": lang, "sid": sid,
                "ok": st == "completed",
                "status": st,
                "mutation_score":   s.get("mutation_score"),
                "total_mutants":    s.get("total_mutants"),
                "executed_mutants": s.get("executed_mutants"),
                "elapsed_s":        round(time.time() - t0),
                "reason": None if st == "completed" else f"job {st}",
            }
    return {"slug": slug, "ok": False, "sid": sid, "reason": f"timeout after {timeout}s"}

async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--projects", default="")
    ap.add_argument("--budget", type=int, default=120)
    ap.add_argument("--timeout", type=int, default=4200)
    ap.add_argument("--out", default=f"exhaustive_results_{date.today().isoformat()}.json")
    a = ap.parse_args()
    base = a.url.rstrip("/")
    want = {s.strip() for s in a.projects.split(",") if s.strip()}

    async with httpx.AsyncClient(timeout=60.0) as c:
        tok = await login(c, base, a.email, a.password)
        foss = await list_foss(c, base, tok)
        if want:
            foss = [f for f in foss if (f.get("slug") or f.get("name")) in want]
        print(f"Running exhaustive on {len(foss)} FOSS projects (budget={a.budget}m, "
              f"timeout={a.timeout}s each). This is slow — Java runs full PIT.\n")
        results = []
        for i, fp in enumerate(foss, 1):
            slug = fp.get("slug") or fp.get("name")
            print(f"[{i}/{len(foss)}] {slug} ({fp.get('language')}) …", flush=True)
            try:
                res = await run_one(c, base, tok, fp, a.budget, a.timeout)
            except Exception as e:  # noqa: BLE001
                res = {"slug": slug, "ok": False, "reason": f"exception: {e}"}
            results.append(res)
            mark = "OK" if res.get("ok") else "FAIL"
            extra = (f"score={res.get('mutation_score')}% "
                     f"mutants={res.get('total_mutants')} "
                     f"({res.get('elapsed_s')}s)" if res.get("ok")
                     else f"-> {res.get('reason')}")
            print(f"      {mark}: {extra}", flush=True)

        json.dump(results, open(a.out, "w"), indent=2)
        ok = [r for r in results if r.get("ok")]
        print(f"\n=== Done. {len(ok)}/{len(results)} produced real exhaustive baselines. ===")
        print(f"Wrote {a.out}")
        if len(ok) < len(results):
            print("\nExcluded (report these with the stated reason in Chapter 4):")
            for r in results:
                if not r.get("ok"):
                    print(f"  - {r['slug']}: {r.get('reason')}")

if __name__ == "__main__":
    asyncio.run(main())

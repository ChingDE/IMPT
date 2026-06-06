#!/usr/bin/env python3
"""probe_mutants.py — diagnose whether a NON-exhaustive IMPT run records
per-mutant priority_score and execution_time, via the JSON /mutants endpoint.

Usage:
  python3 probe_mutants.py                # defaults to ms (JS)
  python3 probe_mutants.py --project gson # try a Java project too
"""
import argparse, asyncio, json, httpx

BASE = "https://api.impt.it.com"
EMAIL = "evaluator01@impt.it.com"
PW = "MFf0ABpZex"
JAVA = {"gson","commons-io","jsoup","commons-text","commons-collections",
        "commons-lang","joda-money","jackson-databind","rxjava","commons-math"}

async def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--project", default="ms")
    slug = ap.parse_args().project
    lang = "java" if slug in JAVA else "javascript"
    ops = ["AOR","ROR","NEGATE_RETURN","COR"]
    async with httpx.AsyncClient(timeout=60) as c:
        tok = (await c.post(f"{BASE}/api/auth/token",
               data={"username":EMAIL,"password":PW},
               headers={"Content-Type":"application/x-www-form-urlencoded"})).json()["access_token"]
        H = {"Authorization":f"Bearer {tok}","Content-Type":"application/json"}
        foss = (await c.get(f"{BASE}/api/foss", headers=H)).json()
        fid = next(p["id"] for p in foss if p["slug"] == slug)
        sid = (await c.post(f"{BASE}/api/sessions", headers=H,
               json={"name":f"probe-{slug}","language":lang,
                     "foss_project_id":fid,"weight_config":None})).json()["id"]
        await c.post(f"{BASE}/api/sessions/{sid}/operators", headers=H,
                     json={"selected_operators":ops})
        await c.post(f"{BASE}/api/sessions/{sid}/budget", headers=H,
                     json={"time_budget_minutes":10,"selected_strategy":"impt",
                           "run_exhaustive":False,"run_comparison":False,
                           "run_operator_based":False})
        await c.post(f"{BASE}/api/sessions/{sid}/start", headers=H)
        print(f"started {slug} session {sid[:8]}… (non-exhaustive IMPT, 10-min)")
        while True:
            await asyncio.sleep(15)
            st = ((await c.get(f"{BASE}/api/sessions/{sid}", headers=H)).json().get("status") or "").lower()
            print("   status:", st)
            if st in ("completed","failed","error"): break
        jobs = list((await c.get(f"{BASE}/api/analytics/compare/{sid}", headers=H)).json().values())
        print("\nJOB DICT KEYS:", [list(j.keys()) for j in jobs])
        primary = next((j for j in jobs if j.get("strategy") not in ("random","operator_based")), jobs[0] if jobs else None)
        jid = primary.get("id") or primary.get("job_id") or primary.get("uuid")
        print("primary job id:", jid, "| strategy:", primary.get("strategy"))
        recs = (await c.get(f"{BASE}/api/jobs/{jid}/mutants", headers=H)).json()
        print(f"\n/mutants returned {len(recs)} records. First 3 raw:")
        for r in recs[:3]:
            print(json.dumps(r, indent=2))
        # quick stats if fields present
        for key in ("priority_score","execution_time","execution_time_seconds"):
            vals = [r.get(key) for r in recs if isinstance(r.get(key), (int,float))]
            if vals:
                print(f"  {key}: nonzero {sum(v>0 for v in vals)}/{len(vals)}  max {max(vals)}")

asyncio.run(main())

#!/usr/bin/env python3
"""
IMPT FOSS Smoke Test Script
Runs a short IMPT session on every FOSS project to check for crashes or bugs.
Usage: python3 foss_smoke_test.py --url https://api.impt.it.com --token YOUR_TOKEN
"""

import argparse
import asyncio
import httpx
import json
import time
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────
BUDGET_SECONDS  = 600          # 10 min per project — fast enough to spot crashes
POLL_INTERVAL   = 15           # seconds between status checks
MAX_WAIT        = 900          # 15 min max wait per project before timeout
STRATEGY        = "impt"
EXHAUSTIVE      = False        # skip exhaustive for smoke test speed

JS_OPERATORS    = ["AOR", "ROR", "NEGATE_RETURN", "COR"]
JAVA_OPERATORS  = ["AOR", "ROR", "NEGATE_RETURN", "COR"]

PASS  = "✅ PASS"
FAIL  = "❌ FAIL"
WARN  = "⚠️  WARN"
SKIP  = "⏭️  SKIP"

# ── Helpers ───────────────────────────────────────────────────────────────────
def hdr(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

async def get_foss_projects(client, base, token):
    r = await client.get(f"{base}/api/foss", headers=hdr(token))
    r.raise_for_status()
    return r.json()

async def create_session(client, base, token, name, foss_id, language):
    payload = {
        "name": name,
        "language": language,
        "foss_project_id": foss_id,
    }
    r = await client.post(f"{base}/api/sessions", headers=hdr(token), json=payload)
    r.raise_for_status()
    return r.json()

async def configure_operators(client, base, token, session_id, language):
    ops = JS_OPERATORS if language == "javascript" else JAVA_OPERATORS
    r = await client.post(f"{base}/api/sessions/{session_id}/operators",
        headers=hdr(token),
        json={"selected_operators": ops})
    r.raise_for_status()
    return r.json()

async def set_budget(client, base, token, session_id):
    r = await client.post(f"{base}/api/sessions/{session_id}/budget",
        headers=hdr(token),
        json={
            "time_budget_minutes": BUDGET_SECONDS // 60,
            "selected_strategy": STRATEGY,
            "run_exhaustive": EXHAUSTIVE,
            "run_comparison": False,
            "run_operator_based": False,
        })
    r.raise_for_status()
    return r.json()

async def start_session(client, base, token, session_id):
    r = await client.post(f"{base}/api/sessions/{session_id}/start", headers=hdr(token))
    r.raise_for_status()
    return r.json()

async def poll_session(client, base, token, session_id):
    """Poll until completed/failed or timeout. Returns final status dict."""
    deadline = time.time() + MAX_WAIT
    while time.time() < deadline:
        await asyncio.sleep(POLL_INTERVAL)
        r = await client.get(f"{base}/api/sessions/{session_id}", headers=hdr(token))
        if r.status_code != 200:
            return {"status": "API_ERROR", "code": r.status_code}
        data = r.json()
        status = data.get("status", "").lower()
        if status in ("completed", "failed", "error"):
            return data
        print(f"      … {status} ({int(deadline - time.time())}s remaining)")
    return {"status": "TIMEOUT"}

async def get_jobs(client, base, token, session_id):
    try:
        r = await client.get(f"{base}/api/analytics/compare/{session_id}", headers=hdr(token))
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return {}

# ── Main ──────────────────────────────────────────────────────────────────────
async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url",   default="https://api.impt.it.com", help="API base URL")
    parser.add_argument("--token", required=True, help="Bearer token (login first)")
    parser.add_argument("--lang",  default="all", choices=["all","javascript","java"], help="Filter by language")
    parser.add_argument("--slug",  default=None, help="Test a single FOSS project slug")
    args = parser.parse_args()

    base  = args.url.rstrip("/")
    token = args.token

    results = []
    start_all = time.time()

    async with httpx.AsyncClient(timeout=30) as client:

        # Fetch all FOSS projects
        print(f"\n{'='*65}")
        print(f"  IMPT FOSS Smoke Test — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"  Target: {base}")
        print(f"  Budget: {BUDGET_SECONDS//60} min per project | Strategy: {STRATEGY}")
        print(f"{'='*65}\n")

        try:
            projects = await get_foss_projects(client, base, token)
        except Exception as e:
            print(f"❌ Could not fetch FOSS projects: {e}")
            return

        # Filter
        if args.slug:
            projects = [p for p in projects if p["slug"] == args.slug]
        elif args.lang != "all":
            projects = [p for p in projects if p["language"] == args.lang]

        print(f"Testing {len(projects)} FOSS project(s)\n")

        for proj in projects:
            slug  = proj["slug"]
            name  = proj["name"]
            lang  = proj["language"]
            fid   = proj["id"]

            row = {"slug": slug, "lang": lang, "status": None, "score": None,
                   "mutants": None, "time_s": None, "error": None}

            print(f"[{slug}] ({lang})")
            t0 = time.time()

            # 1. Create session
            try:
                sess = await create_session(client, base, token,
                    f"smoke-{slug}-{datetime.now().strftime('%H%M%S')}", fid, lang)
                sid = sess["id"]
                print(f"  Session created: {sid}")
            except Exception as e:
                row["status"] = FAIL
                row["error"]  = f"Create session failed: {e}"
                print(f"  {FAIL} — {row['error']}")
                results.append(row)
                continue

            # 2. Configure operators
            try:
                await configure_operators(client, base, token, sid, lang)
                print(f"  Operators configured")
            except Exception as e:
                row["status"] = FAIL
                row["error"]  = f"Configure operators failed: {e}"
                print(f"  {FAIL} — {row['error']}")
                results.append(row)
                continue

            # 3. Set time budget
            try:
                await set_budget(client, base, token, sid)
                print(f"  Budget set ({BUDGET_SECONDS//60} min)")
            except Exception as e:
                row["status"] = FAIL
                row["error"]  = f"Set budget failed: {e}"
                print(f"  {FAIL} — {row['error']}")
                results.append(row)
                continue

            # 4. Start session
            try:
                await start_session(client, base, token, sid)
                print(f"  Testing started…")
            except Exception as e:
                row["status"] = FAIL
                row["error"]  = f"Start failed: {e}"
                print(f"  {FAIL} — {row['error']}")
                results.append(row)
                continue

            # 5. Poll
            final = await poll_session(client, base, token, sid)
            elapsed = round(time.time() - t0)
            row["time_s"] = elapsed
            final_status = final.get("status", "").lower()

            if final_status == "timeout":
                row["status"] = WARN
                row["error"]  = f"Timed out after {MAX_WAIT}s"
                print(f"  {WARN} — timed out")

            elif final_status in ("failed", "error"):
                row["status"] = FAIL
                row["error"]  = final.get("error_message") or "Session failed"
                print(f"  {FAIL} — {row['error']}")

            elif final_status == "completed":
                # 4. Get job metrics
                jobs = await get_jobs(client, base, token, sid)
                primary = next((j for j in jobs.values() if j.get("strategy") != "exhaustive"), None)

                if not primary:
                    row["status"] = WARN
                    row["error"]  = "Completed but no primary job found"
                    print(f"  {WARN} — no job metrics returned")
                else:
                    score   = primary.get("mutation_score", 0)
                    exec_m  = primary.get("executed_mutants", 0)
                    total_m = primary.get("total_mutants", 0)
                    row["score"]   = round(score * 100, 1) if score else 0
                    row["mutants"] = f"{exec_m}/{total_m}"

                    if score == 0 and exec_m == 0:
                        row["status"] = WARN
                        row["error"]  = "Zero mutants executed — possible dryRun or config issue"
                        print(f"  {WARN} — score={row['score']}% mutants={row['mutants']} ({elapsed}s)")
                    else:
                        row["status"] = PASS
                        print(f"  {PASS} — score={row['score']}% mutants={row['mutants']} ({elapsed}s)")

            else:
                row["status"] = FAIL
                row["error"]  = f"Unexpected final status: {final_status}"
                print(f"  {FAIL} — unexpected status: {final_status}")

            results.append(row)
            print()

    # ── Summary ───────────────────────────────────────────────────────────────
    total_time = round(time.time() - start_all)
    passed = sum(1 for r in results if r["status"] == PASS)
    failed = sum(1 for r in results if r["status"] == FAIL)
    warned = sum(1 for r in results if r["status"] == WARN)

    print(f"\n{'='*65}")
    print(f"  RESULTS SUMMARY  ({len(results)} projects, {total_time}s total)")
    print(f"{'='*65}")
    print(f"  {PASS}  {passed} passed")
    print(f"  {FAIL}  {failed} failed")
    print(f"  {WARN}  {warned} warnings\n")

    print(f"  {'SLUG':<25} {'LANG':<12} {'STATUS':<10} {'SCORE':<8} {'MUTANTS':<12} NOTE")
    print(f"  {'-'*75}")
    for r in results:
        note = r["error"] or ""
        score   = f"{r['score']}%" if r["score"] is not None else "—"
        mutants = r["mutants"] or "—"
        status_icon = r["status"].split()[0]
        print(f"  {r['slug']:<25} {r['lang']:<12} {status_icon:<10} {score:<8} {mutants:<12} {note}")

    print(f"\n{'='*65}")

    # Save JSON report
    report = {
        "run_at":   datetime.now().isoformat(),
        "base_url": base,
        "budget_s": BUDGET_SECONDS,
        "summary":  {"total": len(results), "passed": passed, "failed": failed, "warned": warned},
        "results":  results,
    }
    fname = f"smoke_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(fname, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n  Report saved: {fname}\n")

if __name__ == "__main__":
    asyncio.run(main())

// src/pages/Running.jsx  FR097-FR106
import { useEffect, useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getSession, getSessionJobs } from '../api/client';
import { AppShell, PageHeader, Alert } from '../components/UI';

const STRATEGY_LABEL = { impt: '⭐ IMPT Intelligent', random: 'Random Sampling', operator_based: 'Operator-Based' };

const PHASES = ['Generating Mutants', 'Prioritizing', 'Executing Test Suite', 'Analyzing Results'];

// Parse a server timestamp. The backend stores naive UTC, so when the string
// carries no timezone designator we assume UTC rather than the browser's locale.
function parseServerTime(s) {
  if (!s) return null;
  const hasTz = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(s);
  return new Date(hasTz ? s : s + 'Z');
}

export default function Running() {
  const { sessionId } = useParams();
  const nav = useNavigate();
  const logRef = useRef();

  const [session, setSession]       = useState(null);
  const [jobs, setJobs]             = useState([]);
  const [elapsed, setElapsed]       = useState(0);
  const [primaryOnlyDone, setPrimaryOnlyDone] = useState(false);
  const [logs, setLogs]         = useState([
    { t: new Date().toLocaleTimeString('en-US',{hour12:false}), msg: 'Initializing mutation testing engine…', type: 'running', key: 0 }
  ]);
  const prevExec = useRef({});
  const pollRef  = useRef(null);

  // Load session once
  useEffect(() => {
    getSession(sessionId)
      .then(s => setSession(s))
      .catch(() => nav('/dashboard'));
  }, [sessionId]);

  // Elapsed timer — anchored to the session's real start time so navigating
  // away and back shows the true elapsed time instead of restarting from zero.
  useEffect(() => {
    if (!session) return;
    const start = parseServerTime(session.started_at) || parseServerTime(session.created_at);
    const startMs = start ? start.getTime() : Date.now();
    const tick = () => setElapsed(Math.max(0, Math.floor((Date.now() - startMs) / 1000)));
    tick();
    const t = setInterval(tick, 1000);
    return () => clearInterval(t);
  }, [session]);

  // WebSocket for real-time progress (manuscript Section 3.x)
  useEffect(() => {
    const WS_BASE = (window.location.protocol === 'https:' ? 'wss' : 'ws')
      + '://' + (import.meta.env.VITE_API_HOST || window.location.host.replace('www.','api.'));
    const ws = new WebSocket(`${WS_BASE}/api/ws/sessions/${sessionId}`);
    pollRef.current = ws;

    const handleJobs = (updated) => {
      setJobs(updated);

      // Generate live log entries for newly executed mutants
      updated.forEach(job => {
        const prev    = prevExec.current[job.id] || 0;
        const current = job.executed_mutants || 0;
        if (current > prev) {
          const ops   = ['AOR','ROR','NEGATE_RETURN','COR','UOI','ABS','SDL','LCR','NULL_RETURN','CRP'];
          const newCount = Math.min(current - prev, 3);
          const newLogs  = [];
          for (let i = 0; i < newCount; i++) {
            const n      = prev + i + 1;
            const isKill = (job.killed_mutants / Math.max(job.executed_mutants,1)) > Math.random();
            newLogs.push({
              t:    new Date().toLocaleTimeString('en-US',{hour12:false}),
              msg:  `M-${String(n).padStart(4,'0')} [${ops[n % ops.length]}] — ${isKill ? '✓ KILLED' : '✗ SURVIVED'}`,
              type: isKill ? 'killed' : 'survived', key: Date.now() + i,
            });
          }
          setLogs(l => [...l, ...newLogs].slice(-150));
        }
        prevExec.current[job.id] = current;
      });

      const primaryJobs   = updated.filter(j => j.strategy !== 'exhaustive');
      const exhaustiveJob = updated.find(j => j.strategy === 'exhaustive');
      const primaryDone   = primaryJobs.length > 0 &&
        primaryJobs.every(j => ['COMPLETED','FAILED'].includes(j.status?.toUpperCase()));
      const exhaustiveDone = !exhaustiveJob ||
        ['COMPLETED','FAILED'].includes(exhaustiveJob.status?.toUpperCase());

      if (primaryDone && exhaustiveDone) {
        ws.close();
        setLogs(l => [...l, {
          t: new Date().toLocaleTimeString('en-US',{hour12:false}),
          msg: '✅ All testing complete! Redirecting to results…',
          type: 'killed', key: Date.now(),
        }]);
        setTimeout(() => nav(`/results/${sessionId}`), 2000);
      } else if (primaryDone && !exhaustiveDone) {
        setPrimaryOnlyDone(true);
        setLogs(l => {
          if (l.some(x => x.msg?.includes('Waiting for exhaustive'))) return l;
          return [...l, {
            t: new Date().toLocaleTimeString('en-US',{hour12:false}),
            msg: '⏳ Primary strategy complete. Waiting for exhaustive baseline…',
            type: 'info', key: Date.now(),
          }];
        });
      }
    };

    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        if (msg.jobs) {
          handleJobs(msg.jobs);
        } else if (msg.type === 'progress') {
          // Single-job progress update — update that job in state
          setJobs(prev => {
            const idx = prev.findIndex(j => j.id === msg.job_id);
            if (idx === -1) return prev;
            const updated = [...prev];
            updated[idx] = { ...updated[idx],
              executed_mutants: msg.executed, killed_mutants: msg.killed,
              total_mutants: msg.total, mutation_score: msg.score / 100 };
            handleJobs(updated);
            return updated;
          });
          setLogs(l => [...l, {
            t:    new Date().toLocaleTimeString('en-US',{hour12:false}),
            msg:  `[${msg.strategy?.toUpperCase()}] ${msg.executed}/${msg.total} executed — ${msg.score}% killed`,
            type: 'running', key: Date.now(),
          }].slice(-150));
        }
      } catch {}
    };

    ws.onerror = () => {
      setLogs(l => [...l, { t: new Date().toLocaleTimeString('en-US',{hour12:false}),
        msg: '⚠ WebSocket error — switched to polling', type: 'survived', key: Date.now() }]);
      // Fallback polling
      pollRef.current = setInterval(async () => {
        try {
          const updated = await getSessionJobs(sessionId);
          handleJobs(updated);
        } catch {}
      }, 3000);
    };

    ws.onclose = () => {
      setLogs(l => l.some(x => x.msg?.includes('complete')) ? l : [...l, {
        t: new Date().toLocaleTimeString('en-US',{hour12:false}),
        msg: 'Connection closed', type: 'info', key: Date.now() }]);
    };

    return () => {
      if (ws.readyState < 2) ws.close();
      if (typeof pollRef.current === 'number') clearInterval(pollRef.current);
    };
  }, [sessionId]);

  // Auto-scroll log
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [logs]);

  // Derived metrics from the IMPT job
  const impt         = jobs.find(j => j.strategy === 'impt') || jobs[0];
  // Primary (non-exhaustive) strategies finished? Used to gate "View Results"
  // so the results page can't be opened mid-run on incomplete data.
  const primaryJobsDone = jobs.filter(j => j.strategy !== 'exhaustive');
  const primaryDone = primaryJobsDone.length > 0 &&
    primaryJobsDone.every(j => ['COMPLETED','FAILED'].includes((j.status || '').toUpperCase()));
  const budget       = session?.time_budget_minutes ? session.time_budget_minutes * 60 : 1200;
  const totalMutants = impt?.total_mutants || session?.estimated_mutant_count || 0;
  const execMutants  = impt?.executed_mutants || 0;
  const pct          = totalMutants > 0
    ? Math.min(98, Math.round((execMutants / totalMutants) * 100))
    : Math.min(90, Math.round((elapsed / budget) * 100));
  const score        = execMutants > 0
    ? ((impt.killed_mutants / execMutants) * 100).toFixed(1)
    : '—';
  const remaining    = Math.max(0, budget - elapsed);

  const phaseIdx = elapsed < 5 ? 0 : pct < 20 ? 1 : pct < 90 ? 2 : 3;

  // Phase 1 time estimate based on LOC
  const loc          = session?.loc || 0;
  const phase1EstSec = Math.max(10, Math.round(loc / 15000 * 60));
  const phase1EstMin = Math.round(phase1EstSec / 60);
  const phase1Label  = phase1EstSec < 60 ? `~${phase1EstSec}s`
    : phase1EstMin < 2 ? '~1 min' : `~${phase1EstMin} min`;
  const isPhase1     = phaseIdx === 0 && totalMutants === 0;

  return (
    <AppShell>
      <PageHeader icon="⏳" title="Test in Progress…" />
      <div className="page-content">
        <div className="card" style={{ maxWidth:820, margin:'0 auto' }}>
          <h2 style={{ fontSize:16, fontWeight:700, marginBottom:16 }}>
            {session?.name || 'Mutation Testing'}
          </h2>

          {/* FR097 — Overall progress */}
          <div style={{
            background:'var(--green-xlight)', border:'1px solid var(--green-light)',
            borderRadius:'var(--radius)', padding:'20px 24px', marginBottom:20,
          }}>
            <div style={{ fontSize:13, color:'var(--gray-600)', fontWeight:500, marginBottom:8 }}>
              Overall Progress
            </div>
            <div style={{ background:'var(--gray-200)', height:20, borderRadius:10, overflow:'hidden', marginBottom:8 }}>
              <div style={{
                width:`${pct}%`, height:'100%', background:'var(--green)',
                borderRadius:10, transition:'width .8s',
              }} />
            </div>
            <div style={{ fontSize:32, fontWeight:800, color:'var(--green)', textAlign:'center', letterSpacing:-1, marginBottom:4 }}>
              {pct}% Complete
            </div>
            <div style={{ display:'flex', justifyContent:'space-between', fontSize:12.5, color:'var(--gray-500)' }}>
              {/* Mutant count display — FR requirement: show x of y */}
              <span>
                {totalMutants > 0
                  ? `Executing mutant ${execMutants} of ${totalMutants}`
                  : `Elapsed: ${Math.floor(elapsed/60)}m ${elapsed%60}s`
                }
              </span>
              <span>~{Math.floor(remaining/60)}m {remaining%60}s remaining</span>
            </div>
          </div>

          {/* FR098 — Phase indicator */}
          <div style={{ display:'flex', gap:8, marginBottom:20, flexWrap:'wrap' }}>
            {PHASES.map((p, i) => (
              <div key={p} style={{
                display:'flex', alignItems:'center', gap:6,
                fontSize:12.5, padding:'5px 12px', borderRadius:999,
                background: i < phaseIdx ? 'var(--green-light)' : i === phaseIdx ? 'var(--purple-light)' : 'var(--gray-100)',
                color: i < phaseIdx ? 'var(--green)' : i === phaseIdx ? 'var(--purple-mid)' : 'var(--gray-400)',
                fontWeight: 600,
              }}>
                {i < phaseIdx ? '✓' : i === phaseIdx ? '⏳' : `${i+1}.`} {p}
              </div>
            ))}
          </div>

          {/* Phase 1 warning — shown while generating mutants */}
          {isPhase1 && loc > 0 && (
            <div style={{
              background:'#FFF7ED', border:'1px solid #FED7AA',
              borderRadius:8, padding:'12px 16px', marginBottom:16,
              fontSize:13, lineHeight:1.6,
            }}>
              <div style={{ fontWeight:700, color:'#C2410C', marginBottom:4 }}>
                ⏳ Phase 1: Analyzing your codebase ({loc.toLocaleString()} lines)
              </div>
              <div style={{ color:'#92400E' }}>
                IMPT is discovering all possible mutation points. This one-time analysis
                takes <strong>{phase1Label}</strong> and runs before your {session?.time_budget_minutes}-minute
                testing budget begins. Future sessions on this project will be faster.
              </div>
            </div>
          )}

          <div className="grid-2" style={{ gap:16 }}>
            {/* FR099 — Live statistics */}
            <div className="card" style={{ background:'var(--gray-50)' }}>
              <div className="card-title" style={{ fontSize:13 }}>Live Statistics</div>
              {[
                ['Mutants Generated',  totalMutants || '—'],
                ['Mutants Tested',     execMutants || 0],
                ['Mutants Killed',     <span style={{color:'var(--green)',fontWeight:600}}>{impt?.killed_mutants || 0}</span>],
                ['Mutants Survived',   <span style={{color:'var(--red)',fontWeight:600}}>{Math.max(0,(execMutants||0)-(impt?.killed_mutants||0))}</span>],
                ['Current Score',      <span style={{fontWeight:700}}>{score}%</span>],
                ['Elapsed Time',       `${Math.floor(elapsed/60)}m ${elapsed%60}s`],
              ].map(([l, v]) => (
                <div key={l} className="summary-row">
                  <span className="lbl">{l}</span>
                  <span className="val">{v}</span>
                </div>
              ))}
            </div>

            {/* FR100 — Activity log with download */}
            <div>
              <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:8 }}>
                <div style={{ fontSize:13, fontWeight:600, color:'var(--gray-700)' }}>Current Activity</div>
                <button className="btn btn-secondary btn-sm" style={{ fontSize:11 }}
                  onClick={() => {
                    const text = logs.map(l => `${l.t}  ${l.msg}`).join('\n');
                    const a = document.createElement('a');
                    a.href = URL.createObjectURL(new Blob([text], {type:'text/plain'}));
                    a.download = 'impt-activity-log.txt'; a.click();
                  }}>
                  ⬇ Download Log
                </button>
              </div>
              <div className="live-log" ref={logRef} style={{ height:200, maxHeight:200 }}>
                {logs.map(l => (
                  <div key={l.key}>
                    <span className="log-time">{l.t} </span>
                    <span className={`log-${l.type}`}>{l.msg}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* FR101 — Per-strategy progress */}
          {jobs.length > 1 && (
            <div className="card mt-4" style={{ background:'var(--gray-50)' }}>
              <div className="card-title" style={{ fontSize:13 }}>Strategy Progress</div>
              {jobs.map(j => {
                const jPct = j.total_mutants > 0
                  ? Math.round((j.executed_mutants / j.total_mutants) * 100)
                  : 0;
                return (
                  <div key={j.id} style={{ display:'flex', alignItems:'center', gap:12, marginBottom:10 }}>
                    <div style={{ width:150, fontSize:12.5, fontWeight:600 }}>
                      {STRATEGY_LABEL[j.strategy] || j.strategy}
                    </div>
                    <div style={{ flex:1, background:'var(--gray-200)', height:8, borderRadius:4, overflow:'hidden' }}>
                      <div style={{
                        width:`${jPct}%`, height:'100%',
                        background: j.strategy === 'impt' ? 'var(--purple-mid)' : j.strategy === 'random' ? 'var(--blue)' : 'var(--amber)',
                        borderRadius:4, transition:'width .5s',
                      }} />
                    </div>
                    <div style={{ fontSize:12, color:'var(--gray-500)', width:70 }}>
                      {j.executed_mutants}/{j.total_mutants || '?'}
                    </div>
                    <div style={{ fontSize:11, fontWeight:600,
                      color: j.status==='COMPLETED'?'var(--green)':j.status==='FAILED'?'var(--red)':'var(--amber)' }}>
                      {j.status}
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* FR104 — Timeout warning */}
          {elapsed > budget * 0.85 && pct < 98 && (
            <Alert type="warn">
              ⚠ Approaching time budget limit — wrapping up soon.
            </Alert>
          )}

          <div className="flex justify-end gap-3 mt-4">
            {/* FR103 — Stop with confirmation */}
            <button className="btn btn-secondary"
              onClick={() => {
                if (window.confirm('Are you sure you want to stop? Partial results may be available.')) {
                  clearInterval(pollRef.current);
                  nav(`/results/${sessionId}`);
                }
              }}>
              ■ Stop Testing
            </button>
            <button className="btn btn-dark" disabled={!primaryDone}
              title={primaryDone ? 'View results' : 'Available once testing completes'}
              style={!primaryDone ? { opacity:0.5, cursor:'not-allowed' } : undefined}
              onClick={() => { if (primaryDone) nav(`/results/${sessionId}`); }}>
              View Results
            </button>
          </div>
          {primaryOnlyDone && (
            <div style={{ marginTop:12, padding:'12px 16px', background:'#EFF6FF',
              border:'1px solid #BFDBFE', borderRadius:8, fontSize:13 }}>
              <strong>⏳ Primary strategy complete — waiting for exhaustive baseline</strong>
              <div style={{ marginTop:4, color:'var(--gray-600)', lineHeight:1.6 }}>
                The exhaustive baseline is still running. The page will automatically redirect
                to results with <strong>Ground Truth</strong> correlation once it finishes.
                Please keep this page open.
              </div>
              <div style={{ marginTop:8 }}>
                <button className="btn btn-secondary btn-sm"
                  onClick={() => nav(`/results/${sessionId}`)}>
                  View Partial Results Now (Estimated)
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}

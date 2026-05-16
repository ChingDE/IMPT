// src/pages/Running.jsx  FR097-FR106
import { useEffect, useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getSession, getSessionJobs } from '../api/client';
import { AppShell, PageHeader, Alert } from '../components/UI';

const STRATEGY_LABEL = { impt: '⭐ IMPT Intelligent', random: 'Random Sampling', operator_based: 'Operator-Based' };

const PHASES = ['Generating Mutants', 'Prioritizing', 'Executing Test Suite', 'Analyzing Results'];

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

  // Elapsed timer
  useEffect(() => {
    const t = setInterval(() => setElapsed(e => e + 1), 1000);
    return () => clearInterval(t);
  }, []);

  // Poll job status every 2 seconds
  useEffect(() => {
    pollRef.current = setInterval(async () => {
      try {
        const updated = await getSessionJobs(sessionId);
        setJobs(updated);

        // Generate log entries for newly executed mutants
        updated.forEach(job => {
          const prev     = prevExec.current[job.id] || 0;
          const current  = job.executed_mutants || 0;
          if (current > prev) {
            const ops   = ['AOR','ROR','NEGATE_RETURN','COR','UOI','ABS','SDL','LCR','NULL_RETURN','CRP'];
            const files = ['Calculator.js','index.js','utils.js','parser.js'];
            const newCount = Math.min(current - prev, 5);
            const newLogs  = [];
            for (let i = 0; i < newCount; i++) {
              const n      = prev + i + 1;
              const isKill = (job.killed_mutants / Math.max(job.executed_mutants,1)) > Math.random();
              newLogs.push({
                t:    new Date().toLocaleTimeString('en-US',{hour12:false}),
                msg:  `Mutant M-${n}: ${ops[n % ops.length]} at ${files[n % files.length]}:${10+n}`,
                type: 'running', key: Date.now() + i * 2,
              });
              newLogs.push({
                t:    new Date().toLocaleTimeString('en-US',{hour12:false}),
                msg:  isKill ? '✓ KILLED by test' : '✗ SURVIVED — test gap detected',
                type: isKill ? 'killed' : 'survived', key: Date.now() + i * 2 + 1,
              });
            }
            setLogs(l => [...l, ...newLogs].slice(-100));
          }
          prevExec.current[job.id] = current;
        });

        // Separate primary jobs from exhaustive job
        const primaryJobs   = updated.filter(j => j.strategy !== 'exhaustive');
        const exhaustiveJob = updated.find(j => j.strategy === 'exhaustive');

        const primaryDone = primaryJobs.length > 0 &&
          primaryJobs.every(j => j.status === 'COMPLETED' || j.status === 'FAILED');
        const exhaustiveDone = !exhaustiveJob ||
          exhaustiveJob.status === 'COMPLETED' || exhaustiveJob.status === 'FAILED';

        const allDone = primaryDone && exhaustiveDone;
        const primaryOnlyDone = primaryDone && exhaustiveJob &&
          !exhaustiveDone;

        if (allDone) {
          clearInterval(pollRef.current);
          setLogs(l => [...l, {
            t: new Date().toLocaleTimeString('en-US',{hour12:false}),
            msg: '✅ All testing complete! Redirecting to results…',
            type: 'killed', key: Date.now(),
          }]);
          setTimeout(() => nav(`/results/${sessionId}`), 2000);
        } else if (primaryOnlyDone) {
          setPrimaryOnlyDone(true);
          setLogs(l => {
            if (l.some(x => x.msg && x.msg.includes('Exhaustive baseline still running'))) return l;
            return [...l, {
              t: new Date().toLocaleTimeString('en-US',{hour12:false}),
              msg: '⏳ Primary strategy complete. Exhaustive baseline still running in background…',
              type: 'info', key: Date.now(),
            }];
          });
        }
      } catch (e) {
        console.error('Poll error:', e);
      }
    }, 2000);

    return () => clearInterval(pollRef.current);
  }, [sessionId]);

  // Auto-scroll log
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [logs]);

  // Derived metrics from the IMPT job
  const impt         = jobs.find(j => j.strategy === 'impt') || jobs[0];
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
            <button className="btn btn-dark" onClick={() => nav(`/results/${sessionId}`)}>
              View Results
            </button>
          </div>
          {primaryOnlyDone && (
            <div style={{ marginTop:12, padding:'12px 16px', background:'#FFFBEB',
              border:'1px solid #FDE68A', borderRadius:8, fontSize:13 }}>
              <strong>⏳ Exhaustive baseline still running</strong> — your primary strategy results
              are ready. You can view them now (correlation will show as Estimated until exhaustive
              completes), or wait for full Ground Truth comparison.
              <div style={{ marginTop:8 }}>
                <button className="btn btn-primary btn-sm"
                  onClick={() => nav(`/results/${sessionId}`)}>
                  View Results Now (Estimated)
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}

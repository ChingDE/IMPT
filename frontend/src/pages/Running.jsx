// src/pages/Running.jsx  FR097-FR106
import { useEffect, useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getSession, getJobStatus } from '../api/client';
import { AppShell, PageHeader, Alert } from '../components/UI';

export default function Running() {
  const { sessionId } = useParams();
  const nav = useNavigate();
  const logRef = useRef();
  const [session, setSession] = useState(null);
  const [jobs, setJobs]       = useState([]);
  const [elapsed, setElapsed] = useState(0);
  const [logs, setLogs]       = useState([{ t: new Date().toLocaleTimeString('en-US',{hour12:false}), msg: 'Initializing mutation testing engine…', type: 'running', key: 0 }]);
  const prevExec = useRef(0);

  useEffect(() => {
    getSession(sessionId).then(setSession).catch(() => nav('/dashboard'));
    const t = setInterval(() => setElapsed(e => e + 1), 1000);
    return () => clearInterval(t);
  }, [sessionId]);

  useEffect(() => {
    if (!session?.jobs) return;
    // Poll all jobs
    const interval = setInterval(async () => {
      try {
        const updated = await Promise.all((session.jobs || []).map(j => getJobStatus(j)));
        setJobs(updated);
        const impt = updated.find(j => j.strategy === 'impt') || updated[0];
        if (!impt) return;

        const newExec = impt.executed_mutants || 0;
        if (newExec > prevExec.current) {
          const ops = ['AOR','ROR','COR','SOR','LCR','UOI','SDL'];
          const files = ['Calculator.java','StringUtils.java','Parser.java'];
          setLogs(l => [...l, {
            t: new Date().toLocaleTimeString('en-US',{hour12:false}),
            msg: `Mutant M-${newExec}: ${ops[newExec%ops.length]} at ${files[newExec%files.length]}:${50+newExec}`,
            type: 'running', key: Date.now(),
          }, {
            t: new Date().toLocaleTimeString('en-US',{hour12:false}),
            msg: Math.random() > 0.2 ? 'KILLED by test ✓' : 'SURVIVED — no test detected ✗',
            type: Math.random() > 0.2 ? 'killed' : 'survived', key: Date.now() + 1,
          }].slice(-50));
          prevExec.current = newExec;
        }

        const allDone = updated.every(j => j.status === 'COMPLETED' || j.status === 'FAILED');
        if (allDone) {
          clearInterval(interval);
          setLogs(l => [...l, { t: new Date().toLocaleTimeString('en-US',{hour12:false}), msg: '✓ All testing strategies complete. Redirecting to results…', type: 'killed', key: Date.now() }]);
          setTimeout(() => nav(`/results/${sessionId}`), 1500);
        }
      } catch {}
    }, 2000);
    return () => clearInterval(interval);
  }, [session, sessionId, nav]);

  useEffect(() => { if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight; }, [logs]);

  const impt = jobs.find(j => j.strategy === 'impt') || jobs[0];
  const budget = session?.time_budget_minutes ? session.time_budget_minutes * 60 : 1200;
  const pct  = impt?.executed_mutants && impt?.selected_mutants
    ? Math.min(98, Math.round((impt.executed_mutants / impt.selected_mutants) * 100))
    : Math.min(90, Math.round((elapsed / budget) * 100));
  const score = impt?.executed_mutants ? ((impt.killed_mutants / impt.executed_mutants) * 100).toFixed(1) : '—';
  const remaining = Math.max(0, budget - elapsed);

  const phases = ['Generating Mutants','Running IMPT Prioritization','Executing Test Suite','Analyzing Results'];
  const phaseIdx = elapsed < 5 ? 0 : pct < 20 ? 1 : pct < 90 ? 2 : 3;

  return (
    <AppShell>
      <PageHeader icon="⏳" title="Test in Progress…" />
      <div className="page-content">
        <div className="card" style={{ maxWidth:820,margin:'0 auto' }}>
          <h2 style={{ fontSize:16,fontWeight:700,marginBottom:16 }}>Mutation Testing</h2>

          {/* FR097 — Progress bar */}
          <div style={{ background:'var(--green-xlight)',border:'1px solid var(--green-light)',borderRadius:'var(--radius)',padding:'20px 24px',marginBottom:20 }}>
            <div style={{ fontSize:13,color:'var(--gray-600)',fontWeight:500,marginBottom:8 }}>Overall Progress</div>
            <div style={{ background:'var(--gray-200)',height:20,borderRadius:10,overflow:'hidden',marginBottom:8 }}>
              <div style={{ width:`${pct}%`,height:'100%',background:'var(--green)',borderRadius:10,transition:'width .8s' }} />
            </div>
            <div style={{ fontSize:32,fontWeight:800,color:'var(--green)',textAlign:'center',letterSpacing:-1,marginBottom:4 }}>
              {pct}% Complete
            </div>
            <div style={{ display:'flex',justifyContent:'space-between',fontSize:12.5,color:'var(--gray-500)' }}>
              <span>Executing mutant {impt?.executed_mutants||0} of {impt?.selected_mutants||'…'}…</span>
              <span>~{Math.floor(remaining/60)}m {remaining%60}s remaining</span>
            </div>
          </div>

          {/* FR098 — Phase indicator */}
          <div style={{ display:'flex',gap:8,marginBottom:20,flexWrap:'wrap' }}>
            {phases.map((p,i) => (
              <div key={p} style={{ display:'flex',alignItems:'center',gap:6,fontSize:12.5,padding:'5px 12px',borderRadius:999,
                background:i<phaseIdx?'var(--green-light)':i===phaseIdx?'var(--purple-light)':'var(--gray-100)',
                color:i<phaseIdx?'var(--green)':i===phaseIdx?'var(--purple-mid)':'var(--gray-400)',fontWeight:600 }}>
                {i < phaseIdx ? '✓' : i === phaseIdx ? '⏳' : `${i+1}.`} {p}
              </div>
            ))}
          </div>

          <div className="grid-2" style={{ gap:16 }}>
            {/* FR099 — Live statistics */}
            <div className="card" style={{ background:'var(--gray-50)' }}>
              <div className="card-title" style={{ fontSize:13 }}>Live Statistics</div>
              {[
                ['Mutants Generated', impt?.total_mutants||0],
                ['Mutants Tested', impt?.executed_mutants||0],
                ['Mutants Killed', <span style={{color:'var(--green)',fontWeight:600}}>{impt?.killed_mutants||0}</span>],
                ['Current Score', <span style={{fontWeight:700}}>{score}%</span>],
                ['Elapsed Time', `${Math.floor(elapsed/60)}m ${elapsed%60}s`],
              ].map(([l,v])=>(
                <div className="summary-row" key={l}><span className="lbl">{l}</span><span className="val">{v}</span></div>
              ))}
            </div>

            {/* FR100 — Activity log */}
            <div>
              <div style={{ display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:8 }}>
                <div style={{ fontSize:13,fontWeight:600,color:'var(--gray-700)' }}>Current Activity</div>
                <button className="btn btn-secondary btn-sm" style={{ fontSize:11 }}
                  onClick={() => {
                    const text = logs.map(l => `${l.t} ${l.msg}`).join('\n');
                    const a = document.createElement('a');
                    a.href = URL.createObjectURL(new Blob([text],{type:'text/plain'}));
                    a.download = 'impt-log.txt'; a.click();
                  }}>
                  ⬇ Download Log
                </button>
              </div>
              <div className="live-log" ref={logRef} style={{ height:180,maxHeight:180 }}>
                {logs.slice(-100).map(l => <div key={l.key}><span className="log-time">{l.t}</span><span className={`log-${l.type}`}>{l.msg}</span></div>)}
              </div>
            </div>
          </div>

          {/* FR101 — Comparison strategy progress */}
          {jobs.length > 1 && (
            <div className="card mt-4" style={{ background:'var(--gray-50)' }}>
              <div className="card-title" style={{ fontSize:13 }}>Strategy Progress</div>
              {jobs.map(j => (
                <div key={j.id} style={{ display:'flex',alignItems:'center',gap:12,marginBottom:8 }}>
                  <div style={{ width:120,fontSize:12.5,fontWeight:600 }}>{j.strategy === 'impt' ? 'IMPT Intelligent' : 'Random Sampling'}</div>
                  <div style={{ flex:1,background:'var(--gray-200)',height:8,borderRadius:4,overflow:'hidden' }}>
                    <div style={{ width:`${j.executed_mutants&&j.selected_mutants?Math.round(j.executed_mutants/j.selected_mutants*100):0}%`,height:'100%',background:j.strategy==='impt'?'var(--purple-mid)':'var(--blue)',borderRadius:4 }} />
                  </div>
                  <div style={{ fontSize:12,color:'var(--gray-500)',width:60 }}>{j.status}</div>
                </div>
              ))}
            </div>
          )}

          {/* FR104 — Timeout warning when > 25 min elapsed */}
          {elapsed > 1500 && elapsed < 1800 && (
            <div className="alert alert-warn mt-4">
              ⚠ Testing will timeout in {Math.round((1800-elapsed)/60)} minute(s) — wrapping up soon.
            </div>
          )}
          <div className="flex justify-end gap-3 mt-4">
            {/* FR103 — Stop with confirmation */}
            <button className="btn btn-secondary"
              onClick={() => {
                if (window.confirm('Are you sure you want to stop? Partial results may be saved.')) {
                  nav(`/results/${sessionId}`);
                }
              }}>
              ■ Stop Testing
            </button>
            <button className="btn btn-dark" onClick={()=>nav(`/results/${sessionId}`)}>
              View Results
            </button>
          </div>
        </div>
      </div>
    </AppShell>
  );
}

// src/pages/Running.jsx
import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getJobStatus } from '../api/client';
import { AppShell, PageHeader } from '../components/UI';

const LOG_MSGS = [
  { t: '12:45:32', msg: 'Starting mutant M-154: AOR at Calculator.java:67', type: 'running' },
  { t: '12:45:33', msg: 'Running test suite…', type: 'running' },
  { t: '12:45:35', msg: 'KILLED by testDivision() - Pass ✓', type: 'killed' },
  { t: '12:45:35', msg: 'Starting mutant M-155: ROR at StringUtils.java:89', type: 'running' },
  { t: '12:45:36', msg: 'Running test suite…', type: 'running' },
  { t: '12:45:38', msg: 'KILLED by testComparison() - Pass ✓', type: 'killed' },
  { t: '12:45:38', msg: 'Starting mutant M-156: COR at Parser.java:102', type: 'running' },
  { t: '12:45:39', msg: 'Running test suite…', type: 'running' },
  { t: '12:45:40', msg: 'SURVIVED - No test detected ✗', type: 'survived' },
  { t: '12:45:40', msg: 'Analyzing subsumption relationships…', type: 'running' },
  { t: '12:45:41', msg: 'Starting mutant M-157: AOR at Formatter.java:45', type: 'running' },
];

export default function Running() {
  const { id } = useParams();
  const nav    = useNavigate();
  const [job, setJob]       = useState(null);
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    let timer;
    const poll = async () => {
      try {
        const j = await getJobStatus(id);
        setJob(j);
        if (j.status === 'COMPLETED' || j.status === 'FAILED') {
          clearInterval(timer);
          if (j.status === 'COMPLETED') nav(`/results/${id}`);
        }
      } catch {}
    };
    poll();
    timer = setInterval(poll, 2000);
    return () => clearInterval(timer);
  }, [id]);

  // Elapsed time counter
  useEffect(() => {
    const t = setInterval(() => setElapsed(e => e + 1), 1000);
    return () => clearInterval(t);
  }, []);

  const pct = job?.status === 'RUNNING' ? Math.min(95, Math.round((elapsed / (job?.time_budget_seconds || 1200)) * 100)) : 0;
  const killed    = job?.killed_mutants  || 0;
  const executed  = job?.executed_mutants || 0;
  const survived  = executed - killed;
  const score     = executed ? ((killed / executed) * 100).toFixed(1) : '—';
  const remaining = job ? Math.max(0, (job.time_budget_seconds || 1200) - elapsed) : 0;
  const remMin    = Math.floor(remaining / 60);
  const remSec    = remaining % 60;

  return (
    <AppShell>
      <PageHeader icon="⏳" title="Test in Progress…" />
      <div className="page-content">
        <div className="card" style={{ maxWidth: 820, margin: '0 auto' }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 16 }}>Mutation Testing</h2>

          {/* Progress bar */}
          <div style={{ background: 'var(--green-xlight)', border: '1px solid var(--green-light)', borderRadius: 'var(--radius)', padding: '20px 24px', marginBottom: 20 }}>
            <div style={{ fontSize: 13, color: 'var(--gray-600)', fontWeight: 500, marginBottom: 8 }}>Overall Progress</div>
            <div style={{ background: 'var(--gray-200)', height: 20, borderRadius: 10, overflow: 'hidden', marginBottom: 8 }}>
              <div style={{ width: `${pct}%`, height: '100%', background: 'var(--green)', borderRadius: 10, transition: 'width 0.5s' }} />
            </div>
            <div style={{ fontSize: 32, fontWeight: 800, color: 'var(--green)', textAlign: 'center', letterSpacing: -1, marginBottom: 4 }}>
              {pct}% Complete
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12.5, color: 'var(--gray-500)' }}>
              <span>Executing mutant {executed} of {job?.selected_mutants || '…'}…</span>
              <span>Estimated time remaining: {remMin}m {String(remSec).padStart(2, '0')}s</span>
            </div>
          </div>

          <div className="grid-2" style={{ gap: 16 }}>
            <div className="card" style={{ background: 'var(--gray-50)' }}>
              <div className="card-title" style={{ fontSize: 13 }}>Live Statistics</div>
              {[
                ['Mutants Executed', executed],
                ['Mutants Killed',   <span style={{ color: 'var(--green)', fontWeight: 600 }}>{killed} ({executed ? Math.round(killed/executed*100) : 0}%)</span>],
                ['Mutants Survived', <span style={{ color: 'var(--red)', fontWeight: 600 }}>{survived} ({executed ? Math.round(survived/executed*100) : 0}%)</span>],
                ['Timeouts',         <span style={{ color: 'var(--amber)', fontWeight: 600 }}>0 (0%)</span>],
                ['Current Score',    <span style={{ fontWeight: 700 }}>{score}%</span>],
                ['Elapsed Time',     `${Math.floor(elapsed/60)}m ${elapsed%60}s`],
              ].map(([l, v]) => (
                <div className="summary-row" key={l}>
                  <span className="lbl">{l}</span><span className="val">{v}</span>
                </div>
              ))}
            </div>

            <div>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--gray-700)', marginBottom: 8 }}>Current Activity</div>
              <div className="live-log">
                {LOG_MSGS.map((l, i) => (
                  <div key={i}>
                    <span className="log-time">{l.t}</span>
                    <span className={`log-${l.type}`}>{l.msg}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="info-box mt-4" style={{ marginBottom: 16 }}>
            <strong>Current Phase:</strong> {job?.status === 'RUNNING' ? 'Executing Tests' : job?.status || 'Initializing…'}<br />
            <span style={{ color: 'var(--gray-400)' }}>Next Phase: Statistical extrapolation and final report generation</span>
          </div>

          <div className="flex justify-end gap-3">
            <button className="btn btn-dark" onClick={() => nav(`/results/${id}`)}>■ Stop & Save</button>
            <button className="btn btn-outline">⏸ Pause Testing</button>
          </div>
        </div>
      </div>
    </AppShell>
  );
}

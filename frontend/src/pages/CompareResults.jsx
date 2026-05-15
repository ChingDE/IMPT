// src/pages/CompareResults.jsx — Side-by-side session viewer
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { listSessions, compareStrategies } from '../api/client';
import { AppShell, PageHeader, Alert } from '../components/UI';

const STRATEGY_LABEL = {
  impt:           '⭐ IMPT Intelligent',
  random:         '🎲 Random Sampling',
  operator_based: '🔬 Operator-Based',
  exhaustive:     '📋 Exhaustive (Ground Truth)',
};

function SessionPanel({ session, job, exhaustiveJob }) {
  if (!session) return (
    <div style={{ flex:1, background:'var(--gray-50)', border:'2px dashed var(--gray-200)',
      borderRadius:'var(--radius)', padding:24, display:'flex', alignItems:'center',
      justifyContent:'center', color:'var(--gray-400)', fontSize:14, minHeight:300 }}>
      Select a session above
    </div>
  );

  const hasGroundTruth  = exhaustiveJob?.status === 'COMPLETED';
  const baselineScore   = hasGroundTruth
    ? exhaustiveJob.mutation_score
    : (job?.estimated_score ?? job?.mutation_score ?? 0);
  const baselineLabel   = hasGroundTruth ? 'Ground Truth' : 'Estimated';
  const baselineColor   = hasGroundTruth ? 'var(--green)' : 'var(--amber)';
  const primaryTimeSec  = job?.execution_time_seconds ?? 0;
  const exhaustiveTimeSec = hasGroundTruth ? (exhaustiveJob?.execution_time_seconds ?? 0) : 0;
  const timeSavedPct    = exhaustiveTimeSec > 0
    ? Math.round((1 - primaryTimeSec/exhaustiveTimeSec)*100)
    : (job?.time_saved_pct ?? 0);
  const correlation = hasGroundTruth && baselineScore > 0
    ? (1 - Math.abs((job?.mutation_score??0) - baselineScore) / baselineScore).toFixed(2)
    : '≥0.95 (est.)';

  const bsDisplay = typeof baselineScore === 'number'
    ? `${baselineScore > 1 ? baselineScore.toFixed(1) : (baselineScore*100).toFixed(1)}%`
    : '—';

  return (
    <div style={{ flex:1, border:'1px solid var(--gray-200)', borderRadius:'var(--radius)', overflow:'hidden' }}>
      <div style={{ background:'var(--purple-mid)', color:'#fff', padding:'12px 16px' }}>
        <div style={{ fontWeight:700, fontSize:15 }}>{session.name}</div>
        <div style={{ fontSize:12, opacity:0.85, marginTop:2 }}>
          {session.language} · {session.completed_at ? new Date(session.completed_at).toLocaleDateString() : session.status}
        </div>
      </div>
      <div style={{ padding:16 }}>
        {[
          ['Strategy',    STRATEGY_LABEL[job?.strategy]||job?.strategy||'—', 'var(--purple-mid)'],
          ['Mutation Score', `${job?.mutation_score??'—'}%`, 'var(--green)'],
          ['Mutants Tested', `${job?.executed_mutants??job?.mutants_tested??'—'} / ${job?.total_mutants??'—'}`, 'var(--amber)'],
          ['Execution Time', `${Math.round(primaryTimeSec/60)} min`, 'var(--blue)'],
          [`Exhaustive Score (${baselineLabel})`, bsDisplay, baselineColor],
          [`Correlation (${baselineLabel})`, String(correlation), hasGroundTruth?'var(--green)':'var(--amber)'],
          ['Time Saved vs Exhaustive', `${timeSavedPct}%`, 'var(--green)'],
        ].map(([l,v,c]) => (
          <div key={l} style={{ display:'flex',justifyContent:'space-between',alignItems:'center',
            padding:'8px 0',borderBottom:'1px solid var(--gray-100)',fontSize:13 }}>
            <span style={{ color:'var(--gray-600)' }}>{l}</span>
            <span style={{ fontWeight:700,color:c }}>{v}</span>
          </div>
        ))}
        <div style={{ marginTop:10, fontSize:11, padding:'6px 8px', borderRadius:4,
          color: hasGroundTruth?'var(--green)':'var(--amber)',
          background: hasGroundTruth?'var(--green-xlight)':'#FFFBEB',
          border: `1px solid ${hasGroundTruth?'var(--green-light)':'#FDE68A'}` }}>
          {hasGroundTruth
            ? `✓ Ground truth: exhaustive took ${Math.round(exhaustiveTimeSec/60)} min`
            : '⚠ No exhaustive baseline — correlation is estimated (Wilson CI)'}
        </div>
      </div>
    </div>
  );
}

export default function CompareResults() {
  const nav = useNavigate();
  const [sessions, setSessions]     = useState([]);
  const [leftId,  setLeftId]        = useState('');
  const [rightId, setRightId]       = useState('');
  const [leftData,  setLeftData]    = useState({ job:null, exhaustive:null });
  const [rightData, setRightData]   = useState({ job:null, exhaustive:null });
  const [loading, setLoading]       = useState(false);

  useEffect(() => { listSessions().then(setSessions).catch(()=>{}); }, []);

  const loadSession = async (sessionId, setter) => {
    if (!sessionId) { setter({ job:null, exhaustive:null }); return; }
    setLoading(true);
    try {
      const cmp  = await compareStrategies(sessionId);
      const jobs = Object.values(cmp);
      setter({
        job:       jobs.find(j => j.strategy !== 'exhaustive') || jobs[0],
        exhaustive: jobs.find(j => j.strategy === 'exhaustive') || null,
      });
    } catch { setter({ job:null, exhaustive:null }); }
    setLoading(false);
  };

  useEffect(() => { loadSession(leftId,  setLeftData);  }, [leftId]);
  useEffect(() => { loadSession(rightId, setRightData); }, [rightId]);

  const leftSession  = sessions.find(s => s.id === leftId);
  const rightSession = sessions.find(s => s.id === rightId);

  return (
    <AppShell>
      <PageHeader icon="🔀" title="Compare Sessions"
        right={<button className="hdr-btn ghost" onClick={()=>nav(-1)}>← Back</button>}
      />
      <div className="page-content">
        <div className="card mb-4">
          <div className="card-title" style={{ marginBottom:12 }}>Select Two Sessions to View Side-by-Side</div>
          <div style={{ display:'flex',gap:16,alignItems:'center',flexWrap:'wrap' }}>
            <div style={{ flex:1 }}>
              <label className="form-label">Session A</label>
              <select className="form-select" value={leftId} onChange={e=>setLeftId(e.target.value)}>
                <option value="">— Choose session —</option>
                {sessions.filter(s=>s.status==='completed').map(s=>(
                  <option key={s.id} value={s.id}>{s.name} ({new Date(s.completed_at||s.created_at).toLocaleDateString()})</option>
                ))}
              </select>
            </div>
            <div style={{ fontSize:18,color:'var(--gray-400)',paddingTop:20 }}>vs</div>
            <div style={{ flex:1 }}>
              <label className="form-label">Session B</label>
              <select className="form-select" value={rightId} onChange={e=>setRightId(e.target.value)}>
                <option value="">— Choose session —</option>
                {sessions.filter(s=>s.status==='completed').map(s=>(
                  <option key={s.id} value={s.id}>{s.name} ({new Date(s.completed_at||s.created_at).toLocaleDateString()})</option>
                ))}
              </select>
            </div>
          </div>
          <div style={{ marginTop:8,fontSize:12,color:'var(--gray-400)' }}>
            Each session is shown with its own results vs its exhaustive baseline (ground truth or estimated independently).
            This viewer does not cross-compare the two sessions — use it to evaluate different strategies or projects.
          </div>
        </div>

        {loading && <Alert type="info">Loading session data…</Alert>}

        <div style={{ display:'flex',gap:16,alignItems:'flex-start' }}>
          <SessionPanel session={leftSession}  job={leftData.job}  exhaustiveJob={leftData.exhaustive} />
          <SessionPanel session={rightSession} job={rightData.job} exhaustiveJob={rightData.exhaustive} />
        </div>
      </div>
    </AppShell>
  );
}

// src/pages/CompareResults.jsx — Compare two sessions side by side
import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { listSessions, compareStrategies } from '../api/client';
import { AppShell, PageHeader, Alert } from '../components/UI';

const fmt = secs => {
  if (!secs) return '—';
  if (secs < 60) return `${Math.round(secs)}s`;
  return `${(secs / 60).toFixed(1)} min`;
};

const MetricCard = ({ label, a, b, unit='', better='high', note }) => {
  const aNum = parseFloat(a) || 0;
  const bNum = parseFloat(b) || 0;
  const diff = aNum - bNum;
  const aBetter = better === 'high' ? diff > 0 : diff < 0;
  const bBetter = better === 'high' ? diff < 0 : diff > 0;
  const tied    = Math.abs(diff) < 0.01;
  return (
    <div style={{ background:'#fff', border:'1px solid var(--gray-200)', borderRadius:10,
      padding:'16px', textAlign:'center' }}>
      <div style={{ fontSize:11, color:'var(--gray-500)', textTransform:'uppercase',
        letterSpacing:'0.05em', fontWeight:600, marginBottom:12 }}>{label}</div>
      <div style={{ display:'flex', justifyContent:'center', alignItems:'baseline', gap:12 }}>
        <div>
          <div style={{ fontSize:24, fontWeight:800,
            color: tied ? 'var(--gray-700)' : aBetter ? 'var(--green)' : 'var(--red)' }}>
            {a}{unit}
          </div>
          <div style={{ fontSize:11, color:'var(--gray-400)', marginTop:2 }}>Session A</div>
        </div>
        <div style={{ fontSize:18, color:'var(--gray-300)', fontWeight:300 }}>vs</div>
        <div>
          <div style={{ fontSize:24, fontWeight:800,
            color: tied ? 'var(--gray-700)' : bBetter ? 'var(--green)' : 'var(--red)' }}>
            {b}{unit}
          </div>
          <div style={{ fontSize:11, color:'var(--gray-400)', marginTop:2 }}>Session B</div>
        </div>
      </div>
      {note && <div style={{ fontSize:11, color:'var(--gray-500)', marginTop:8, lineHeight:1.5 }}>{note}</div>}
    </div>
  );
};

export default function CompareResults() {
  const nav = useNavigate();
  const [searchParams] = useSearchParams();
  const [sessions,   setSessions]   = useState([]);
  const [sessionA,   setSessionA]   = useState(searchParams.get('a') || '');
  const [sessionB,   setSessionB]   = useState(searchParams.get('b') || '');
  const [jobsA,      setJobsA]      = useState(null);
  const [jobsB,      setJobsB]      = useState(null);
  const [loading,    setLoading]    = useState(false);
  const [error,      setError]      = useState('');

  useEffect(() => {
    listSessions().then(all => setSessions(all.filter(s => s.status === 'completed'))).catch(() => {});
  }, []);

  // Auto-compare if both are pre-selected from URL
  useEffect(() => {
    if (searchParams.get('a') && searchParams.get('b')) handleCompare();
  }, []);

  const handleCompare = async () => {
    if (!sessionA || !sessionB) { setError('Please select two sessions to compare.'); return; }
    if (sessionA === sessionB)  { setError('Please select two different sessions.'); return; }
    setError(''); setLoading(true);
    try {
      const [a, b] = await Promise.all([compareStrategies(sessionA), compareStrategies(sessionB)]);
      setJobsA(a); setJobsB(b);
    } catch {
      setError('Failed to load comparison data. Please try again.');
    } finally { setLoading(false); }
  };

  const getMetrics = (jobs) => {
    if (!jobs) return null;
    const primary   = Object.values(jobs).find(j => j.strategy !== 'exhaustive');
    const exhaustive = Object.values(jobs).find(j => j.strategy === 'exhaustive');
    if (!primary) return null;
    const score   = (primary.mutation_score || 0) * 100;
    const exhScore = exhaustive ? (exhaustive.mutation_score || 0) * 100 : null;
    const execSecs  = primary.execution_time_seconds || 0;
    const correlation = primary.real_correlation;
    return { primary, exhaustive, score, exhScore, execSecs, correlation,
             executed: primary.executed_mutants || 0, total: primary.total_mutants || 0,
             timeSaved: primary.time_saved_pct || 0 };
  };

  const mA = getMetrics(jobsA);
  const mB = getMetrics(jobsB);
  const sA = sessions.find(s => s.id === sessionA);
  const sB = sessions.find(s => s.id === sessionB);

  const getSummary = () => {
    if (!mA || !mB) return null;
    const scoreDiff = mA.score - mB.score;
    const timeDiff  = mB.execSecs - mA.execSecs;
    const faster    = timeDiff > 0 ? 'A' : 'B';
    const higher    = scoreDiff > 0 ? 'A' : 'B';

    if (Math.abs(scoreDiff) < 1) {
      return `Sessions A and B achieved nearly identical mutation scores (${mA.score.toFixed(1)}% vs ${mB.score.toFixed(1)}%). ` +
        (Math.abs(timeDiff) > 5
          ? `Session ${faster} completed ${fmt(Math.abs(timeDiff))} faster, making it the more efficient option.`
          : `Both sessions also completed in similar time.`);
    }

    return `Session ${higher} achieved a ${Math.abs(scoreDiff).toFixed(1)} percentage point higher mutation score ` +
      `(${(higher === 'A' ? mA : mB).score.toFixed(1)}% vs ${(higher === 'A' ? mB : mA).score.toFixed(1)}%). ` +
      (Math.abs(timeDiff) > 5
        ? `Session ${faster} was ${fmt(Math.abs(timeDiff))} faster. ` +
          (higher !== faster
            ? `There is a tradeoff — the more accurate session took longer. Consider your time constraints.`
            : `Session ${higher} achieved both a better score and faster execution.`)
        : `Execution time was similar for both sessions.`);
  };

  return (
    <AppShell>
      <PageHeader icon="⚖️" title="Compare Results"
        right={<button className="btn btn-secondary btn-sm" onClick={() => nav(-1)}>← Back</button>}
      />
      <div className="page-content">

        {/* Session selector */}
        <div className="card mb-4">
          <div style={{ fontSize:14, fontWeight:600, marginBottom:4 }}>Select Sessions to Compare</div>
          <div style={{ fontSize:12, color:'var(--gray-500)', marginBottom:12 }}>
            Only completed sessions are listed — sessions still running or that ended without results can't be compared.
          </div>
          <div style={{ display:'flex', gap:12, alignItems:'flex-end', flexWrap:'wrap' }}>
            <div style={{ flex:1, minWidth:200 }}>
              <div style={{ fontSize:11, color:'var(--gray-500)', marginBottom:4, fontWeight:600 }}>SESSION A</div>
              <select value={sessionA} onChange={e => setSessionA(e.target.value)}
                style={{ width:'100%', padding:'8px 10px', borderRadius:6,
                  border:'1px solid var(--gray-200)', fontSize:13 }}>
                <option value="">— Select a session —</option>
                {sessions.map(s => (
                  <option key={s.id} value={s.id}>{s.name} ({new Date(s.updated_at||s.created_at).toLocaleDateString()})</option>
                ))}
              </select>
            </div>
            <div style={{ fontSize:18, color:'var(--gray-400)', paddingBottom:8 }}>vs</div>
            <div style={{ flex:1, minWidth:200 }}>
              <div style={{ fontSize:11, color:'var(--gray-500)', marginBottom:4, fontWeight:600 }}>SESSION B</div>
              <select value={sessionB} onChange={e => setSessionB(e.target.value)}
                style={{ width:'100%', padding:'8px 10px', borderRadius:6,
                  border:'1px solid var(--gray-200)', fontSize:13 }}>
                <option value="">— Select a session —</option>
                {sessions.map(s => (
                  <option key={s.id} value={s.id}>{s.name} ({new Date(s.updated_at||s.created_at).toLocaleDateString()})</option>
                ))}
              </select>
            </div>
            <button className="btn btn-primary" onClick={handleCompare} disabled={loading}>
              {loading ? 'Loading…' : '⚖️ Compare'}
            </button>
          </div>
          {error && <div style={{ marginTop:12 }}><Alert type="error">{error}</Alert></div>}
        </div>

        {/* Results */}
        {mA && mB && (
          <>
            {/* Summary banner */}
            <div style={{ background:'var(--purple-mid)', borderRadius:10, padding:'20px 24px',
              marginBottom:24, color:'#fff' }}>
              <div style={{ fontSize:12, fontWeight:700, textTransform:'uppercase',
                letterSpacing:'0.1em', marginBottom:8, opacity:0.8 }}>📊 Comparison Summary</div>
              <div style={{ fontSize:15, lineHeight:1.75 }}>{getSummary()}</div>
            </div>

            {/* Metric cards */}
            <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit,minmax(150px,1fr))', gap:12, marginBottom:24 }}>
              <MetricCard label="Mutation Score" a={mA.score.toFixed(1)} b={mB.score.toFixed(1)} unit="%" better="high"
                note={Math.abs(mA.score - mB.score) < 1 ? 'Virtually identical' :
                  `${Math.abs(mA.score - mB.score).toFixed(1)}pp difference`} />
              <MetricCard label="Execution Time" a={fmt(mA.execSecs)} b={fmt(mB.execSecs)} better="low"
                note={mA.execSecs && mB.execSecs ?
                  (mA.execSecs < mB.execSecs ? `A is ${fmt(mB.execSecs - mA.execSecs)} faster` :
                   mB.execSecs < mA.execSecs ? `B is ${fmt(mA.execSecs - mB.execSecs)} faster` : 'Same speed') : ''} />
              <MetricCard label="Mutants Tested"
                a={`${mA.executed}/${mA.total}`} b={`${mB.executed}/${mB.total}`} better="high"
                note={`A: ${mA.total > 0 ? ((mA.executed/mA.total)*100).toFixed(0) : 0}% sample · B: ${mB.total > 0 ? ((mB.executed/mB.total)*100).toFixed(0) : 0}% sample`} />
              <MetricCard label="Time Saved vs Exhaustive"
                a={`${mA.timeSaved.toFixed(1)}%`} b={`${mB.timeSaved.toFixed(1)}%`} better="high"
                note="Higher = more efficient than exhaustive testing" />
              <MetricCard label="Correlation"
                a={mA.correlation != null ? mA.correlation.toFixed(3) : '—'}
                b={mB.correlation != null ? mB.correlation.toFixed(3) : '—'}
                better="high"
                note="How closely results match exhaustive testing" />
              <MetricCard label="Exhaustive Score"
                a={mA.exhScore != null ? `${mA.exhScore.toFixed(1)}%` : '—'}
                b={mB.exhScore != null ? `${mB.exhScore.toFixed(1)}%` : '—'}
                better="high"
                note="Ground truth score (only if exhaustive was run)" />
            </div>

            {/* Key differences table */}
            <div className="card mb-4">
              <div className="card-title" style={{ marginBottom:16 }}>Key Differences</div>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Category</th>
                    <th style={{ textAlign:'center' }}>{sA?.name || 'Session A'}</th>
                    <th style={{ textAlign:'center' }}>{sB?.name || 'Session B'}</th>
                    <th>Insight</th>
                  </tr>
                </thead>
                <tbody>
                  {[
                    {
                      cat: 'Mutation Score',
                      a: `${mA.score.toFixed(1)}%`, b: `${mB.score.toFixed(1)}%`,
                      insight: Math.abs(mA.score - mB.score) < 1
                        ? 'Effectively identical — both sessions found the same proportion of bugs.'
                        : `${mA.score > mB.score ? 'A' : 'B'} found ${Math.abs(mA.score - mB.score).toFixed(1)}pp more bugs.`,
                    },
                    {
                      cat: 'Mutants Skipped',
                      a: mA.total - mA.executed, b: mB.total - mB.executed,
                      insight: 'Mutants not executed due to subsumption or time budget.',
                    },
                    {
                      cat: 'Survived Mutants',
                      a: mA.executed - (mA.primary.killed_mutants || 0),
                      b: mB.executed - (mB.primary.killed_mutants || 0),
                      insight: 'Survived mutants represent potential test gaps.',
                    },
                    {
                      cat: 'Strategy',
                      a: mA.primary.strategy === 'impt' ? '⭐ IMPT' :
                         mA.primary.strategy === 'operator_based' ? '🔬 Operator' : '🎲 Random',
                      b: mB.primary.strategy === 'impt' ? '⭐ IMPT' :
                         mB.primary.strategy === 'operator_based' ? '🔬 Operator' : '🎲 Random',
                      insight: mA.primary.strategy === mB.primary.strategy
                        ? 'Both sessions used the same strategy.'
                        : 'Different strategies — score differences may reflect prioritization effectiveness.',
                    },
                  ].map(({ cat, a, b, insight }) => (
                    <tr key={cat}>
                      <td style={{ fontWeight:600 }}>{cat}</td>
                      <td style={{ textAlign:'center' }}>{String(a)}</td>
                      <td style={{ textAlign:'center' }}>{String(b)}</td>
                      <td style={{ fontSize:12, color:'var(--gray-500)', lineHeight:1.5 }}>{insight}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Recommendation */}
            <div style={{ background:'#fffbeb', border:'1px solid #fde68a', borderRadius:10,
              padding:'16px 20px', fontSize:13, lineHeight:1.75 }}>
              <strong>💡 Recommendation: </strong>
              {(() => {
                if (!mA || !mB) return '';
                const scoreDiff = Math.abs(mA.score - mB.score);
                const timeDiff  = Math.abs(mA.execSecs - mB.execSecs);
                const aFaster   = mA.execSecs < mB.execSecs;
                const aHigher   = mA.score > mB.score;

                if (scoreDiff < 1)
                  return `Both sessions performed similarly. ${aFaster ? 'Session A' : 'Session B'} was faster, making it the more efficient choice for regular use.`;
                if (aHigher && aFaster)
                  return `Session A achieved both a higher score and faster execution — it is the clearly superior configuration for this project.`;
                if (!aHigher && !aFaster)
                  return `Session B achieved both a higher score and faster execution — it is the clearly superior configuration for this project.`;
                return `There is a tradeoff: ${aHigher ? 'Session A' : 'Session B'} scores ${scoreDiff.toFixed(1)}pp higher but takes ${fmt(timeDiff)} longer. ` +
                  `Use the higher-scoring session for critical releases and the faster one for day-to-day development feedback.`;
              })()}
            </div>
          </>
        )}

        {!mA && !mB && !loading && (
          <div style={{ textAlign:'center', padding:'60px 20px', color:'var(--gray-400)' }}>
            <div style={{ fontSize:48, marginBottom:16 }}>⚖️</div>
            <div style={{ fontSize:16, fontWeight:600, marginBottom:8 }}>Select two sessions above to compare</div>
            <div style={{ fontSize:13 }}>You can also click the Compare button on any session in Test History.</div>
          </div>
        )}

      </div>
    </AppShell>
  );
}

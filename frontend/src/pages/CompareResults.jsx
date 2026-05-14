// src/pages/CompareResults.jsx  FR119-FR128
import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { compareStrategies } from '../api/client';
import { AppShell, PageHeader, Alert } from '../components/UI';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

const STRATEGY_LABELS = {
  impt:          '⭐ IMPT Intelligent',
  random:        'Random Sampling',
  operator_based:'Operator-Based',
};

const CORRELATION_LABEL = r => {
  if (r === null || r === undefined) return '—';
  const n = parseFloat(r);
  if (n >= 0.8) return { label: `r = ${n.toFixed(2)} (Strong)`,   color: 'var(--green)' };
  if (n >= 0.6) return { label: `r = ${n.toFixed(2)} (Moderate)`, color: 'var(--amber)' };
  return            { label: `r = ${n.toFixed(2)} (Weak)`,     color: 'var(--red)'   };
};

export default function CompareResults() {
  const { sessionId } = useParams();
  const nav = useNavigate();
  const [data, setData]   = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    compareStrategies(sessionId)
      .then(setData)
      .catch(e => setError(e.response?.data?.detail || 'Failed to load comparison data.'));
  }, [sessionId]);

  const strategies = data ? Object.values(data) : [];
  const impt = strategies.find(s => s.strategy === 'impt');

  // Chart data
  const scoreChart = strategies.map(s => ({
    name: STRATEGY_LABELS[s.strategy] || s.strategy,
    'Mutation Score (%)': s.mutation_score,
  }));
  const timeChart = strategies.map(s => ({
    name: STRATEGY_LABELS[s.strategy] || s.strategy,
    'Execution Time (min)': s.execution_time_min,
  }));

  const handleExportCSV = () => {
    if (!strategies.length) return;
    const headers = ['Strategy','Mutation Score (%)','Execution Time (min)','Time Saved (%)','Correlation','Mutants Tested','Total Mutants'];
    const rows = strategies.map(s => [
      STRATEGY_LABELS[s.strategy] || s.strategy,
      s.mutation_score, s.execution_time_min, s.time_saved_pct,
      s.estimated_correlation ?? '—', s.mutants_tested, s.total_mutants,
    ]);
    const csv = [headers, ...rows].map(r => r.join(',')).join('\n');
    const a   = document.createElement('a');
    a.href    = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
    a.download = `comparison-${sessionId.slice(0,8)}.csv`;
    a.click();
  };

  return (
    <AppShell>
      <PageHeader icon="🔀" title="Strategy Comparison Results"
        right={
          <div style={{ display:'flex',gap:8 }}>
            {strategies.length > 0 && (
              <button className="hdr-btn ghost" onClick={handleExportCSV}>⬇ Export CSV</button>
            )}
            <button className="hdr-btn ghost" onClick={() => nav(`/results/${sessionId}`)}>← Back to Results</button>
          </div>
        }
      />
      <div className="page-content">
        {error && <Alert type="error">{error}</Alert>}
        {!data ? (
          <div style={{ textAlign:'center',padding:40,color:'var(--gray-400)' }}>Loading comparison data…</div>
        ) : (
          <>
            {/* FR125 — IMPT advantage summary banner */}
            {impt && (
              <div className="card mb-4" style={{
                background:'linear-gradient(135deg,var(--purple-mid),var(--purple))',
                color:'#fff', border:'none',
              }}>
                <div style={{ fontWeight:700,fontSize:14,marginBottom:8 }}>📊 Comparison Summary</div>
                <div style={{ fontSize:13.5,opacity:.9,lineHeight:1.65 }}>
                  IMPT Intelligent achieved <strong>{impt.mutation_score}%</strong> mutation score
                  with <strong>{impt.time_saved_pct}%</strong> time savings compared to exhaustive testing,
                  while maintaining a <strong>{impt.estimated_correlation}</strong> correlation
                  with exhaustive results — superior to all comparison strategies below.
                </div>
              </div>
            )}

            {/* FR119–FR122 — Comparison table */}
            <div className="card mb-4">
              <div className="card-title">Metric Comparison</div>
              <div style={{ overflowX:'auto' }}>
                <table className="data-table" style={{ minWidth:700 }}>
                  <thead>
                    <tr>
                      <th>Strategy</th>
                      <th>Mutation Score</th>
                      <th>Exec Time</th>
                      <th>Time Saved</th>
                      {/* FR122 — Pearson r */}
                      <th>Correlation (Pearson r)</th>
                      <th>Mutants Tested</th>
                    </tr>
                  </thead>
                  <tbody>
                    {strategies.map(s => {
                      const cor = CORRELATION_LABEL(s.estimated_correlation);
                      return (
                        <tr key={s.strategy} className={s.strategy === 'impt' ? 'impt-row' : ''}>
                          {/* FR127 — Clickable strategy name */}
                          <td className="bold" style={{ cursor:'pointer',color:'var(--purple-mid)' }}
                            onClick={() => nav(`/results/${sessionId}?strategy=${s.strategy}`)}>
                            {STRATEGY_LABELS[s.strategy] || s.strategy}
                          </td>
                          <td>
                            <span style={{ fontWeight:700, color: s.mutation_score >= 80 ? 'var(--green)' : 'var(--amber)' }}>
                              {s.mutation_score}%
                            </span>
                          </td>
                          <td>{s.execution_time_min} min</td>
                          <td className="text-green font-bold">{s.time_saved_pct}%</td>
                          <td style={{ color: cor.color }}>{typeof cor === 'object' ? cor.label : cor}</td>
                          <td>{s.mutants_tested}/{s.total_mutants}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              {/* FR122 — Interpretation guide */}
              <div style={{ fontSize:12,color:'var(--gray-400)',marginTop:10 }}>
                Correlation guide: <strong>r &gt; 0.8</strong> = Strong &nbsp;|&nbsp;
                <strong>0.6–0.8</strong> = Moderate &nbsp;|&nbsp;
                <strong>&lt; 0.6</strong> = Weak
              </div>
            </div>

            {/* FR121 — Time savings metric */}
            {impt && (
              <div className="grid-2 mb-4" style={{ gap:16 }}>
                <div className="stat-card green" style={{ textAlign:'center' }}>
                  <div className="stat-label">IMPT Time Saved vs Exhaustive</div>
                  <div className="stat-value">{impt.time_saved_pct}%</div>
                  <div style={{ fontSize:12,color:'var(--green)',marginTop:4 }}>
                    ({impt.execution_time_min} min vs estimated exhaustive)
                  </div>
                </div>
                <div className="stat-card purple" style={{ textAlign:'center' }}>
                  <div className="stat-label">IMPT Mutation Score</div>
                  <div className="stat-value">{impt.mutation_score}%</div>
                </div>
              </div>
            )}

            {/* FR123 — Mutation score comparison chart */}
            <div className="card mb-4">
              <div className="card-title">📊 Mutation Score Comparison</div>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={scoreChart} margin={{ top:5,right:20,left:-10,bottom:5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--gray-100)" />
                  <XAxis dataKey="name" tick={{ fontSize:11 }} />
                  <YAxis domain={[0,100]} tick={{ fontSize:11 }} tickFormatter={v => `${v}%`} />
                  <Tooltip formatter={v => [`${v}%`, 'Mutation Score']} />
                  <Bar dataKey="Mutation Score (%)" fill="var(--purple-mid)" radius={[4,4,0,0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* FR124 — Execution time comparison chart */}
            <div className="card mb-4">
              <div className="card-title">⏱ Execution Time Comparison</div>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={timeChart} margin={{ top:5,right:20,left:-10,bottom:5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--gray-100)" />
                  <XAxis dataKey="name" tick={{ fontSize:11 }} />
                  <YAxis tick={{ fontSize:11 }} tickFormatter={v => `${v}m`} />
                  <Tooltip formatter={v => [`${v} min`, 'Execution Time']} />
                  <Bar dataKey="Execution Time (min)" fill="var(--blue)" radius={[4,4,0,0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>

            <div className="flex justify-between">
              <button className="btn btn-secondary" onClick={() => nav(`/results/${sessionId}`)}>← Back to Results</button>
              <button className="btn btn-outline btn-sm" onClick={handleExportCSV}>⬇ Export CSV</button>
            </div>
          </>
        )}
      </div>
    </AppShell>
  );
}

// src/pages/Reports.jsx — Aggregate analytics for all sessions
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getReportsStats } from '../api/client';
import { AppShell, PageHeader } from '../components/UI';

const fmt = secs => {
  if (!secs) return '—';
  if (secs < 60) return `${Math.round(secs)}s`;
  return `${Math.round(secs / 60)} min`;
};

const ScoreBadge = ({ score }) => {
  const color = score >= 85 ? '#16a34a' : score >= 70 ? '#ca8a04' : score >= 55 ? '#ea580c' : '#dc2626';
  const bg    = score >= 85 ? '#dcfce7' : score >= 70 ? '#fef9c3' : score >= 55 ? '#ffedd5' : '#fee2e2';
  return (
    <span style={{ fontWeight:700, fontSize:13, padding:'3px 10px', borderRadius:999,
      background:bg, color }}>{score.toFixed(1)}%</span>
  );
};

const MiniBar = ({ value, max, color }) => (
  <div style={{ display:'flex', alignItems:'center', gap:8 }}>
    <div style={{ flex:1, background:'var(--gray-100)', borderRadius:4, height:8 }}>
      <div style={{ width:`${Math.min(100, (value/max)*100)}%`, height:'100%',
        background:color, borderRadius:4, transition:'width .4s' }} />
    </div>
    <span style={{ fontSize:12, color:'var(--gray-600)', minWidth:24 }}>{value}</span>
  </div>
);

export default function Reports() {
  const nav = useNavigate();
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getReportsStats().then(setStats).catch(() => {}).finally(() => setLoading(false));
  }, []);

  if (loading) return (
    <AppShell>
      <PageHeader icon="📊" title="Results & Reports" />
      <div className="page-content" style={{ textAlign:'center', paddingTop:60, color:'var(--gray-400)' }}>
        Loading analytics…
      </div>
    </AppShell>
  );

  if (!stats || stats.total_tests === 0) return (
    <AppShell>
      <PageHeader icon="📊" title="Results & Reports" />
      <div className="page-content">
        <div style={{ textAlign:'center', padding:'80px 20px' }}>
          <div style={{ fontSize:48, marginBottom:16 }}>📊</div>
          <div style={{ fontSize:18, fontWeight:700, color:'var(--gray-700)', marginBottom:8 }}>
            No test data yet
          </div>
          <div style={{ fontSize:14, color:'var(--gray-500)', marginBottom:24, lineHeight:1.65 }}>
            Complete your first mutation test session to see aggregate analytics here.
          </div>
          <button className="btn btn-primary" onClick={() => nav('/new-session')}>
            🚀 Start a Test Session
          </button>
        </div>
      </div>
    </AppShell>
  );

  const { total_tests, avg_score, avg_time_secs, projects_tested, trend, distribution, recent } = stats;
  // Map session id -> name (from the recent list) so trend points can name their session on hover.
  const nameById = Object.fromEntries((recent || []).map(r => [r.session_id, r.name]));
  const distMax = Math.max(...Object.values(distribution), 1);
  const trendMin = trend.length ? Math.min(...trend.map(t => t.score)) - 5 : 0;
  const trendMax = trend.length ? Math.max(...trend.map(t => t.score)) + 5 : 100;

  // Simple inline SVG line chart for trend
  const TrendChart = () => {
    if (trend.length < 2) return (
      <div style={{ height:160, display:'grid', placeItems:'center', color:'var(--gray-400)', fontSize:13 }}>
        Need at least 2 completed sessions to show trend
      </div>
    );
    const W = 600, H = 140, PAD = 20;
    const xs = trend.map((_, i) => PAD + (i / (trend.length - 1)) * (W - PAD * 2));
    const ys = trend.map(t => H - PAD - ((t.score - trendMin) / (trendMax - trendMin)) * (H - PAD * 2));
    const path = xs.map((x, i) => `${i === 0 ? 'M' : 'L'}${x},${ys[i]}`).join(' ');
    const area = `M${xs[0]},${H - PAD} ` + xs.map((x, i) => `L${x},${ys[i]}`).join(' ') + ` L${xs[xs.length-1]},${H - PAD} Z`;
    const lastScore = trend[trend.length - 1]?.score;
    const firstScore = trend[0]?.score;
    const improving = lastScore >= firstScore;

    return (
      <div>
        <svg viewBox={`0 0 ${W} ${H}`} style={{ width:'100%', height:160 }}>
          <defs>
            <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#7C3AED" stopOpacity="0.2" />
              <stop offset="100%" stopColor="#7C3AED" stopOpacity="0" />
            </linearGradient>
          </defs>
          {/* Grid lines */}
          {[0, 25, 50, 75, 100].map(pct => {
            const y = H - PAD - ((pct - trendMin) / (trendMax - trendMin)) * (H - PAD * 2);
            if (y < PAD || y > H - PAD) return null;
            return <line key={pct} x1={PAD} x2={W - PAD} y1={y} y2={y}
              stroke="#e5e7eb" strokeWidth={0.5} />;
          })}
          {/* Area fill */}
          <path d={area} fill="url(#areaGrad)" />
          {/* Line */}
          <path d={path} fill="none" stroke="#7C3AED" strokeWidth={2.5} strokeLinejoin="round" />
          {/* Dots — each with a larger transparent hit target and a hover tooltip naming the session */}
          {xs.map((x, i) => {
            const t = trend[i];
            const label = `${nameById[t.session_id] || 'Session'} — ${t.score}% on ${t.date}`;
            return (
              <g key={i}>
                <circle cx={x} cy={ys[i]} r={4} fill="#7C3AED" stroke="#fff" strokeWidth={2} />
                <circle cx={x} cy={ys[i]} r={10} fill="transparent" style={{ cursor:'pointer' }}>
                  <title>{label}</title>
                </circle>
              </g>
            );
          })}
        </svg>
        <div style={{ display:'flex', justifyContent:'space-between', fontSize:11, color:'var(--gray-400)', marginTop:4 }}>
          {trend.map((t, i) => <span key={i}>{t.date}</span>)}
        </div>
        <div style={{ marginTop:12, padding:'10px 14px', background: improving ? '#f0fdf4' : '#fff7ed',
          border:`1px solid ${improving ? '#86efac' : '#fdba74'}`, borderRadius:8, fontSize:13, lineHeight:1.6 }}>
          <strong>{improving ? '📈 Trend Analysis:' : '📉 Trend Analysis:'}</strong>{' '}
          Your average mutation score {improving ? 'improved' : 'declined'} from{' '}
          <strong>{firstScore}%</strong> to <strong>{lastScore}%</strong> over the last {trend.length} sessions
          ({improving ? '+' : ''}{(lastScore - firstScore).toFixed(1)} percentage points).{' '}
          {improving
            ? 'Your test suite quality is improving. Keep focusing on high-effectiveness operators.'
            : 'Consider reviewing survived mutants in recent sessions to identify test gaps.'}
        </div>
      </div>
    );
  };

  return (
    <AppShell>
      <PageHeader icon="📊" title="Results & Reports"
        right={
          <button className="btn btn-secondary btn-sm" onClick={() => nav('/history')}>
            📋 View Test History
          </button>
        }
      />
      <div className="page-content">

        {/* Summary stats */}
        <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:16, marginBottom:24 }}>
          {[
            { label:'Total Tests Run',    value:total_tests,  color:'var(--purple-mid)', suffix:'' },
            { label:'Avg Mutation Score', value:`${avg_score}%`, color:'var(--green)',  suffix:'' },
            { label:'Avg Testing Time',   value:fmt(avg_time_secs), color:'var(--amber)', suffix:'' },
            { label:'Projects Tested',    value:projects_tested, color:'var(--blue)', suffix:'' },
          ].map(({ label, value, color }) => (
            <div key={label} className="card" style={{ textAlign:'center', padding:'20px 16px' }}>
              <div style={{ fontSize:32, fontWeight:800, color, marginBottom:4 }}>{value}</div>
              <div style={{ fontSize:12, color:'var(--gray-500)', textTransform:'uppercase',
                letterSpacing:'0.05em', fontWeight:600 }}>{label}</div>
            </div>
          ))}
        </div>

        {/* Trend chart */}
        <div className="card mb-4">
          <div className="card-title" style={{ marginBottom:16 }}>📈 Mutation Score Trend</div>
          <TrendChart />
        </div>

        {/* Recent results table */}
        <div className="card mb-4">
          <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:16 }}>
            <div className="card-title" style={{ margin:0 }}>🕐 Recent Test Results</div>
            <button className="btn btn-secondary btn-sm" onClick={() => nav('/history')}>
              View All →
            </button>
          </div>
          {recent.length === 0 ? (
            <div style={{ textAlign:'center', padding:'20px', color:'var(--gray-400)', fontSize:13 }}>
              No completed sessions yet
            </div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Session Name</th>
                  <th>Date</th>
                  <th>Mutation Score</th>
                  <th>Mutants Tested</th>
                  <th>Time</th>
                  <th>Saved</th>
                  <th>Strategy</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {recent.map(r => (
                  <tr key={r.session_id}>
                    <td style={{ fontWeight:600 }}>{r.name}</td>
                    <td style={{ fontSize:12, color:'var(--gray-500)' }}>
                      {new Date(r.completed_at).toLocaleDateString('en-US',
                        { month:'short', day:'numeric', hour:'2-digit', minute:'2-digit' })}
                    </td>
                    <td><ScoreBadge score={r.mutation_score} /></td>
                    <td style={{ fontSize:13 }}>{r.executed_mutants} / {r.total_mutants}</td>
                    <td style={{ fontSize:13 }}>{fmt(r.execution_secs)}</td>
                    <td style={{ fontSize:13, color:'var(--green)', fontWeight:600 }}>
                      {r.time_saved_pct > 0 ? `${r.time_saved_pct.toFixed(0)}%` : '—'}
                    </td>
                    <td style={{ fontSize:12 }}>
                      <span className="badge badge-blue">
                        {r.strategy === 'impt' ? 'IMPT' :
                         r.strategy === 'operator_based' ? 'Operator' : 'Random'}
                      </span>
                    </td>
                    <td>
                      <div style={{ display:'flex', gap:6 }}>
                        <button className="btn btn-primary btn-sm"
                          onClick={() => nav(`/results/${r.session_id}`)}>View</button>
                        <button className="btn btn-secondary btn-sm"
                          onClick={() => nav(`/compare?a=${r.session_id}`)}>Compare</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Score distribution */}
        <div className="card mb-4">
          <div className="card-title" style={{ marginBottom:16 }}>📊 Mutation Score Distribution</div>
          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:32, alignItems:'start' }}>
            <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
              {[
                { label:'Excellent (85–100%)', key:'excellent', color:'#16a34a' },
                { label:'Good (70–84%)',        key:'good',      color:'#65a30d' },
                { label:'Average (55–69%)',     key:'average',   color:'#ca8a04' },
                { label:'Poor (0–54%)',         key:'poor',      color:'#dc2626' },
              ].map(({ label, key, color }) => (
                <div key={key}>
                  <div style={{ display:'flex', justifyContent:'space-between',
                    fontSize:13, marginBottom:4, color:'var(--gray-700)' }}>
                    <span>{label}</span>
                    <span style={{ fontWeight:600 }}>{distribution[key]} tests</span>
                  </div>
                  <MiniBar value={distribution[key]} max={distMax} color={color} />
                </div>
              ))}
            </div>
            <div style={{ padding:'16px', background:'#fffbeb', border:'1px solid #fde68a',
              borderRadius:8, fontSize:13, lineHeight:1.75 }}>
              <strong>💡 Insight</strong><br />
              {(() => {
                const good = distribution.excellent + distribution.good;
                const total = Object.values(distribution).reduce((a,b) => a+b, 0);
                const pct = total > 0 ? Math.round((good/total)*100) : 0;
                return `${pct}% of your sessions scored above 70%, ${pct >= 75 ? 'which is above' : 'approaching'} the industry average for web applications. `;
              })()}
              {distribution.poor > 0
                ? `${distribution.poor} session${distribution.poor > 1 ? 's' : ''} scored below 55% — review the survived mutants in those sessions to identify test gaps.`
                : 'No sessions scored below 55%. Your test suite quality is consistently solid.'}
            </div>
          </div>
        </div>

      </div>
    </AppShell>
  );
}

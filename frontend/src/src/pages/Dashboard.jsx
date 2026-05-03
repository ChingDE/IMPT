// src/pages/Dashboard.jsx
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { listJobs, getSummary } from '../api/client';
import { AppShell, PageHeader, StatCard, ScorePill, TrendChart } from '../components/UI';
import { User } from 'lucide-react';

export default function Dashboard() {
  const nav = useNavigate();
  const { user } = useAuth();
  const [jobs, setJobs]       = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([listJobs(), getSummary()])
      .then(([j, s]) => { setJobs(j || []); setSummary(s); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const completed = jobs.filter(j => j.status === 'COMPLETED');
  const avgSaved  = completed.length
    ? Math.round(completed.reduce((a, j) => a + (j.time_saved_pct || 0), 0) / completed.length)
    : 0;
  const avgCorr   = completed.length
    ? (completed.reduce((a, j) => a + (j.estimated_score || 0), 0) / completed.length).toFixed(2)
    : '—';

  const trendData = completed.slice(-7).map((j, i) => ({
    date: new Date(j.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
    score: Math.round((j.mutation_score || 0) * 100),
  }));

  return (
    <AppShell>
      <PageHeader icon="🏠" title="User Dashboard"
        right={<div className="hdr-avatar" onClick={() => nav('/profile')}><User size={16} /></div>} />
      <div className="page-content">
        {/* Key metrics */}
        <div className="grid-2 mb-4">
          <div className="stat-card green">
            <div className="stat-label">Time Saved</div>
            <div className="stat-value">{completed.length ? `${avgSaved}%` : '—'}</div>
            <div className="stat-delta" style={{ color: 'var(--green)' }}>
              {completed.length ? `vs exhaustive testing` : 'Run your first test'}
            </div>
          </div>
          <div className="stat-card green">
            <div className="stat-label">Correlation</div>
            <div className="stat-value">{avgCorr}</div>
            <div className="stat-delta" style={{ color: 'var(--green)' }}>High Confidence</div>
          </div>
        </div>

        {/* Recent test sessions */}
        <div className="card mb-4">
          <div className="flex items-center justify-between mb-3">
            <div className="card-title" style={{ marginBottom: 0 }}>Recent Test Sessions</div>
            <span className="link text-sm" onClick={() => nav('/history')}>View Full Test History</span>
          </div>
          {loading ? (
            <div style={{ textAlign: 'center', padding: '20px', color: 'var(--gray-400)' }}>Loading…</div>
          ) : jobs.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '30px', color: 'var(--gray-400)' }}>
              <div style={{ fontSize: 32, marginBottom: 8 }}>🔬</div>
              <div>No test sessions yet. Run your first mutation test!</div>
            </div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Project</th>
                  <th>Date</th>
                  <th>Score</th>
                  <th>Time</th>
                </tr>
              </thead>
              <tbody>
                {jobs.slice(0, 5).map(j => (
                  <tr key={j.id} style={{ cursor: 'pointer' }} onClick={() => nav(`/results/${j.id}`)}>
                    <td className="bold">{j.project_id?.slice(0, 12) || '—'}</td>
                    <td className="text-muted text-sm">{new Date(j.created_at).toLocaleDateString()}</td>
                    <td>{j.mutation_score ? <ScorePill value={Math.round(j.mutation_score * 100)} /> : <span className="badge badge-gray">{j.status}</span>}</td>
                    <td className="text-muted">{j.execution_time_seconds ? `${(j.execution_time_seconds / 60).toFixed(1)}m` : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Quick actions */}
        <div className="grid-3 mb-4">
          <button className="btn btn-primary btn-lg" style={{ padding: '20px', fontSize: 15, justifyContent: 'center' }}
            onClick={() => nav('/new-session')}>
            🚀 New Test Session
          </button>
          <button className="btn btn-outline" style={{ padding: '20px', fontSize: 14 }}
            onClick={() => nav('/profiles')}>
            📁 Load Saved Profile
          </button>
          <button className="btn btn-outline" style={{ padding: '20px', fontSize: 14 }}
            onClick={() => nav('/reports')}>
            📋 View Reports
          </button>
        </div>

        {/* Performance trend */}
        <div className="card">
          <div className="card-title">📈 Performance Trend</div>
          <TrendChart data={trendData} />
          {trendData.length > 1 && (
            <div className="info-box mt-3">
              📊 <strong>Trend Analysis:</strong> Based on your last {trendData.length} test sessions.
              Average mutation score: {Math.round(trendData.reduce((a, d) => a + d.score, 0) / trendData.length)}%.
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}

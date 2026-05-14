// src/pages/Dashboard.jsx  FR040–FR050
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { listSessions, deleteSession, getDashboardStats, getTrend } from '../api/client';
import { AppShell, PageHeader, StatusBadge, Alert, TrendChart, ConfirmModal } from '../components/UI';

export default function Dashboard() {
  const nav = useNavigate();
  const { user } = useAuth();
  const [sessions, setSessions]   = useState([]);
  const [stats, setStats]         = useState(null);
  const [trend, setTrend]         = useState([]);
  const [loading, setLoading]     = useState(true);
  const [deleteTarget, setDeleteTarget] = useState(null);

  useEffect(() => {
    Promise.all([listSessions(), getDashboardStats(), getTrend()])
      .then(([s, st, tr]) => { setSessions(s || []); setStats(st); setTrend(tr || []); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteSession(deleteTarget.id);
      setSessions(s => s.filter(x => x.id !== deleteTarget.id));
    } catch {}
    setDeleteTarget(null);
  };

  const firstName = user?.first_name || 'there';
  const isFirstTime = sessions.filter(s => s.status === 'completed').length === 0;

  return (
    <AppShell>
      <PageHeader icon="🏠" title="User Dashboard" />
      <div className="page-content">
        {/* FR040 — Welcome message */}
        <h2 style={{ fontSize: 20, fontWeight: 700, marginBottom: 20 }}>
          Welcome back, {firstName}!
        </h2>

        {/* FR041-FR043 — Key metrics */}
        <div className="grid-3 mb-4">
          <div className="stat-card green">
            <div className="stat-label">Total Time Saved</div>
            <div className="stat-value" style={{ fontSize: 22 }}>
              {stats ? `${stats.time_saved_hours}h ${stats.time_saved_minutes}m` : '—'}
            </div>
            <div className="stat-delta text-green">vs exhaustive testing</div>
          </div>
          <div className="stat-card purple">
            <div className="stat-label">Total Sessions</div>
            <div className="stat-value">{stats?.total_sessions ?? '—'}</div>
          </div>
          <div className="stat-card blue">
            <div className="stat-label">Active Sessions</div>
            <div className="stat-value">{stats?.active_sessions ?? '—'}</div>
            <div className="stat-delta text-blue">in progress or configured</div>
          </div>
        </div>

        {/* FR048 — Quick start guide for first-time users */}
        {isFirstTime && !loading && (
          <div className="card mb-4" style={{ background: 'var(--purple-xlight)', borderColor: 'var(--purple-light)' }}>
            <div className="card-title">🚀 Quick Start Guide</div>
            <p style={{ fontSize: 13.5, color: 'var(--gray-600)', marginBottom: 14, lineHeight: 1.65 }}>
              Welcome to IMPT! Here's how to run your first mutation test:
            </p>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              {['1. Upload Project', '2. Configure Operators', '3. Set Time Budget', '4. Run Testing', '5. View Results'].map((s, i) => (
                <div key={i} style={{ background: '#fff', border: '1px solid var(--purple-light)', borderRadius: 8, padding: '10px 16px', fontSize: 13, fontWeight: 500 }}>
                  {s}
                </div>
              ))}
            </div>
            <button className="btn btn-primary mt-3" onClick={() => nav('/new-session')}>
              🚀 Start Your First Test
            </button>
          </div>
        )}

        {/* FR044-FR047 — Session table */}
        <div className="card mb-4">
          <div className="flex items-center justify-between mb-3">
            <div className="card-title" style={{ marginBottom: 0 }}>Recent Test Sessions</div>
            <button className="btn btn-primary btn-sm" onClick={() => nav('/new-session')}>+ New Session</button>
          </div>

          {loading ? (
            <div style={{ textAlign: 'center', padding: 20, color: 'var(--gray-400)' }}>Loading…</div>
          ) : sessions.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 30, color: 'var(--gray-400)' }}>
              <div style={{ fontSize: 32, marginBottom: 8 }}>🔬</div>
              No test sessions yet. Create your first session to get started!
            </div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Session Name</th>
                  <th>Language</th>
                  <th>Status</th>
                  <th>Created</th>
                  <th>Last Modified</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {sessions.slice(0, 8).map(s => (
                  <tr key={s.id} style={{ cursor: 'pointer' }}
                    onClick={() => {
                      const id = s.id;
                      if (s.status === 'completed')  return nav(`/results/${id}`);
                      if (s.status === 'running')    return nav(`/running/${id}`);
                      if (s.status === 'ready')      return nav(`/sessions/${id}/review`);
                      if (s.status === 'configured') return nav(`/sessions/${id}/budget`);
                      if (s.status === 'uploaded')   return nav(`/sessions/${id}/operators`);
                      return nav(`/sessions/${id}/upload`);
                    }}>
                    <td className="bold">{s.name}</td>
                    <td><span className="badge badge-blue">{s.language}</span></td>
                    <td><StatusBadge status={s.status} /></td>
                    <td className="text-muted text-sm">{new Date(s.created_at).toLocaleDateString()}</td>
                    <td className="text-muted text-sm">{new Date(s.updated_at).toLocaleDateString()}</td>
                    <td onClick={e => e.stopPropagation()}>
                      <button className="btn btn-secondary btn-sm" style={{ color: 'var(--red)', fontSize: 12 }}
                        onClick={() => setDeleteTarget(s)}>Delete</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {sessions.length > 8 && (
            <div style={{ textAlign: 'center', marginTop: 12 }}>
              <span className="link text-sm" onClick={() => nav('/history')}>View All Sessions →</span>
            </div>
          )}
        </div>

        {/* Performance trend */}
        <div className="card">
          <div className="card-title">📈 Performance Trend</div>
          <TrendChart data={trend} />
        </div>
      </div>

      {/* FR047 — Delete confirmation */}
      {deleteTarget && (
        <ConfirmModal
          title="Delete Session"
          message={`Are you sure you want to delete "${deleteTarget.name}"? This action cannot be undone.`}
          confirmLabel="Delete"
          confirmClass="btn-danger"
          onConfirm={handleDelete}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
    </AppShell>
  );
}

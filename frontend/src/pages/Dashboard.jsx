// src/pages/Dashboard.jsx  FR040–FR050
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { listSessions, deleteSession, getDashboardStats, getTrend } from '../api/client';

const STEPS = [
  {
    label: '1. Upload Project',
    icon: '📁',
    details: [
      'Click New Test Session in the sidebar.',
      'Enter a session name and select your language (Java or JavaScript).',
      'Upload your project as a .zip file, or choose a FOSS project from the library.',
      'Your zip must include pom.xml / build.gradle (Java) or package.json (JavaScript) at the root.',
      'Maximum upload size is 50 MB.',
    ],
  },
  {
    label: '2. Configure Operators',
    icon: '🔬',
    details: [
      'Select which mutation operators IMPT should apply to your code.',
      'The default High Effectiveness set (AOR, ROR, NEGATE_RETURN, COR) is recommended for most projects.',
      'Only operators compatible with your selected language are shown.',
      'Hover over any operator for a plain-language description of what it changes.',
    ],
  },
  {
    label: '3. Set Time Budget',
    icon: '⏱️',
    details: [
      'Use the slider to set how long IMPT may run (5–120 minutes).',
      'IMPT selects the highest-priority mutants that fit within your budget.',
      'Recommended: 15–20 min for a standard session, 30–60 min for thorough coverage.',
      'Optionally enable the Exhaustive Baseline to get a ground-truth comparison score.',
    ],
  },
  {
    label: '4. Run Testing',
    icon: '▶️',
    details: [
      'Review your full configuration on the Review step, then click Start Mutation Testing.',
      'The session runs in the background — you can navigate away safely.',
      'The live progress screen shows real-time phase indicators and mutant execution count.',
      'You will be automatically redirected to your results when testing completes.',
    ],
  },
  {
    label: '5. View Results',
    icon: '📊',
    details: [
      'The Results page shows your mutation score, mutants tested, time saved, and correlation.',
      'The Prioritized Mutants table lists every executed mutant with its status (Killed / Survived).',
      'Survived mutants are test gaps — they show the exact file and line where a test is missing.',
      'Export your results as CSV, HTML report, or JSON for further analysis.',
    ],
  },
];

function QuickStartSteps() {
  const [open, setOpen] = useState(null);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {STEPS.map((step, i) => {
        const isOpen = open === i;
        return (
          <div key={i} style={{ background: '#fff', border: `1px solid ${isOpen ? 'var(--purple-mid)' : 'var(--purple-light)'}`,
            borderRadius: 8, overflow: 'hidden', transition: 'border-color .15s' }}>
            <button
              onClick={() => setOpen(isOpen ? null : i)}
              style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '10px 16px', background: 'none', border: 'none', cursor: 'pointer',
                textAlign: 'left', gap: 12 }}>
              <span style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--gray-800)', display: 'flex', alignItems: 'center', gap: 8 }}>
                <span>{step.icon}</span>{step.label}
              </span>
              <span style={{ color: 'var(--purple-mid)', fontSize: 14, transition: 'transform .2s',
                transform: isOpen ? 'rotate(180deg)' : 'rotate(0deg)', display: 'inline-block' }}>▼</span>
            </button>
            {isOpen && (
              <ul style={{ margin: 0, padding: '0 16px 12px 40px', listStyle: 'disc' }}>
                {step.details.map((d, j) => (
                  <li key={j} style={{ fontSize: 13, color: 'var(--gray-600)', lineHeight: 1.7, marginBottom: 2 }}>{d}</li>
                ))}
              </ul>
            )}
          </div>
        );
      })}
    </div>
  );
}
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
              {stats ? stats.time_saved_display || '—' : '—'}
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
              Welcome to IMPT! Click any step to learn what to do.
            </p>
            <QuickStartSteps />
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
                  <th>Project</th>
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
                    <td style={{ fontSize:12, color:'var(--gray-600)', maxWidth:200, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }} title={s.project_name || ''}>{s.project_name || '—'}</td>
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

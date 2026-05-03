// src/components/UI.jsx
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
  Home, PlayCircle, BarChart2, Settings, Clock, Save, HelpCircle,
  User, Shield, Info, CheckCircle, XCircle, AlertTriangle, ChevronRight
} from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, PieChart, Pie, Cell } from 'recharts';

// ── Sidebar ───────────────────────────────────────────────────────
export function Sidebar() {
  const nav = useNavigate();
  const loc = useLocation();
  const { user, signOut } = useAuth();

  const navItems = [
    { path: '/dashboard',    label: 'Dashboard',         icon: Home },
    { path: '/new-session',  label: 'New Test Session',  icon: PlayCircle },
    { path: '/reports',      label: 'Results & Reports', icon: BarChart2 },
    { path: '/config',       label: 'Configuration',     icon: Settings },
    { path: '/history',      label: 'History',           icon: Clock },
    { path: '/profiles',     label: 'Saved Profiles',    icon: Save },
    { path: '/help',         label: 'Help & Docs',       icon: HelpCircle },
  ];

  const isActive = (path) => {
    if (path === '/new-session') return loc.pathname.startsWith('/new-session') || loc.pathname.startsWith('/running') || loc.pathname.startsWith('/results');
    return loc.pathname === path || loc.pathname.startsWith(path + '/');
  };

  return (
    <div className="sidebar">
      <div className="sidebar-logo">
        <div className="sidebar-logo-mark">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <polygon points="10,2 18,7 18,13 10,18 2,13 2,7" fill="rgba(255,255,255,0.85)" />
            <polygon points="10,2 18,7 10,10 2,7" fill="#fff" />
          </svg>
        </div>
        <div className="sidebar-logo-text">
          <div className="name">IMPT</div>
          <div className="sub">NovaSoft · FEU Tech</div>
        </div>
      </div>

      <nav className="sidebar-nav">
        {navItems.map(({ path, label, icon: Icon }) => (
          <button key={path} className={`nav-link ${isActive(path) ? 'active' : ''}`} onClick={() => nav(path)}>
            <Icon size={16} /> {label}
          </button>
        ))}
        <hr className="divider" />
        <button className={`nav-link ${loc.pathname === '/profile' ? 'active' : ''}`} onClick={() => nav('/profile')}>
          <User size={16} /> My Profile
        </button>
        {user?.role === 'admin' && (
          <button className={`nav-link ${loc.pathname === '/admin' ? 'active' : ''}`} onClick={() => nav('/admin')}>
            <Shield size={16} /> Admin Dashboard
          </button>
        )}
      </nav>

      <div className="sidebar-footer">
        <div className="sys-status-label">System Status</div>
        <div className="sys-status-ok"><div className="sys-dot" /> All systems normal</div>
        <div className="sys-time">Last test: 2 hours ago</div>
        <button className="btn btn-secondary btn-sm btn-full mt-3" style={{ fontSize: 12 }} onClick={() => { signOut(); nav('/login'); }}>
          Sign out
        </button>
      </div>
    </div>
  );
}

// ── AppShell ─────────────────────────────────────────────────────
export function AppShell({ children }) {
  return (
    <div className="app-shell">
      <Sidebar />
      <div className="main-area">{children}</div>
    </div>
  );
}

// ── PageHeader ───────────────────────────────────────────────────
export function PageHeader({ icon, title, right }) {
  const nav = useNavigate();
  return (
    <div className="page-header">
      <div className="page-header-left">
        {icon && <span style={{ fontSize: 20 }}>{icon}</span>}
        <span className="page-title">{title}</span>
      </div>
      <div className="page-header-right">
        {right}
        <div className="hdr-avatar" onClick={() => nav('/profile')}>
          <User size={16} />
        </div>
      </div>
    </div>
  );
}

// ── WizardHeader ─────────────────────────────────────────────────
export function WizardHeader({ title, step, totalSteps, stepLabel, right }) {
  const pct = (step / totalSteps) * 100;
  return (
    <>
      <div className="page-header">
        <div className="page-header-left">
          <PlayCircle size={20} style={{ color: '#fff' }} />
          <span className="page-title">{title}</span>
        </div>
        <div className="page-header-right">{right}</div>
      </div>
      <div className="wizard-bar">
        <div className="wizard-track">
          <div className="wizard-fill" style={{ width: `${pct}%` }} />
        </div>
        <div className="wizard-label">Step {step} of {totalSteps}: {stepLabel}</div>
      </div>
    </>
  );
}

// ── ScorePill ────────────────────────────────────────────────────
export function ScorePill({ value }) {
  const n = parseFloat(value);
  const cls = n >= 85 ? 'excellent' : n >= 70 ? 'good' : n >= 55 ? 'fair' : 'poor';
  return <span className={`score-pill ${cls}`}>{value}%</span>;
}

// ── ScoreRing ────────────────────────────────────────────────────
export function ScoreRing({ value, size = 140 }) {
  const r = 50, circ = 2 * Math.PI * r;
  const pct = parseFloat(value) / 100;
  const color = pct >= 0.85 ? 'var(--green)' : pct >= 0.70 ? 'var(--amber)' : 'var(--red)';
  return (
    <div className="score-ring-wrap" style={{ width: size, height: size, margin: '0 auto' }}>
      <svg width={size} height={size} viewBox="0 0 120 120">
        <circle cx="60" cy="60" r={r} fill="none" stroke="var(--gray-100)" strokeWidth="10" />
        <circle cx="60" cy="60" r={r} fill="none" stroke={color} strokeWidth="10"
          strokeDasharray={`${circ * pct} ${circ}`} strokeLinecap="round" />
      </svg>
      <div className="score-ring-label">
        <span className="ring-pct" style={{ color }}>{value}%</span>
        <span className="ring-sub">score</span>
      </div>
    </div>
  );
}

// ── StatCard ─────────────────────────────────────────────────────
export function StatCard({ label, value, delta, deltaColor, variant = '' }) {
  return (
    <div className={`stat-card ${variant}`}>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {delta && <div className="stat-delta" style={{ color: deltaColor || 'var(--gray-400)' }}>{delta}</div>}
    </div>
  );
}

// ── Alert ────────────────────────────────────────────────────────
export function Alert({ type = 'info', children }) {
  const icons = { info: Info, success: CheckCircle, error: XCircle, warn: AlertTriangle };
  const Icon = icons[type] || Info;
  return (
    <div className={`alert alert-${type}`}>
      <Icon size={16} />
      <div>{children}</div>
    </div>
  );
}

// ── InfoBox ──────────────────────────────────────────────────────
export function InfoBox({ variant = '', children }) {
  return <div className={`info-box ${variant}`}>{children}</div>;
}

// ── Trend Line Chart ─────────────────────────────────────────────
export function TrendChart({ data }) {
  if (!data?.length) return (
    <div style={{ height: 160, background: 'var(--gray-50)', border: '1px solid var(--gray-200)', borderRadius: 'var(--radius-sm)', display: 'grid', placeItems: 'center' }}>
      <span style={{ color: 'var(--gray-400)', fontSize: 13 }}>No trend data yet</span>
    </div>
  );
  return (
    <ResponsiveContainer width="100%" height={160}>
      <LineChart data={data} margin={{ top: 5, right: 10, left: -10, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--gray-100)" />
        <XAxis dataKey="date" tick={{ fontSize: 11, fill: 'var(--gray-400)' }} />
        <YAxis domain={[0, 100]} tick={{ fontSize: 11, fill: 'var(--gray-400)' }} />
        <Tooltip formatter={(v) => [`${v}%`, 'Score']} />
        <Line type="monotone" dataKey="score" stroke="var(--purple-mid)" strokeWidth={2} dot={{ r: 3, fill: 'var(--purple-mid)' }} />
      </LineChart>
    </ResponsiveContainer>
  );
}

// ── Distribution Bar Chart ────────────────────────────────────────
export function DistributionChart({ data }) {
  const COLORS = ['#16A34A', '#F59E0B', '#D97706', '#DC2626'];
  if (!data?.length) return (
    <div style={{ height: 140, background: 'var(--gray-50)', border: '1px solid var(--gray-200)', borderRadius: 'var(--radius-sm)', display: 'grid', placeItems: 'center' }}>
      <span style={{ color: 'var(--gray-400)', fontSize: 13 }}>No distribution data</span>
    </div>
  );
  return (
    <ResponsiveContainer width="100%" height={140}>
      <BarChart data={data} margin={{ top: 5, right: 10, left: -10, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--gray-100)" />
        <XAxis dataKey="range" tick={{ fontSize: 11, fill: 'var(--gray-400)' }} />
        <YAxis tick={{ fontSize: 11, fill: 'var(--gray-400)' }} />
        <Tooltip />
        {data.map((_, i) => null)}
        <Bar dataKey="count" radius={[4, 4, 0, 0]}>
          {data.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

// ── Pagination ───────────────────────────────────────────────────
export function Pagination({ page, total, perPage, onChange }) {
  const pages = Math.ceil(total / perPage);
  if (pages <= 1) return null;
  return (
    <div className="pagination">
      <button className="page-num" onClick={() => onChange(Math.max(1, page - 1))}>←</button>
      {Array.from({ length: Math.min(pages, 5) }, (_, i) => i + 1).map(p => (
        <button key={p} className={`page-num ${p === page ? 'active' : ''}`} onClick={() => onChange(p)}>{p}</button>
      ))}
      <button className="page-num" onClick={() => onChange(Math.min(pages, page + 1))}>→</button>
    </div>
  );
}

// ── Tooltip helper ───────────────────────────────────────────────
export function TooltipIcon({ text }) {
  return (
    <span title={text} style={{ cursor: 'help', color: 'var(--blue)', display: 'inline-flex', marginLeft: 3 }}>
      <Info size={13} />
    </span>
  );
}

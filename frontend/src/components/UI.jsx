// src/components/UI.jsx
import { useNavigate, useLocation } from 'react-router-dom';
import { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import {
  Home, PlayCircle, BarChart2, Settings, Clock, Save, HelpCircle,
  TrendingUp, History, GitCompare,
  User, Shield, Info, CheckCircle, XCircle, AlertTriangle, X,
  ChevronLeft, ChevronRight,
} from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, BarChart, Bar, Cell } from 'recharts';

// ── Logo ──────────────────────────────────────────────────────────
export const LogoMark = ({ size = 36 }) => (
  <img src="/logo.png" alt="IMPT Logo" style={{ width: size, height: size, objectFit: 'contain', flexShrink: 0 }} />
);

// ── Sidebar ───────────────────────────────────────────────────────
export function Sidebar() {
  const nav = useNavigate();
  const loc = useLocation();
  const { user, signOut } = useAuth();
  const [collapsed, setCollapsed] = useState(false);

  const navItems = [
    { path: '/dashboard',   label: 'Dashboard',         icon: Home },
    { path: '/new-session', label: 'New Test Session',  icon: PlayCircle },
    { path: '/reports',     label: 'Results & Reports', icon: TrendingUp },
    { path: '/history',     label: 'Test History',      icon: History },
    { path: '/compare',     label: 'Compare Results',   icon: GitCompare },
    { path: '/help',        label: 'Help & Docs',       icon: HelpCircle },
  ];

  const isActive = p => loc.pathname === p || loc.pathname.startsWith(p + '/');
  const w = collapsed ? 60 : 240;

  return (
    <div style={{
      width: w, minWidth: w, background: '#fff',
      borderRight: '1px solid var(--gray-200)',
      display: 'flex', flexDirection: 'column', flexShrink: 0,
      overflowY: 'auto', overflowX: 'hidden',
      transition: 'width .2s ease, min-width .2s ease',
      position: 'relative',
    }}>
      {/* Logo */}
      <div style={{
        padding: collapsed ? '18px 0 14px' : '18px 20px 14px',
        borderBottom: '1px solid var(--gray-100)',
        display: 'flex', alignItems: 'center',
        justifyContent: collapsed ? 'center' : 'flex-start',
        gap: 10, overflow: 'hidden',
      }}>
        <LogoMark size={32} />
        {!collapsed && (
          <div style={{ overflow: 'hidden', whiteSpace: 'nowrap' }}>
            <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--gray-900)' }}>IMPT</div>
            <div style={{ fontSize: 10, color: 'var(--gray-400)', marginTop: 1 }}>NovaSoft · FEU Tech</div>
          </div>
        )}
      </div>

      {/* Nav items */}
      <nav style={{ padding: collapsed ? '10px 6px' : '10px', flex: 1 }}>
        {navItems.map(({ path, label, icon: Icon }) => {
          const active = isActive(path);
          return (
            <button key={path}
              title={collapsed ? label : undefined}
              onClick={() => nav(path)}
              style={{
                display: 'flex', alignItems: 'center',
                justifyContent: collapsed ? 'center' : 'flex-start',
                gap: collapsed ? 0 : 10,
                width: '100%', padding: collapsed ? '10px 0' : '9px 12px',
                borderRadius: 6, border: 'none', cursor: 'pointer',
                background: active ? 'var(--purple-xlight)' : 'transparent',
                color: active ? 'var(--purple-mid)' : 'var(--gray-600)',
                fontWeight: active ? 600 : 400, fontSize: 13.5,
                marginBottom: 2, whiteSpace: 'nowrap', overflow: 'hidden',
                transition: 'background .15s',
              }}>
              <Icon size={16} style={{ flexShrink: 0 }} />
              {!collapsed && <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{label}</span>}
            </button>
          );
        })}
        <hr style={{ border: 'none', borderTop: '1px solid var(--gray-100)', margin: '8px 0' }} />
        {[
          { path: '/profile', label: 'My Profile', icon: User },
          ...(user?.role === 'admin' ? [{ path: '/admin', label: 'Admin Dashboard', icon: Shield }] : []),
        ].map(({ path, label, icon: Icon }) => {
          const active = loc.pathname === path || loc.pathname.startsWith(path + '/');
          return (
            <button key={path}
              title={collapsed ? label : undefined}
              onClick={() => nav(path)}
              style={{
                display: 'flex', alignItems: 'center',
                justifyContent: collapsed ? 'center' : 'flex-start',
                gap: collapsed ? 0 : 10,
                width: '100%', padding: collapsed ? '10px 0' : '9px 12px',
                borderRadius: 6, border: 'none', cursor: 'pointer',
                background: active ? 'var(--purple-xlight)' : 'transparent',
                color: active ? 'var(--purple-mid)' : 'var(--gray-600)',
                fontWeight: active ? 600 : 400, fontSize: 13.5,
                marginBottom: 2, whiteSpace: 'nowrap', overflow: 'hidden',
              }}>
              <Icon size={16} style={{ flexShrink: 0 }} />
              {!collapsed && <span>{label}</span>}
            </button>
          );
        })}
      </nav>

      {/* Footer */}
      {!collapsed && (
        <div style={{ padding: '14px 16px', borderTop: '1px solid var(--gray-100)' }}>
          <div style={{ fontSize: 10, color: 'var(--gray-400)', textTransform: 'uppercase',
            letterSpacing: '0.05em', marginBottom: 4 }}>System Status</div>
          <div style={{ fontSize: 12, color: 'var(--green)', display: 'flex',
            alignItems: 'center', gap: 6 }}>
            <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--green)' }} />
            All systems normal
          </div>
          <button className="btn btn-secondary btn-sm btn-full mt-3" style={{ fontSize: 12 }}
            onClick={() => { signOut(); nav('/login'); }}>
            Sign out
          </button>
        </div>
      )}
      {collapsed && (
        <div style={{ padding: '12px 0', borderTop: '1px solid var(--gray-100)',
          display: 'flex', justifyContent: 'center' }}>
          <button title="Sign out"
            onClick={() => { signOut(); nav('/login'); }}
            style={{ background: 'none', border: 'none', cursor: 'pointer',
              color: 'var(--gray-400)', fontSize: 18, padding: '6px' }}>
            ⏻
          </button>
        </div>
      )}

      {/* Collapse toggle */}
      <button
        onClick={() => setCollapsed(c => !c)}
        title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        style={{
          position: 'absolute', top: 20, right: -12,
          width: 24, height: 24, borderRadius: '50%',
          border: '1px solid var(--gray-200)', background: '#fff',
          cursor: 'pointer', display: 'flex', alignItems: 'center',
          justifyContent: 'center', boxShadow: '0 1px 4px rgba(0,0,0,0.1)',
          zIndex: 10, padding: 0, color: 'var(--gray-500)',
        }}>
        {collapsed ? <ChevronRight size={13} /> : <ChevronLeft size={13} />}
      </button>
    </div>
  );
}

// ── AppShell ──────────────────────────────────────────────────────
export function AppShell({ children }) {
  const { user, showTimeout, extendSession, countdown, signOut } = useAuth();
  const nav = useNavigate();

  return (
    <div className="app-shell">
      <Sidebar />
      <div className="main-area">
        {/* FR050 — Email verification banner */}
        {user && !user.is_verified && <VerifyBanner />}
        {children}
      </div>

      {/* NFR016 — Session timeout modal */}
      {showTimeout && (
        <div className="timeout-overlay">
          <div className="timeout-modal">
            <h3>Session Expiring Soon</h3>
            <p>Your session will expire due to inactivity. Continue working?</p>
            <div className="timeout-countdown">{countdown}s</div>
            <div className="flex gap-3 justify-end mt-3">
              <button className="btn btn-secondary" onClick={() => { signOut(); nav('/login'); }}>Sign Out</button>
              <button className="btn btn-primary" onClick={extendSession}>Continue Working</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Verify Banner ─────────────────────────────────────────────────
function VerifyBanner() {
  const [dismissed, setDismissed] = useState(false);
  const [sending, setSending]     = useState(false);
  const [sent, setSent]           = useState(false);

  if (dismissed) return null;

  const handleResend = async () => {
    setSending(true);
    try {
      const { resendVerification } = await import('../api/client');
      await resendVerification();
      setSent(true);
    } catch {}
    setSending(false);
  };

  return (
    <div className="verify-banner">
      <span>⚠️ Please verify your email to unlock all features.</span>
      <div className="actions">
        {sent
          ? <span style={{ color: 'var(--green)', fontWeight: 600 }}>✓ Verification email sent!</span>
          : <button onClick={handleResend} disabled={sending}>{sending ? 'Sending…' : 'Resend verification email'}</button>
        }
        <button className="dismiss-btn" onClick={() => setDismissed(true)}>×</button>
      </div>
    </div>
  );
}

// ── PageHeader ────────────────────────────────────────────────────
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
        <div className="hdr-avatar" onClick={() => nav('/profile')}><User size={16} /></div>
      </div>
    </div>
  );
}

// ── WizardHeader ──────────────────────────────────────────────────
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
        <div className="wizard-track"><div className="wizard-fill" style={{ width: `${pct}%` }} /></div>
        <div className="wizard-label">Step {step} of {totalSteps}: {stepLabel}</div>
      </div>
    </>
  );
}

// ── Alert ─────────────────────────────────────────────────────────
export function Alert({ type = 'info', children }) {
  const icons = { info: Info, success: CheckCircle, error: XCircle, warn: AlertTriangle };
  const Icon = icons[type] || Info;
  return <div className={`alert alert-${type}`}><Icon size={16} /><div>{children}</div></div>;
}

// ── InfoBox ───────────────────────────────────────────────────────
export function InfoBox({ variant = '', children }) {
  return <div className={`info-box ${variant}`}>{children}</div>;
}

// ── ScorePill ─────────────────────────────────────────────────────
export function ScorePill({ value }) {
  const n = parseFloat(value);
  const cls = n >= 85 ? 'excellent' : n >= 70 ? 'good' : n >= 55 ? 'fair' : 'poor';
  return <span className={`score-pill ${cls}`}>{value}%</span>;
}

// ── SessionStatusBadge ────────────────────────────────────────────
const STATUS_STYLES = {
  not_started: { bg: 'var(--gray-100)',         color: 'var(--gray-500)', label: 'Not Started' },
  uploaded:    { bg: 'var(--blue-light)',        color: 'var(--blue)',     label: 'Uploaded' },
  configured:  { bg: 'var(--purple-light)',      color: 'var(--purple-mid)', label: 'Configured' },
  ready:       { bg: '#FEF9C3',                  color: '#854D0E',         label: 'Ready' },
  running:     { bg: var_amber_light(),          color: '#92400E',         label: 'In Progress' },
  completed:   { bg: 'var(--green-light)',       color: 'var(--green)',    label: 'Completed' },
  failed:      { bg: 'var(--red-light)',         color: 'var(--red)',      label: 'Failed' },
};
function var_amber_light(){ return 'var(--amber-light)'; }

export function StatusBadge({ status }) {
  const s = STATUS_STYLES[status] || STATUS_STYLES.not_started;
  return (
    <span className="session-status" style={{ background: s.bg, color: s.color }}>
      {status === 'running' && '⏳ '}
      {status === 'completed' && '✓ '}
      {status === 'failed' && '✗ '}
      {s.label}
    </span>
  );
}

// ── Charts ────────────────────────────────────────────────────────
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
        <Tooltip formatter={v => [`${v}%`, 'Score']} />
        <Line type="monotone" dataKey="score" stroke="var(--purple-mid)" strokeWidth={2} dot={{ r: 3, fill: 'var(--purple-mid)' }} />
      </LineChart>
    </ResponsiveContainer>
  );
}

// ── Confirm modal ─────────────────────────────────────────────────
export function ConfirmModal({ title, message, confirmLabel = 'Confirm', confirmClass = 'btn-danger', onConfirm, onCancel }) {
  return (
    <div className="timeout-overlay">
      <div className="timeout-modal">
        <h3>{title}</h3>
        <p>{message}</p>
        <div className="flex gap-3 justify-end mt-4">
          <button className="btn btn-secondary" onClick={onCancel} autoFocus>Cancel</button>
          <button className={`btn ${confirmClass}`} onClick={onConfirm}>{confirmLabel}</button>
        </div>
      </div>
    </div>
  );
}

// ── TooltipIcon ───────────────────────────────────────────────────
export function TooltipIcon({ text }) {
  return (
    <span title={text} style={{ cursor: 'help', color: 'var(--blue)', display: 'inline-flex', marginLeft: 3 }}>
      <Info size={13} />
    </span>
  );
}

// ── Pagination ────────────────────────────────────────────────────
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

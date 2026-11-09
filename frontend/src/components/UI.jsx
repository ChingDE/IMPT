// src/components/UI.jsx
import { useNavigate, useLocation, Link } from 'react-router-dom';
import { useState, useEffect, createContext, useContext } from 'react';
import { useAuth } from '../context/AuthContext';
import { PrivacyContent, TermsContent } from '../pages/Legal';
import {
  Home, PlayCircle, BarChart2, Settings, Clock, Save, HelpCircle,
  TrendingUp, History, GitCompare,
  User, Shield, Info, CheckCircle, XCircle, AlertTriangle, X,
  ChevronLeft, ChevronRight, LogOut, Menu,
} from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, BarChart, Bar, Cell } from 'recharts';

// ── Mobile layout helpers ─────────────────────────────────────────
// Below 768px the sidebar becomes a slide-out drawer opened from the page header.
const MOBILE_QUERY = '(max-width: 768px)';
export function useIsMobile() {
  const get = () => typeof window !== 'undefined' && window.matchMedia(MOBILE_QUERY).matches;
  const [isMobile, setIsMobile] = useState(get);
  useEffect(() => {
    const mq = window.matchMedia(MOBILE_QUERY);
    const onChange = () => setIsMobile(mq.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);
  return isMobile;
}
const MobileNavCtx = createContext({ open: false, setOpen: () => {} });
export const useMobileNav = () => useContext(MobileNavCtx);
export function MobileMenuButton() {
  const { setOpen } = useMobileNav();
  return (
    <button className="hdr-menu-btn" aria-label="Open menu" onClick={() => setOpen(true)}>
      <Menu size={20} />
    </button>
  );
}

// ── Logo ──────────────────────────────────────────────────────────
export const LogoMark = ({ size = 36 }) => (
  <img src="/impt-logo.png" alt="IMPT logo" style={{ width: size, height: size, objectFit: 'contain', flexShrink: 0 }} />
);

// NovaSoft team credit: the compact mark (sidebar) and the full banner (auth pages, legal pages)
export const NovaSoftMark = ({ size = 18 }) => (
  <img src="/novasoft-mark.png" alt="NovaSoft logo" style={{ width: size, height: size, objectFit: 'contain', flexShrink: 0 }} />
);
export const NovaSoftBanner = ({ height = 44 }) => (
  <img src="/novasoft-banner.png" alt="NovaSoft — Innovation Software" style={{ height, width: 'auto', display: 'block' }} />
);

// Left brand panel for the auth pages (split layout). The dashboard screenshot
// is rendered greyed-out behind this content via the .auth-aside::before rule.
// ── Legal pop-up (Terms / Privacy) — shared modal over the right panel ─────────
const LegalCtx = createContext(null);
export const useLegalModal = () => useContext(LegalCtx) || { openLegal: () => {}, closeLegal: () => {} };

export function LegalModalProvider({ children }) {
  const [legal, setLegal] = useState(null);   // 'terms' | 'privacy' | null
  const openLegal  = (type) => setLegal(type);
  const closeLegal = () => setLegal(null);

  useEffect(() => {
    if (!legal) return;
    const onKey = (e) => { if (e.key === 'Escape') closeLegal(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [legal]);

  return (
    <LegalCtx.Provider value={{ openLegal, closeLegal }}>
      {children}
      {legal && (
        <>
          <style>{`
            .legal-overlay{position:fixed;top:0;bottom:0;right:0;left:50%;
              background:rgba(20,18,15,.45);display:flex;align-items:center;
              justify-content:center;padding:28px;z-index:1000}
            .legal-modal{background:#fff;border-radius:14px;width:100%;max-width:600px;
              max-height:88vh;display:flex;flex-direction:column;overflow:hidden;
              box-shadow:0 18px 50px rgba(0,0,0,.28)}
            .legal-modal-head{display:flex;align-items:center;justify-content:space-between;
              padding:18px 24px;border-bottom:1px solid var(--gray-200)}
            .legal-modal-title{font-size:18px;font-weight:800;margin:0;color:var(--gray-900)}
            .legal-modal-body{padding:20px 24px;overflow-y:auto}
            .legal-modal-foot{padding:12px 24px;border-top:1px solid var(--gray-200);text-align:right}
            .legal-close{background:none;border:none;font-size:24px;line-height:1;
              cursor:pointer;color:var(--gray-500)}
            @media (max-width:900px){ .legal-overlay{left:0} }
            @media (max-width:560px){ .legal-overlay{padding:12px} .legal-modal{max-height:92vh}
              .legal-modal-head,.legal-modal-body,.legal-modal-foot{padding-left:16px;padding-right:16px} }
          `}</style>
          <div className="legal-overlay" role="dialog" aria-modal="true"
            aria-label={legal === 'terms' ? 'Terms of Service' : 'Privacy Policy'}
            onClick={closeLegal}>
            <div className="legal-modal" onClick={(e) => e.stopPropagation()}>
              <div className="legal-modal-head">
                <h2 className="legal-modal-title">{legal === 'terms' ? 'Terms of Service' : 'Privacy Policy'}</h2>
                <button type="button" className="legal-close" aria-label="Close" onClick={closeLegal}>&times;</button>
              </div>
              <div className="legal-modal-body">
                {legal === 'terms' ? <TermsContent /> : <PrivacyContent />}
              </div>
              <div className="legal-modal-foot">
                <button type="button" className="btn btn-secondary btn-sm" onClick={closeLegal}>Close</button>
              </div>
            </div>
          </div>
        </>
      )}
    </LegalCtx.Provider>
  );
}

export function AuthAside() {
  const { openLegal } = useLegalModal();
  return (
    <>
    {/* Phones: the aside is hidden, so show a slim brand bar above the form instead */}
    <div className="auth-mobile-brand">
      <div className="auth-mobile-brand-impt">
        <LogoMark size={36} />
        <span>IMPT</span>
      </div>
      <div className="auth-mobile-brand-credit">
        <span>Built by</span>
        <NovaSoftMark size={18} />
        <strong>NovaSoft</strong>
      </div>
    </div>
    <aside className="auth-aside">
      <div className="auth-aside-top">
        <LogoMark size={56} />
        <div>
          <div className="auth-aside-brand">IMPT</div>
          <div className="auth-aside-tagline">Intelligent Mutation Prioritization Tool</div>
        </div>
      </div>
      <div className="auth-aside-mid">
        <h1 className="auth-aside-headline">Test smarter, <em>not exhaustively.</em></h1>
        <p className="auth-aside-blurb">
          IMPT prioritizes the mutants most likely to find real bugs in your code,
          then proves the result with statistical confidence — typically in a fifth of the time.
        </p>
      </div>
      <div className="auth-aside-footer">
        <div className="auth-aside-credit">
          <span className="auth-aside-credit-label">Built by</span>
          <NovaSoftBanner height={46} />
          <span className="auth-aside-credit-org">FEU Institute of Technology · 2025–2026</span>
        </div>
        <span className="auth-aside-links">
          <a href="#" onClick={(e) => { e.preventDefault(); openLegal('privacy'); }}>Privacy</a>
          <a href="#" onClick={(e) => { e.preventDefault(); openLegal('terms'); }}>Terms</a>
        </span>
      </div>
    </aside>
    </>
  );
}

// ── Sidebar ───────────────────────────────────────────────────────
export function Sidebar() {
  const nav = useNavigate();
  const loc = useLocation();
  const { user, signOut } = useAuth();
  const isMobile = useIsMobile();
  const { open: drawerOpen, setOpen: setDrawerOpen } = useMobileNav();
  const [collapsedPref, setCollapsedPref] = useState(() => localStorage.getItem('sidebar_collapsed') === 'true');
  // The drawer on phones always shows full labels; collapsing only applies on larger screens
  const collapsed = !isMobile && collapsedPref;

  // Close the drawer after navigating, and when the screen grows past the phone breakpoint
  useEffect(() => { setDrawerOpen(false); }, [loc.pathname, isMobile]);  // eslint-disable-line react-hooks/exhaustive-deps

  const toggleCollapsed = (val) => {
    const next = typeof val === 'boolean' ? val : !collapsedPref;
    setCollapsedPref(next);
    localStorage.setItem('sidebar_collapsed', String(next));
  };

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
    <div className={`app-sidebar${drawerOpen ? ' open' : ''}`} style={{
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
            <div style={{ fontSize: 10, color: 'var(--gray-400)', marginTop: 1 }}>Mutation Prioritization Tool</div>
          </div>
        )}
        {isMobile && (
          <button className="sidebar-close" aria-label="Close menu" onClick={() => setDrawerOpen(false)}>
            <X size={18} />
          </button>
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
          <button className="sidebar-desktop-only" onClick={() => toggleCollapsed(true)}
            style={{ marginTop: 8, width: '100%', background: 'none', border: 'none',
              cursor: 'pointer', color: 'var(--gray-400)', fontSize: 12,
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4, padding: '4px 0' }}>
            <ChevronLeft size={13} /> Collapse
          </button>
          <div style={{ marginTop: 10, paddingTop: 10, borderTop: '1px solid var(--gray-100)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
            fontSize: 11, color: 'var(--gray-400)' }}>
            <NovaSoftMark size={16} />
            <span>Built by <strong style={{ color: 'var(--gray-600)', fontWeight: 600 }}>NovaSoft</strong></span>
          </div>
          {/* Phones hide the floating Privacy/Terms bar, so the links live in the drawer */}
          <div className="sidebar-mobile-only" style={{ justifyContent: 'center', gap: 14, marginTop: 8, fontSize: 11 }}>
            <a href="/privacy" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--gray-400)' }}>Privacy Policy</a>
            <a href="/terms" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--gray-400)' }}>Terms of Service</a>
          </div>
        </div>
      )}
      {collapsed && (
        <div style={{ padding: '12px 0', borderTop: '1px solid var(--gray-100)',
          display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
          <button title="Sign out"
            onClick={() => { signOut(); nav('/login'); }}
            style={{ background: 'none', border: 'none', cursor: 'pointer',
              color: 'var(--gray-400)', padding: '6px', display: 'flex',
              alignItems: 'center', justifyContent: 'center' }}>
            <LogOut size={16} />
          </button>
          <button title="Expand sidebar" onClick={() => toggleCollapsed(false)}
            style={{ background: 'none', border: 'none', cursor: 'pointer',
              color: 'var(--gray-400)', padding: '4px', display: 'flex', alignItems: 'center' }}>
            <ChevronRight size={15} />
          </button>
          <span title="Built by NovaSoft" style={{ display: 'flex', marginTop: 4 }}>
            <NovaSoftMark size={20} />
          </span>
        </div>
      )}
    </div>
  );
}

// ── AppShell ──────────────────────────────────────────────────────
export function AppShell({ children }) {
  const { user, showTimeout, extendSession, countdown, signOut } = useAuth();
  const nav = useNavigate();
  const [navOpen, setNavOpen] = useState(false);

  return (
    <MobileNavCtx.Provider value={{ open: navOpen, setOpen: setNavOpen }}>
    <div className="app-shell">
      <Sidebar />
      {navOpen && <div className="mobile-nav-backdrop" onClick={() => setNavOpen(false)} />}
      <div className="main-area">
        {/* FR050 — Email verification banner */}
        {user && !user.is_verified && <VerifyBanner email={user.email} />}
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

      {/* NFR072 — Privacy/Terms footer links accessible from all pages */}
      <div className="legal-float" style={{ position:'fixed', bottom:0, right:0, padding:'4px 12px',
        fontSize:10, color:'var(--gray-400)', display:'flex', gap:12, zIndex:5,
        background:'rgba(255,255,255,.8)', backdropFilter:'blur(4px)',
        borderTop:'1px solid var(--gray-100)', borderLeft:'1px solid var(--gray-100)',
        borderTopLeftRadius:8 }}>
        <a href="/privacy" target="_blank" rel="noopener noreferrer"
          style={{ color:'var(--gray-400)', textDecoration:'none' }}
          onMouseOver={e=>e.target.style.color='var(--purple-mid)'}
          onMouseOut={e=>e.target.style.color='var(--gray-400)'}>Privacy Policy</a>
        <a href="/terms" target="_blank" rel="noopener noreferrer"
          style={{ color:'var(--gray-400)', textDecoration:'none' }}
          onMouseOver={e=>e.target.style.color='var(--purple-mid)'}
          onMouseOut={e=>e.target.style.color='var(--gray-400)'}>Terms of Service</a>
      </div>
    </div>
    </MobileNavCtx.Provider>
  );
}

// ── Verify Banner ─────────────────────────────────────────────────
function VerifyBanner({ email }) {
  const [dismissed, setDismissed] = useState(false);
  const [sending, setSending]     = useState(false);
  const [sent, setSent]           = useState(false);
  const [error, setError]         = useState('');

  if (dismissed) return null;

  const handleResend = async () => {
    setSending(true); setError('');
    try {
      const { resendVerification } = await import('../api/client');
      await resendVerification(email);   // the endpoint needs the address
      setSent(true);
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not resend the email. Please try again.');
    }
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
        {error && <span style={{ color: 'var(--red)', fontWeight: 600 }}>{error}</span>}
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
        <MobileMenuButton />
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
          <MobileMenuButton />
          <PlayCircle size={20} style={{ color: '#fff', flexShrink: 0 }} />
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
export function Alert({ type = 'info', children, onDismiss }) {
  const [visible, setVisible] = useState(true);
  const icons = { info: Info, success: CheckCircle, error: XCircle, warn: AlertTriangle };
  const Icon = icons[type] || Info;

  useEffect(() => {
    // NFR042: auto-dismiss success messages after 5 seconds
    if (type === 'success') {
      const t = setTimeout(() => { setVisible(false); onDismiss?.(); }, 5000);
      return () => clearTimeout(t);
    }
  }, [type]);

  if (!visible) return null;

  return (
    <div className={`alert alert-${type}`} style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8 }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
        <Icon size={16} style={{ flexShrink: 0, marginTop: 2 }} />
        <div>{children}</div>
      </div>
      <button onClick={() => { setVisible(false); onDismiss?.(); }}
        style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'inherit', opacity: 0.6, fontSize: 16, lineHeight: 1, padding: 0, flexShrink: 0 }}>×</button>
    </div>
  );
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

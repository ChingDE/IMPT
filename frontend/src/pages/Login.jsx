// src/pages/Login.jsx  FR001–FR010
import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { login } from '../api/client';
import { Alert, LogoMark } from '../components/UI';

const REMEMBER_KEY = 'impt_remembered_email';

export default function Login() {
  const nav = useNavigate();
  const [searchParams] = useSearchParams();
  const reason = searchParams.get('reason');
  const { signIn } = useAuth();

  // Pre-fill remembered email on mount
  const [form, setForm] = useState({
    email:        localStorage.getItem(REMEMBER_KEY) || '',
    password:     '',
    rememberMe:   !!localStorage.getItem(REMEMBER_KEY),
    keepSignedIn: false,
  });
  const [error,    setError]   = useState('');
  const [loading,  setLoading] = useState(false);
  const [attempts, setAttempts]= useState(0);
  const [locked,   setLocked]  = useState(false);

  const set = k => e => setForm(f => ({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }));

  const handleSubmit = async e => {
    e.preventDefault();
    if (locked) return;
    setLoading(true); setError('');
    try {
      const data = await login(form.email, form.password);

      // Remember me — save email only
      if (form.rememberMe) {
        localStorage.setItem(REMEMBER_KEY, form.email);
      } else {
        localStorage.removeItem(REMEMBER_KEY);
      }

      signIn(data.access_token, data.user, form.keepSignedIn);
      nav('/dashboard');
    } catch (err) {
      const detail = err.response?.data?.detail || 'Invalid email or password. Please try again.';
      if (err.response?.status === 423) {
        setLocked(true); setError(detail);
      } else {
        setAttempts(n => n + 1); setError(detail);
      }
    } finally {
      setLoading(false);
    }
  };

  const Checkbox = ({ id, checked, onChange, label, sub }) => (
    <label htmlFor={id} style={{ display:'flex', alignItems:'flex-start', gap:8, cursor:'pointer', userSelect:'none' }}>
      <input id={id} type="checkbox" checked={checked} onChange={onChange}
        style={{ marginTop:3, accentColor:'var(--purple-mid)', width:15, height:15, flexShrink:0 }} />
      <span style={{ fontSize:13, color:'var(--gray-600)', lineHeight:1.4 }}>
        {label}
        {sub && <span style={{ display:'block', fontSize:11.5, color:'var(--gray-400)', marginTop:1 }}>{sub}</span>}
      </span>
    </label>
  );

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-logo">
          <LogoMark size={64} />
          <div style={{ marginTop:12 }}>
            <div className="auth-brand">NovaSoft</div>
            <div className="auth-sub">Innovation Software</div>
            <div className="auth-tagline">Intelligent Mutation Prioritization Tool</div>
          </div>
        </div>

        {reason === 'unverified' && (
          <Alert type="warn">⚠ Your account email is not yet verified. Please check your inbox for the verification link, then log in again.</Alert>
        )}
        {reason === 'password_changed' && (
          <Alert type="success">✓ Password changed successfully. Please log in with your new password.</Alert>
        )}
        {error && <Alert type={locked ? 'error' : attempts > 0 ? 'warn' : 'error'}>{error}</Alert>}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label">Email Address</label>
            <input className={`form-input ${error ? 'error' : ''}`} type="email"
              placeholder="your.email@example.com" value={form.email} onChange={set('email')} required />
          </div>
          <div className="form-group">
            <label className="form-label">Password</label>
            <input className={`form-input ${error ? 'error' : ''}`} type="password"
              placeholder="••••••••" value={form.password} onChange={set('password')} required />
          </div>

          {/* Two separate checkboxes */}
          <div style={{ display:'flex', flexDirection:'column', gap:10, marginBottom:16 }}>
            <Checkbox id="rememberMe" checked={form.rememberMe} onChange={set('rememberMe')}
              label="Remember me"
              sub="Pre-fills your email next time you visit the login page." />
            <Checkbox id="keepSignedIn" checked={form.keepSignedIn} onChange={set('keepSignedIn')}
              label="Keep me signed in"
              sub="Stay logged in after closing the browser. Uncheck on shared computers." />
          </div>

          <div className="flex items-center justify-between mb-3">
            <span style={{fontSize:13,color:'var(--gray-400)'}} />
            <span className="link text-sm" onClick={() => nav('/forgot-password')}>Forgot password?</span>
          </div>

          <button className="btn btn-primary btn-full btn-lg" type="submit" disabled={loading || locked}>
            {loading ? 'Signing in…' : 'Sign In'}
          </button>
        </form>

        <div style={{ textAlign:'center', marginTop:20, fontSize:13.5, color:'var(--gray-500)' }}>
          Don't have an account?{' '}
          <span className="link" onClick={() => nav('/register')}>Sign Up</span>
        </div>

        <div style={{ textAlign:'center', marginTop:12, paddingTop:12, borderTop:'1px solid var(--gray-200)' }}>
          <span style={{ fontSize:12.5, color:'var(--gray-400)' }}>
            Administrator?{' '}
            <span className="link" style={{ color:'#1E3A5F', fontWeight:600 }}
              onClick={() => nav('/admin-login')}>Admin Login →</span>
          </span>
        </div>
      </div>
    </div>
  );
}

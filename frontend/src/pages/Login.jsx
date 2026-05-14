// src/pages/Login.jsx  FR001–FR010
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { login } from '../api/client';
import { Alert, LogoMark } from '../components/UI';

export default function Login() {
  const nav = useNavigate();
  const { signIn } = useAuth();
  const [form, setForm]     = useState({ email: '', password: '', remember: false });
  const [error, setError]   = useState('');
  const [loading, setLoading] = useState(false);
  const [attempts, setAttempts] = useState(0);
  const [locked, setLocked]   = useState(false);

  const set = k => e => setForm(f => ({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }));

  const handleSubmit = async e => {
    e.preventDefault();
    if (locked) return;
    setLoading(true); setError('');
    try {
      const data = await login(form.email, form.password);
      signIn(data.access_token, data.user);
      nav('/dashboard');
    } catch (err) {
      const detail = err.response?.data?.detail || 'Invalid email or password. Please try again.';
      // Check for lockout (423 status)
      if (err.response?.status === 423) {
        setLocked(true);
        setError(detail);
      } else {
        const n = attempts + 1;
        setAttempts(n);
        setError(detail);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-logo">
          <LogoMark size={28} />
          <div style={{ marginTop: 12 }}>
            <div className="auth-brand">NovaSoft</div>
            <div className="auth-sub">Innovation Software</div>
            <div className="auth-tagline">Intelligent Mutation Prioritization Tool</div>
          </div>
        </div>

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
          <div className="flex items-center justify-between mb-3">
            <label className="form-check">
              <input type="checkbox" checked={form.remember} onChange={set('remember')} />
              Remember me
            </label>
            <span className="link text-sm" onClick={() => nav('/forgot-password')}>Forgot password?</span>
          </div>
          <button className="btn btn-primary btn-full btn-lg" type="submit" disabled={loading || locked}>
            {loading ? 'Signing in…' : 'Sign In'}
          </button>
        </form>

        <div style={{ textAlign: 'center', marginTop: 20, fontSize: 13.5, color: 'var(--gray-500)' }}>
          Don't have an account?{' '}
          <span className="link" onClick={() => nav('/register')}>Sign Up</span>
        </div>

        {/* FR010 — Admin link subtle in footer */}
        <div style={{ textAlign: 'center', marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--gray-200)' }}>
          <span style={{ fontSize: 12.5, color: 'var(--gray-400)' }}>
            Administrator?{' '}
            <span className="link" style={{ color: '#1E3A5F', fontWeight: 600 }}
              onClick={() => nav('/admin-login')}>Admin Login →</span>
          </span>
        </div>
      </div>
    </div>
  );
}

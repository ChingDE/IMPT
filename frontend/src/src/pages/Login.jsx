// src/pages/Login.jsx
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { login } from '../api/client';
import { Alert } from '../components/UI';

export default function Login() {
  const nav = useNavigate();
  const { signIn } = useAuth();
  const [form, setForm]       = useState({ email: '', password: '', remember: false });
  const [error, setError]     = useState('');
  const [attempts, setAttempts] = useState(0);
  const [loading, setLoading] = useState(false);

  const set = k => e => setForm(f => ({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }));

  const handleSubmit = async e => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const data = await login(form.email, form.password);
      signIn(data.access_token, data.user);
      nav('/dashboard');
    } catch {
      const n = attempts + 1;
      setAttempts(n);
      setError(n >= 5
        ? 'Account locked after 5 failed attempts. Please reset your password.'
        : `Invalid email or password. ${5 - n} attempt${5 - n === 1 ? '' : 's'} remaining.`
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-logo">
          <div className="auth-logo-icon">
            <svg width="32" height="32" viewBox="0 0 20 20" fill="none">
              <polygon points="10,2 18,7 18,13 10,18 2,13 2,7" fill="rgba(255,255,255,0.85)" />
              <polygon points="10,2 18,7 10,10 2,7" fill="#fff" />
            </svg>
          </div>
          <div className="auth-brand">NovaSoft</div>
          <div className="auth-sub">Innovation Software</div>
          <div className="auth-tagline">Intelligent Mutation Prioritization Tool</div>
        </div>

        {error && (
          <Alert type="error">
            <strong>Login Failed</strong> — {error}
          </Alert>
        )}

        {attempts >= 2 && attempts < 5 && (
          <Alert type="warn">
            <strong>Attempts remaining: {5 - attempts} of 5</strong><br />
            Account will be locked after 5 failed attempts.
          </Alert>
        )}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label">Email Address</label>
            <input className={`form-input ${error ? 'error' : ''}`} type="email" placeholder="your.email@example.com"
              value={form.email} onChange={set('email')} required />
          </div>
          <div className="form-group">
            <label className="form-label">Password</label>
            <input className={`form-input ${error ? 'error' : ''}`} type="password" placeholder="••••••••"
              value={form.password} onChange={set('password')} required />
          </div>
          <div className="flex items-center justify-between mb-3">
            <label className="form-check">
              <input type="checkbox" checked={form.remember} onChange={set('remember')} />
              Remember me
            </label>
            <span className="link text-sm" onClick={() => nav('/forgot')}>Forgot password?</span>
          </div>
          <button className="btn btn-primary btn-full btn-lg" type="submit" disabled={loading || attempts >= 5}>
            {loading ? 'Signing in…' : 'Sign In'}
          </button>
        </form>

        <div style={{ textAlign: 'center', marginTop: 20, fontSize: 13.5, color: 'var(--gray-500)' }}>
          Don't have an account? <span className="link" onClick={() => nav('/register')}>Sign Up</span>
        </div>
      </div>
    </div>
  );
}

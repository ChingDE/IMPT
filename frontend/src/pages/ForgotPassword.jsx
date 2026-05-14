// src/pages/ForgotPassword.jsx  FR029-FR033
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { forgotPassword } from '../api/client';
import { Alert, LogoMark } from '../components/UI';

export function ForgotPassword() {
  const nav = useNavigate();
  const [email, setEmail]   = useState('');
  const [sent, setSent]     = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async e => {
    e.preventDefault();
    setLoading(true);
    try {
      await forgotPassword(email);
      setSent(true);  // FR032: always show same message
    } catch {
      setSent(true);  // FR032: even on error, show same message
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-logo">
          <LogoMark size={24} />
          <div style={{ marginTop: 10 }}>
            <div className="auth-brand">Reset Password</div>
            <div className="auth-sub">Enter your email to receive reset instructions</div>
          </div>
        </div>

        {sent ? (
          <>
            <Alert type="success">
              If an account exists with this email, you will receive password reset instructions shortly.
            </Alert>
            <button className="btn btn-secondary btn-full" onClick={() => nav('/login')}>
              ← Back to Login
            </button>
          </>
        ) : (
          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label className="form-label">Email Address</label>
              <input className="form-input" type="email" placeholder="your.email@example.com"
                value={email} onChange={e => setEmail(e.target.value)} required />
            </div>
            <button className="btn btn-primary btn-full btn-lg" type="submit" disabled={loading}>
              {loading ? 'Sending…' : 'Send Reset Instructions'}
            </button>
            <button type="button" className="btn btn-secondary btn-full mt-2" onClick={() => nav('/login')}>
              ← Back to Login
            </button>
          </form>
        )}
      </div>
    </div>
  );
}

// src/pages/ResetPassword.jsx  FR034-FR039
import { CheckCircle } from 'lucide-react';

export function ResetPassword() {
  const nav = useNavigate();
  const token = new URLSearchParams(window.location.search).get('token') || '';
  const [form, setForm] = useState({ new_password: '', confirm_password: '' });
  const [error, setError]   = useState('');
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);

  const pw = form.new_password;
  const checks = [
    pw.length >= 8, /[A-Z]/.test(pw), /[a-z]/.test(pw), /\d/.test(pw), /[!@#$%^&*]/.test(pw),
  ];
  const score  = checks.filter(Boolean).length;
  const colors = ['','var(--red)','var(--amber)','#22C55E','#22C55E','var(--green)'];
  const labels = ['','Weak','Fair','Good','Good','Strong'];
  const widths = ['0%','25%','50%','75%','85%','100%'];

  const handleSubmit = async e => {
    e.preventDefault();
    if (form.new_password !== form.confirm_password) { setError('Passwords do not match.'); return; }
    setLoading(true); setError('');
    try {
      const { resetPassword } = await import('../api/client');
      await resetPassword({ token, new_password: form.new_password, confirm_password: form.confirm_password });
      setSuccess(true);
      setTimeout(() => nav('/login'), 3000);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to reset password. The link may have expired.');
    } finally {
      setLoading(false);
    }
  };

  if (!token) return (
    <div className="auth-page">
      <div className="auth-card">
        <Alert type="error">Invalid password reset link. Please request a new one.</Alert>
        <button className="btn btn-secondary btn-full" onClick={() => nav('/forgot-password')}>Request New Link</button>
      </div>
    </div>
  );

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-logo">
          <LogoMark size={24} />
          <div style={{ marginTop: 10 }}>
            <div className="auth-brand">Set New Password</div>
          </div>
        </div>

        {success ? (
          <>
            <Alert type="success">
              <strong>Password reset successful!</strong> You can now log in with your new password.
              Redirecting in 3 seconds…
            </Alert>
            <button className="btn btn-primary btn-full" onClick={() => nav('/login')}>Go to Login</button>
          </>
        ) : (
          <form onSubmit={handleSubmit}>
            {error && <Alert type="error">{error}</Alert>}

            <div className="form-group">
              <label className="form-label">New Password</label>
              <input className="form-input" type="password" placeholder="••••••••"
                value={form.new_password} onChange={e => setForm(f => ({ ...f, new_password: e.target.value }))} />
              {pw && (
                <>
                  <div style={{ fontSize: 12, marginTop: 4, color: colors[score], fontWeight: 600 }}>
                    Password Strength: {labels[score]}
                  </div>
                  <div className="strength-bar">
                    <div className="strength-fill" style={{ width: widths[score], background: colors[score] }} />
                  </div>
                </>
              )}
            </div>

            <div className="form-group">
              <label className="form-label">Confirm New Password</label>
              <input
                className={`form-input ${form.confirm_password && form.new_password === form.confirm_password ? 'success' : form.confirm_password ? 'error' : ''}`}
                type="password" placeholder="••••••••"
                value={form.confirm_password} onChange={e => setForm(f => ({ ...f, confirm_password: e.target.value }))} />
              {form.confirm_password && form.new_password === form.confirm_password &&
                <div className="form-hint ok"><CheckCircle size={12} /> Passwords match</div>}
            </div>

            <button className="btn btn-primary btn-full btn-lg" type="submit" disabled={loading || score < 3}>
              {loading ? 'Resetting…' : 'Reset Password'}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}

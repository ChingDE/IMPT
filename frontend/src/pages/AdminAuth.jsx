// src/pages/AdminLogin.jsx
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { adminLogin } from '../api/client';
import { Alert, AuthAside } from '../components/UI';

export function AdminLogin() {
  const nav = useNavigate();
  const { signIn } = useAuth();
  const [form, setForm]     = useState({ username: '', password: '' });
  const [error, setError]   = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async e => {
    e.preventDefault();
    setLoading(true); setError('');
    try {
      const data = await adminLogin(form);
      signIn(data.access_token, data.user);
      if (data.user.must_change_password) nav('/admin-first-login');
      else nav('/admin');
    } catch (err) {
      setError(err.response?.data?.detail || 'Incorrect username or password.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page"><AuthAside />
      <div className="auth-card">
        <div className="auth-logo">
          <div className="auth-brand">Admin Portal</div>
          <div style={{ marginTop: 8, display: 'inline-block', background: '#FEF3C7', color: '#92400E', fontSize: 11, fontWeight: 700, padding: '3px 12px', borderRadius: 999, letterSpacing: .4 }}>
            ADMINISTRATOR ACCESS
          </div>
        </div>

        {error && <Alert type="error">{error}</Alert>}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label">Username</label>
            <input className={`form-input ${error ? 'error' : ''}`} type="text" placeholder="admin"
              value={form.username} onChange={e => setForm(f => ({ ...f, username: e.target.value }))} required />
          </div>
          <div className="form-group">
            <label className="form-label">Password</label>
            <PasswordInput className={`form-input ${error ? 'error' : ''}`} placeholder="••••••••"
              value={form.password} onChange={e => setForm(f => ({ ...f, password: e.target.value }))} required />
          </div>
          <button className="btn btn-full btn-lg" type="submit" disabled={loading}
            style={{ background: '#1E3A5F', color: '#fff', marginTop: 4 }}>
            {loading ? 'Signing in…' : 'Sign In as Administrator'}
          </button>
        </form>

        <div style={{ textAlign: 'center', marginTop: 20, fontSize: 13, color: 'var(--gray-400)' }}>
          Not an admin? <span className="link" onClick={() => nav('/login')}>Go to User Login</span>
        </div>
      </div>
    </div>
  );
}

// Admin first login
import { CheckCircle } from 'lucide-react';
import PasswordInput from '../components/PasswordInput';

export function AdminFirstLogin() {
  const nav = useNavigate();
  const { setUser } = useAuth();
  const [form, setForm] = useState({ new_username: '', new_password: '', confirm: '', new_email: '' });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const pw = form.new_password;
  const checks = [pw.length>=8, /[A-Z]/.test(pw), /[a-z]/.test(pw), /\d/.test(pw), /[!@#$%^&*]/.test(pw)];
  const score  = checks.filter(Boolean).length;
  const colors = ['','var(--red)','var(--amber)','#22C55E','#22C55E','var(--green)'];
  const widths = ['0%','25%','50%','75%','85%','100%'];

  const handleSubmit = async e => {
    e.preventDefault();
    if (form.new_password !== form.confirm) { setError('Passwords do not match.'); return; }
    if (score < 3) { setError('Please choose a stronger password.'); return; }
    setLoading(true); setError('');
    try {
      const { changeAdminCreds } = await import('../api/client');
      const data = await changeAdminCreds({ new_username: form.new_username, new_password: form.new_password, new_email: form.new_email });
      if (setUser) setUser(data);
      nav('/admin');
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to update credentials. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page"><AuthAside />
      <div className="auth-card wide">
        <div className="auth-logo">
          <div className="auth-brand">Set Up Your Admin Account</div>
        </div>

        <div style={{ background:'#FEF3C7',border:'1px solid #FDE68A',borderLeft:'4px solid #F59E0B',borderRadius:6,padding:'12px 14px',fontSize:13,color:'#78350F',marginBottom:18,lineHeight:1.55 }}>
          <strong>Welcome, Administrator.</strong> You are using the default credentials.
          Please set a new username, password, and email address before continuing.
          You cannot skip this step.
        </div>

        {error && <Alert type="error">{error}</Alert>}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label">New Username</label>
            <input className="form-input" type="text" placeholder="Choose a username"
              value={form.new_username} onChange={e => setForm(f => ({ ...f, new_username: e.target.value }))} required />
          </div>
          <div className="form-group">
            <label className="form-label">New Email Address</label>
            <input className="form-input" type="email" placeholder="admin@yourorg.com"
              value={form.new_email} onChange={e => setForm(f => ({ ...f, new_email: e.target.value }))} required />
          </div>
          <div className="form-group">
            <label className="form-label">New Password</label>
            <PasswordInput className="form-input" placeholder="••••••••"
              value={form.new_password} onChange={e => setForm(f => ({ ...f, new_password: e.target.value }))} required />
            {pw && (
              <>
                <div style={{ fontSize:12,marginTop:4,color:colors[score],fontWeight:600 }}>Password Strength: {['','Weak','Fair','Good','Good','Strong'][score]}</div>
                <div className="strength-bar"><div className="strength-fill" style={{ width:widths[score],background:colors[score] }} /></div>
              </>
            )}
          </div>
          <div className="form-group">
            <label className="form-label">Confirm New Password</label>
            <PasswordInput
              className={`form-input ${form.confirm && form.new_password===form.confirm ? 'success' : form.confirm ? 'error' : ''}`}
              placeholder="••••••••"
              value={form.confirm} onChange={e => setForm(f => ({ ...f, confirm: e.target.value }))} required />
            {form.confirm && form.new_password===form.confirm && <div className="form-hint ok"><CheckCircle size={12} /> Passwords match</div>}
          </div>
          <button className="btn btn-full btn-lg" type="submit" disabled={loading || score < 3}
            style={{ background:'#1E3A5F',color:'#fff',marginTop:4 }}>
            {loading ? 'Saving…' : 'Save & Continue to Admin Dashboard'}
          </button>
        </form>
      </div>
    </div>
  );
}

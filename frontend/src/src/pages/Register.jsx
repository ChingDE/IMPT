// src/pages/Register.jsx
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { register, login } from '../api/client';
import { Alert } from '../components/UI';
import { CheckCircle } from 'lucide-react';

export default function Register() {
  const nav = useNavigate();
  const { signIn } = useAuth();
  const [form, setForm] = useState({ email: '', password: '', confirm: '', fullName: '', org: '', agree: false });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const set = k => e => setForm(f => ({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }));

  const strength = (() => {
    const p = form.password;
    const checks = [p.length >= 8, /[A-Z]/.test(p), /[a-z]/.test(p), /\d/.test(p), /[!@#$%^&*]/.test(p)];
    const score = checks.filter(Boolean).length;
    const labels = ['', 'Weak', 'Fair', 'Good', 'Good', 'Strong'];
    const colors = ['', 'var(--red)', 'var(--amber)', '#22C55E', '#22C55E', 'var(--green)'];
    const widths  = ['0%', '25%', '50%', '75%', '85%', '100%'];
    return { score, label: labels[score], color: colors[score], width: widths[score], checks };
  })();

  const reqLabels = ['At least 8 characters', 'One uppercase letter', 'One lowercase letter', 'One number', 'One special character'];

  const handleSubmit = async e => {
    e.preventDefault();
    if (form.password !== form.confirm) { setError('Passwords do not match.'); return; }
    if (!form.agree) { setError('Please agree to the Terms of Service.'); return; }
    setLoading(true); setError('');
    try {
      await register({ email: form.email, password: form.password, full_name: form.fullName, role: 'student' });
      const data = await login(form.email, form.password);
      signIn(data.access_token, data.user);
      nav('/dashboard');
    } catch (err) {
      setError(err.response?.data?.detail || 'Registration failed. Please try again.');
    } finally { setLoading(false); }
  };

  return (
    <div className="auth-page">
      <div className="auth-card" style={{ maxWidth: 460 }}>
        <div className="auth-logo">
          <div className="auth-logo-icon">
            <svg width="32" height="32" viewBox="0 0 20 20" fill="none">
              <polygon points="10,2 18,7 18,13 10,18 2,13 2,7" fill="rgba(255,255,255,0.85)" />
              <polygon points="10,2 18,7 10,10 2,7" fill="#fff" />
            </svg>
          </div>
          <div className="auth-brand">Create Your Account</div>
          <div className="auth-tagline">Intelligent Mutation Prioritization Tool</div>
        </div>

        {error && <Alert type="error">{error}</Alert>}

        <form onSubmit={handleSubmit}>
          <div className="form-row-2">
            <div className="form-group">
              <label className="form-label">Full Name</label>
              <input className="form-input" placeholder="John Doe" value={form.fullName} onChange={set('fullName')} required />
            </div>
            <div className="form-group">
              <label className="form-label">Organization (Optional)</label>
              <input className="form-input" placeholder="Your company name" value={form.org} onChange={set('org')} />
            </div>
          </div>
          <div className="form-group">
            <label className="form-label">Email Address</label>
            <input className={`form-input ${form.email && /\S+@\S+\.\S+/.test(form.email) ? 'success' : ''}`}
              type="email" placeholder="john.doe@example.com" value={form.email} onChange={set('email')} required />
            {form.email && /\S+@\S+\.\S+/.test(form.email) &&
              <div className="form-hint ok"><CheckCircle size={12} /> Valid email format</div>}
          </div>
          <div className="form-group">
            <label className="form-label">Password</label>
            <input className="form-input" type="password" placeholder="••••••••" value={form.password} onChange={set('password')} required />
            {form.password && (
              <>
                <div style={{ fontSize: 12, marginTop: 4, color: strength.color, fontWeight: 600 }}>
                  Password Strength: {strength.label}
                </div>
                <div className="strength-bar">
                  <div className="strength-fill" style={{ width: strength.width, background: strength.color }} />
                </div>
                <div style={{ background: 'var(--gray-50)', borderRadius: 6, padding: '8px 12px', marginTop: 4 }}>
                  {reqLabels.map((l, i) => (
                    <div key={i} style={{ fontSize: 12, padding: '2px 0', display: 'flex', alignItems: 'center', gap: 6,
                      color: strength.checks[i] ? 'var(--green)' : 'var(--gray-400)' }}>
                      {strength.checks[i] ? <CheckCircle size={11} /> : '○'} {l}
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
          <div className="form-group">
            <label className="form-label">Confirm Password</label>
            <input className={`form-input ${form.confirm && form.password === form.confirm ? 'success' : form.confirm ? 'error' : ''}`}
              type="password" placeholder="••••••••" value={form.confirm} onChange={set('confirm')} />
            {form.confirm && form.password === form.confirm &&
              <div className="form-hint ok"><CheckCircle size={12} /> Passwords match</div>}
          </div>
          <div style={{ marginBottom: 16 }}>
            <label className="form-check">
              <input type="checkbox" checked={form.agree} onChange={set('agree')} />
              I agree to the Terms of Service and Privacy Policy
            </label>
          </div>
          <button className="btn btn-primary btn-full btn-lg" type="submit" disabled={loading}>
            {loading ? 'Creating account…' : 'Create Account'}
          </button>
        </form>

        <div style={{ textAlign: 'center', marginTop: 16, fontSize: 13.5, color: 'var(--gray-500)' }}>
          Already have an account? <span className="link" onClick={() => nav('/login')}>Sign In</span>
        </div>
      </div>
    </div>
  );
}

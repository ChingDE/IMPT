// src/pages/Register.jsx  FR011–FR021
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { register } from '../api/client';
import { Alert, LogoMark } from '../components/UI';
import { CheckCircle } from 'lucide-react';

function PasswordStrength({ password }) {
  const checks = [
    { label: 'At least 8 characters',   ok: password.length >= 8 },
    { label: 'One uppercase letter',     ok: /[A-Z]/.test(password) },
    { label: 'One lowercase letter',     ok: /[a-z]/.test(password) },
    { label: 'One number',               ok: /\d/.test(password) },
    { label: 'One special character',    ok: /[!@#$%^&*]/.test(password) },
  ];
  const score  = checks.filter(c => c.ok).length;
  const labels = ['', 'Weak', 'Fair', 'Good', 'Good', 'Strong'];
  const colors = ['', 'var(--red)', 'var(--amber)', '#22C55E', '#22C55E', 'var(--green)'];
  const widths = ['0%', '25%', '50%', '75%', '85%', '100%'];

  if (!password) return null;
  return (
    <>
      <div style={{ fontSize: 12, marginTop: 4, color: colors[score], fontWeight: 600 }}>
        Password Strength: {labels[score]}
      </div>
      <div className="strength-bar">
        <div className="strength-fill" style={{ width: widths[score], background: colors[score] }} />
      </div>
      <div style={{ background: 'var(--gray-50)', borderRadius: 6, padding: '8px 12px', marginTop: 4 }}>
        {checks.map((c, i) => (
          <div key={i} style={{ fontSize: 12, padding: '2px 0', display: 'flex', alignItems: 'center', gap: 6,
            color: c.ok ? 'var(--green)' : 'var(--gray-400)' }}>
            {c.ok ? <CheckCircle size={11} /> : '○'} {c.label}
          </div>
        ))}
      </div>
    </>
  );
}

export default function Register() {
  const nav = useNavigate();
  const [form, setForm] = useState({
    first_name:'', last_name:'', email:'', organization:'',
    password:'', confirm:'', agree: false,
  });
  const [errors, setErrors] = useState({});
  const [globalError, setGlobalError] = useState('');
  const [loading, setLoading] = useState(false);

  const set = k => e => {
    setForm(f => ({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }));
    setErrors(er => ({ ...er, [k]: '' }));
  };

  const validate = () => {
    const errs = {};
    if (!form.first_name.trim()) errs.first_name = 'First name is required';
    else if (!/^[A-Za-z\s\-]+$/.test(form.first_name)) errs.first_name = 'Only letters, spaces, and hyphens';
    if (!form.last_name.trim()) errs.last_name = 'Last name is required';
    else if (!/^[A-Za-z\s\-]+$/.test(form.last_name)) errs.last_name = 'Only letters, spaces, and hyphens';
    if (!/\S+@\S+\.\S+/.test(form.email)) errs.email = 'Please enter a valid email address';
    if (form.password.length < 8) errs.password = 'Password must be at least 8 characters';
    if (form.password !== form.confirm) errs.confirm = 'Passwords do not match';
    if (!form.agree) errs.agree = 'You must accept the Terms of Service';
    return errs;
  };

  const handleSubmit = async e => {
    e.preventDefault();
    const errs = validate();
    if (Object.keys(errs).length) { setErrors(errs); return; }
    setLoading(true); setGlobalError('');
    try {
      await register({
        email: form.email,
        password: form.password,
        first_name: form.first_name,
        last_name: form.last_name,
        organization: form.organization || undefined,
      });
      nav('/verify-email-sent', { state: { email: form.email } });
    } catch (err) {
      const detail = err.response?.data?.detail || 'Registration failed. Please try again.';
      if (detail.includes('already registered')) setErrors(e => ({ ...e, email: detail }));
      else setGlobalError(detail);
    } finally {
      setLoading(false);
    }
  };

  const Field = ({ id, label, type = 'text', placeholder, optional = false }) => (
    <div className="form-group">
      <label className="form-label">{label}{optional && <span style={{ color: 'var(--gray-400)', fontWeight: 400 }}> (Optional)</span>}</label>
      <input
        className={`form-input ${errors[id] ? 'error' : form[id] && !errors[id] ? 'success' : ''}`}
        type={type} placeholder={placeholder}
        value={form[id]} onChange={set(id)}
      />
      {errors[id] && <div className="form-hint err">{errors[id]}</div>}
      {id === 'email' && form.email && !errors.email && /\S+@\S+\.\S+/.test(form.email) &&
        <div className="form-hint ok"><CheckCircle size={12} /> Valid email format</div>}
      {id === 'confirm' && form.confirm && form.password === form.confirm && !errors.confirm &&
        <div className="form-hint ok"><CheckCircle size={12} /> Passwords match</div>}
    </div>
  );

  return (
    <div className="auth-page">
      <div className="auth-card wide">
        <div className="auth-logo">
          <LogoMark size={24} />
          <div style={{ marginTop: 10 }}>
            <div className="auth-brand">Create Your Account</div>
            <div className="auth-tagline">Intelligent Mutation Prioritization Tool</div>
          </div>
        </div>

        {globalError && <Alert type="error">{globalError}</Alert>}

        <form onSubmit={handleSubmit}>
          <div className="form-row-2">
            <Field id="first_name" label="First Name" placeholder="John" />
            <Field id="last_name"  label="Last Name"  placeholder="Doe" />
          </div>
          <Field id="email"        label="Email Address"         type="email" placeholder="john@example.com" />
          <Field id="organization" label="Organization"          placeholder="Your company" optional />

          <div className="form-group">
            <label className="form-label">Password</label>
            <input className={`form-input ${errors.password ? 'error' : ''}`} type="password"
              placeholder="••••••••" value={form.password} onChange={set('password')} />
            {errors.password && <div className="form-hint err">{errors.password}</div>}
            <PasswordStrength password={form.password} />
          </div>

          <Field id="confirm" label="Confirm Password" type="password" placeholder="••••••••" />

          <div className="form-group">
            <label className="form-check">
              <input type="checkbox" checked={form.agree} onChange={set('agree')} />
              I agree to the{' '}
              <span className="link" onClick={() => window.open('/terms', '_blank')}>Terms of Service</span>
              {' '}and{' '}
              <span className="link" onClick={() => window.open('/privacy', '_blank')}>Privacy Policy</span>
            </label>
            {errors.agree && <div className="form-hint err">{errors.agree}</div>}
          </div>

          <button className="btn btn-primary btn-full btn-lg" type="submit" disabled={loading || !form.agree}>
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

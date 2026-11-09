// src/pages/Register.jsx  FR011–FR021
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { register } from '../api/client';
import { Alert, AuthAside, useLegalModal } from '../components/UI';
import { CheckCircle } from 'lucide-react';
import PasswordInput from '../components/PasswordInput';

// ── Password strength — defined OUTSIDE Register so it never remounts ─────────
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
          <div key={i} style={{ fontSize: 12, padding: '2px 0', display: 'flex', alignItems: 'center',
            gap: 6, color: c.ok ? 'var(--green)' : 'var(--gray-400)' }}>
            {c.ok ? <CheckCircle size={11} /> : '○'} {c.label}
          </div>
        ))}
      </div>
    </>
  );
}

export default function Register() {
  const nav = useNavigate();
  const { openLegal } = useLegalModal();
  const [form, setFormState] = useState({
    first_name: '', last_name: '', email: '', organization: '',
    password: '', confirm: '', agree: false,
  });
  const [touched, setTouched]     = useState({});
  const [errors, setErrors]       = useState({});
  const [globalError, setGlobalError] = useState('');
  const [loading, setLoading]     = useState(false);

  // Update field without touching error state during typing
  const handleChange = (key) => (e) => {
    const value = e.target.type === 'checkbox' ? e.target.checked : e.target.value;
    setFormState(prev => ({ ...prev, [key]: value }));
    // Clear error for this field when user types
    if (errors[key]) {
      setErrors(prev => ({ ...prev, [key]: '' }));
    }
  };

  const handleBlur = (key) => () => {
    setTouched(prev => ({ ...prev, [key]: true }));
  };

  // Only show error if field has been touched
  const fieldError = (key) => touched[key] ? errors[key] : '';

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

  const handleSubmit = async (e) => {
    e.preventDefault();
    // Mark all fields as touched on submit
    setTouched({ first_name:true, last_name:true, email:true, password:true, confirm:true, agree:true });
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
      if (detail.includes('already registered')) {
        setErrors(prev => ({ ...prev, email: detail }));
        setTouched(prev => ({ ...prev, email: true }));
      } else {
        setGlobalError(detail);
      }
    } finally {
      setLoading(false);
    }
  };

  // Input class — only show red/green after field is touched
  const inputClass = (key) => {
    const err = fieldError(key);
    if (err) return 'form-input error';
    if (touched[key] && form[key]) return 'form-input success';
    return 'form-input';
  };

  return (
    <div className="auth-page"><AuthAside />
      <div className="auth-card wide">
        <div className="auth-logo">
          <div className="auth-brand">Create Your Account</div>
        </div>

        {globalError && <Alert type="error">{globalError}</Alert>}

        <form onSubmit={handleSubmit} noValidate>
          {/* First + Last name */}
          <div className="form-row-2">
            <div className="form-group">
              <label className="form-label">First Name</label>
              <input
                className={inputClass('first_name')}
                type="text"
                placeholder="John"
                value={form.first_name}
                onChange={handleChange('first_name')}
                onBlur={handleBlur('first_name')}
              />
              {fieldError('first_name') && (
                <div className="form-hint err">{fieldError('first_name')}</div>
              )}
            </div>
            <div className="form-group">
              <label className="form-label">Last Name</label>
              <input
                className={inputClass('last_name')}
                type="text"
                placeholder="Doe"
                value={form.last_name}
                onChange={handleChange('last_name')}
                onBlur={handleBlur('last_name')}
              />
              {fieldError('last_name') && (
                <div className="form-hint err">{fieldError('last_name')}</div>
              )}
            </div>
          </div>

          {/* Email */}
          <div className="form-group">
            <label className="form-label">Email Address</label>
            <input
              className={inputClass('email')}
              type="email"
              placeholder="john@example.com"
              value={form.email}
              onChange={handleChange('email')}
              onBlur={handleBlur('email')}
            />
            {fieldError('email') && (
              <div className="form-hint err">{fieldError('email')}</div>
            )}
            {touched.email && form.email && !fieldError('email') && /\S+@\S+\.\S+/.test(form.email) && (
              <div className="form-hint ok"><CheckCircle size={12} /> Valid email format</div>
            )}
          </div>

          {/* Organization (optional) */}
          <div className="form-group">
            <label className="form-label">
              Organization <span style={{ color: 'var(--gray-400)', fontWeight: 400 }}>(Optional)</span>
            </label>
            <input
              className="form-input"
              type="text"
              placeholder="Your company or university"
              value={form.organization}
              onChange={handleChange('organization')}
            />
          </div>

          {/* Password */}
          <div className="form-group">
            <label className="form-label">Password</label>
            <PasswordInput
              className={inputClass('password')}
              placeholder="••••••••"
              value={form.password}
              onChange={handleChange('password')}
              onBlur={handleBlur('password')}
            />
            {fieldError('password') && (
              <div className="form-hint err">{fieldError('password')}</div>
            )}
            <PasswordStrength password={form.password} />
          </div>

          {/* Confirm password */}
          <div className="form-group">
            <label className="form-label">Confirm Password</label>
            <PasswordInput
              className={inputClass('confirm')}
              placeholder="••••••••"
              value={form.confirm}
              onChange={handleChange('confirm')}
              onBlur={handleBlur('confirm')}
            />
            {fieldError('confirm') && (
              <div className="form-hint err">{fieldError('confirm')}</div>
            )}
            {touched.confirm && form.confirm && form.password === form.confirm && !fieldError('confirm') && (
              <div className="form-hint ok"><CheckCircle size={12} /> Passwords match</div>
            )}
          </div>

          {/* ToS checkbox */}
          <div className="form-group">
            <label className="form-check">
              <input
                type="checkbox"
                checked={form.agree}
                onChange={handleChange('agree')}
              />
              <span>
                I agree to the{' '}
                <span className="link" onClick={(e) => { e.preventDefault(); openLegal('terms'); }}>
                  Terms of Service
                </span>
                {' '}and{' '}
                <span className="link" onClick={(e) => { e.preventDefault(); openLegal('privacy'); }}>
                  Privacy Policy
                </span>
              </span>
            </label>
            {fieldError('agree') && (
              <div className="form-hint err">{fieldError('agree')}</div>
            )}
          </div>

          <button
            className="btn btn-primary btn-full btn-lg"
            type="submit"
            disabled={loading || !form.agree}
          >
            {loading ? 'Creating account…' : 'Create Account'}
          </button>
        </form>

        <div style={{ textAlign: 'center', marginTop: 16, fontSize: 13.5, color: 'var(--gray-500)' }}>
          Already have an account?{' '}
          <span className="link" onClick={() => nav('/login')}>Sign In</span>
        </div>
      </div>
    </div>
  );
}

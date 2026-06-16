// src/pages/VerifyEmail.jsx  FR020, FR022-FR023, FR025-FR028
import { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { resendVerification } from '../api/client';
import { Alert, AuthAside } from '../components/UI';

const emailInputStyle = {
  width: '100%', padding: '10px 12px', marginBottom: 12,
  border: '1px solid #d1d5db', borderRadius: 8, fontSize: 14, boxSizing: 'border-box',
};

export function VerifyEmailSent() {
  const nav = useNavigate();
  const { state } = useLocation();
  const email = state?.email;            // real address passed from Register
  const [sending, setSending] = useState(false);
  const [sent, setSent]       = useState(false);
  const [error, setError]     = useState('');

  const handleResend = async () => {
    if (!email) {
      setError('We could not find your email address. Please return to login and sign in, or register again.');
      return;
    }
    setSending(true); setError('');
    try {
      await resendVerification(email);
      setSent(true);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to resend. Please try again.');
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="auth-page"><AuthAside />
      <div className="auth-card">
        <div className="auth-logo">
          <div style={{ fontSize: 48, marginBottom: 12 }}>📧</div>
          <div className="auth-brand">Check Your Email</div>
        </div>

        <div style={{ background: 'var(--green-xlight)', border: '1px solid var(--green-light)', borderRadius: 8, padding: '16px', marginBottom: 20, fontSize: 13.5, color: 'var(--gray-700)', lineHeight: 1.65, textAlign: 'center' }}>
          Account created successfully! We've sent a verification email to{' '}
          <strong>{email || 'your email address'}</strong>. Please check your inbox and click the verification link to activate your account.
          <div style={{ marginTop: 8, fontSize: 12, color: 'var(--gray-500)' }}>
            Verification is required to use mutation testing features.
          </div>
        </div>

        {error && <Alert type="error">{error}</Alert>}
        {sent && <Alert type="success">Verification email resent. Please check your inbox.</Alert>}

        <button className="btn btn-outline btn-full" onClick={handleResend} disabled={sending || sent}>
          {sending ? 'Sending…' : sent ? '✓ Email Sent' : 'Resend Verification Email'}
        </button>

        <button className="btn btn-secondary btn-full mt-2" onClick={() => nav('/login')}>
          Return to Login Page
        </button>
      </div>
    </div>
  );
}

// src/pages/VerifyEmail.jsx  FR025-FR028
export function VerifyEmail() {
  const nav = useNavigate();
  const [state, setState] = useState('loading');  // loading | success | expired | invalid | resent
  const [sending, setSending] = useState(false);
  const [email, setEmail] = useState('');
  const [error, setError] = useState('');

  // NOTE: this must be useEffect, not useState — it runs the verification once on mount.
  useEffect(() => {
    const token = new URLSearchParams(window.location.search).get('token');
    if (!token) { setState('invalid'); return; }
    import('../api/client').then(({ verifyEmail }) => {
      verifyEmail(token)
        .then(() => { setState('success'); setTimeout(() => nav('/login'), 3000); })
        .catch(err => {
          const detail = err.response?.data?.detail || '';
          if (detail.includes('expired')) setState('expired');
          else setState('invalid');
        });
    });
  }, []);

  const handleResend = async () => {
    if (!email) { setError('Please enter your email address.'); return; }
    setSending(true); setError('');
    try {
      await resendVerification(email);
      setState('resent');
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to resend. Please try again.');
    }
    setSending(false);
  };

  return (
    <div className="auth-page"><AuthAside />
      <div className="auth-card">

        {state === 'loading' && (
          <div style={{ textAlign: 'center', padding: '20px', color: 'var(--gray-500)' }}>
            Verifying your email…
          </div>
        )}

        {state === 'success' && (
          <>
            <div style={{ textAlign: 'center', fontSize: 48, marginBottom: 12 }}>✅</div>
            <Alert type="success">
              <strong>Email verified successfully!</strong> Your account is now active.
              You can now access all IMPT features. Redirecting to login in 3 seconds…
            </Alert>
            <button className="btn btn-primary btn-full" onClick={() => nav('/login')}>
              Go to Login
            </button>
          </>
        )}

        {state === 'expired' && (
          <>
            <Alert type="warn">
              This verification link has expired. Enter your email to request a new one.
            </Alert>
            <input
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={e => setEmail(e.target.value)}
              style={emailInputStyle}
            />
            {error && <Alert type="error">{error}</Alert>}
            <button className="btn btn-primary btn-full" onClick={handleResend} disabled={sending}>
              {sending ? 'Sending…' : 'Resend Verification Email'}
            </button>
            <button className="btn btn-secondary btn-full mt-2" onClick={() => nav('/login')}>
              Return to Login
            </button>
          </>
        )}

        {state === 'invalid' && (
          <>
            <Alert type="error">
              Invalid verification link. If you've already verified your account, please log in.
            </Alert>
            <button className="btn btn-primary btn-full" onClick={() => nav('/login')}>
              Go to Login
            </button>
          </>
        )}

        {state === 'resent' && (
          <>
            <Alert type="success">New verification email sent. Please check your inbox.</Alert>
            <button className="btn btn-secondary btn-full" onClick={() => nav('/login')}>
              Return to Login
            </button>
          </>
        )}
      </div>
    </div>
  );
}

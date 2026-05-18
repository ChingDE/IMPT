"""
services/email.py
Email service using Resend (3,000 emails/month free).
Falls back to logging if RESEND_API_KEY is not configured (local dev).

Setup:
  1. Sign up at resend.com
  2. Add and verify your domain (impt.it.com)
  3. Create an API key
  4. Set RESEND_API_KEY and EMAIL_FROM in .env
"""
from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger(__name__)


def _get_resend():
    try:
        import resend
        from config.settings import get_settings
        s = get_settings()
        if not s.RESEND_API_KEY:
            return None
        resend.api_key = s.RESEND_API_KEY
        return resend
    except ImportError:
        log.warning("resend package not installed — emails will be logged only")
        return None


def _send(to: str, subject: str, html: str) -> bool:
    """Send an email. Returns True if sent, False if logged only."""
    from config.settings import get_settings
    s = get_settings()

    if not s.EMAIL_ENABLED:
        log.info(
            "EMAIL (dev mode — not sent):\n"
            "  To:      %s\n"
            "  Subject: %s\n"
            "  Preview: %s",
            to, subject, html[:200]
        )
        return False

    resend = _get_resend()
    if not resend:
        return False

    try:
        params = {
            "from": s.EMAIL_FROM,
            "to": [to],
            "subject": subject,
            "html": html,
        }
        resend.Emails.send(params)
        log.info("Email sent to %s: %s", to, subject)
        return True
    except Exception as exc:
        log.error("Failed to send email to %s: %s", to, exc)
        return False


# ── Email templates ────────────────────────────────────────────────────────────

def _base_template(content: str, preview: str = "") -> str:
    """Shared HTML wrapper for all emails."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>IMPT</title>
</head>
<body style="margin:0;padding:0;background:#F3F4F6;font-family:Arial,sans-serif;">
<div style="max-width:560px;margin:40px auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">
  <!-- Header -->
  <div style="background:#7C3AED;padding:28px 32px;text-align:center;">
    <h1 style="color:#fff;margin:0;font-size:22px;font-weight:700;letter-spacing:-0.5px;">IMPT</h1>
    <p style="color:rgba(255,255,255,0.8);margin:4px 0 0;font-size:13px;">
      Intelligent Mutation Prioritization Tool
    </p>
  </div>
  <!-- Body -->
  <div style="padding:32px;">
    {content}
  </div>
  <!-- Footer -->
  <div style="background:#F9FAFB;border-top:1px solid #E5E7EB;padding:20px 32px;text-align:center;">
    <p style="color:#9CA3AF;font-size:12px;margin:0;">
      NovaSoft · FEU Institute of Technology<br>
      This email was sent to you because you registered at impt.it.com.
    </p>
  </div>
</div>
</body>
</html>"""


def send_verification_email(
    to: str,
    first_name: str,
    verification_url: str,
) -> bool:
    """FR019 — Welcome + email verification link."""
    content = f"""
    <h2 style="color:#111827;font-size:20px;margin:0 0 16px;">
      Welcome to IMPT, {first_name}! 👋
    </h2>
    <p style="color:#4B5563;line-height:1.6;margin:0 0 20px;">
      Thank you for creating your account. To start using mutation testing features,
      please verify your email address by clicking the button below.
    </p>
    <div style="text-align:center;margin:28px 0;">
      <a href="{verification_url}"
         style="background:#7C3AED;color:#fff;text-decoration:none;padding:13px 28px;
                border-radius:8px;font-weight:600;font-size:15px;display:inline-block;">
        Verify Email Address
      </a>
    </div>
    <p style="color:#6B7280;font-size:13px;line-height:1.6;">
      This link expires in <strong>24 hours</strong>. If you did not create this account,
      you can safely ignore this email.
    </p>
    <p style="color:#6B7280;font-size:12px;margin-top:16px;">
      If the button above does not work, copy and paste this link into your browser:<br>
      <span style="color:#7C3AED;word-break:break-all;">{verification_url}</span>
    </p>
    """
    return _send(to, "Verify your IMPT email address", _base_template(content))


def send_password_reset_email(
    to: str,
    first_name: str,
    reset_url: str,
) -> bool:
    """FR031 — Password reset link."""
    content = f"""
    <h2 style="color:#111827;font-size:20px;margin:0 0 16px;">
      Reset your password
    </h2>
    <p style="color:#4B5563;line-height:1.6;margin:0 0 20px;">
      Hi {first_name}, we received a request to reset your IMPT password.
      Click the button below to choose a new password.
    </p>
    <div style="text-align:center;margin:28px 0;">
      <a href="{reset_url}"
         style="background:#7C3AED;color:#fff;text-decoration:none;padding:13px 28px;
                border-radius:8px;font-weight:600;font-size:15px;display:inline-block;">
        Reset Password
      </a>
    </div>
    <div style="background:#FEF3C7;border:1px solid #FDE68A;border-radius:8px;
                padding:14px;margin:20px 0;">
      <p style="color:#92400E;font-size:13px;margin:0;line-height:1.6;">
        ⚠️ <strong>Security notice:</strong> This link expires in <strong>1 hour</strong>
        and can only be used once. Do not share this link with anyone.
      </p>
    </div>
    <p style="color:#6B7280;font-size:13px;">
      If you did not request a password reset, please ignore this email.
      Your password will not be changed.
    </p>
    <p style="color:#6B7280;font-size:12px;margin-top:16px;">
      If the button above does not work, copy and paste this link into your browser:<br>
      <span style="color:#7C3AED;word-break:break-all;">{reset_url}</span>
    </p>
    """
    return _send(to, "Reset your IMPT password", _base_template(content))


def send_session_complete_email(
    to: str,
    first_name: str,
    session_name: str,
    mutation_score: float,
    time_saved_pct: float,
    results_url: str,
) -> bool:
    """Optional — notify user when a long mutation testing job completes."""
    score_color = "#16A34A" if mutation_score >= 0.85 else "#D97706" if mutation_score >= 0.70 else "#DC2626"
    content = f"""
    <h2 style="color:#111827;font-size:20px;margin:0 0 16px;">
      ✅ Mutation testing complete!
    </h2>
    <p style="color:#4B5563;line-height:1.6;margin:0 0 20px;">
      Hi {first_name}, your mutation testing session
      <strong>"{session_name}"</strong> has completed.
    </p>
    <div style="background:#F0FDF4;border:1px solid #BBF7D0;border-radius:8px;padding:20px;margin:20px 0;">
      <div style="display:flex;gap:24px;flex-wrap:wrap;">
        <div>
          <p style="color:#6B7280;font-size:12px;margin:0 0 4px;">Mutation Score</p>
          <p style="color:{score_color};font-size:28px;font-weight:800;margin:0;">
            {round(mutation_score * 100, 1)}%
          </p>
        </div>
        <div>
          <p style="color:#6B7280;font-size:12px;margin:0 0 4px;">Time Saved</p>
          <p style="color:#16A34A;font-size:28px;font-weight:800;margin:0;">
            {round(time_saved_pct, 1)}%
          </p>
        </div>
      </div>
    </div>
    <div style="text-align:center;margin:28px 0;">
      <a href="{results_url}"
         style="background:#7C3AED;color:#fff;text-decoration:none;padding:13px 28px;
                border-radius:8px;font-weight:600;font-size:15px;display:inline-block;">
        View Full Results
      </a>
    </div>
    """
    return _send(to, f"Results ready: {session_name}", _base_template(content))


def send_admin_error_alert(error_type: str, message: str, detail: str = "") -> bool:
    """
    NFR036: Send critical error notification to admin email.
    Triggered for: database connection failure, disk > 90%, crash, high error rate.
    """
    from config.settings import get_settings
    s = get_settings()
    admin_email = getattr(s, 'ADMIN_ALERT_EMAIL', None) or getattr(s, 'EMAIL_FROM', None)
    if not admin_email:
        log.warning("NFR036: ADMIN_ALERT_EMAIL not set — cannot send error alert")
        return False

    html = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto">
      <div style="background:#dc2626;color:#fff;padding:16px 24px;border-radius:8px 8px 0 0">
        <h2 style="margin:0">⚠️ IMPT System Alert: {error_type}</h2>
      </div>
      <div style="background:#fff;border:1px solid #e5e7eb;padding:24px;border-radius:0 0 8px 8px">
        <p><strong>Error:</strong> {message}</p>
        {f'<pre style="background:#f3f4f6;padding:12px;border-radius:6px;font-size:12px;overflow:auto">{detail}</pre>' if detail else ''}
        <p style="color:#6b7280;font-size:12px;margin-top:24px">
          IMPT · NovaSoft · FEU Institute of Technology<br>
          This is an automated alert. Do not reply to this email.
        </p>
      </div>
    </div>
    """
    return _send(admin_email, f"[IMPT ALERT] {error_type}", html)

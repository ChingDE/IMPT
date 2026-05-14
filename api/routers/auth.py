"""
api/routers/auth.py
All authentication endpoints.

FR001–FR010  Login
FR011–FR021  Registration (with email verification)
FR022–FR028  Email verification
FR029–FR039  Password reset
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import (
    create_access_token, generate_secure_token,
    get_current_user, hash_password, verify_password,
)
from api.schemas.schemas import (
    AdminLoginRequest, ChangeAdminPasswordRequest,
    ForgotPasswordRequest, MessageOut, ResetPasswordRequest,
    TokenOut, UserOut, UserRegister,
)
from config.settings import get_settings
from db.database import get_db
from db.models.orm_models import User
from db.repositories.repositories import (
    AuditLogRepository, EmailVerificationRepository,
    PasswordResetRepository, UserRepository,
)
from services.email import send_password_reset_email, send_verification_email

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])
settings = get_settings()


def _client_ip(request: Request) -> str:
    return request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown")


# ── Register ───────────────────────────────────────────────────────────────────

@router.post("/register", response_model=MessageOut, status_code=201)
async def register(
    payload: UserRegister,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """FR011–FR020: Register new user, send verification email."""
    user_repo   = UserRepository(db)
    audit_repo  = AuditLogRepository(db)
    verify_repo = EmailVerificationRepository(db)

    # FR014: Check duplicate email
    if await user_repo.get_by_email(payload.email):
        raise HTTPException(
            status_code=409,
            detail="This email address is already registered. Please log in or use a different email."
        )

    # FR018: Create unverified account
    user = await user_repo.create(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        first_name=payload.first_name,
        last_name=payload.last_name,
        organization=payload.organization,
        role="user",
        is_verified=False,
    )

    # FR019: Create verification token (24-hour expiry)
    token = generate_secure_token()
    expires_at = datetime.utcnow() + timedelta(hours=settings.EMAIL_VERIFICATION_EXPIRE_HOURS)
    await verify_repo.create(user.id, token, expires_at)

    await db.commit()

    # Send verification email
    verify_url = f"{settings.FRONTEND_URL}/verify-email?token={token}"
    send_verification_email(payload.email, payload.first_name, verify_url)

    await audit_repo.log(
        category="AUTH", action="register",
        message=f"New user registered: {payload.email}",
        user_id=user.id, ip_address=_client_ip(request),
    )
    await db.commit()

    # FR020: Return message — frontend redirects to email verification confirmation page
    return MessageOut(
        message=f"Account created successfully! We've sent a verification email to {payload.email}. "
                "Please check your inbox and click the verification link to activate your account."
    )


# ── Login ──────────────────────────────────────────────────────────────────────

@router.post("/token", response_model=TokenOut)
async def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """FR005–FR008: Login with email + password. Lockout after 5 failed attempts."""
    user_repo  = UserRepository(db)
    audit_repo = AuditLogRepository(db)
    ip         = _client_ip(request)

    user = await user_repo.get_by_email(form.username)

    # FR008: Check lockout BEFORE validating password (NFR022)
    if user and user.is_locked_out:
        remaining = int((user.lockout_until - datetime.utcnow()).total_seconds() / 60)
        raise HTTPException(
            status_code=423,
            detail=f"Account temporarily locked due to too many failed attempts. "
                   f"Please try again in {remaining} minute(s) or reset your password."
        )

    # FR006: Validate credentials
    if not user or not verify_password(form.password, user.hashed_password):
        if user:
            await user_repo.increment_failed_login(user)
            await db.commit()
            remaining_attempts = max(0, settings.LOGIN_MAX_ATTEMPTS - user.failed_login_attempts)
            detail = (
                f"Invalid email or password. Please try again. "
                f"{remaining_attempts} attempt(s) remaining before temporary lockout ({settings.LOGIN_LOCKOUT_MINUTES} minutes)."
                if remaining_attempts > 0
                else f"Account locked for {settings.LOGIN_LOCKOUT_MINUTES} minutes due to too many failed attempts."
            )
        else:
            detail = "Invalid email or password. Please try again."

        await audit_repo.log(
            category="AUTH", action="login_failed",
            message=f"Failed login for: {form.username}",
            ip_address=ip, level="WARNING", outcome="failure",
        )
        await db.commit()

        raise HTTPException(status_code=401, detail=detail,
                            headers={"WWW-Authenticate": "Bearer"})

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Your account has been suspended. Contact support for assistance.")

    # Reset failed attempts on success
    await user_repo.reset_failed_login(user)

    token = create_access_token({"sub": user.id, "role": user.role})

    await audit_repo.log(
        category="AUTH", action="login",
        message=f"User logged in: {user.email}",
        user_id=user.id, ip_address=ip,
    )
    await db.commit()

    return TokenOut(access_token=token, token_type="bearer", user=UserOut.model_validate(user))


# ── Admin login ────────────────────────────────────────────────────────────────

@router.post("/admin-token", response_model=TokenOut)
async def admin_login(
    payload: AdminLoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """FR010: Admin login with username + password."""
    user_repo  = UserRepository(db)
    audit_repo = AuditLogRepository(db)
    ip         = _client_ip(request)

    user = await user_repo.get_by_username(payload.username)

    if not user or not verify_password(payload.password, user.hashed_password):
        await audit_repo.log(
            category="AUTH", action="admin_login_failed",
            message=f"Failed admin login for username: {payload.username}",
            ip_address=ip, level="WARNING", outcome="failure",
        )
        await db.commit()
        raise HTTPException(status_code=401, detail="Incorrect username or password.")

    if user.role != "admin":
        raise HTTPException(status_code=403, detail="This login is for admin accounts only.")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated.")

    await user_repo.reset_failed_login(user)
    token = create_access_token({"sub": user.id, "role": user.role})

    await audit_repo.log(
        category="AUTH", action="admin_login",
        message=f"Admin logged in: {user.username}",
        user_id=user.id, ip_address=ip,
    )
    await db.commit()

    return TokenOut(access_token=token, token_type="bearer", user=UserOut.model_validate(user))


# ── Admin first-login password change ─────────────────────────────────────────

@router.post("/change-admin-credentials", response_model=UserOut)
async def change_admin_credentials(
    payload: ChangeAdminPasswordRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Admin forced first-login credential update."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    user_repo  = UserRepository(db)
    audit_repo = AuditLogRepository(db)

    if payload.new_username != current_user.username:
        if await user_repo.get_by_username(payload.new_username):
            raise HTTPException(status_code=409, detail="Username already taken")

    if payload.new_email != current_user.email:
        if await user_repo.get_by_email(payload.new_email):
            raise HTTPException(status_code=409, detail="Email already registered")

    updated = await user_repo.update(
        current_user,
        username=payload.new_username,
        hashed_password=hash_password(payload.new_password),
        email=payload.new_email,
        must_change_password=False,
    )

    await audit_repo.log(
        category="AUTH", action="admin_credentials_changed",
        message=f"Admin updated credentials",
        user_id=current_user.id, ip_address=_client_ip(request),
    )
    await db.commit()
    return updated


# ── Email verification ─────────────────────────────────────────────────────────

@router.get("/verify-email", response_model=MessageOut)
async def verify_email(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """FR025–FR028: Verify email via token from link."""
    verify_repo = EmailVerificationRepository(db)
    user_repo   = UserRepository(db)

    token_obj = await verify_repo.get_by_token(token)

    if not token_obj:
        raise HTTPException(
            status_code=400,
            detail="Invalid verification link. If you've already verified your account, please log in."
        )

    if token_obj.used:
        raise HTTPException(
            status_code=400,
            detail="Invalid verification link. If you've already verified your account, please log in."
        )

    if datetime.utcnow() > token_obj.expires_at.replace(tzinfo=None):
        raise HTTPException(
            status_code=410,
            detail="This verification link has expired. Please request a new verification email."
        )

    # Activate account
    user = await user_repo.get_by_id(token_obj.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    await user_repo.update(user, is_verified=True)
    await verify_repo.mark_used(token_obj)
    await db.commit()

    return MessageOut(
        message="Email verified successfully! Your account is now active. You can now access all IMPT features."
    )


@router.post("/resend-verification", response_model=MessageOut)
async def resend_verification(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """FR023: Resend verification email. Max 3 per hour."""
    if current_user.is_verified:
        raise HTTPException(status_code=400, detail="Email already verified.")

    verify_repo = EmailVerificationRepository(db)

    # Rate limit: max 3 resends per hour
    latest = await verify_repo.get_latest_for_user(current_user.id)
    if latest:
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        if latest.resend_count >= 3 and latest.last_resend_at and latest.last_resend_at > one_hour_ago:
            raise HTTPException(
                status_code=429,
                detail="Too many resend requests. Please wait before requesting another verification email."
            )

    # Invalidate old tokens and create new one
    await verify_repo.invalidate_existing(current_user.id)
    token = generate_secure_token()
    expires_at = datetime.utcnow() + timedelta(hours=settings.EMAIL_VERIFICATION_EXPIRE_HOURS)
    new_token = await verify_repo.create(current_user.id, token, expires_at)

    # Update resend count
    new_token.resend_count = (latest.resend_count + 1) if latest else 1
    new_token.last_resend_at = datetime.utcnow()
    db.add(new_token)

    await db.commit()

    verify_url = f"{settings.FRONTEND_URL}/verify-email?token={token}"
    send_verification_email(current_user.email, current_user.first_name, verify_url)

    return MessageOut(message="Verification email sent. Please check your inbox.")


# ── Password recovery ──────────────────────────────────────────────────────────

@router.post("/forgot-password", response_model=MessageOut)
async def forgot_password(
    payload: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """FR029–FR032: Request password reset email."""
    user_repo  = UserRepository(db)
    reset_repo = PasswordResetRepository(db)

    user = await user_repo.get_by_email(payload.email)

    # FR030 / FR032: Same response regardless of whether email exists (prevents enumeration)
    standard_response = MessageOut(
        message="If an account exists with this email, you will receive password reset instructions shortly."
    )

    if not user:
        return standard_response

    # FR031: Create reset token (1-hour expiry)
    token = generate_secure_token()
    expires_at = datetime.utcnow() + timedelta(hours=settings.PASSWORD_RESET_EXPIRE_HOURS)
    await reset_repo.create(user.id, token, expires_at)
    await db.commit()

    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    send_password_reset_email(user.email, user.first_name, reset_url)

    return standard_response


@router.post("/reset-password", response_model=MessageOut)
async def reset_password(
    payload: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """FR034–FR039: Reset password using token from email."""
    reset_repo = PasswordResetRepository(db)
    user_repo  = UserRepository(db)

    token_obj = await reset_repo.get_by_token(payload.token)

    if not token_obj:
        raise HTTPException(
            status_code=400,
            detail="This link is invalid or has already been used. Please request a new password reset link."
        )
    if token_obj.used:
        raise HTTPException(
            status_code=400,
            detail="This link is invalid or has already been used. Please request a new password reset link."
        )
    if datetime.utcnow() > token_obj.expires_at.replace(tzinfo=None):
        raise HTTPException(
            status_code=410,
            detail="This reset link has expired. Please request a new password reset link."
        )
    if payload.new_password != payload.confirm_password:
        raise HTTPException(status_code=422, detail="Passwords do not match.")

    user = await user_repo.get_by_id(token_obj.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    await user_repo.update(user, hashed_password=hash_password(payload.new_password))
    await reset_repo.mark_used(token_obj)
    await db.commit()

    return MessageOut(
        message="Password reset successful! You can now log in with your new password."
    )


# ── Current user ───────────────────────────────────────────────────────────────

@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    return current_user

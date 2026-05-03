"""
api/routers/auth.py
Authentication endpoints.

Regular users:  POST /api/auth/register
                POST /api/auth/token          (email + password)
                GET  /api/auth/me

Admin:          POST /api/auth/admin-token    (username + password)
                POST /api/auth/change-password (forced on first login)
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from api.schemas import TokenOut, UserCreate, UserOut
from db.database import get_db
from db.models.orm_models import User
from db.repositories import UserRepository

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ── Regular user: register ────────────────────────────────────────────────────

@router.post("/register", response_model=UserOut, status_code=201)
async def register(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    repo = UserRepository(db)
    if await repo.get_by_email(payload.email):
        raise HTTPException(status_code=409, detail="Email already registered")
    user = await repo.create(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
    )
    await db.commit()
    return user


# ── Regular user: login (email + password) ────────────────────────────────────

@router.post("/token", response_model=TokenOut)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    repo = UserRepository(db)
    user = await repo.get_by_email(form.username)
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated")

    token = create_access_token({"sub": user.id, "role": user.role})
    return TokenOut(
        access_token=token,
        token_type="bearer",
        user=UserOut.model_validate(user),
    )


# ── Admin: login (username + password) ───────────────────────────────────────

class AdminLoginForm(BaseModel):
    username: str
    password: str


@router.post("/admin-token", response_model=TokenOut)
async def admin_login(
    payload: AdminLoginForm,
    db: AsyncSession = Depends(get_db),
):
    repo = UserRepository(db)
    user = await repo.get_by_username(payload.username)

    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This login is for admin accounts only",
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated")

    token = create_access_token({"sub": user.id, "role": user.role})
    return TokenOut(
        access_token=token,
        token_type="bearer",
        user=UserOut.model_validate(user),
    )


# ── Admin: forced password change on first login ──────────────────────────────

class ChangePasswordPayload(BaseModel):
    new_username: str
    new_password: str
    new_email: str


@router.post("/change-password", response_model=UserOut)
async def change_password(
    payload: ChangePasswordPayload,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Called when must_change_password is True (after first admin login).
    Updates username, password, and email in one step.
    Clears the must_change_password flag.
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    repo = UserRepository(db)

    # Validate no conflicts
    if payload.new_username != current_user.username:
        existing = await repo.get_by_username(payload.new_username)
        if existing:
            raise HTTPException(status_code=409, detail="Username already taken")

    if payload.new_email != current_user.email:
        existing = await repo.get_by_email(payload.new_email)
        if existing:
            raise HTTPException(status_code=409, detail="Email already registered")

    if len(payload.new_password) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters")

    # Apply changes
    current_user.username          = payload.new_username
    current_user.hashed_password   = hash_password(payload.new_password)
    current_user.email             = payload.new_email
    current_user.must_change_password = False

    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)
    return current_user


# ── Current user ──────────────────────────────────────────────────────────────

@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    return current_user

"""api/routers/github.py — GitHub account linking and repository import.

Flow:
  1. GET  /api/github/authorize-url   -> signed state + GitHub authorize URL
  2. (browser) GitHub consent
  3. GET  /api/github/callback        -> exchange code, store encrypted token, redirect to app
  4. GET  /api/github/status          -> {connected, login}
  5. GET  /api/github/repos           -> list (search-aware) repos, incl. private
  6. GET  /api/github/repos/{o}/{r}/branches
  7. POST /api/github/import/{session_id} -> tarball -> extract -> analyze (same as upload)
"""
from __future__ import annotations

import io
import logging
import shutil
import tarfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_user
from config.settings import get_settings
from db.database import get_db
from db.models.orm_models import User
from db.repositories.repositories import TestSessionRepository, UserRepository
from api.schemas.schemas import SessionOut
from services import github_client as gh
from services.crypto import encrypt, decrypt
from services.project_analysis import analyze_into_session

log = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/api/github", tags=["github"])

_OAUTH_PURPOSE = "gh_oauth"


# ── OAuth ──────────────────────────────────────────────────────────────────

@router.get("/authorize-url")
async def authorize_url(return_session: str = Query(""),
                        current_user: User = Depends(get_current_user)):
    if not settings.GITHUB_ENABLED:
        raise HTTPException(status_code=503, detail="GitHub integration is not configured.")
    state = jwt.encode(
        {"sub": current_user.id, "purpose": _OAUTH_PURPOSE, "ret": return_session,
         "exp": datetime.utcnow() + timedelta(minutes=10)},
        settings.SECRET_KEY, algorithm=settings.ALGORITHM,
    )
    return {"url": gh.authorize_url(state)}


@router.get("/callback")
async def callback(code: str = Query(""), state: str = Query(""),
                   db: AsyncSession = Depends(get_db)):
    """GitHub redirects here. Validates state, stores the token, returns to the app."""
    def _back(ok: bool, ret: str = ""):
        dest = f"{settings.FRONTEND_URL}"
        dest += f"/sessions/{ret}/upload" if ret else "/new-session"
        return RedirectResponse(f"{dest}?github={'connected' if ok else 'error'}", status_code=302)

    try:
        payload = jwt.decode(state, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("purpose") != _OAUTH_PURPOSE:
            raise JWTError("bad purpose")
        user_id = payload.get("sub"); ret = payload.get("ret", "")
    except JWTError:
        return _back(False)

    if not code:
        return _back(False, ret)

    token = await gh.exchange_code_for_token(code)
    if not token:
        return _back(False, ret)
    ghuser = await gh.get_authenticated_user(token)
    login = (ghuser or {}).get("login")

    users = UserRepository(db)
    user = await users.get_by_id(user_id)
    if not user:
        return _back(False, ret)
    await users.update(user, github_token=encrypt(token), github_login=login,
                       github_connected_at=datetime.now(timezone.utc))
    await db.commit()
    return _back(True, ret)


@router.get("/status")
async def status(current_user: User = Depends(get_current_user)):
    return {
        "enabled": settings.GITHUB_ENABLED,
        "connected": bool(current_user.github_token),
        "login": current_user.github_login,
    }


@router.delete("/disconnect")
async def disconnect(current_user: User = Depends(get_current_user),
                     db: AsyncSession = Depends(get_db)):
    users = UserRepository(db)
    await users.update(current_user, github_token=None, github_login=None,
                       github_connected_at=None)
    await db.commit()
    return {"message": "GitHub account disconnected."}


# ── Repo browsing ────────────────────────────────────────────────────────────

def _require_token(user: User) -> str:
    tok = decrypt(user.github_token) if user.github_token else None
    if not tok:
        raise HTTPException(status_code=400, detail="GitHub account is not connected.")
    return tok


@router.get("/repos")
async def repos(query: str = Query(""), page: int = Query(1, ge=1),
                current_user: User = Depends(get_current_user)):
    tok = _require_token(current_user)
    return await gh.list_repos(tok, login=current_user.github_login,
                               query=query.strip(), page=page)


@router.get("/repos/{owner}/{repo}/branches")
async def branches(owner: str, repo: str,
                   current_user: User = Depends(get_current_user)):
    tok = _require_token(current_user)
    return {"branches": await gh.list_branches(tok, owner, repo)}


# ── Import ─────────────────────────────────────────────────────────────────

class GithubImportBody(BaseModel):
    owner: str
    repo: str
    ref: str
    subdir: Optional[str] = None


def _safe_extract(tar: tarfile.TarFile, dest: Path) -> None:
    dest_resolved = dest.resolve()
    for m in tar.getmembers():
        target = (dest / m.name).resolve()
        if not str(target).startswith(str(dest_resolved)):
            raise HTTPException(status_code=422, detail="Unsafe path in repository archive.")
    tar.extractall(dest)


@router.post("/import/{session_id}", response_model=SessionOut)
async def import_repo(session_id: str, body: GithubImportBody,
                      current_user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    repo_db = TestSessionRepository(db)
    session = await repo_db.get_by_id(session_id)
    if not session or session.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found")

    tok = _require_token(current_user)
    data = await gh.download_tarball(tok, body.owner, body.repo, body.ref)
    if data is None:
        raise HTTPException(status_code=502, detail="Could not download the repository from GitHub.")
    max_bytes = settings.GITHUB_MAX_IMPORT_MB * 1024 * 1024
    if len(data) > max_bytes:
        raise HTTPException(status_code=413,
            detail=f"Repository exceeds the {settings.GITHUB_MAX_IMPORT_MB}MB import limit.")

    # Extract into the same uploads location an upload would use.
    upload_dir = Path(settings.UPLOAD_DIR) / current_user.id / session_id / "source"
    upload_dir.mkdir(parents=True, exist_ok=True)
    for f in upload_dir.iterdir():
        shutil.rmtree(f) if f.is_dir() else f.unlink()

    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            _safe_extract(tar, upload_dir)
    except tarfile.TarError:
        raise HTTPException(status_code=422, detail="The downloaded archive could not be read.")

    label = f"{body.owner}/{body.repo}@{body.ref}"
    return await analyze_into_session(
        db, repo_db, session, upload_dir,
        language=session.language, source_label=label,
        size_bytes=len(data), subdir=body.subdir,
    )

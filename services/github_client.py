"""services/github_client.py — thin async wrapper over the GitHub REST API.

No `git` binary required: repositories are fetched as tarballs over HTTPS, which
drops straight into the existing extract-and-analyze pipeline. Works for private
repos because every call is authenticated with the user's OAuth token.
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from config.settings import get_settings

log = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
_ACCEPT = "application/vnd.github+json"
_TIMEOUT = httpx.Timeout(30.0, read=120.0)


def authorize_url(state: str) -> str:
    """Build the GitHub OAuth authorize URL the browser is redirected to."""
    s = get_settings()
    redirect_uri = f"{s.API_BASE_URL}/api/github/callback"
    from urllib.parse import urlencode
    q = urlencode({
        "client_id": s.GITHUB_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "scope": s.GITHUB_OAUTH_SCOPE,
        "state": state,
        "allow_signup": "false",
    })
    return f"https://github.com/login/oauth/authorize?{q}"


async def exchange_code_for_token(code: str) -> Optional[str]:
    s = get_settings()
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        r = await c.post(
            GITHUB_TOKEN_URL,
            headers={"Accept": "application/json"},
            data={
                "client_id": s.GITHUB_CLIENT_ID,
                "client_secret": s.GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": f"{s.API_BASE_URL}/api/github/callback",
            },
        )
    if r.status_code != 200:
        log.warning("GitHub token exchange failed: %s", r.status_code)
        return None
    return r.json().get("access_token")


def _headers(token: str) -> dict:
    return {"Accept": _ACCEPT, "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28"}


async def get_authenticated_user(token: str) -> Optional[dict]:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        r = await c.get(f"{GITHUB_API}/user", headers=_headers(token))
    return r.json() if r.status_code == 200 else None


async def list_repos(token: str, login: Optional[str] = None,
                     query: str = "", page: int = 1, per_page: int = 30) -> list:
    """List repos the user can access. If query is given, use the search API
    (scoped to the user) so people with many repos can filter instead of scroll."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        if query and login:
            r = await c.get(
                f"{GITHUB_API}/search/repositories",
                headers=_headers(token),
                params={"q": f"{query} user:{login} fork:true",
                        "per_page": per_page, "page": page},
            )
            items = r.json().get("items", []) if r.status_code == 200 else []
        else:
            r = await c.get(
                f"{GITHUB_API}/user/repos",
                headers=_headers(token),
                params={"per_page": per_page, "page": page, "sort": "updated",
                        "affiliation": "owner,collaborator,organization_member"},
            )
            items = r.json() if r.status_code == 200 else []
    return [{
        "full_name": x.get("full_name"),
        "owner": (x.get("owner") or {}).get("login"),
        "name": x.get("name"),
        "private": x.get("private"),
        "default_branch": x.get("default_branch"),
        "language": x.get("language"),
        "updated_at": x.get("updated_at"),
        "size_kb": x.get("size"),
    } for x in items if x.get("full_name")]


async def list_branches(token: str, owner: str, repo: str,
                        page: int = 1, per_page: int = 100) -> list:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
        r = await c.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/branches",
            headers=_headers(token), params={"per_page": per_page, "page": page},
        )
    if r.status_code != 200:
        return []
    return [b.get("name") for b in r.json() if b.get("name")]


async def download_tarball(token: str, owner: str, repo: str, ref: str) -> Optional[bytes]:
    """Download repo@ref as a .tar.gz (follows the redirect to codeload)."""
    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as c:
        r = await c.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/tarball/{ref}",
            headers=_headers(token),
        )
    if r.status_code != 200:
        log.warning("Tarball download failed for %s/%s@%s: %s", owner, repo, ref, r.status_code)
        return None
    return r.content

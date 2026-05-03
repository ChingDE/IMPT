"""
tests/api/test_api.py
API integration tests using FastAPI TestClient (synchronous httpx).
Uses an in-memory SQLite database — no PostgreSQL or Redis required.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from db.database import Base, get_db
from main import create_app

# ── In-memory SQLite for tests ───────────────────────────────────────────────

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestSessionLocal = async_sessionmaker(
    bind=test_engine, class_=AsyncSession, expire_on_commit=False
)


async def override_get_db():
    async with TestSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@pytest_asyncio.fixture(scope="function")
async def client():
    """Fresh DB + async test client for each test."""
    # Create tables
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac

    # Drop tables after each test
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _register_and_login(client: AsyncClient, email="test@feu.edu.ph", pw="Password123"):
    await client.post("/api/auth/register", json={
        "email": email, "password": pw, "full_name": "Test User", "role": "student"
    })
    resp = await client.post(
        "/api/auth/token",
        data={"username": email, "password": pw},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    return resp.json()["access_token"]


async def _create_project(client: AsyncClient, token: str, name="Demo Project"):
    resp = await client.post(
        "/api/projects",
        json={"name": name, "framework": "PIT", "loc": 5000, "test_count": 100},
        headers={"Authorization": f"Bearer {token}"},
    )
    return resp.json()


# ─────────────────────────────────────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────────────────────────────────────

class TestHealth:
    @pytest.mark.asyncio
    async def test_health_ok(self, client):
        r = await client.get("/api/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert "version" in body
        assert body["db"] == "ok"

    @pytest.mark.asyncio
    async def test_root_redirect(self, client):
        r = await client.get("/")
        assert r.status_code == 200
        assert "docs" in r.json()


# ─────────────────────────────────────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────────────────────────────────────

class TestAuth:
    @pytest.mark.asyncio
    async def test_register_success(self, client):
        r = await client.post("/api/auth/register", json={
            "email": "ching@feu.edu.ph",
            "password": "SecurePass1",
            "full_name": "Daniel Ching",
            "role": "student",
        })
        assert r.status_code == 201
        body = r.json()
        assert body["email"] == "ching@feu.edu.ph"
        assert body["role"] == "student"
        assert "id" in body
        assert "hashed_password" not in body

    @pytest.mark.asyncio
    async def test_register_duplicate_email(self, client):
        payload = {"email": "dupe@feu.edu.ph", "password": "Password1"}
        await client.post("/api/auth/register", json=payload)
        r = await client.post("/api/auth/register", json=payload)
        assert r.status_code == 409

    @pytest.mark.asyncio
    async def test_register_invalid_role(self, client):
        r = await client.post("/api/auth/register", json={
            "email": "x@x.com", "password": "Password1", "role": "hacker"
        })
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_login_success(self, client):
        await client.post("/api/auth/register", json={
            "email": "login@feu.edu.ph", "password": "Password1"
        })
        r = await client.post(
            "/api/auth/token",
            data={"username": "login@feu.edu.ph", "password": "Password1"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert r.status_code == 200
        body = r.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"
        assert "user" in body

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, client):
        await client.post("/api/auth/register", json={
            "email": "wp@feu.edu.ph", "password": "Password1"
        })
        r = await client.post(
            "/api/auth/token",
            data={"username": "wp@feu.edu.ph", "password": "WrongPassword"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_me_endpoint(self, client):
        token = await _register_and_login(client)
        r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["email"] == "test@feu.edu.ph"

    @pytest.mark.asyncio
    async def test_me_no_token(self, client):
        r = await client.get("/api/auth/me")
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_me_bad_token(self, client):
        r = await client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"})
        assert r.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# Projects
# ─────────────────────────────────────────────────────────────────────────────

class TestProjects:
    @pytest.mark.asyncio
    async def test_create_project(self, client):
        token = await _register_and_login(client)
        r = await client.post(
            "/api/projects",
            json={"name": "My Java App", "framework": "PIT", "loc": 3000, "test_count": 80},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201
        body = r.json()
        assert body["name"] == "My Java App"
        assert body["framework"] == "PIT"

    @pytest.mark.asyncio
    async def test_create_project_invalid_framework(self, client):
        token = await _register_and_login(client)
        r = await client.post(
            "/api/projects",
            json={"name": "Bad", "framework": "GRADLE"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_list_projects_empty(self, client):
        token = await _register_and_login(client)
        r = await client.get("/api/projects", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json() == []

    @pytest.mark.asyncio
    async def test_list_projects(self, client):
        token = await _register_and_login(client)
        await _create_project(client, token, "P1")
        await _create_project(client, token, "P2")
        r = await client.get("/api/projects", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert len(r.json()) == 2

    @pytest.mark.asyncio
    async def test_get_project(self, client):
        token   = await _register_and_login(client)
        project = await _create_project(client, token)
        r = await client.get(
            f"/api/projects/{project['id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["id"] == project["id"]

    @pytest.mark.asyncio
    async def test_get_project_not_found(self, client):
        token = await _register_and_login(client)
        r = await client.get(
            "/api/projects/nonexistent-id",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_project_isolation(self, client):
        """User A cannot see User B's projects."""
        token_a = await _register_and_login(client, "a@feu.edu.ph")
        token_b = await _register_and_login(client, "b@feu.edu.ph", "Password456")
        project = await _create_project(client, token_a)
        r = await client.get(
            f"/api/projects/{project['id']}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_project(self, client):
        token   = await _register_and_login(client)
        project = await _create_project(client, token)
        r = await client.delete(
            f"/api/projects/{project['id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 204
        # Confirm gone
        r2 = await client.get(
            f"/api/projects/{project['id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r2.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Jobs
# ─────────────────────────────────────────────────────────────────────────────

class TestJobs:
    @pytest.mark.asyncio
    async def test_submit_job(self, client):
        token   = await _register_and_login(client)
        project = await _create_project(client, token)
        r = await client.post(
            "/api/jobs",
            json={
                "project_id":          project["id"],
                "time_budget_seconds": 120,
                "optimizer_strategy":  "GREEDY",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 202
        body = r.json()
        assert body["project_id"] == project["id"]
        assert body["status"] in ("PENDING", "RUNNING", "COMPLETED")

    @pytest.mark.asyncio
    async def test_submit_job_invalid_project(self, client):
        token = await _register_and_login(client)
        r = await client.post(
            "/api/jobs",
            json={"project_id": "bad-id", "time_budget_seconds": 120},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_submit_job_invalid_budget(self, client):
        token   = await _register_and_login(client)
        project = await _create_project(client, token)
        r = await client.post(
            "/api/jobs",
            json={"project_id": project["id"], "time_budget_seconds": 10},  # < 60
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_list_jobs_empty(self, client):
        token = await _register_and_login(client)
        r = await client.get("/api/jobs", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json() == []

    @pytest.mark.asyncio
    async def test_get_job_status(self, client):
        token   = await _register_and_login(client)
        project = await _create_project(client, token)
        job_r   = await client.post(
            "/api/jobs",
            json={"project_id": project["id"], "time_budget_seconds": 120},
            headers={"Authorization": f"Bearer {token}"},
        )
        job_id = job_r.json()["id"]
        r = await client.get(
            f"/api/jobs/{job_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["id"] == job_id

    @pytest.mark.asyncio
    async def test_job_not_found(self, client):
        token = await _register_and_login(client)
        r = await client.get("/api/jobs/fake-id", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_job_isolation(self, client):
        """User A cannot see User B's jobs."""
        token_a = await _register_and_login(client, "ja@feu.edu.ph")
        token_b = await _register_and_login(client, "jb@feu.edu.ph", "Password789")
        project = await _create_project(client, token_a)
        job_r   = await client.post(
            "/api/jobs",
            json={"project_id": project["id"], "time_budget_seconds": 120},
            headers={"Authorization": f"Bearer {token_a}"},
        )
        job_id = job_r.json()["id"]
        r = await client.get(
            f"/api/jobs/{job_id}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_completed_job_has_result(self, client):
        """Submit a job, wait for sync completion, then retrieve result."""
        import asyncio
        token   = await _register_and_login(client)
        project = await _create_project(client, token)
        job_r   = await client.post(
            "/api/jobs",
            json={"project_id": project["id"], "time_budget_seconds": 120},
            headers={"Authorization": f"Bearer {token}"},
        )
        job_id = job_r.json()["id"]

        # Poll until completed (sync path should finish quickly)
        for _ in range(20):
            status_r = await client.get(
                f"/api/jobs/{job_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            if status_r.json()["status"] == "COMPLETED":
                break
            await asyncio.sleep(0.3)

        result_r = await client.get(
            f"/api/jobs/{job_id}/result",
            headers={"Authorization": f"Bearer {token}"},
        )
        if result_r.status_code == 200:
            body = result_r.json()
            assert body["total_mutants"] > 0
            assert 0.0 <= body["mutation_score"] <= 1.0
            assert body["ci_lower"] <= body["ci_upper"]

    @pytest.mark.asyncio
    async def test_mutants_endpoint_after_completion(self, client):
        import asyncio
        token   = await _register_and_login(client)
        project = await _create_project(client, token)
        job_r   = await client.post(
            "/api/jobs",
            json={"project_id": project["id"], "time_budget_seconds": 120},
            headers={"Authorization": f"Bearer {token}"},
        )
        job_id = job_r.json()["id"]

        for _ in range(20):
            s = await client.get(f"/api/jobs/{job_id}", headers={"Authorization": f"Bearer {token}"})
            if s.json()["status"] == "COMPLETED":
                break
            await asyncio.sleep(0.3)

        mr = await client.get(
            f"/api/jobs/{job_id}/mutants",
            headers={"Authorization": f"Bearer {token}"},
        )
        if mr.status_code == 200:
            mutants = mr.json()
            assert isinstance(mutants, list)
            if mutants:
                m = mutants[0]
                assert "operator" in m
                assert "status" in m
                assert "priority_score" in m

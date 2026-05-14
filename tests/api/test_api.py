"""tests/api/test_api.py — API endpoint tests using in-memory SQLite."""
import pytest
from fastapi.testclient import TestClient
from main import create_app
from db.database import create_tables, AsyncSessionLocal
import asyncio

app = create_app()

@pytest.fixture(scope="module")
def client():
    asyncio.run(create_tables())
    with TestClient(app) as c:
        yield c


class TestHealth:
    def test_health_ok(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_version(self, client):
        r = client.get("/api/health")
        assert "version" in r.json()


class TestAuth:
    def test_register(self, client):
        r = client.post("/api/auth/register", json={
            "email": "test@example.com",
            "password": "Test@1234",
            "first_name": "Test",
            "last_name": "User",
        })
        assert r.status_code in (201, 409)

    def test_login(self, client):
        client.post("/api/auth/register", json={
            "email": "login@example.com",
            "password": "Test@1234",
            "first_name": "Login",
            "last_name": "User",
        })
        r = client.post("/api/auth/token",
                        data={"username": "login@example.com", "password": "Test@1234"})
        assert r.status_code == 200
        assert "access_token" in r.json()

    def test_login_wrong_password(self, client):
        r = client.post("/api/auth/token",
                        data={"username": "login@example.com", "password": "wrong"})
        assert r.status_code == 401

    def test_me_requires_auth(self, client):
        r = client.get("/api/auth/me")
        assert r.status_code == 401

    def test_me_with_token(self, client):
        r = client.post("/api/auth/token",
                        data={"username": "login@example.com", "password": "Test@1234"})
        token = r.json()["access_token"]
        r2 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r2.status_code == 200
        assert r2.json()["email"] == "login@example.com"

    def test_forgot_password_always_200(self, client):
        r = client.post("/api/auth/forgot-password",
                        json={"email": "nonexistent@example.com"})
        assert r.status_code == 200

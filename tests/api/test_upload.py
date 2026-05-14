"""tests/api/test_upload.py — Session upload endpoint tests."""
import io
import zipfile
import asyncio
import pytest
from fastapi.testclient import TestClient
from main import create_app
from db.database import create_tables

app = create_app()


def _make_zip(files: dict) -> bytes:
    """Create an in-memory ZIP with the given filename→content mapping."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


@pytest.fixture(scope="module")
def client():
    asyncio.run(create_tables())
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def auth_headers(client):
    client.post("/api/auth/register", json={
        "email": "upload@example.com",
        "password": "Upload@1234",
        "first_name": "Upload",
        "last_name": "Tester",
    })
    # Manually verify the user so session creation is allowed
    import asyncio
    from db.database import AsyncSessionLocal
    from db.repositories.repositories import UserRepository
    async def _verify():
        async with AsyncSessionLocal() as db:
            repo = UserRepository(db)
            user = await repo.get_by_email("upload@example.com")
            if user:
                await repo.update(user, is_verified=True)
                await db.commit()
    asyncio.run(_verify())
    r = client.post("/api/auth/token",
                    data={"username": "upload@example.com", "password": "Upload@1234"})
    token = r.json().get("access_token", "")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def java_session_id(client, auth_headers):
    r = client.post("/api/sessions",
                    json={"name": "JavaUploadTest", "language": "java"},
                    headers=auth_headers)
    return r.json()["id"]


@pytest.fixture(scope="module")
def js_session_id(client, auth_headers):
    r = client.post("/api/sessions",
                    json={"name": "JSUploadTest", "language": "javascript"},
                    headers=auth_headers)
    return r.json()["id"]


class TestSessionCreate:
    def test_create_java_session(self, client, auth_headers):
        r = client.post("/api/sessions",
                        json={"name": "MyJavaSession", "language": "java"},
                        headers=auth_headers)
        assert r.status_code == 201
        assert r.json()["status"] == "not_started"
        assert r.json()["language"] == "java"

    def test_create_js_session(self, client, auth_headers):
        r = client.post("/api/sessions",
                        json={"name": "MyJSSession", "language": "javascript"},
                        headers=auth_headers)
        assert r.status_code == 201
        assert r.json()["language"] == "javascript"

    def test_invalid_language_rejected(self, client, auth_headers):
        r = client.post("/api/sessions",
                        json={"name": "BadLang", "language": "python"},
                        headers=auth_headers)
        assert r.status_code == 422

    def test_empty_name_rejected(self, client, auth_headers):
        r = client.post("/api/sessions",
                        json={"name": "", "language": "java"},
                        headers=auth_headers)
        assert r.status_code == 422

    def test_requires_auth(self, client):
        r = client.post("/api/sessions",
                        json={"name": "Test", "language": "java"})
        assert r.status_code == 401


class TestUploadSuccess:
    def test_valid_java_zip_accepted(self, client, auth_headers, java_session_id):
        zip_data = _make_zip({
            "pom.xml": "<project><modelVersion>4.0.0</modelVersion></project>",
            "src/main/java/Calculator.java": "public class Calculator { }",
            "src/test/java/CalculatorTest.java": "@Test public void test() { }",
        })
        r = client.post(
            f"/api/sessions/{java_session_id}/upload",
            files={"file": ("project.zip", zip_data, "application/zip")},
            headers=auth_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "uploaded"
        assert data["detected_framework"] == "PIT"
        assert data["upload_filename"] == "project.zip"

    def test_valid_js_zip_accepted(self, client, auth_headers, js_session_id):
        zip_data = _make_zip({
            "package.json": '{"name":"test","version":"1.0.0"}',
            "src/index.js": "module.exports = { add: (a,b) => a+b };",
            "src/index.test.js": "test('adds', () => {});",
        })
        r = client.post(
            f"/api/sessions/{js_session_id}/upload",
            files={"file": ("js-project.zip", zip_data, "application/zip")},
            headers=auth_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["detected_framework"] == "Stryker"


class TestUploadValidation:
    def test_non_zip_rejected(self, client, auth_headers, java_session_id):
        r = client.post(
            f"/api/sessions/{java_session_id}/upload",
            files={"file": ("project.tar.gz", b"fake content", "application/gzip")},
            headers=auth_headers,
        )
        assert r.status_code == 415

    def test_java_without_pom_rejected(self, client, auth_headers):
        r = client.post("/api/sessions",
                        json={"name": "NoPomSession", "language": "java"},
                        headers=auth_headers)
        sid = r.json()["id"]
        zip_data = _make_zip({
            "src/Calculator.java": "public class Calculator { }",
        })
        r2 = client.post(
            f"/api/sessions/{sid}/upload",
            files={"file": ("nopom.zip", zip_data, "application/zip")},
            headers=auth_headers,
        )
        assert r2.status_code == 422

    def test_js_without_package_json_rejected(self, client, auth_headers):
        r = client.post("/api/sessions",
                        json={"name": "NoPkgSession", "language": "javascript"},
                        headers=auth_headers)
        sid = r.json()["id"]
        zip_data = _make_zip({
            "src/index.js": "const x = 1;",
        })
        r2 = client.post(
            f"/api/sessions/{sid}/upload",
            files={"file": ("nopkg.zip", zip_data, "application/zip")},
            headers=auth_headers,
        )
        assert r2.status_code == 422

    def test_upload_requires_auth(self, client, java_session_id):
        zip_data = _make_zip({"pom.xml": "<project/>"})
        r = client.post(
            f"/api/sessions/{java_session_id}/upload",
            files={"file": ("p.zip", zip_data, "application/zip")},
        )
        assert r.status_code == 401

    def test_wrong_session_returns_404(self, client, auth_headers):
        zip_data = _make_zip({"pom.xml": "<project/>"})
        r = client.post(
            "/api/sessions/nonexistent-id/upload",
            files={"file": ("p.zip", zip_data, "application/zip")},
            headers=auth_headers,
        )
        assert r.status_code == 404

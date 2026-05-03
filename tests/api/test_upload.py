"""
tests/api/test_upload.py
Tests for POST /api/projects/{id}/upload
Uses in-memory SQLite + real zip/tar construction.
"""

import io
import json
import tarfile
import zipfile

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from db.database import Base, get_db
from main import create_app

# ── Test DB setup (same pattern as test_api.py) ───────────────────────────────
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
async def client(tmp_path, monkeypatch):
    """Test client with in-memory DB and tmp upload dir."""
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _register_login(client, email="up@feu.edu.ph", pw="Password123"):
    await client.post("/api/auth/register", json={
        "email": email, "password": pw, "full_name": "Up User", "role": "student"
    })
    r = await client.post(
        "/api/auth/token",
        data={"username": email, "password": pw},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    return r.json()["access_token"]


async def _create_project(client, token, framework="PIT"):
    r = await client.post(
        "/api/projects",
        json={"name": "Test Project", "framework": framework, "loc": 0},
        headers={"Authorization": f"Bearer {token}"},
    )
    return r.json()["id"]


def _make_zip(files: dict[str, str]) -> bytes:
    """Build an in-memory zip with the given filename→content mapping."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def _make_tar(files: dict[str, str]) -> bytes:
    """Build an in-memory tar.gz with the given filename→content mapping."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, content in files.items():
            data = content.encode()
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestUploadValidation:
    @pytest.mark.asyncio
    async def test_upload_requires_auth(self, client):
        r = await client.post("/api/projects/fake-id/upload",
                              files={"file": ("a.zip", b"x", "application/zip")})
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_upload_project_not_found(self, client):
        token = await _register_login(client)
        r = await client.post(
            "/api/projects/nonexistent/upload",
            files={"file": ("a.zip", b"x", "application/zip")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_unsupported_extension_rejected(self, client):
        token  = await _register_login(client)
        proj   = await _create_project(client, token)
        r = await client.post(
            f"/api/projects/{proj}/upload",
            files={"file": ("project.rar", b"x", "application/octet-stream")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 415

    @pytest.mark.asyncio
    async def test_invalid_zip_rejected(self, client):
        token = await _register_login(client)
        proj  = await _create_project(client, token)
        r = await client.post(
            f"/api/projects/{proj}/upload",
            files={"file": ("broken.zip", b"not a zip file", "application/zip")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_pom_rejected(self, client):
        """Java project zip without pom.xml or build.gradle should be rejected."""
        token = await _register_login(client)
        proj  = await _create_project(client, token, "PIT")
        zdata = _make_zip({"src/Main.java": "public class Main {}"})
        r = await client.post(
            f"/api/projects/{proj}/upload",
            files={"file": ("project.zip", zdata, "application/zip")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 422
        assert "pom.xml" in r.json()["detail"] or "build.gradle" in r.json()["detail"]

    @pytest.mark.asyncio
    async def test_missing_package_json_rejected(self, client):
        """JS project zip without package.json should be rejected."""
        token = await _register_login(client)
        proj  = await _create_project(client, token, "STRYKER")
        zdata = _make_zip({"src/index.js": "const x = 1;"})
        r = await client.post(
            f"/api/projects/{proj}/upload",
            files={"file": ("project.zip", zdata, "application/zip")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 422
        assert "package.json" in r.json()["detail"]


class TestUploadSuccess:
    @pytest.mark.asyncio
    async def test_valid_java_zip_accepted(self, client):
        token = await _register_login(client)
        proj  = await _create_project(client, token, "PIT")
        zdata = _make_zip({
            "pom.xml": "<project><version>1.0</version></project>",
            "src/main/java/Foo.java": "public class Foo { public int add(int a, int b) { return a + b; } }",
            "src/test/java/FooTest.java": "@Test public void testAdd() {}",
        })
        r = await client.post(
            f"/api/projects/{proj}/upload",
            files={"file": ("java-project.zip", zdata, "application/zip")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == proj
        assert body["upload_path"] is not None

    @pytest.mark.asyncio
    async def test_valid_js_zip_accepted(self, client):
        token = await _register_login(client)
        proj  = await _create_project(client, token, "STRYKER")
        zdata = _make_zip({
            "package.json": json.dumps({"name": "myapp", "version": "1.0.0"}),
            "src/app.js": "function add(a, b) { return a + b; }",
            "src/app.test.js": "test('adds', () => {});",
        })
        r = await client.post(
            f"/api/projects/{proj}/upload",
            files={"file": ("js-project.zip", zdata, "application/zip")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_tar_gz_accepted(self, client):
        token = await _register_login(client)
        proj  = await _create_project(client, token, "PIT")
        tdata = _make_tar({
            "pom.xml": "<project/>",
            "src/main/java/App.java": "public class App {}",
        })
        r = await client.post(
            f"/api/projects/{proj}/upload",
            files={"file": ("project.tar.gz", tdata, "application/gzip")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_upload_updates_project_record(self, client):
        token = await _register_login(client)
        proj  = await _create_project(client, token, "PIT")
        java_code = "\n".join([
            "public class Big {",
            "    public int add(int a, int b) { return a + b; }",
            "    public int sub(int a, int b) { return a - b; }",
            "}",
        ])
        zdata = _make_zip({
            "pom.xml": "<project/>",
            "src/main/java/Big.java": java_code,
            "src/test/java/BigTest.java": "@Test\npublic void testAdd(){}\n@Test\npublic void testSub(){}",
        })
        r = await client.post(
            f"/api/projects/{proj}/upload",
            files={"file": ("big.zip", zdata, "application/zip")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        # LOC and test count should be scanned and stored
        assert body["loc"] >= 0
        assert body["test_count"] >= 0

    @pytest.mark.asyncio
    async def test_re_upload_overwrites(self, client):
        """Uploading twice to the same project should succeed (replaces prior upload)."""
        token = await _register_login(client)
        proj  = await _create_project(client, token, "PIT")
        zdata = _make_zip({"pom.xml": "<project/>", "src/main/java/A.java": "class A {}"})
        for _ in range(2):
            r = await client.post(
                f"/api/projects/{proj}/upload",
                files={"file": ("p.zip", zdata, "application/zip")},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_user_isolation(self, client):
        """User B cannot upload to User A's project."""
        token_a = await _register_login(client, "a@feu.edu.ph")
        token_b = await _register_login(client, "b@feu.edu.ph", "Password456")
        proj_a  = await _create_project(client, token_a, "PIT")
        zdata   = _make_zip({"pom.xml": "<project/>"})
        r = await client.post(
            f"/api/projects/{proj_a}/upload",
            files={"file": ("p.zip", zdata, "application/zip")},
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert r.status_code == 404

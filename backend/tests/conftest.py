import os
import sys
import tempfile
from pathlib import Path

# Environnement isolé AVANT l'import de l'application (settings lus à l'import).
_tmp = tempfile.mkdtemp(prefix="wathiqa-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmp) / 'test.sqlite'}"
os.environ["RAG_MODE"] = "local"
os.environ["REDIS_URL"] = ""
os.environ["ADMIN_BOOTSTRAP_EMAIL"] = "admin@test.ma"
os.environ["ADMIN_BOOTSTRAP_PASSWORD"] = "S3cret-test!"
os.environ["JWT_SECRET"] = "test-secret-with-at-least-32-bytes-long"
for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ELEVENLABS_API_KEY"):
    os.environ.pop(key, None)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    from app.middleware.security import rate_limiter

    rate_limiter.reset()
    yield


@pytest.fixture(scope="session")
def admin_headers(client):
    r = client.post("/api/admin/auth/login", json={"email": "admin@test.ma", "password": "S3cret-test!"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}

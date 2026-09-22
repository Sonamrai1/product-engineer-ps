import httpx
import pytest
import pytest_asyncio

from app import config, db
from app.main import app


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(config, "BASE_DELAY", 0.05)
    monkeypatch.setattr(config, "WEBHOOK_URL", "http://example.invalid/receive")
    db.init_db()
    yield


@pytest_asyncio.fixture
async def async_client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def make_response(status_code: int) -> httpx.Response:
    return httpx.Response(status_code, request=httpx.Request("POST", "http://example.invalid/receive"))

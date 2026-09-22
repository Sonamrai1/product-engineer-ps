import pytest
from starlette.testclient import TestClient

from app import config, db
from app.hub import hub
from app.main import app


@pytest.fixture(autouse=True)
def fresh_state(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
    hub._subscribers.clear()
    yield
    hub._subscribers.clear()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

from unittest.mock import AsyncMock

import pytest

from app import config, db, delivery
from .conftest import make_response


async def test_success():
    db.insert_event("evt-success", "order.created", "2026-01-01T00:00:00Z", {"foo": "bar"})

    mock_client = AsyncMock()
    mock_client.post.return_value = make_response(200)

    await delivery.deliver_event("evt-success", client=mock_client)

    event = db.get_event("evt-success")
    assert event["state"] == "SUCCESS"

    attempts = db.get_attempts("evt-success")
    assert len(attempts) == 1
    assert attempts[0]["outcome"] == "success"
    assert attempts[0]["status_code"] == 200
    mock_client.post.assert_awaited_once()


async def test_retry_then_success(monkeypatch):
    db.insert_event("evt-retry", "order.created", "2026-01-01T00:00:00Z", {"foo": "bar"})

    mock_client = AsyncMock()
    mock_client.post.side_effect = [make_response(503), make_response(200)]
    monkeypatch.setattr(delivery.asyncio, "sleep", AsyncMock())

    await delivery.deliver_event("evt-retry", client=mock_client)

    event = db.get_event("evt-retry")
    assert event["state"] == "SUCCESS"

    attempts = db.get_attempts("evt-retry")
    assert len(attempts) == 2
    assert attempts[0]["outcome"] == "retry"
    assert attempts[0]["status_code"] == 503
    assert attempts[1]["outcome"] == "success"
    assert mock_client.post.await_count == 2


async def test_exhaustion(monkeypatch):
    monkeypatch.setattr(config, "MAX_ATTEMPTS", 3)
    db.insert_event("evt-exhausted", "order.created", "2026-01-01T00:00:00Z", {"foo": "bar"})

    mock_client = AsyncMock()
    mock_client.post.return_value = make_response(500)
    monkeypatch.setattr(delivery.asyncio, "sleep", AsyncMock())

    await delivery.deliver_event("evt-exhausted", client=mock_client)

    event = db.get_event("evt-exhausted")
    assert event["state"] == "FAILED"

    attempts = db.get_attempts("evt-exhausted")
    assert len(attempts) == 3
    assert [a["outcome"] for a in attempts] == ["retry", "retry", "failed"]
    assert mock_client.post.await_count == 3


async def test_permanent_4xx_fails_without_retrying(monkeypatch):
    db.insert_event("evt-bad-request", "order.created", "2026-01-01T00:00:00Z", {"foo": "bar"})

    mock_client = AsyncMock()
    mock_client.post.return_value = make_response(400)
    sleep_mock = AsyncMock()
    monkeypatch.setattr(delivery.asyncio, "sleep", sleep_mock)

    await delivery.deliver_event("evt-bad-request", client=mock_client)

    event = db.get_event("evt-bad-request")
    assert event["state"] == "FAILED"

    attempts = db.get_attempts("evt-bad-request")
    assert len(attempts) == 1
    assert attempts[0]["outcome"] == "failed"
    sleep_mock.assert_not_awaited()


@pytest.mark.parametrize(
    ("status_code", "exc", "expected"),
    [
        (200, None, False),
        (404, None, False),
        (400, None, False),
        (429, None, True),
        (500, None, True),
        (503, None, True),
        (None, TimeoutError("timed out"), True),
    ],
)
def test_is_retryable(status_code, exc, expected):
    assert delivery.is_retryable(status_code, exc) is expected

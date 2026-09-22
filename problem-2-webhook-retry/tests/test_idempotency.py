import asyncio
from unittest.mock import AsyncMock

import pytest

from app import main


@pytest.fixture(autouse=True)
def no_real_delivery(monkeypatch):
    # These tests are about dedupe at the /events layer, not delivery - stub
    # the background worker out so we're not making real HTTP calls or
    # waiting on retry backoff while asserting on the create response.
    monkeypatch.setattr(main.delivery, "deliver_event", AsyncMock(return_value=None))


def sample_event(event_id: str) -> dict:
    return {
        "eventId": event_id,
        "type": "order.created",
        "occurredAt": "2026-01-01T00:00:00Z",
        "payload": {"orderId": "abc123"},
    }


async def test_idempotent_sequential(async_client):
    body = sample_event("evt-seq-1")

    first = await async_client.post("/events", json=body)
    second = await async_client.post("/events", json=body)

    assert first.json()["idempotent"] is False
    assert second.json()["idempotent"] is True

    listing = await async_client.get(f"/events/{body['eventId']}")
    assert listing.status_code == 200
    # only one delivery job should ever have been scheduled for this id
    main.delivery.deliver_event.assert_awaited_once()


async def test_idempotent_concurrent(async_client):
    body = sample_event("evt-concurrent-1")

    responses = await asyncio.gather(*[async_client.post("/events", json=body) for _ in range(20)])
    flags = [r.json()["idempotent"] for r in responses]

    # exactly one of the 20 racing requests should be the "real" create
    assert flags.count(False) == 1
    assert flags.count(True) == 19

    # and the delivery worker only ever got scheduled once for this event
    main.delivery.deliver_event.assert_awaited_once()

    listing = await async_client.get(f"/events/{body['eventId']}")
    assert listing.status_code == 200

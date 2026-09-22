import asyncio
import json
import random
import time

import httpx

from . import config, db


def is_retryable(status_code: int | None, exc: Exception | None) -> bool:
    """A network error or timeout is always worth retrying - we don't know if
    the request even reached the receiver. Past that, only 429 and 5xx get a
    retry; any other 4xx means the receiver understood us and rejected the
    request, so sending it again won't help.
    """
    if exc is not None:
        return True
    if status_code == 429:
        return True
    if status_code is not None and status_code >= 500:
        return True
    return False


def backoff_delay(attempt_no: int) -> float:
    delay = config.BASE_DELAY * (2 ** (attempt_no - 1))
    jitter = random.uniform(0, config.BASE_DELAY)
    return delay + jitter


async def deliver_event(event_id: str, client: httpx.AsyncClient | None = None) -> None:
    """Drives one event through delivery to a terminal state (SUCCESS/FAILED),
    retrying on the way per is_retryable(), up to config.MAX_ATTEMPTS.

    `client` is injectable so tests can hand in a mock instead of hitting a
    real network - production code just leaves it out and gets a real one.
    """
    event = await asyncio.to_thread(db.get_event, event_id)
    if event is None:
        return

    await asyncio.to_thread(db.update_event_state, event_id, "DELIVERING")
    payload = json.loads(event["payload"])
    body = {
        "eventId": event["event_id"],
        "type": event["type"],
        "occurredAt": event["occurred_at"],
        "payload": payload,
    }

    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient(timeout=5.0)

    try:
        for attempt_no in range(1, config.MAX_ATTEMPTS + 1):
            status_code = None
            error = None
            exc = None
            start = time.monotonic()

            try:
                response = await client.post(config.WEBHOOK_URL, json=body)
                status_code = response.status_code
            except Exception as e:  # noqa: BLE001 - genuinely want any transport error here
                exc = e
                error = str(e)

            duration_ms = (time.monotonic() - start) * 1000

            if exc is None and status_code is not None and 200 <= status_code < 300:
                await asyncio.to_thread(
                    db.insert_attempt, event_id, attempt_no, status_code, error, "success", duration_ms
                )
                await asyncio.to_thread(db.update_event_state, event_id, "SUCCESS")
                return

            attempts_remaining = attempt_no < config.MAX_ATTEMPTS

            if is_retryable(status_code, exc) and attempts_remaining:
                await asyncio.to_thread(
                    db.insert_attempt, event_id, attempt_no, status_code, error, "retry", duration_ms
                )
                await asyncio.sleep(backoff_delay(attempt_no))
                continue

            # Either a permanent 4xx, or we're out of attempts - either way this
            # event is done.
            await asyncio.to_thread(
                db.insert_attempt, event_id, attempt_no, status_code, error, "failed", duration_ms
            )
            await asyncio.to_thread(db.update_event_state, event_id, "FAILED")
            return
    finally:
        if owns_client:
            await client.aclose()

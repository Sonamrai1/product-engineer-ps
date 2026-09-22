# Webhook Retry Engine

FastAPI + SQLite + httpx. Accepts events, delivers each one to `WEBHOOK_URL`
with retries and exponential backoff, and tracks every attempt.

## Prerequisites

- Python 3.10+ (tested on 3.12.3)
- No external services - SQLite file, no broker

## Demo video

[Add the demo video link here before submitting - see the root
`DEMO_SCRIPT.md` for the walkthrough this was recorded from.]

## Setup

```
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Running it

Terminal 1 - a flaky receiver to retry against (fails twice per event, then succeeds):
```
FAIL_COUNT=2 uvicorn test_receiver:app --port 9000
```

Terminal 2 - the retry engine itself:
```
WEBHOOK_URL=http://localhost:9000/receive uvicorn app.main:app --port 8000
```

Then:
```
curl -X POST localhost:8000/events -H 'content-type: application/json' -d '{
  "eventId": "evt-001",
  "type": "order.created",
  "occurredAt": "2026-01-01T00:00:00Z",
  "payload": {"orderId": "abc123"}
}'

curl localhost:8000/events/evt-001
```

Send the same body again and you'll get `"idempotent": true` back with no
new delivery job. Check `localhost:9000/_seen` to see the receiver's own
attempt count per event.

## Demo - how to trigger each acceptance criterion

1. **Idempotent POST.** Run the `curl -X POST .../events` command above
   twice with the exact same body. First response: `"idempotent": false`.
   Second: `"idempotent": true` - no second delivery job was queued.
2. **Retry with exponential backoff on transient failure.** With the
   receiver running as `FAIL_COUNT=2`, POST a new event and wait ~1s, then
   `curl localhost:8000/events/{eventId}`. The `attempts` array shows two
   `500` responses (`outcome: "retry"`) followed by a `200`
   (`outcome: "success"`).
3. **Exhaustion after `MAX_ATTEMPTS`.** Restart the receiver with
   `FAIL_COUNT=10` (always fails), POST a new event, wait a couple
   seconds, then GET it - `state` is `FAILED` and `attempts` has exactly
   6 entries (`MAX_ATTEMPTS`), the last one `outcome: "failed"`.
4. **Permanent 4xx never retried.** The demo receiver only ever returns
   500 or 200, so this one isn't practical to click through by hand -
   it's exercised directly by
   `tests/test_delivery.py::test_permanent_4xx_fails_without_retrying`,
   which mocks a 400 response and asserts exactly one attempt is made.

## Tests

```
pytest
```

Covers: successful delivery, retry-then-success, exhaustion after
`MAX_ATTEMPTS`, permanent 4xx failing without a retry, the `is_retryable`
matrix, and idempotency under both sequential and concurrent duplicate
POSTs. No real sleeps - backoff delays are mocked out.

## API

**POST /events**
```json
{ "eventId": "evt-001", "type": "order.created", "occurredAt": "...", "payload": {} }
```
Returns `{ eventId, state, idempotent }`. A repeat `eventId` returns the
existing event's current state with `idempotent: true` and does not queue a
second delivery.

**GET /events/{eventId}**
```json
{ "eventId": "...", "type": "...", "occurredAt": "...", "state": "SUCCESS", "attempts": [ ... ] }
```
`attempts` is ordered oldest-first, each with `attempt_no`, `status_code`,
`error`, `outcome` (`success` / `retry` / `failed`), and `duration_ms`.

## Config (env vars)

| Var | Default | Notes |
|---|---|---|
| `WEBHOOK_URL` | `http://localhost:9000/receive` | where events get delivered |
| `MAX_ATTEMPTS` | `6` | total attempts before giving up |
| `BASE_DELAY` | `1` | seconds; delay = `BASE_DELAY * 2^(n-1) + jitter` |
| `DB_PATH` | `webhook.db` | SQLite file |

See `SUBMISSION.md` for the design write-up.


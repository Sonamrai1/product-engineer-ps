# Product Engineering Challenge Submission

## Candidate

- **Name:** [TODO]
- **Email:** [TODO]
- **GitHub:** [TODO]
- **Selected problem:** Problem 2 - Webhook Retry Engine
- **Demo video:** [Add the demo video link here before submitting]

## Run the project

Prerequisites: Python 3.10+.

```
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
FAIL_COUNT=2 uvicorn test_receiver:app --port 9000                          # terminal 1
WEBHOOK_URL=http://localhost:9000/receive uvicorn app.main:app --port 8000  # terminal 2
```

To trigger the successful scenario: POST an event to `localhost:8000/events`,
then GET it - `state` becomes `SUCCESS` after the flaky receiver's two
failures and one success.

To trigger the failure/recovery scenario: same POST/GET - the `attempts`
array shows two `500` (`outcome: "retry"`) attempts before the successful
one. Restarting the receiver with `FAIL_COUNT=10` and posting a new event
demonstrates exhaustion: `state` becomes `FAILED` after exactly
`MAX_ATTEMPTS` (6) attempts.

## Run the tests

```
pytest -v
```

13 tests: successful delivery, retry-then-success, exhaustion after
`MAX_ATTEMPTS`, permanent 4xx failing without a retry, the `is_retryable`
matrix, and idempotency under sequential and concurrent duplicate POSTs. No
real sleeps.

## Architecture and data flow

```
POST /events -> db.insert_event() [UNIQUE(event_id) enforces dedupe]
             -> asyncio.create_task(deliver_event()) [fire-and-forget]
                  -> loop: POST to WEBHOOK_URL, record attempt, classify outcome
                  -> retryable + attempts left -> sleep(backoff) -> retry
                  -> success or exhausted/permanent -> terminal state
GET /events/{id} -> event row + ordered attempts
```

- `app/db.py` - `events` and `attempts` tables. `insert_event` relies on the
  `event_id` UNIQUE constraint, not check-then-insert, so it's safe under
  concurrent identical requests.
- `app/delivery.py` - `is_retryable()` and `deliver_event()`, the retry loop
  with exponential backoff.
- `app/main.py` - the two HTTP endpoints.
- `test_receiver.py` - standalone flaky receiver for manual/demo use.

## Technology choices

FastAPI + `httpx.AsyncClient` over a sync framework: the delivery loop is
naturally I/O-bound (waiting on HTTP responses and backoff sleeps), and
async lets a single process handle many in-flight deliveries without a
thread per event. SQLite over Postgres/a real broker: the assignment is
scoped to "a distributed production system is not expected," and SQLite's
own `AUTOINCREMENT`-style UNIQUE constraint gives the idempotency guarantee
without extra infrastructure - explicitly called out as the first thing to
change at real scale, below.

## Important decisions

- **Retryable classification:** retry on 5xx, 429, and network/timeout
  errors; never retry other 4xx, since those mean the receiver understood
  the request and rejected it - resending won't help.
- **Retry limit and backoff:** `MAX_ATTEMPTS = 6`, delay =
  `BASE_DELAY * 2^(n-1) + jitter` (`BASE_DELAY` overridable via env, set to
  `0.05` in tests so the full backoff ladder runs in milliseconds).
- **Delivery guarantee: at-least-once, not exactly-once.** A response can be
  lost independently of the request it answered, so the sender can never be
  certain "no confirmation" means "didn't happen" vs. "happened, I just
  didn't hear about it." Retrying is the only option that doesn't risk
  silently losing work - which means the *receiver* must dedupe on
  `eventId`, not the sender.
- **Concurrent duplicate submissions:** handled by the `event_id` UNIQUE
  constraint directly on the INSERT (not a check-then-insert race) - two
  simultaneous POSTs with the same id, exactly one succeeds, the other gets
  `IntegrityError` and is treated as the idempotent case. Tested directly
  with 20 concurrent requests (`test_idempotent_concurrent`).
- **What's retained per attempt:** `attempt_no`, timestamp, `status_code`,
  `error`, `outcome` (`success`/`retry`/`failed`), and `duration_ms` - enough
  to answer "what happened and how long did it take" without replaying logs.

## Assumptions and limitations

- Single WEBHOOK_URL, single process - no multi-tenant routing or multiple
  subscriber endpoints (explicitly out of scope).
- No request signing or endpoint health checks - both called out as
  optional in the brief and left out to keep the required delivery
  behavior the focus.
- Delivery runs as an in-process `asyncio.create_task` - fine for one
  process, not for multiple workers (see below).

## Production and scale

- **What could still cause a receiver to observe a duplicate delivery?**
  Any time our request reaches the receiver but the response back to us is
  lost (timeout, connection reset) - we retry believing it failed, the
  receiver sees the same `eventId` twice. This is inherent to at-least-once
  delivery, not a bug; it's why the receiver dedupes on `eventId` too.
- **Operating with many workers:** the current design is single-process.
  Moving to Postgres and adding `SELECT ... FOR UPDATE SKIP LOCKED` lets
  multiple worker processes each claim a distinct PENDING event without
  double-processing it - SQLite can't do row-level locking, so this needs
  the database swap first.
- **Preventing one failing endpoint from consuming all capacity:** a
  circuit breaker keyed by destination - after N consecutive failures,
  stop attempting new deliveries to that destination for a cooldown window
  instead of burning worker time on doomed retries against a target that's
  down.
- **Metrics and alerts:** delivery success rate and current `FAILED` count
  by destination, attempts-to-success distribution (a creeping average
  toward `MAX_ATTEMPTS` is an early warning), time from `PENDING` to
  terminal state, and receiver-observed duplicate rate if exposed.

## AI usage

Used Claude for scaffolding and tests, manually reviewed logic.

## Credibility note

[TODO]

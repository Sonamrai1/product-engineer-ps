# Submission — Reconnecting Real-Time Feed

## Candidate

- **Name:** [TODO]
- **Email:** [TODO]
- **GitHub:** [TODO]
- **Selected problem:** Problem 3 - Reconnecting Real-Time Feed
- **Demo video:** [Add the demo video link here before submitting]

## Run the project

```
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Open `http://localhost:8000/` - two independent demo clients sit side by
side, both against the same room by default. See the README's "Demo - how
to trigger each acceptance criterion" section for exact click-by-click
steps for AC1-AC4.

## Run the tests

```
pytest -v
```

4 tests, no `sleep()` anywhere:
- `test_live_broadcast` - a connected client receives a freshly published update.
- `test_replay_after_cursor` - connecting with a non-zero `last_seq` only
  replays what's newer than that cursor.
- `test_replay_then_live_continues_in_order` - backlog and live delivery
  hand off to each other without a gap.
- `test_dedupe_overlapping_publish_during_subscribe_window` - deliberately
  forces an update into the race window between subscribing and finishing
  the backlog read, and checks it still only arrives once.

## Architecture and data flow

- FastAPI app with two entry points: `POST /rooms/{room_id}/updates`
  (publish) and `WS /ws/{room_id}?last_seq=` (subscribe + replay).
- SQLite (`updates` table) is the durable log of every update, keyed by a
  global `AUTOINCREMENT` `seq`.
- An in-memory `RoomHub` (`app/hub.py`) does pub/sub: one `asyncio.Queue`
  per connected socket, grouped by `room_id`.
- `stream_updates()` (`app/stream.py`) merges DB backlog + live queue into
  one gap-free, duplicate-free generator per connection.
- `static/index.html` is a self-contained two-client demo with its own
  reconnect state machine (vanilla JS, no framework).

```
POST /rooms/{id}/updates -> db.insert_update() -> hub.publish() -> per-connection asyncio.Queue
                                                                          |
WS /ws/{id}?last_seq=N -> stream_updates() -> [DB backlog seq>N] + [live queue] -> websocket.send_json()
```

## Technology choices

- **WebSocket over SSE/polling**: bidirectional-feeling low latency, one
  persistent connection, and a clean `onclose` signal the client's
  reconnect state machine depends on.
- **SQLite over a message broker**: the assignment's scope didn't call for
  horizontal scale, and SQLite's own `AUTOINCREMENT` rowid gives an atomic,
  monotonic `seq` for free - no separate counter to keep in sync.
- **In-memory `asyncio.Queue` per connection over a broker-backed pub/sub**:
  single-process is enough for the stated scope; explicitly documented
  below as the thing to swap out for multi-instance deployment.
- **No frontend framework for the demo page**: two clients and one state
  machine each didn't need React/Vue overhead, and a single
  dependency-free HTML file is easier for a reviewer to open and read
  top to bottom.

## Important decisions

- **Subscribe before reading backlog.** `stream_updates()` calls
  `hub.subscribe()` before querying the DB for backlog, specifically so
  nothing published after connection start can be missed. The tradeoff is
  a possible duplicate in the narrow race window between subscribing and
  finishing the backlog read - handled next.
- **`sent_seq` tracking to dedupe the replay/live overlap.** Anything
  arriving via the live queue with `seq <= sent_seq` (already covered by
  backlog) is dropped before it reaches the client. Tested directly by
  `test_dedupe_overlapping_publish_during_subscribe_window`, which forces
  an update into that exact window on demand.
- **Client-side `Set` dedupe on `id` as a second line of defense** -
  because a disconnect/reconnect is a fresh subscription with no memory of
  the previous connection's state, the server can only guarantee no
  repeats *within* one connection, not *across* connections.
- **Bounded reconnect**: exponential backoff (500ms, doubling, capped at
  10s) with jitter, and a hard cap of 8 attempts before the client stops
  retrying on its own and waits for a manual click. An unbounded retry
  loop against a genuinely dead server is just quiet, pointless load.
- **Global `seq` rather than per-room.** Using SQLite's own rowid means the
  sequence spans all rooms, not reset per room. That's fine because the
  only guarantee a client needs is "within my room, later updates have
  bigger numbers" - a subsequence of a total order still satisfies that,
  and computing a safe per-room counter would need its own locking for no
  real benefit.

## Assumptions and limitations

- `content` is a plain string, not structured JSON - the spec's own
  example read as a message-like update, so the schema wasn't built out
  for a shape that wasn't asked for.
- One process, one machine is acceptable scope for this deliverable.
  Multi-instance broadcast is a known limitation, called out explicitly
  below rather than silently ignored.
- No authentication/authorization on rooms - anyone who knows a `room_id`
  can read and post to it. Reasonable for a take-home; not something to
  ship as-is.
- Reviewers run this locally (`uvicorn` + a browser on the same machine)
  rather than needing TLS - the demo page hardcodes `ws://`, not `wss://`.
- "Server-assigned seq" was read as "assigned at write time, strictly
  increasing" rather than "gapless per room." SQLite's rowid satisfies the
  former; the spec's own phrasing ("monotonic int for ordering") matches
  that reading.
- `get_updates_since` loads the entire backlog into memory in one query -
  fine for a demo, not for a room with a very long history (see below).

## Production and scale

- **What happens if a client disconnects immediately after sending an
  update?** The update was already POSTed and committed to SQLite before
  the connection dropped - publish and subscribe are fully decoupled, so a
  POST doesn't depend on that client's own WebSocket being open. Other
  connected clients still receive it live, and the disconnected client (or
  any client) sees it on reconnect via replay, since it's already durable.
  There's nothing special to handle here precisely because of that
  decoupling.
- **How would multiple backend instances share and order events?** The
  biggest real gap in the current design. `RoomHub` only knows about
  connections on its own process, so a client on instance A never sees a
  publish that hit instance B. Fix: back the hub with Redis pub/sub (or
  NATS) - `publish()` becomes "publish to Redis channel `room:{id}`," and
  every instance also subscribes to that channel and fans out to its own
  local WebSocket connections. Ordering would also need to move off
  SQLite's local `AUTOINCREMENT` to a shared sequence (Postgres, single
  writer, same trick as now) since two instances can't both hand out
  rowids from separate local files.
- **How would you prevent an unbounded history replay?** Right now
  `get_updates_since` loads the entire matching backlog in one query and
  sends it in one pass - a client connecting with a very old or zero
  `last_seq` on a long-lived room could pull an unbounded amount of
  history. Fix: page the backlog query (batches of, say, 500 by `seq`) and
  send in chunks instead of one `fetchall()`, and/or cap how far back a
  cold reconnect is allowed to replay before falling back to "here's the
  latest N, you've missed too much to replay individually."
- **What would you monitor in production?** Per-room active connection
  count and publish rate; the rate at which the live-queue dedupe filter
  actually fires (`update["seq"] <= sent_seq`) - near-zero means the race
  window is rarely hit in practice, a high rate would mean something's off
  with connection timing; and reconnect frequency per client, since one
  client cycling through `RECONNECTING` far more than others usually
  points at a specific network path or client bug rather than the server.
- **SQLite to Postgres** is also the natural move alongside the
  multi-instance change above - SQLite's single-writer model is fine at
  demo scale but becomes the bottleneck under real write concurrency, and
  Postgres unlocks `LISTEN/NOTIFY` as an alternative to a separate broker.
- **Auth** before this goes anywhere near production - currently anyone
  with a room id has full read/write access to it.

## AI usage

Used Claude for scaffolding and tests, manually reviewed logic.

## Credibility note

[TODO]

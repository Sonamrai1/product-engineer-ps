# Realtime Feed

FastAPI + WebSocket + SQLite. Rooms of updates, ordered by a server-assigned
sequence number, with reconnect-and-resume via `last_seq`.

## Prerequisites

- Python 3.10+ (uses `X | None` union syntax and builtin generics like
  `dict[str, Any]`; tested on 3.12.3)
- No other services needed - SQLite file, no external DB or broker

## Demo video

[Add the demo video link here before submitting - see the root
`DEMO_SCRIPT.md` for the walkthrough this was recorded from.]

## Setup

```
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Running it

```
uvicorn app.main:app --reload --port 8000
```

Open `http://localhost:8000/` - two independent demo clients sit side by
side, both against the same room by default. Publish something and both
receive it live. Try "Simulate drop" on one client - it goes
`RECONNECTING` with visible backoff, then catches back up from wherever it
left off without missing or duplicating anything.

## Demo - how to trigger each acceptance criterion

1. **AC1 - Live broadcast, server-ordered.** With both client panels open
   and `CONNECTED`, publish a message from the form. Both panels receive it
   immediately, each showing the same `#seq` number.
2. **AC2 - Drop and reconnect with visible backoff.** Click **Simulate
   drop** on one panel. Its status pill goes `RECONNECTING` immediately,
   with a countdown in the log that doubles each attempt (500ms, 1s, 2s,
   ... capped at 10s). After 8 failed attempts it settles on
   `DISCONNECTED` and waits for a manual **Connect** click instead of
   retrying forever.
3. **AC3 - Replay via `last_seq` after reconnecting.** While the panel
   from step 2 is down, publish another message from the form - only the
   still-connected panel gets it live. When the dropped panel reconnects,
   it replays exactly the message(s) it missed (via `?last_seq=`), in
   order, with no gap.
4. **AC4 - Client-side dedupe on overlap.** Click **Reset cursor** on a
   connected panel (forces `last_seq` back to 0, so the server replays the
   room's full history). Anything already shown once is logged as "dup
   ignored" instead of appearing twice - the `id`-keyed `Set` is doing the
   filtering.

## API

**POST /rooms/{room_id}/updates**
```json
{ "content": "something happened" }
```
Returns the stored update: `{ id, room_id, content, seq, created_at }`.

**WS /ws/{room_id}?last_seq=0**
On connect, immediately streams every update in the room with
`seq > last_seq` (in order), then keeps streaming new ones as they're
published. Never closes on its own - the client decides when to leave.

## Tests

```
pytest
```

- `test_live_broadcast` - a connected client receives a freshly published update.
- `test_replay_after_cursor` - connecting with a non-zero `last_seq` only
  replays what's newer than that cursor.
- `test_replay_then_live_continues_in_order` - backlog and live delivery
  hand off to each other without a gap.
- `test_dedupe_overlapping_publish_during_subscribe_window` - deliberately
  forces an update into the race window between subscribing and finishing
  the backlog read, and checks it still only arrives once.

See `SUBMISSION.md` for the reasoning behind the choices here.


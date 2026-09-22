import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable

from . import db
from .hub import hub


async def stream_updates(
    room_id: str,
    last_seq: int,
    _on_subscribed: Callable[[], Awaitable[None]] | None = None,
) -> AsyncGenerator[dict, None]:
    """Yields every update for room_id with seq > last_seq exactly once, in
    order - backlog from the DB first, then whatever gets published live.

    Subscribing to the live queue *before* reading the backlog is what makes
    this gap-free: nothing published after this call starts can be missed.
    The cost is that something published in the narrow window between
    subscribing and finishing the backlog read can land in both places -
    `sent_seq` is how that repeat gets caught and dropped before it reaches
    the caller.

    `_on_subscribed` only exists for tests - it's a hook to force something
    into that exact race window on demand instead of hoping to hit it by
    timing.
    """
    queue = hub.subscribe(room_id)
    try:
        if _on_subscribed is not None:
            await _on_subscribed()

        sent_seq = last_seq
        backlog = await asyncio.to_thread(db.get_updates_since, room_id, last_seq)
        for update in backlog:
            sent_seq = update["seq"]
            yield update

        while True:
            update = await queue.get()
            if update["seq"] <= sent_seq:
                continue  # already delivered via backlog - race-window repeat
            sent_seq = update["seq"]
            yield update
    finally:
        hub.unsubscribe(room_id, queue)

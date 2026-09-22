import asyncio
from collections import defaultdict


class RoomHub:
    """Tracks one asyncio.Queue per connected websocket, grouped by room.
    Publishing an update fans it out to every queue subscribed to that room.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)

    def subscribe(self, room_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers[room_id].add(queue)
        return queue

    def unsubscribe(self, room_id: str, queue: asyncio.Queue) -> None:
        subs = self._subscribers.get(room_id)
        if not subs:
            return
        subs.discard(queue)
        if not subs:
            del self._subscribers[room_id]

    async def publish(self, room_id: str, update: dict) -> None:
        for queue in list(self._subscribers.get(room_id, ())):
            await queue.put(update)


hub = RoomHub()

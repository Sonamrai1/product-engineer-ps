import asyncio

from app import db
from app.hub import hub
from app.stream import stream_updates


def test_live_broadcast(client):
    with client.websocket_connect("/ws/room-a?last_seq=0") as ws:
        resp = client.post("/rooms/room-a/updates", json={"content": "hello"})
        assert resp.status_code == 200
        assert resp.json()["content"] == "hello"

        received = ws.receive_json()
        assert received["content"] == "hello"
        assert received["room_id"] == "room-a"
        assert received["seq"] == resp.json()["seq"]


def test_replay_after_cursor(client):
    published = [client.post("/rooms/room-b/updates", json={"content": f"msg-{i}"}).json() for i in range(3)]
    cursor = published[0]["seq"]  # pretend we already saw msg-0

    with client.websocket_connect(f"/ws/room-b?last_seq={cursor}") as ws:
        first = ws.receive_json()
        second = ws.receive_json()

    assert first["content"] == "msg-1"
    assert second["content"] == "msg-2"
    assert first["seq"] < second["seq"]


def test_replay_then_live_continues_in_order(client):
    client.post("/rooms/room-c/updates", json={"content": "before"})

    with client.websocket_connect("/ws/room-c?last_seq=0") as ws:
        backlog_item = ws.receive_json()
        assert backlog_item["content"] == "before"

        client.post("/rooms/room-c/updates", json={"content": "after"})
        live_item = ws.receive_json()
        assert live_item["content"] == "after"
        assert live_item["seq"] > backlog_item["seq"]


async def test_dedupe_overlapping_publish_during_subscribe_window():
    """Forces the exact race stream_updates is designed to survive: an
    update lands after subscribing but before the backlog read finishes,
    so it's visible to both paths. It should still reach the consumer
    exactly once, in order.
    """
    room_id = "race-room"
    db.insert_update(room_id, "before-1")

    async def on_subscribed():
        update = await asyncio.to_thread(db.insert_update, room_id, "race-update")
        await hub.publish(room_id, update)

    received = []
    async for update in stream_updates(room_id, 0, _on_subscribed=on_subscribed):
        received.append(update)
        if len(received) == 2:
            break

    assert [u["content"] for u in received] == ["before-1", "race-update"]
    assert len({u["id"] for u in received}) == 2  # no repeats

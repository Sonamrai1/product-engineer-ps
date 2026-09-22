import asyncio
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from . import db, delivery

app = FastAPI(title="Webhook Retry Engine")
db.init_db()


class EventIn(BaseModel):
    eventId: str
    type: str
    occurredAt: str
    payload: dict[str, Any]


@app.post("/events")
async def create_event(event: EventIn):
    created = await asyncio.to_thread(
        db.insert_event, event.eventId, event.type, event.occurredAt, event.payload
    )

    if created:
        # Fire and forget - the caller gets an immediate ack, delivery
        # happens in the background and its progress is visible via GET.
        asyncio.create_task(delivery.deliver_event(event.eventId))
        return {"eventId": event.eventId, "state": "PENDING", "idempotent": False}

    existing = await asyncio.to_thread(db.get_event, event.eventId)
    return {"eventId": event.eventId, "state": existing["state"], "idempotent": True}


@app.get("/events/{event_id}")
async def get_event(event_id: str):
    event = await asyncio.to_thread(db.get_event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event not found")

    attempts = await asyncio.to_thread(db.get_attempts, event_id)
    return {
        "eventId": event["event_id"],
        "type": event["type"],
        "occurredAt": event["occurred_at"],
        "state": event["state"],
        "attempts": attempts,
    }

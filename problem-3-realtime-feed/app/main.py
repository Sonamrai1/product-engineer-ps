import asyncio

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import db
from .hub import hub
from .stream import stream_updates

app = FastAPI(title="Realtime Feed")
db.init_db()
app.mount("/static", StaticFiles(directory="static"), name="static")


class UpdateIn(BaseModel):
    content: str


@app.get("/")
async def index():
    return FileResponse("static/index.html")


@app.post("/rooms/{room_id}/updates")
async def publish_update(room_id: str, body: UpdateIn):
    update = await asyncio.to_thread(db.insert_update, room_id, body.content)
    await hub.publish(room_id, update)
    return update


@app.websocket("/ws/{room_id}")
async def ws_room(websocket: WebSocket, room_id: str, last_seq: int = 0):
    await websocket.accept()
    try:
        async for update in stream_updates(room_id, last_seq):
            await websocket.send_json(update)
    except WebSocketDisconnect:
        pass

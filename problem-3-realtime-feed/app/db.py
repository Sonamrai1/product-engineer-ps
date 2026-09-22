import sqlite3
import uuid
from datetime import datetime, timezone

from . import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS updates (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT UNIQUE NOT NULL,
    room_id TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_updates_room_seq ON updates(room_id, seq);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db() -> None:
    conn = get_conn()
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
    finally:
        conn.close()


def insert_update(room_id: str, content: str) -> dict:
    """seq comes straight from SQLite's own AUTOINCREMENT rowid - that's
    already atomic and monotonic, so there's no separate counter to get out
    of sync. It's a global sequence rather than per-room, which is fine:
    what matters is that within any one room, later inserts get bigger
    numbers, and rowid guarantees exactly that.
    """
    update_id = str(uuid.uuid4())
    created_at = _now()
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO updates (id, room_id, content, created_at) VALUES (?, ?, ?, ?)",
            (update_id, room_id, content, created_at),
        )
        conn.commit()
        return {
            "id": update_id,
            "room_id": room_id,
            "content": content,
            "seq": cur.lastrowid,
            "created_at": created_at,
        }
    finally:
        conn.close()


def get_updates_since(room_id: str, last_seq: int) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM updates WHERE room_id = ? AND seq > ? ORDER BY seq ASC",
            (room_id, last_seq),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

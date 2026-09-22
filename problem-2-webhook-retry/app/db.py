import sqlite3
import json
from datetime import datetime, timezone

from . import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    payload TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'PENDING',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL REFERENCES events(event_id),
    attempt_no INTEGER NOT NULL,
    at TEXT NOT NULL,
    status_code INTEGER,
    error TEXT,
    outcome TEXT NOT NULL,
    duration_ms REAL,
    UNIQUE(event_id, attempt_no)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_conn() -> sqlite3.Connection:
    # A fresh connection per call rather than one shared handle - SQLite's
    # own file locking (plus the busy timeout) is what makes concurrent
    # writers safe here, not anything we'd add in Python.
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


def insert_event(event_id: str, type_: str, occurred_at: str, payload: dict) -> bool:
    """Returns True if this created a new row, False if event_id already existed.

    The UNIQUE constraint on event_id is what actually enforces this under
    concurrency - two workers racing to insert the same id both run this
    function, exactly one INSERT succeeds, the other hits IntegrityError.
    """
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO events (event_id, type, occurred_at, payload, state, created_at) "
            "VALUES (?, ?, ?, ?, 'PENDING', ?)",
            (event_id, type_, occurred_at, json.dumps(payload), _now()),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def get_event(event_id: str) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_event_state(event_id: str, state: str) -> None:
    conn = get_conn()
    try:
        conn.execute("UPDATE events SET state = ? WHERE event_id = ?", (state, event_id))
        conn.commit()
    finally:
        conn.close()


def insert_attempt(
    event_id: str,
    attempt_no: int,
    status_code: int | None,
    error: str | None,
    outcome: str,
    duration_ms: float,
) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO attempts (event_id, attempt_no, at, status_code, error, outcome, duration_ms) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (event_id, attempt_no, _now(), status_code, error, outcome, duration_ms),
        )
        conn.commit()
    finally:
        conn.close()


def get_attempts(event_id: str) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM attempts WHERE event_id = ? ORDER BY attempt_no ASC", (event_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

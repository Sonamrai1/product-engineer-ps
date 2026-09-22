"""
Stand-in webhook receiver that fails the first FAIL_COUNT deliveries for each
eventId, then succeeds - so you can watch the retry engine actually retry
against something real instead of a mock.

Run:
    FAIL_COUNT=2 uvicorn test_receiver:app --port 9000

Then point the retry engine at it:
    WEBHOOK_URL=http://localhost:9000/receive uvicorn app.main:app --port 8000
"""
import os
from collections import defaultdict

from fastapi import FastAPI, Request, Response

app = FastAPI(title="Flaky test receiver")

FAIL_COUNT = int(os.environ.get("FAIL_COUNT", "2"))
_seen: dict[str, int] = defaultdict(int)


@app.post("/receive")
async def receive(request: Request):
    body = await request.json()
    event_id = body.get("eventId", "unknown")
    _seen[event_id] += 1
    attempt = _seen[event_id]

    if attempt <= FAIL_COUNT:
        return Response(status_code=500, content=f"pretending to break, attempt {attempt}")

    return {"received": True, "eventId": event_id, "attempt": attempt}


@app.get("/_seen")
async def seen():
    """Lets you check attempt counts without digging through logs."""
    return _seen

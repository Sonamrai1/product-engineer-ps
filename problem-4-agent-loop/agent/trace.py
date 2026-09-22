import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# Deliberately pattern-based rather than a fixed list of known keys - a
# secret can show up inside a log message or tool result just as easily as
# a structured field, so this has to scan values, not just field names.
_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{10,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?i)(api[_-]?key|password|secret|token)\s*[=:]\s*\S+"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9\-_.]+"),
]


def redact(value: Any) -> Any:
    """Recursively scrubs anything secret-shaped out of strings, dicts and
    lists. Called from Trace.append() itself so a secret never sits in the
    trace even momentarily - there's no separate "sanitize before display"
    step to forget to call.
    """
    if isinstance(value, str):
        redacted = value
        for pattern in _SECRET_PATTERNS:
            redacted = pattern.sub("[REDACTED]", redacted)
        return redacted
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


@dataclass
class TraceEvent:
    step: int
    type: str  # model_decision | tool_call | tool_result | error | final
    data: dict
    at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class Trace:
    """An ordered, append-only record of one agent run. This *is* the run's
    retained state - the loop doesn't keep any other memory of what
    happened between steps.
    """

    def __init__(self) -> None:
        self.events: list[TraceEvent] = []

    def append(self, step: int, event_type: str, data: dict) -> TraceEvent:
        event = TraceEvent(step=step, type=event_type, data=redact(data))
        self.events.append(event)
        return event

    def types(self) -> list[str]:
        return [e.type for e in self.events]

    def to_list(self) -> list[dict]:
        return [{"step": e.step, "type": e.type, "data": e.data, "at": e.at} for e in self.events]

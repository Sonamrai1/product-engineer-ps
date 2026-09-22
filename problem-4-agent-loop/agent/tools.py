from typing import Any, Callable, Optional

from pydantic import BaseModel, Field


class ToolError(Exception):
    """Raised by a tool's own function when it can't do its job. Distinct
    from a pydantic ValidationError, which means the *input* was malformed
    before the tool ever ran.
    """

    def __init__(self, message: str, recoverable: bool = True) -> None:
        super().__init__(message)
        self.recoverable = recoverable


class Tool:
    def __init__(self, name: str, schema: type[BaseModel], fn: Callable[[BaseModel], Any], description: str = ""):
        self.name = name
        self.schema = schema
        self.fn = fn
        self.description = description

    def run(self, raw_input: dict) -> Any:
        """Validates raw_input against the schema (raises pydantic's own
        ValidationError on bad input) then runs the tool. Kept as one step
        so every tool call goes through the same validate-then-run path,
        whether it's called from the loop or directly from a test.
        """
        validated = self.schema.model_validate(raw_input)
        return self.fn(validated)


# ---------------------------------------------------------------------------
# Fixture data. Static and in-memory on purpose - no paid API, no network.
# ---------------------------------------------------------------------------

_LOGS = [
    {
        "timestamp": "2026-01-14T09:00:00Z",
        "service": "checkout",
        "level": "ERROR",
        "message": "Payment gateway timeout after 30s",
    },
    {
        "timestamp": "2026-01-14T09:05:00Z",
        "service": "checkout",
        "level": "ERROR",
        # Deliberately fake, shaped like a real API key on purpose - this
        # fixture exists to prove the trace's redaction pass actually works
        # (see tests/test_loop.py::test_secrets_are_redacted...). It's not,
        # and was never, a real credential.
        "message": "Payment gateway timeout, retrying with api_key=sk-test-FAKEKEYDONOTUSE0000",
    },
    {
        "timestamp": "2026-01-14T09:10:00Z",
        "service": "auth",
        "level": "WARN",
        "message": "Rate limit approaching for user login endpoint",
    },
    {
        "timestamp": "2026-01-14T09:15:00Z",
        "service": "checkout",
        "level": "INFO",
        "message": "Payment succeeded after retry",
    },
    {
        "timestamp": "2026-01-14T09:20:00Z",
        "service": "inventory",
        "level": "ERROR",
        "message": "Stock sync job failed: connection refused",
    },
]

_METRICS = {
    "checkout_latency_ms": [
        {"timestamp": "2026-01-14T09:00:00Z", "value": 420},
        {"timestamp": "2026-01-14T09:05:00Z", "value": 3100},
        {"timestamp": "2026-01-14T09:10:00Z", "value": 2800},
        {"timestamp": "2026-01-14T09:15:00Z", "value": 450},
    ],
    "error_rate": [
        {"timestamp": "2026-01-14T09:00:00Z", "value": 0.01},
        {"timestamp": "2026-01-14T09:05:00Z", "value": 0.18},
        {"timestamp": "2026-01-14T09:10:00Z", "value": 0.12},
        {"timestamp": "2026-01-14T09:15:00Z", "value": 0.02},
    ],
}

_KB = [
    {
        "title": "Payment gateway timeouts",
        "snippet": "If the checkout service logs repeated gateway timeouts, check the "
        "provider status page first - this is usually on their side, not ours.",
        "url": "kb://articles/123",
    },
    {
        "title": "Rate limiting on the auth service",
        "snippet": "Auth enforces per-IP rate limits. Warnings in the logs are expected "
        "under load and don't need action unless they turn into 429s.",
        "url": "kb://articles/456",
    },
]


# ---------------------------------------------------------------------------
# search_logs
# ---------------------------------------------------------------------------


class SearchLogsInput(BaseModel):
    query: str = Field(min_length=1)
    service: Optional[str] = None
    limit: int = Field(default=10, ge=1, le=50)


def _search_logs(input: SearchLogsInput) -> list[dict]:
    matches = [
        entry
        for entry in _LOGS
        if input.query.lower() in entry["message"].lower()
        and (input.service is None or entry["service"] == input.service)
    ]
    return matches[: input.limit]


search_logs = Tool(
    name="search_logs",
    schema=SearchLogsInput,
    fn=_search_logs,
    description="Search recent log lines by substring, optionally scoped to one service.",
)


# ---------------------------------------------------------------------------
# get_metrics
# ---------------------------------------------------------------------------


class GetMetricsInput(BaseModel):
    metric_name: str = Field(min_length=1)


def _get_metrics(input: GetMetricsInput) -> list[dict]:
    if input.metric_name not in _METRICS:
        known = ", ".join(sorted(_METRICS))
        raise ToolError(f"unknown metric '{input.metric_name}' - known metrics: {known}", recoverable=True)
    return _METRICS[input.metric_name]


get_metrics = Tool(
    name="get_metrics",
    schema=GetMetricsInput,
    fn=_get_metrics,
    description="Fetch a time series for a known metric name.",
)


# ---------------------------------------------------------------------------
# search_kb
# ---------------------------------------------------------------------------


class SearchKbInput(BaseModel):
    query: str = Field(min_length=1)


def _search_kb(input: SearchKbInput) -> list[dict]:
    # A magic query used only in tests to force a deliberately unrecoverable
    # failure (e.g. "the KB index is down") without needing real infra to
    # break on demand.
    if input.query == "__kb_down__":
        raise ToolError("KB search index is unavailable", recoverable=False)

    return [
        article
        for article in _KB
        if input.query.lower() in (article["title"] + " " + article["snippet"]).lower()
    ]


search_kb = Tool(
    name="search_kb",
    schema=SearchKbInput,
    fn=_search_kb,
    description="Search the knowledge base by substring over title and snippet.",
)


def default_tools() -> dict[str, Tool]:
    return {t.name: t for t in (search_logs, get_metrics, search_kb)}

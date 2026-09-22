# Observable Agent Loop

Python, no paid API. A bounded tool-using loop with a fully typed,
redacted, ordered trace of everything it did - built and tested entirely
against a scripted `FakeModel`.

## Prerequisites

- Python 3.10+ (tested on 3.12.3)
- No external services - pure library, no server to run

## Demo video

[Add the demo video link here before submitting - see the root
`DEMO_SCRIPT.md` for the walkthrough this was recorded from.]

## Setup

```
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Demo - how to trigger each acceptance criterion

This is a library, not a server - the "demo" is running short scripts (or
the equivalent tests) in a Python shell with the venv active.

1. **Multi-step run to a final answer, evidence separated from
   conclusion.** Run the "Quick look" script below as-is. `result.conclusion`
   and `result.evidence` print as two distinct values, and
   `result.trace.to_list()` shows the full ordered sequence:
   `model_decision -> tool_call -> tool_result` repeated, then `final`.
2. **Recoverable tool failure - model gets another shot.** Run
   `pytest -v -k test_validation_error_is_recorded_and_model_recovers_next_step`
   and read the test body - it scripts one call with an out-of-range
   `limit`, watches an `error` event land in the trace, then a corrected
   retry that reaches `SUCCESS`/`final`.
3. **Unrecoverable tool failure stops immediately.** Run
   `pytest -v -k test_unrecoverable_tool_failure_stops_without_a_further_model_call`
   - it asserts `model.calls == 1`, i.e. the loop never asked the model
   again after the unrecoverable failure, even though a second scripted
   decision was sitting right there unused.
4. **Step limit enforced without a bonus call.** Run
   `pytest -v -k test_max_steps_enforced_without_an_extra_model_call` -
   asserts `model.calls == max_steps` exactly, not `max_steps + 1`.

## Quick look

```python
from agent.loop import run_agent
from agent.model import FakeModel, ToolCallDecision, FinalDecision
from agent.tools import default_tools

script = [
    ToolCallDecision("search_logs", {"query": "timeout", "service": "checkout"}),
    ToolCallDecision("get_metrics", {"metric_name": "checkout_latency_ms"}),
    FinalDecision(
        conclusion="Checkout latency spiked because of payment gateway timeouts.",
        evidence=[
            "search_logs found 2 timeout errors on the checkout service",
            "checkout_latency_ms rose from ~420ms to ~3100ms in the same window",
        ],
    ),
]

result = run_agent(FakeModel(script), default_tools(), max_steps=6)

print(result.conclusion)     # the conclusion, on its own
print(result.evidence)       # what backs it, as a separate list
for event in result.trace.to_list():
    print(event["step"], event["type"], event["data"])
```

## Running the tests

```
pytest -v
```

Covers: tool input validation (`tests/test_tools.py`), and in
`tests/test_loop.py` - a full multi-step run to a final answer, a
validation error the model recovers from, an unknown-tool error the model
recovers from, an unrecoverable tool failure that stops the loop
immediately (without asking the model again), the step limit being
enforced without a bonus model call, and secrets getting redacted out of
the trace before they're ever stored.

## What's here

- `agent/tools.py` - the `Tool` type (name + pydantic schema + function) and
  three fixture-backed tools: `search_logs`, `get_metrics`, `search_kb`.
- `agent/model.py` - the `Model` interface and `FakeModel`, which replays a
  scripted list of decisions so tests are deterministic.
- `agent/trace.py` - the ordered trace and the secret-redaction pass applied
  to every event as it's written.
- `agent/loop.py` - `run_agent()`, the loop itself.

See `SUBMISSION.md` for the design write-up.


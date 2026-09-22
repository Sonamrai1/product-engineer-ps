# Product Engineering Challenge Submission

## Candidate

- **Name:** [TODO]
- **Email:** [TODO]
- **GitHub:** [TODO]
- **Selected problem:** Problem 4 - Observable Agent Loop
- **Demo video:** [Add the demo video link here before submitting]

## Run the project

Prerequisites: Python 3.10+. Pure library, no server to run.

```
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

To trigger the successful multi-step scenario and the failure/recovery
scenario, see the README's "Demo - how to trigger each acceptance
criterion" section (four numbered steps, each pointing at a runnable
script or a specific test).

## Run the tests

```
pytest -v
```

16 tests: tool validation, a full multi-step run to a final answer, a
validation error the model recovers from, an unrecoverable tool failure
that stops the loop without a further model call, the step limit enforced
without a bonus call, and secrets redacted before they reach the trace.

## Architecture and data flow

```
Model.decide(trace, step) -> ToolCallDecision | FinalDecision
        |                                |
        v                                v
Tool.run(input) -> validate -> result   loop appends `final` event, returns
        |
        v
trace.append(step, type, data)  [redaction happens here, before storage]
```

Three separate things, each replaceable on its own:

- **`Tool`** (`agent/tools.py`) - a name, a pydantic schema, and a function.
  The schema is the contract - the loop never needs to know a tool's
  internals, only that `tool.run(raw_input)` returns a result or raises.
- **`Model`** (`agent/model.py`) - one method: `decide(trace, step) ->
  Decision`. `FakeModel` implements it by replaying a scripted list of
  decisions instead of calling anything real.
- **`Trace`** (`agent/trace.py`) - the ordered, append-only record that
  *is* the run's retained state, with secret redaction applied at write
  time.
- **`run_agent()`** (`agent/loop.py`) - the loop itself: decide, validate,
  call, trace, repeat until final or out of steps.

## Technology choices

Plain Python + pydantic, no agent framework: the exercise is about the
control loop itself (validation, error handling, bounded execution), and
a framework would hide exactly the mechanics being demonstrated behind its
own abstractions. Pydantic specifically for tool schemas because it gives
real validation errors for free (missing fields, out-of-range values) that
the loop can catch and turn into a recoverable trace event, rather than
hand-rolling input checks per tool.

## Important decisions

- **Interfaces are split so each piece is independently replaceable.**
  `Tool`, `Model`, and `Trace` don't know about each other's internals -
  `FakeModel` is a real `Model`, not a mock bolted onto the loop, so the
  same `run_agent()` runs a scripted test today and a real model later
  without the loop code changing.
- **Validation happens before the tool function ever runs**, via
  `Tool.run()` calling the pydantic schema first. A bad call becomes an
  `error` trace event and the loop continues, rather than crashing the run
  over a mistake the model might correct next step.
- **The `Trace` is the only retained state.** There's no separate agent
  memory object - `model.decide(trace, step)` gets the complete ordered
  history every time, which is also what a real model implementation would
  build its next prompt from.
- **Limits enforce via the loop bound itself**, not an "ask the model to
  wrap up" exception - `range(1, max_steps + 1)` calls `model.decide()` at
  most `max_steps` times, full stop, tested directly
  (`model.calls == max_steps`, never `+ 1`).
- **Secret redaction happens inside `Trace.append()`**, before storage, not
  as a display-time filter - so there's no code path that can forward an
  unredacted trace, because the unredacted version never exists past the
  moment a tool result came back.
- **No chain-of-thought in the trace.** `ToolCallDecision` and
  `FinalDecision` have no "why" field - a real model's reasoning has
  nowhere to accidentally leak into the trace. If the "why" matters, it has
  to become an actual tool call or evidence in the final answer.

## Assumptions and limitations

- `FakeModel` ignores the trace it's handed and just replays a fixed
  script - fine for deterministic tests, but a real model implementation
  would need to actually build a prompt from the trace on every call.
- Tools are synchronous, in-process, static-fixture-backed - no real I/O,
  per the assignment's scope (synthetic/mocked data only).
- Redaction patterns are pattern-based (API-key shapes, `key=value` pairs,
  `Bearer` headers) rather than an exhaustive secret-detection system -
  reasonable for a demo, not a substitute for a real secrets-scanning tool
  in production.
- Single agent run at a time, in-process - concurrency and remote
  execution are addressed as design (below), not implemented.

## Production and scale

- **What prevents the agent from calling tools indefinitely?** `max_steps`
  bounds the loop directly, and the bound is enforced by the `for` loop's
  own range rather than by asking the model whether it's done - so there's
  no path where a model that never produces a `FinalDecision` runs longer
  than the configured budget, and no extra call spent asking it to wrap up.
- **How would you add a consequential tool requiring human approval?**
  Add a new `Decision` variant (or a flag on `ToolCallDecision`) for
  "requires approval," and a corresponding trace event type
  (`approval_requested`). The loop would pause after emitting that event -
  return control to the caller instead of proceeding to `tool.run()` -
  and a separate resume entry point would either execute the tool (on
  approval) or record a `denied` outcome and let the model try something
  else next step. The key constraint: the tool itself never runs until
  the approval event is answered, so the trace has a clean record of
  "asked, then approved/denied, then (maybe) executed."
- **How would you run concurrent agent jobs in a cloud environment?**
  Same shape as the "running remotely" design below - `run_agent()` takes
  a `Model` and a `tools` dict and returns a `Trace` (just data), which
  makes it portable to a queue-based setup: a run request goes on a queue,
  a stateless worker pulls one job, builds `Model`+`tools` from the job's
  config, and calls `run_agent()`. Any worker can pick up any job, so
  concurrency is just "run more workers" - the one thing this doesn't
  solve for free is a tool call with a real side effect (files an
  incident, sends a notification): if a worker crashes after the tool ran
  but before the result was persisted, a naive resume re-runs it and
  doubles the side effect. That needs the same idempotency-key treatment
  as Problem 2's webhook retry engine - keyed on run id + step number.
- **Which run data would you persist for debugging, cost analysis, and
  evaluation?** The full `Trace` itself (every `model_decision`,
  `tool_call`, `tool_result`, `error`, `final` event, already redacted)
  keyed by a run id, plus per-step latency and, for a real model, token
  counts and estimated cost per call. For evaluation specifically: the
  initial objective, the final `conclusion`/`evidence` split, and whether
  the run ended in `final`, `max_steps`, or `unrecoverable_error` - that
  three-way split alone is enough to build a dashboard of "how often does
  the agent actually finish" over time.
- **Running the same harness remotely, architecturally:** a queue holds
  pending run requests; a stateless worker pulls one, builds `Model` +
  `tools` from the job config, and calls `run_agent()`; each
  `trace.append()` would also write the event to durable storage as it
  happens, keyed by run id and step, so a crashed worker's progress is
  never lost and a new worker can resume from the last persisted step
  instead of starting over.

## AI usage

Used Claude for scaffolding and tests, manually reviewed logic.

## Credibility note

[TODO]

from agent.loop import run_agent
from agent.model import FakeModel, FinalDecision, ToolCallDecision
from agent.tools import default_tools


def test_multi_step_with_fake_model_reaches_final_answer():
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
    model = FakeModel(script)

    result = run_agent(model, default_tools(), max_steps=6)

    assert result.completed is True
    assert result.stopped_reason == "final"
    assert "latency spiked" in result.conclusion
    assert len(result.evidence) == 2
    assert result.trace.types() == [
        "model_decision", "tool_call", "tool_result",
        "model_decision", "tool_call", "tool_result",
        "model_decision", "final",
    ]


def test_validation_error_is_recorded_and_model_recovers_next_step():
    script = [
        ToolCallDecision("search_logs", {"query": "timeout", "limit": 999}),  # invalid, out of range
        ToolCallDecision("search_logs", {"query": "timeout"}),  # corrected
        FinalDecision(conclusion="Found timeout errors in checkout logs.", evidence=["search_logs result"]),
    ]
    model = FakeModel(script)

    result = run_agent(model, default_tools(), max_steps=6)

    assert result.completed is True
    error_events = [e for e in result.trace.events if e.type == "error"]
    assert len(error_events) == 1
    assert error_events[0].data["error_type"] == "validation"
    assert error_events[0].data["recoverable"] is True
    # the loop kept going after the bad call instead of aborting
    assert "tool_result" in result.trace.types()


def test_unknown_tool_recoverable_error_lets_model_try_again():
    script = [
        ToolCallDecision("delete_everything", {}),  # not a real tool
        FinalDecision(conclusion="Gave up gracefully.", evidence=[]),
    ]
    model = FakeModel(script)

    result = run_agent(model, default_tools(), max_steps=6)

    assert result.completed is True
    error_events = [e for e in result.trace.events if e.type == "error"]
    assert len(error_events) == 1
    assert "unknown tool" in error_events[0].data["message"]


def test_unrecoverable_tool_failure_stops_without_a_further_model_call():
    script = [
        ToolCallDecision("search_kb", {"query": "__kb_down__"}),
        FinalDecision(conclusion="should never be reached", evidence=[]),
    ]
    model = FakeModel(script)

    result = run_agent(model, default_tools(), max_steps=6)

    assert result.completed is False
    assert result.stopped_reason == "unrecoverable_error"
    assert "unrecoverable" in result.conclusion
    # the model was only ever asked once - the second scripted decision
    # (the never-reached FinalDecision) was never consumed
    assert model.calls == 1
    assert result.trace.types() == ["model_decision", "tool_call", "error", "final"]


def test_max_steps_enforced_without_an_extra_model_call():
    max_steps = 3
    # every decision is a tool call - the model never offers a final answer
    script = [ToolCallDecision("get_metrics", {"metric_name": "error_rate"}) for _ in range(max_steps)]
    model = FakeModel(script)

    result = run_agent(model, default_tools(), max_steps=max_steps)

    assert result.completed is False
    assert result.stopped_reason == "max_steps"
    # exactly max_steps calls - no bonus call asking the model to wrap up
    assert model.calls == max_steps
    final_events = [e for e in result.trace.events if e.type == "final"]
    assert len(final_events) == 1


def test_secrets_are_redacted_before_they_reach_the_trace():
    script = [
        ToolCallDecision("search_logs", {"query": "retrying"}),
        FinalDecision(conclusion="Retry attempted with credentials.", evidence=[]),
    ]
    model = FakeModel(script)

    result = run_agent(model, default_tools(), max_steps=6)

    serialized = str(result.trace.to_list())
    assert "sk-test-FAKEKEYDONOTUSE0000" not in serialized
    assert "[REDACTED]" in serialized

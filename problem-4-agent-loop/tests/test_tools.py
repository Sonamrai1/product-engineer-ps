import pydantic
import pytest

from agent.tools import ToolError, get_metrics, search_kb, search_logs


def test_search_logs_filters_by_query_and_service():
    results = search_logs.run({"query": "timeout", "service": "checkout"})
    assert len(results) == 2
    assert all(r["service"] == "checkout" for r in results)
    assert all("timeout" in r["message"].lower() for r in results)


def test_search_logs_respects_limit():
    results = search_logs.run({"query": "e", "limit": 1})
    assert len(results) == 1


def test_search_logs_rejects_empty_query():
    with pytest.raises(pydantic.ValidationError):
        search_logs.run({"query": ""})


def test_search_logs_rejects_limit_out_of_range():
    with pytest.raises(pydantic.ValidationError):
        search_logs.run({"query": "timeout", "limit": 500})


def test_get_metrics_known_metric():
    points = get_metrics.run({"metric_name": "checkout_latency_ms"})
    assert len(points) == 4
    assert points[0]["value"] == 420


def test_get_metrics_unknown_metric_raises_recoverable_tool_error():
    with pytest.raises(ToolError) as exc_info:
        get_metrics.run({"metric_name": "made_up_metric"})
    assert exc_info.value.recoverable is True


def test_get_metrics_rejects_missing_field():
    with pytest.raises(pydantic.ValidationError):
        get_metrics.run({})


def test_search_kb_returns_matches():
    results = search_kb.run({"query": "gateway"})
    assert len(results) == 1
    assert results[0]["title"] == "Payment gateway timeouts"


def test_search_kb_no_matches_returns_empty_list():
    results = search_kb.run({"query": "nonexistent topic entirely"})
    assert results == []


def test_search_kb_simulated_unrecoverable_failure():
    with pytest.raises(ToolError) as exc_info:
        search_kb.run({"query": "__kb_down__"})
    assert exc_info.value.recoverable is False

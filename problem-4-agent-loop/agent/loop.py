from dataclasses import dataclass, field

import pydantic

from .model import FinalDecision, Model, ToolCallDecision
from .tools import Tool, ToolError
from .trace import Trace


@dataclass
class AgentResult:
    completed: bool  # True only if the model produced a FinalDecision
    stopped_reason: str  # "final" | "max_steps" | "unrecoverable_error"
    conclusion: str | None
    evidence: list[str] = field(default_factory=list)
    trace: Trace = field(default_factory=Trace)


def run_agent(model: Model, tools: dict[str, Tool], max_steps: int = 6) -> AgentResult:
    trace = Trace()

    for step in range(1, max_steps + 1):
        decision = model.decide(trace, step)

        if isinstance(decision, FinalDecision):
            trace.append(step, "model_decision", {"kind": "final"})
            trace.append(step, "final", {"conclusion": decision.conclusion, "evidence": decision.evidence})
            return AgentResult(True, "final", decision.conclusion, decision.evidence, trace)

        assert isinstance(decision, ToolCallDecision)
        trace.append(
            step,
            "model_decision",
            {"kind": "tool_call", "tool_name": decision.tool_name, "tool_input": decision.tool_input},
        )
        trace.append(step, "tool_call", {"tool_name": decision.tool_name, "tool_input": decision.tool_input})

        tool = tools.get(decision.tool_name)
        if tool is None:
            trace.append(step, "error", {"message": f"unknown tool: {decision.tool_name}", "recoverable": True})
            continue

        try:
            result = tool.run(decision.tool_input)
        except pydantic.ValidationError as exc:
            trace.append(
                step,
                "error",
                {"message": str(exc), "recoverable": True, "error_type": "validation"},
            )
            continue
        except ToolError as exc:
            trace.append(
                step,
                "error",
                {"message": str(exc), "recoverable": exc.recoverable, "error_type": "tool"},
            )
            if not exc.recoverable:
                conclusion = f"Stopped: {decision.tool_name} failed with an unrecoverable error - {exc}"
                trace.append(step, "final", {"conclusion": conclusion, "evidence": []})
                return AgentResult(False, "unrecoverable_error", conclusion, [], trace)
            continue

        trace.append(step, "tool_result", {"tool_name": decision.tool_name, "result": result})

    # Exhausted the step budget without a final answer - stop here, no
    # extra model call to "ask for a final answer anyway".
    conclusion = f"Stopped after reaching the {max_steps}-step limit without a final answer."
    trace.append(max_steps, "final", {"conclusion": conclusion, "evidence": []})
    return AgentResult(False, "max_steps", conclusion, [], trace)

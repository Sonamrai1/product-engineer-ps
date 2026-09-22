from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Union

from .trace import Trace


@dataclass
class ToolCallDecision:
    tool_name: str
    tool_input: dict


@dataclass
class FinalDecision:
    conclusion: str
    evidence: list[str] = field(default_factory=list)


Decision = Union[ToolCallDecision, FinalDecision]


class Model(ABC):
    """Anything that can look at the trace so far and decide what to do
    next. A real implementation would turn the trace into a prompt and call
    out to an LLM; it's abstracted here so the loop itself never needs to
    know or care which.
    """

    @abstractmethod
    def decide(self, trace: Trace, step: int) -> Decision:
        raise NotImplementedError


class FakeModel(Model):
    """Deterministic stand-in used everywhere in tests (and anywhere else a
    real, paid model isn't wanted) - just replays a pre-written sequence of
    decisions, one per call. It ignores the trace it's handed; a real model
    wouldn't.
    """

    def __init__(self, script: list[Decision]) -> None:
        self.script = script
        self.calls = 0

    def decide(self, trace: Trace, step: int) -> Decision:
        if self.calls >= len(self.script):
            raise RuntimeError(
                f"FakeModel script exhausted at step {step} - only {len(self.script)} decisions were scripted"
            )
        decision = self.script[self.calls]
        self.calls += 1
        return decision

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any


class RunState(str, Enum):
    CREATED = "CREATED"
    DATA_VALIDATED = "DATA_VALIDATED"
    BACKTESTED = "BACKTESTED"
    EVALUATED = "EVALUATED"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


_TRANSITIONS = {
    RunState.CREATED: {RunState.DATA_VALIDATED, RunState.FAILED},
    RunState.DATA_VALIDATED: {RunState.BACKTESTED, RunState.FAILED},
    RunState.BACKTESTED: {RunState.EVALUATED, RunState.FAILED},
    RunState.EVALUATED: {RunState.COMPLETED, RunState.REJECTED, RunState.FAILED},
    RunState.COMPLETED: set(),
    RunState.REJECTED: set(),
    RunState.FAILED: set(),
}


class StateMachine:
    def __init__(self) -> None:
        self.state = RunState.CREATED
        self.history: list[dict[str, Any]] = []

    def transition(self, target: RunState, detail: str = "") -> None:
        if target not in _TRANSITIONS[self.state]:
            raise ValueError(f"invalid state transition: {self.state.value} -> {target.value}")
        event = {
            "from": self.state.value,
            "to": target.value,
            "at": datetime.now(timezone.utc).isoformat(),
        }
        if detail:
            event["detail"] = detail
        self.history.append(event)
        self.state = target

    def fail(self, detail: str) -> None:
        if self.state not in {RunState.COMPLETED, RunState.REJECTED, RunState.FAILED}:
            self.transition(RunState.FAILED, detail)

    def as_dict(self) -> dict[str, Any]:
        return {"state": self.state.value, "history": self.history}

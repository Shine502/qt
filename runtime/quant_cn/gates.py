from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class GateResult:
    name: str
    passed: bool
    actual: float | int | str | None
    limit: float | int | str
    comparison: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _numeric_gate(
    name: str, actual: Any, limit: float | int, comparison: str
) -> GateResult:
    valid = isinstance(actual, (int, float)) and not isinstance(actual, bool) and math.isfinite(actual)
    value = actual if valid else None
    if not valid:
        passed = False
    elif comparison == ">=":
        passed = actual >= limit
    elif comparison == "<=":
        passed = actual <= limit
    else:
        raise ValueError(f"unsupported comparison: {comparison}")
    return GateResult(name, passed, value, limit, comparison)


def evaluate_gates(
    metrics: dict[str, float | int], policy: dict[str, Any]
) -> list[GateResult]:
    return [
        _numeric_gate("test_rows", metrics.get("rows"), policy["min_test_rows"], ">="),
        _numeric_gate(
            "test_total_return",
            metrics.get("total_return"),
            policy["min_test_total_return"],
            ">=",
        ),
        _numeric_gate("test_sharpe", metrics.get("sharpe"), policy["min_test_sharpe"], ">="),
        _numeric_gate(
            "test_max_drawdown",
            metrics.get("max_drawdown"),
            policy["max_test_drawdown"],
            "<=",
        ),
        _numeric_gate(
            "test_annualized_volatility",
            metrics.get("annualized_volatility"),
            policy["max_test_annualized_volatility"],
            "<=",
        ),
    ]


def evaluate_relative_gates(
    candidate: dict[str, float | int],
    baseline: dict[str, float | int],
    policy: dict[str, Any],
    same_dataset: bool,
) -> list[GateResult]:
    baseline_sharpe = baseline.get("sharpe")
    baseline_return = baseline.get("total_return")
    baseline_drawdown = baseline.get("max_drawdown")
    improvement = (
        candidate.get("sharpe", float("nan")) - baseline_sharpe
        if isinstance(baseline_sharpe, (int, float))
        else float("nan")
    )
    return [
        GateResult("same_dataset", same_dataset, "same" if same_dataset else "different", "same", "=="),
        _numeric_gate(
            "sharpe_improvement",
            improvement,
            policy["min_sharpe_improvement"],
            ">=",
        ),
        _numeric_gate(
            "candidate_total_return",
            candidate.get("total_return"),
            baseline_return if isinstance(baseline_return, (int, float)) else float("nan"),
            ">=",
        ),
        _numeric_gate(
            "candidate_max_drawdown",
            candidate.get("max_drawdown"),
            baseline_drawdown + policy["max_drawdown_slippage"]
            if isinstance(baseline_drawdown, (int, float))
            else float("nan"),
            "<=",
        ),
    ]

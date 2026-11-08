"""Offline quantitative research and gated strategy evaluation."""

from .a_share import (
    AShareBacktestRow,
    AShareBar,
    AShareConfig,
    CorporateAction,
    Trade,
    load_a_share_data,
    run_a_share_backtest,
)
from .backtest import Bar, BacktestRow, calculate_metrics, run_backtest
from .gates import GateResult, evaluate_gates, evaluate_relative_gates
from .pipeline import execute
from .state import RunState, StateMachine

__all__ = [
    "Bar",
    "BacktestRow",
    "GateResult",
    "RunState",
    "StateMachine",
    "calculate_metrics",
    "evaluate_gates",
    "evaluate_relative_gates",
    "execute",
    "run_backtest",
]

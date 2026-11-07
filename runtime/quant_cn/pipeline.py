from __future__ import annotations

import csv
import json
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .backtest import BacktestRow, calculate_metrics, run_backtest
from .data import load_bars
from .gates import GateResult, evaluate_gates, evaluate_relative_gates
from .state import RunState, StateMachine

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY = PLUGIN_ROOT / "references" / "policies" / "default.json"
NUMERIC_POLICY_KEYS = (
    "train_fraction",
    "min_rows",
    "min_test_rows",
    "min_test_total_return",
    "min_test_sharpe",
    "max_test_drawdown",
    "max_test_annualized_volatility",
    "max_fee_bps",
    "min_sharpe_improvement",
    "max_drawdown_slippage",
)


def _write_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _save_state(run_dir: Path, machine: StateMachine) -> None:
    _write_json(run_dir / "state.json", machine.as_dict())


def load_policy(path: str | Path | None = None) -> dict[str, Any]:
    policy_path = Path(path) if path else DEFAULT_POLICY
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    for key in NUMERIC_POLICY_KEYS:
        value = policy.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"policy field {key} must be a finite number")
    if not 0.5 <= policy["train_fraction"] < 1.0:
        raise ValueError("policy train_fraction must be in [0.5, 1.0)")
    if policy["min_rows"] < 2 or policy["min_test_rows"] < 1:
        raise ValueError("policy row limits are too small")
    if policy["max_fee_bps"] < 0:
        raise ValueError("policy max_fee_bps must be non-negative")
    return policy


def _load_baseline(path: str | Path) -> dict[str, Any]:
    baseline = json.loads(Path(path).read_text(encoding="utf-8"))
    if baseline.get("schema_version") != 1 or baseline.get("mode") != "start":
        raise ValueError("baseline must be a schema v1 start result")
    metrics = baseline.get("metrics", {}).get("test", {})
    for key in ("sharpe", "total_return", "max_drawdown"):
        value = metrics.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"baseline test metric {key} must be finite")
    if not isinstance(baseline.get("data", {}).get("sha256"), str):
        raise ValueError("baseline data sha256 is missing")
    return baseline


def _write_equity(path: Path, rows: list[BacktestRow], split_index: int) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["date", "segment", "close", "asset_return", "signal", "position", "turnover", "net_return", "equity"]
        )
        for index, row in enumerate(rows):
            writer.writerow(
                [
                    row.date,
                    "train" if index < split_index else "test",
                    row.close,
                    row.asset_return,
                    row.signal,
                    row.position,
                    row.turnover,
                    row.net_return,
                    row.equity,
                ]
            )


def execute(
    mode: str,
    data_path: str | Path,
    fast: int = 5,
    slow: int = 20,
    fee_bps: float = 10.0,
    output_root: str | Path = ".qt/runs",
    baseline_path: str | Path | None = None,
    policy_path: str | Path | None = None,
) -> dict[str, Any]:
    if mode not in {"start", "evo"}:
        raise ValueError("mode must be start or evo")
    if mode == "evo" and baseline_path is None:
        raise ValueError("evo requires a baseline result")
    policy = load_policy(policy_path)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]
    run_dir = Path(output_root).resolve() / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    machine = StateMachine()
    _save_state(run_dir, machine)
    try:
        if isinstance(fast, bool) or isinstance(slow, bool) or fast < 1 or slow <= fast:
            raise ValueError("window constraints: fast >= 1 and slow > fast")
        bars, digest = load_bars(data_path)
        if len(bars) < max(int(policy["min_rows"]), slow + 2):
            raise ValueError(f"insufficient data: {len(bars)} rows")
        machine.transition(RunState.DATA_VALIDATED, f"{len(bars)} rows")
        _save_state(run_dir, machine)

        baseline = _load_baseline(baseline_path) if mode == "evo" else None
        rows = run_backtest(bars, fast=fast, slow=slow, fee_bps=fee_bps)
        split_index = int(len(rows) * policy["train_fraction"])
        train_metrics = calculate_metrics(rows[:split_index])
        test_metrics = calculate_metrics(rows[split_index:])
        machine.transition(RunState.BACKTESTED, f"test rows: {len(rows) - split_index}")
        _save_state(run_dir, machine)

        gates = evaluate_gates(test_metrics, policy)
        gates.append(
            GateResult(
                "fee_bps",
                fee_bps <= policy["max_fee_bps"],
                fee_bps,
                policy["max_fee_bps"],
                "<=",
            )
        )
        if baseline is not None:
            gates.extend(
                evaluate_relative_gates(
                    test_metrics,
                    baseline["metrics"]["test"],
                    policy,
                    digest == baseline["data"]["sha256"],
                )
            )
        accepted = all(gate.passed for gate in gates)
        machine.transition(RunState.EVALUATED)
        machine.transition(RunState.COMPLETED if accepted else RunState.REJECTED)
        _save_state(run_dir, machine)
        _write_equity(run_dir / "equity_curve.csv", rows, split_index)
        result: dict[str, Any] = {
            "schema_version": 1,
            "run_id": run_id,
            "mode": mode,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "state": machine.state.value,
            "data": {
                "path": str(Path(data_path).resolve()),
                "sha256": digest,
                "rows": len(bars),
                "start": bars[0].date,
                "end": bars[-1].date,
                "train_rows": split_index,
                "test_rows": len(rows) - split_index,
            },
            "parameters": {"fast": fast, "slow": slow, "fee_bps": fee_bps},
            "metrics": {"train": train_metrics, "test": test_metrics},
            "gates": [gate.as_dict() for gate in gates],
            "decision": {
                "accepted": accepted,
                "reasons": [
                    f"{gate.name}: expected {gate.comparison} {gate.limit}, got {gate.actual}"
                    for gate in gates
                    if not gate.passed
                ],
                "baseline_modified": False,
            },
            "artifacts": {"equity_curve": "equity_curve.csv", "state": "state.json"},
        }
        if baseline is not None:
            result["baseline"] = {
                "path": str(Path(baseline_path).resolve()),
                "run_id": baseline.get("run_id"),
                "test_metrics": baseline["metrics"]["test"],
            }
        _write_json(run_dir / "result.json", result)
        return result
    except Exception as error:
        machine.fail(str(error))
        _save_state(run_dir, machine)
        _write_json(run_dir / "error.json", {"error": str(error)})
        raise

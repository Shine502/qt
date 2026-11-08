from __future__ import annotations

import csv
import json
import math
import uuid
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .a_share import (
    AShareBacktestRow,
    AShareConfig,
    CorporateAction,
    Trade,
    load_a_share_data,
    run_a_share_backtest,
)
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
        raise ValueError("policy train_fraction must be in [0.5, 1.0]")
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


def _split_rows(
    rows: list[Any],
    train_fraction: float,
    validation_start: str | None,
    test_start: str | None,
) -> dict[str, list[Any]]:
    if (validation_start is None) != (test_start is None):
        raise ValueError("validation_start and test_start must be provided together")
    if validation_start is not None and test_start is not None:
        validation_date = date.fromisoformat(validation_start).isoformat()
        test_date = date.fromisoformat(test_start).isoformat()
        if validation_date >= test_date:
            raise ValueError("validation_start must precede test_start")
        segments = {
            "train": [row for row in rows if row.date < validation_date],
            "validation": [row for row in rows if validation_date <= row.date < test_date],
            "test": [row for row in rows if row.date >= test_date],
        }
        if any(not segment for segment in segments.values()):
            raise ValueError("train, validation and test segments must all contain rows")
        return segments
    split_index = int(len(rows) * train_fraction)
    segments = {"train": rows[:split_index], "test": rows[split_index:]}
    if not segments["train"] or not segments["test"]:
        raise ValueError("train and test segments must both contain rows")
    return segments


def _segment_names(rows: list[Any], segments: dict[str, list[Any]]) -> dict[str, str]:
    return {
        row.date: name
        for name, segment in segments.items()
        for row in segment
    }


def _write_equity(path: Path, rows: list[Any], segments: dict[str, list[Any]]) -> None:
    segment_names = _segment_names(rows, segments)
    detailed = bool(rows) and isinstance(rows[0], AShareBacktestRow)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        header = [
            "date", "segment", "close", "asset_return", "signal", "position",
            "turnover", "net_return", "equity",
        ]
        if detailed:
            header.extend(
                ["adjusted_close", "open", "cash", "shares", "dividend_cash", "trade_notional", "fees"]
            )
        writer.writerow(header)
        for row in rows:
            values = [
                row.date, segment_names[row.date], row.close, row.asset_return,
                row.signal, row.position, row.turnover, row.net_return, row.equity,
            ]
            if detailed:
                values.extend(
                    [row.adjusted_close, row.open, row.cash, row.shares, row.dividend_cash,
                     row.trade_notional, row.fees]
                )
            writer.writerow(values)


def _write_trades(path: Path, trades: list[Trade]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["date", "side", "shares", "price", "notional", "commission", "stamp_duty"],
        )
        writer.writeheader()
        writer.writerows(trade.as_dict() for trade in trades)


def _write_actions(path: Path, actions: list[CorporateAction]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "ex_date", "record_date", "cash_dividend_per_share",
                "stock_dividend_ratio", "transfer_ratio",
            ],
        )
        writer.writeheader()
        writer.writerows(action.as_dict() for action in actions)


def execute(
    mode: str,
    data_path: str | Path,
    fast: int = 5,
    slow: int = 20,
    fee_bps: float = 10.0,
    output_root: str | Path = ".qt/runs",
    baseline_path: str | Path | None = None,
    policy_path: str | Path | None = None,
    adjusted_data_path: str | Path | None = None,
    events_path: str | Path | None = None,
    initial_cash: float = 1_000_000.0,
    commission_rate: float = 0.00025,
    min_commission: float = 5.0,
    slippage_bps: float = 5.0,
    lot_size: int = 100,
    validation_start: str | None = None,
    test_start: str | None = None,
    data_source: str | None = None,
    symbol: str | None = None,
) -> dict[str, Any]:
    if mode not in {"start", "evo"}:
        raise ValueError("mode must be start or evo")
    if mode == "evo" and baseline_path is None:
        raise ValueError("evo requires a baseline result")
    if (adjusted_data_path is None) != (events_path is None):
        raise ValueError("adjusted_data_path and events_path must be provided together")
    detailed = adjusted_data_path is not None and events_path is not None
    policy = load_policy(policy_path)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]
    run_dir = Path(output_root).resolve() / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    machine = StateMachine()
    _save_state(run_dir, machine)
    try:
        if isinstance(fast, bool) or isinstance(slow, bool) or fast < 1 or slow <= fast:
            raise ValueError("window constraints: fast >= 1 and slow > fast")
        actions: list[CorporateAction] = []
        hashes: dict[str, str] = {}
        if detailed:
            bars, actions, hashes = load_a_share_data(
                data_path, adjusted_data_path, events_path
            )
            row_count = len(bars)
            first_date = bars[0].date
            last_date = bars[-1].date
            data_hash = hashes["dataset_sha256"]
        else:
            generic_bars, data_hash = load_bars(data_path)
            row_count = len(generic_bars)
            first_date = generic_bars[0].date
            last_date = generic_bars[-1].date
        if row_count < max(int(policy["min_rows"]), slow + 2):
            raise ValueError(f"insufficient data: {row_count} rows")
        machine.transition(RunState.DATA_VALIDATED, f"{row_count} rows")
        _save_state(run_dir, machine)

        baseline = _load_baseline(baseline_path) if mode == "evo" else None
        trades: list[Trade] = []
        benchmark_rows: list[AShareBacktestRow] = []
        benchmark_trades: list[Trade] = []
        if detailed:
            config = AShareConfig(
                initial_cash=initial_cash,
                commission_rate=commission_rate,
                min_commission=min_commission,
                slippage_bps=slippage_bps,
                lot_size=lot_size,
            )
            rows, trades = run_a_share_backtest(bars, actions, fast, slow, config)
            benchmark_rows, benchmark_trades = run_a_share_backtest(
                bars, actions, fast, slow, config, signals=[1] * len(bars)
            )
        else:
            rows = run_backtest(generic_bars, fast=fast, slow=slow, fee_bps=fee_bps)
        segments = _split_rows(rows, policy["train_fraction"], validation_start, test_start)
        metrics = {
            name: calculate_metrics(segment)
            for name, segment in segments.items()
        }
        benchmark_metrics = (
            {
                name: calculate_metrics(
                    [row for row in benchmark_rows if row.date in {item.date for item in segment}]
                )
                for name, segment in segments.items()
            }
            if detailed
            else None
        )
        machine.transition(RunState.BACKTESTED, f"test rows: {len(segments['test'])}")
        _save_state(run_dir, machine)

        selection_segment = "validation" if baseline is not None and "validation" in metrics else "test"
        if baseline is not None and selection_segment not in baseline.get("metrics", {}):
            raise ValueError(f"baseline is missing {selection_segment} metrics")
        gates = evaluate_gates(metrics[selection_segment], policy, segment=selection_segment)
        if detailed:
            gates.append(
                GateResult(
                    "commission_rate",
                    commission_rate <= policy["max_fee_bps"] / 10_000.0,
                    commission_rate,
                    policy["max_fee_bps"] / 10_000.0,
                    "<=",
                )
            )
        else:
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
                    metrics[selection_segment],
                    baseline["metrics"][selection_segment],
                    policy,
                    data_hash == baseline["data"]["sha256"],
                )
            )
        accepted = all(gate.passed for gate in gates)
        machine.transition(RunState.EVALUATED)
        machine.transition(RunState.COMPLETED if accepted else RunState.REJECTED)
        _save_state(run_dir, machine)
        _write_equity(run_dir / "equity_curve.csv", rows, segments)
        artifacts = {"equity_curve": "equity_curve.csv", "state": "state.json"}
        if detailed:
            _write_equity(run_dir / "benchmark_equity_curve.csv", benchmark_rows, segments)
            _write_trades(run_dir / "trades.csv", trades)
            _write_trades(run_dir / "benchmark_trades.csv", benchmark_trades)
            _write_actions(run_dir / "corporate_actions.csv", actions)
            artifacts.update(
                {
                    "benchmark_equity_curve": "benchmark_equity_curve.csv",
                    "trades": "trades.csv",
                    "benchmark_trades": "benchmark_trades.csv",
                    "corporate_actions": "corporate_actions.csv",
                }
            )
        data: dict[str, Any] = {
            "path": str(Path(data_path).resolve()),
            "sha256": data_hash,
            "rows": row_count,
            "start": first_date,
            "end": last_date,
            "train_rows": len(segments["train"]),
            "test_rows": len(segments["test"]),
        }
        if "validation" in segments:
            data["validation_rows"] = len(segments["validation"])
            data["validation_start"] = validation_start
            data["test_start"] = test_start
        if detailed:
            data["files"] = {
                "raw": {"path": str(Path(data_path).resolve()), "sha256": hashes["raw_sha256"]},
                "adjusted": {
                    "path": str(Path(adjusted_data_path).resolve()),
                    "sha256": hashes["adjusted_sha256"],
                },
                "events": {
                    "path": str(Path(events_path).resolve()),
                    "sha256": hashes["events_sha256"],
                },
            }
        if data_source:
            data["source"] = data_source
        if symbol:
            data["symbol"] = symbol
        parameters: dict[str, Any] = {"fast": fast, "slow": slow}
        if detailed:
            parameters["execution"] = asdict(config)
            parameters["price_adjustment"] = "forward"
            parameters["execution_timing"] = "next_open"
        else:
            parameters["fee_bps"] = fee_bps
        result: dict[str, Any] = {
            "schema_version": 1,
            "run_id": run_id,
            "mode": mode,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "state": machine.state.value,
            "data": data,
            "parameters": parameters,
            "metrics": metrics,
            "gates": [gate.as_dict() for gate in gates],
            "decision": {
                "accepted": accepted,
                "evaluation_segment": selection_segment,
                "reasons": [
                    f"{gate.name}: expected {gate.comparison} {gate.limit}, got {gate.actual}"
                    for gate in gates
                    if not gate.passed
                ],
                "baseline_modified": False,
            },
            "artifacts": artifacts,
            "limitations": (
                [
                    "No limit-up/limit-down or suspension execution simulation.",
                    "Cash dividends are credited before ex-date trading; dividend taxes are not modeled.",
                    "Corporate-action completeness depends on the supplied normalized events file.",
                ]
                if detailed
                else []
            ),
        }
        if benchmark_metrics is not None:
            result["benchmark"] = {"name": "buy_and_hold", "metrics": benchmark_metrics}
        if baseline is not None:
            result["baseline"] = {
                "path": str(Path(baseline_path).resolve()),
                "run_id": baseline.get("run_id"),
                "evaluation_segment": selection_segment,
                "metrics": baseline["metrics"][selection_segment],
            }
        _write_json(run_dir / "result.json", result)
        return result
    except Exception as error:
        machine.fail(str(error))
        _save_state(run_dir, machine)
        _write_json(run_dir / "error.json", {"error": str(error)})
        raise

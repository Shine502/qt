from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.quant_cn.pipeline import execute, load_policy


def validate_plugin() -> None:
    manifest = json.loads((ROOT / "kimi.plugin.json").read_text(encoding="utf-8"))
    required = ["commands/start.md", "commands/evo.md", "skills/start/SKILL.md", "skills/evo/SKILL.md"]
    required.extend(f"agents/{name}.md" for name in (
        "research-lead",
        "evolution-lead",
        "data-specialist",
        "strategy-specialist",
        "risk-specialist",
        "backtest-specialist",
        "validation-specialist",
        "report-specialist",
    ))
    missing = [path for path in required if not (ROOT / path).is_file()]
    if missing:
        raise ValueError("missing plugin files: " + ", ".join(missing))
    if manifest.get("name") != "qt":
        raise ValueError("manifest name must be qt")
    load_policy()


def _add_run_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--data", required=True, help="CSV with date,close columns; raw OHLC for A-share mode")
    parser.add_argument("--adjusted-data", help="forward-adjusted OHLC CSV for A-share mode")
    parser.add_argument("--events", help="normalized corporate-action CSV for A-share mode")
    parser.add_argument("--fast", type=int, default=5)
    parser.add_argument("--slow", type=int, default=20)
    parser.add_argument("--fee-bps", type=float, default=10.0)
    parser.add_argument("--initial-cash", type=float, default=1_000_000.0)
    parser.add_argument("--commission-rate", type=float, default=0.00025)
    parser.add_argument("--min-commission", type=float, default=5.0)
    parser.add_argument("--slippage-bps", type=float, default=5.0)
    parser.add_argument("--lot-size", type=int, default=100)
    parser.add_argument("--validation-start", help="YYYY-MM-DD; enables train/validation/test split")
    parser.add_argument("--test-start", help="YYYY-MM-DD; enables train/validation/test split")
    parser.add_argument("--data-source")
    parser.add_argument("--symbol")
    parser.add_argument("--output", default=".qt/runs")
    parser.add_argument("--policy")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qt", description="Offline quantitative research controller")
    subparsers = parser.add_subparsers(dest="action", required=True)
    start = subparsers.add_parser("start", help="run and gate a strategy")
    _add_run_arguments(start)
    evo = subparsers.add_parser("evo", help="compare a candidate with a start baseline")
    _add_run_arguments(evo)
    evo.add_argument("--baseline", required=True, help="path to a start result.json")
    status = subparsers.add_parser("status", help="show persisted run state")
    status.add_argument("--run", required=True, help="run directory")
    subparsers.add_parser("validate", help="validate plugin structure and policy")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.action == "validate":
            validate_plugin()
            print("plugin validation passed")
            return 0
        if args.action == "status":
            state_path = Path(args.run) / "state.json"
            print(json.dumps(json.loads(state_path.read_text(encoding="utf-8")), ensure_ascii=False, indent=2))
            return 0
        result = execute(
            mode=args.action,
            data_path=args.data,
            fast=args.fast,
            slow=args.slow,
            fee_bps=args.fee_bps,
            output_root=args.output,
            baseline_path=getattr(args, "baseline", None),
            policy_path=args.policy,
            adjusted_data_path=args.adjusted_data,
            events_path=args.events,
            initial_cash=args.initial_cash,
            commission_rate=args.commission_rate,
            min_commission=args.min_commission,
            slippage_bps=args.slippage_bps,
            lot_size=args.lot_size,
            validation_start=args.validation_start,
            test_start=args.test_start,
            data_source=args.data_source,
            symbol=args.symbol,
        )
        summary = {
            "run_id": result["run_id"],
            "run_dir": str(Path(args.output).resolve() / result["run_id"]),
            "state": result["state"],
            "accepted": result["decision"]["accepted"],
            "evaluation_segment": result["decision"]["evaluation_segment"],
            "test_metrics": result["metrics"]["test"],
            "reasons": result["decision"]["reasons"],
        }
        if "validation" in result["metrics"]:
            summary["validation_metrics"] = result["metrics"]["validation"]
        if "benchmark" in result:
            summary["benchmark_test_metrics"] = result["benchmark"]["metrics"]["test"]
        print(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False))
        return 0 if result["decision"]["accepted"] else 2
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"qt: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

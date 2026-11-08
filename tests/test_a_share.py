import csv
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from runtime.quant_cn.a_share import (
    AShareBar,
    AShareConfig,
    CorporateAction,
    load_a_share_data,
    run_a_share_backtest,
    stamp_duty_rate,
)
from runtime.quant_cn.pipeline import execute


class AShareBacktestTests(unittest.TestCase):
    def test_signal_executes_at_next_open(self):
        bars = [
            AShareBar(day, close, close, close, close, close)
            for day, close in zip(
                ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"],
                [100.0, 100.0, 110.0, 120.0],
            )
        ]
        config = AShareConfig(
            initial_cash=10_000, commission_rate=0, min_commission=0, slippage_bps=0, lot_size=1
        )
        rows, trades = run_a_share_backtest(bars, [], config=config, signals=[1, 0, 0, 0])
        self.assertEqual([trade.date for trade in trades], ["2024-01-02", "2024-01-03"])
        self.assertEqual(trades[0].price, 100)
        self.assertEqual(trades[1].price, 110)
        self.assertEqual(rows[1].shares, 100)
        self.assertEqual(rows[-1].equity, 10_994.5)

    def test_minimum_commission_and_sell_stamp_duty(self):
        bars = [
            AShareBar(day, 100, 100, 100, 100, 100)
            for day in ["2024-01-01", "2024-01-02", "2024-01-03"]
        ]
        config = AShareConfig(
            initial_cash=20_000, commission_rate=0.00025, min_commission=5, slippage_bps=0
        )
        rows, trades = run_a_share_backtest(bars, [], config=config, signals=[1, 0, 0])
        self.assertEqual(trades[0].shares, 100)
        self.assertEqual(trades[0].commission, 5)
        self.assertEqual(trades[1].commission, 5)
        self.assertEqual(trades[1].stamp_duty, 5)
        self.assertEqual(rows[-1].equity, 19_985)

    def test_corporate_action_before_ex_date_trading(self):
        bars = [
            AShareBar(day, close, close, close, close, close)
            for day, close in zip(
                ["2024-01-01", "2024-01-02", "2024-01-03"], [100.0, 100.0, 90.0]
            )
        ]
        action = CorporateAction("2024-01-03", "2024-01-02", 10, 0.1, 0)
        config = AShareConfig(
            initial_cash=20_000, commission_rate=0, min_commission=0, slippage_bps=0
        )
        rows, _ = run_a_share_backtest(bars, [action], config=config, signals=[1, 1, 1])
        self.assertEqual(rows[-1].dividend_cash, 2_000)
        self.assertAlmostEqual(rows[-1].shares, 220)
        self.assertAlmostEqual(rows[-1].equity, 21_800)

    def test_stamp_duty_boundary(self):
        self.assertEqual(stamp_duty_rate("2023-08-27"), 0.001)
        self.assertEqual(stamp_duty_rate("2023-08-28"), 0.0005)


class ASharePipelineTests(unittest.TestCase):
    def _write_inputs(self, root: Path, mismatch: bool = False) -> tuple[Path, Path, Path]:
        raw_path = root / "raw.csv"
        adjusted_path = root / "adjusted.csv"
        events_path = root / "events.csv"
        fields = ["date", "open", "high", "low", "close"]
        start = date(2023, 1, 1)
        with raw_path.open("w", encoding="utf-8", newline="") as raw_handle, adjusted_path.open(
            "w", encoding="utf-8", newline=""
        ) as adjusted_handle:
            raw_writer = csv.DictWriter(raw_handle, fieldnames=fields)
            adjusted_writer = csv.DictWriter(adjusted_handle, fieldnames=fields)
            raw_writer.writeheader()
            adjusted_writer.writeheader()
            for index in range(90):
                current = (start + timedelta(days=index)).isoformat()
                close = 100 + index
                raw_writer.writerow(
                    {"date": current, "open": close, "high": close, "low": close, "close": close}
                )
                adjusted_date = (start + timedelta(days=index + 1)).isoformat() if mismatch and index == 89 else current
                adjusted_writer.writerow(
                    {"date": adjusted_date, "open": close, "high": close, "low": close, "close": close}
                )
        events_path.write_text(
            "ex_date,record_date,cash_dividend_per_share,stock_dividend_ratio,transfer_ratio\n",
            encoding="utf-8",
        )
        return raw_path, adjusted_path, events_path

    def test_three_segments_benchmark_and_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw, adjusted, events = self._write_inputs(root)
            baseline = execute(
                "start",
                raw,
                adjusted_data_path=adjusted,
                events_path=events,
                fast=2,
                slow=5,
                output_root=root / "runs",
                validation_start="2023-02-01",
                test_start="2023-03-01",
                data_source="synthetic fixture",
            )
            self.assertEqual(set(baseline["metrics"]), {"train", "validation", "test"})
            self.assertEqual(baseline["benchmark"]["name"], "buy_and_hold")
            self.assertEqual(baseline["data"]["train_rows"], 31)
            self.assertEqual(baseline["data"]["validation_rows"], 28)
            self.assertEqual(baseline["data"]["test_rows"], 31)
            run_dir = root / "runs" / baseline["run_id"]
            for name in baseline["artifacts"].values():
                self.assertTrue((run_dir / name).is_file(), name)
            baseline_path = run_dir / "result.json"
            original = baseline_path.read_bytes()
            candidate = execute(
                "evo",
                raw,
                adjusted_data_path=adjusted,
                events_path=events,
                fast=2,
                slow=5,
                output_root=root / "runs",
                baseline_path=baseline_path,
                validation_start="2023-02-01",
                test_start="2023-03-01",
            )
            self.assertEqual(candidate["decision"]["evaluation_segment"], "validation")
            self.assertIn("validation_sharpe", {gate["name"] for gate in candidate["gates"]})
            self.assertFalse(candidate["decision"]["accepted"])
            self.assertEqual(baseline_path.read_bytes(), original)

    def test_mismatched_adjusted_dates_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = self._write_inputs(Path(temporary), mismatch=True)
            with self.assertRaisesRegex(ValueError, "dates must match"):
                load_a_share_data(*paths)


if __name__ == "__main__":
    unittest.main()

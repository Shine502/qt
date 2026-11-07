import unittest

from runtime.quant_cn.backtest import Bar, BacktestRow, calculate_metrics, run_backtest


class BacktestTests(unittest.TestCase):
    def test_signal_is_executed_on_next_bar(self):
        bars = [Bar(day, close) for day, close in zip(
            ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"],
            [1.0, 1.0, 1.0, 2.0, 1.0],
        )]
        rows = run_backtest(bars, fast=1, slow=2, fee_bps=0)
        self.assertEqual(rows[3].signal, 1)
        self.assertEqual(rows[3].position, 0)
        self.assertEqual(rows[4].position, 1)
        self.assertAlmostEqual(rows[4].net_return, -0.5)

    def test_entry_fee_is_charged_once(self):
        bars = [Bar(f"2024-01-0{index + 1}", close) for index, close in enumerate([1, 1, 1, 2, 2])]
        rows = run_backtest(bars, fast=1, slow=2, fee_bps=10)
        self.assertAlmostEqual(rows[4].turnover, 1)
        self.assertAlmostEqual(rows[4].net_return, -0.001)

    def test_metrics_reconcile_compounded_returns(self):
        rows = [
            BacktestRow("2024-01-01", 1, 0, 0, 1, 0, 0.1, 1.1),
            BacktestRow("2024-01-02", 1, 0, 0, 1, 0, -0.05, 1.045),
        ]
        metrics = calculate_metrics(rows)
        self.assertAlmostEqual(metrics["total_return"], 0.045)
        self.assertAlmostEqual(metrics["max_drawdown"], 0.05)
        self.assertEqual(metrics["rows"], 2)


if __name__ == "__main__":
    unittest.main()

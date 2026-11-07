import math
import unittest

from runtime.quant_cn.gates import evaluate_gates, evaluate_relative_gates
from runtime.quant_cn.pipeline import load_policy


class GateTests(unittest.TestCase):
    def setUp(self):
        self.policy = load_policy()
        self.metrics = {
            "rows": 20,
            "total_return": 0.1,
            "sharpe": 1.0,
            "max_drawdown": 0.05,
            "annualized_volatility": 0.2,
        }

    def test_non_finite_metric_fails_closed(self):
        self.metrics["sharpe"] = math.nan
        gates = evaluate_gates(self.metrics, self.policy)
        gate = next(item for item in gates if item.name == "test_sharpe")
        self.assertFalse(gate.passed)
        self.assertIsNone(gate.actual)

    def test_threshold_boundary_passes(self):
        self.metrics["max_drawdown"] = self.policy["max_test_drawdown"]
        gates = evaluate_gates(self.metrics, self.policy)
        self.assertTrue(next(item for item in gates if item.name == "test_max_drawdown").passed)

    def test_evolution_requires_same_data_and_improvement(self):
        gates = evaluate_relative_gates(self.metrics, self.metrics, self.policy, same_dataset=False)
        self.assertFalse(all(gate.passed for gate in gates))
        self.assertFalse(next(gate for gate in gates if gate.name == "same_dataset").passed)
        self.assertFalse(next(gate for gate in gates if gate.name == "sharpe_improvement").passed)


if __name__ == "__main__":
    unittest.main()

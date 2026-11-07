import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from runtime.quant_cn.data import load_bars
from runtime.quant_cn.pipeline import execute

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "prices.csv"


class PipelineTests(unittest.TestCase):
    def test_start_and_evolution_decision(self):
        with tempfile.TemporaryDirectory() as temporary:
            baseline = execute("start", FIXTURE, output_root=temporary)
            self.assertTrue(baseline["decision"]["accepted"])
            self.assertEqual(baseline["state"], "COMPLETED")
            baseline_path = Path(temporary) / baseline["run_id"] / "result.json"
            original = baseline_path.read_bytes()
            candidate = execute(
                "evo", FIXTURE, output_root=temporary, baseline_path=baseline_path
            )
            self.assertFalse(candidate["decision"]["accepted"])
            self.assertEqual(candidate["state"], "REJECTED")
            self.assertFalse(candidate["decision"]["baseline_modified"])
            self.assertEqual(baseline_path.read_bytes(), original)

    def test_duplicate_dates_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bad.csv"
            path.write_text("date,close\n2024-01-01,1\n2024-01-01,2\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "strictly increasing"):
                load_bars(path)

    def test_controller_end_to_end(self):
        with tempfile.TemporaryDirectory() as temporary:
            completed = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "qt.py"), "start", "--data", str(FIXTURE), "--output", temporary],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            summary = json.loads(completed.stdout)
            result_path = Path(summary["run_dir"]) / "result.json"
            self.assertTrue(result_path.is_file())
            status = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "qt.py"), "status", "--run", summary["run_dir"]],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertEqual(json.loads(status.stdout)["state"], "COMPLETED")


if __name__ == "__main__":
    unittest.main()

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PluginStructureTests(unittest.TestCase):
    def test_manifest_and_public_entries(self):
        manifest = json.loads((ROOT / "kimi.plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["name"], "qt")
        self.assertEqual(manifest["commands"], "./commands/")
        self.assertEqual(manifest["skills"], "./skills/")
        self.assertEqual(manifest["agents"], "./agents/")
        self.assertTrue((ROOT / "commands" / "start.md").is_file())
        self.assertTrue((ROOT / "commands" / "evo.md").is_file())

    def test_two_leads_and_six_specialists(self):
        agents = sorted((ROOT / "agents").glob("*.md"))
        self.assertEqual(len(agents), 8)
        for agent in agents:
            content = agent.read_text(encoding="utf-8")
            self.assertTrue(content.startswith("---\n"))
            self.assertIn("description:", content)

    def test_fixture_is_explicitly_synthetic(self):
        self.assertIn("synthetic", (ROOT / "tests" / "fixtures" / "README.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "tradingagents" / "agents" / "utils" / "factor_rules.py"
SPEC = importlib.util.spec_from_file_location("factor_rules", MODULE_PATH)
factor_rules = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(factor_rules)

_candidate_rule_paths = factor_rules._candidate_rule_paths
load_factor_rules = factor_rules.load_factor_rules


class FactorRulesPathTests(unittest.TestCase):
    def test_candidate_paths_are_deduplicated(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            examples_dir = project_dir / "examples"
            examples_dir.mkdir()
            rule_path = examples_dir / "factor_rules.json"
            rule_path.write_text(json.dumps({"rules": []}), encoding="utf-8")

            config = {
                "project_dir": str(project_dir),
                "factor_rules_path": str(rule_path),
            }

            original_env = factor_rules.os.environ.get("TRADINGAGENTS_FACTOR_RULES_PATH")
            factor_rules.os.environ["TRADINGAGENTS_FACTOR_RULES_PATH"] = str(rule_path)
            try:
                paths = _candidate_rule_paths(config)
            finally:
                if original_env is None:
                    factor_rules.os.environ.pop("TRADINGAGENTS_FACTOR_RULES_PATH", None)
                else:
                    factor_rules.os.environ["TRADINGAGENTS_FACTOR_RULES_PATH"] = original_env

            self.assertEqual(paths.count(rule_path.resolve()), 1)

    def test_load_factor_rules_accepts_rules_object(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            examples_dir = project_dir / "examples"
            examples_dir.mkdir()
            rule_path = examples_dir / "factor_rules.json"
            payload = {"rules": [{"name": "Value", "signal": "bullish"}]}
            rule_path.write_text(json.dumps(payload), encoding="utf-8")

            rules, loaded_path = load_factor_rules({"project_dir": str(project_dir)})
            self.assertEqual(rules, payload["rules"])
            self.assertEqual(Path(loaded_path), rule_path.resolve())

    def test_outside_project_rule_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as project_tmp, tempfile.TemporaryDirectory() as outside_tmp:
            project_dir = Path(project_tmp)
            outside_path = Path(outside_tmp) / "factor_rules.json"
            outside_path.write_text(json.dumps({"rules": [{"name": "Outside"}]}), encoding="utf-8")

            rules, loaded_path = load_factor_rules(
                {
                    "project_dir": str(project_dir),
                    "factor_rules_path": str(outside_path),
                }
            )

            self.assertEqual(rules, [])
            self.assertIsNone(loaded_path)


if __name__ == "__main__":
    unittest.main()

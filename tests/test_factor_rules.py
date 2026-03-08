import ast
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "tradingagents" / "agents" / "utils" / "factor_rules.py"
GRAPH_SETUP_PATH = Path(__file__).resolve().parents[1] / "tradingagents" / "graph" / "setup.py"
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "tradingagents" / "default_config.py"
FACTOR_RULE_ANALYST_PATH = Path(__file__).resolve().parents[1] / "tradingagents" / "agents" / "analysts" / "factor_rule_analyst.py"
SPEC = importlib.util.spec_from_file_location("factor_rules", MODULE_PATH)
factor_rules = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(factor_rules)

_candidate_rule_paths = factor_rules._candidate_rule_paths
load_factor_rules = factor_rules.load_factor_rules
summarize_factor_rules = factor_rules.summarize_factor_rules


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

    def test_load_factor_rules_accepts_top_level_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            examples_dir = project_dir / "examples"
            examples_dir.mkdir()
            rule_path = examples_dir / "factor_rules.json"
            payload = [{"name": "Value", "signal": "bullish"}]
            rule_path.write_text(json.dumps(payload), encoding="utf-8")

            rules, loaded_path = load_factor_rules({"project_dir": str(project_dir)})
            self.assertEqual(rules, payload)
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

    def test_non_standard_rule_filename_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            examples_dir = project_dir / "examples"
            examples_dir.mkdir()
            wrong_name = examples_dir / "manual_rules.json"
            wrong_name.write_text(json.dumps({"rules": [{"name": "Ignored"}]}), encoding="utf-8")

            rules, loaded_path = load_factor_rules(
                {
                    "project_dir": str(project_dir),
                    "factor_rules_path": str(wrong_name),
                }
            )

            self.assertEqual(rules, [])
            self.assertIsNone(loaded_path)

    def test_missing_explicit_rule_path_does_not_fall_back_silently(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            examples_dir = project_dir / "examples"
            examples_dir.mkdir()
            default_rule_path = examples_dir / "factor_rules.json"
            default_rule_path.write_text(json.dumps({"rules": [{"name": "Default"}]}), encoding="utf-8")
            missing_explicit_path = project_dir / "factor_rules.json"
            missing_explicit_path.unlink(missing_ok=True)

            rules, loaded_path = load_factor_rules(
                {
                    "project_dir": str(project_dir),
                    "factor_rules_path": str(missing_explicit_path),
                }
            )

            self.assertEqual(rules, [])
            self.assertEqual(Path(loaded_path), missing_explicit_path.resolve())

    def test_invalid_rules_object_raises_value_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            examples_dir = project_dir / "examples"
            examples_dir.mkdir()
            rule_path = examples_dir / "factor_rules.json"
            rule_path.write_text(json.dumps({"rules": {"name": "bad-shape"}}), encoding="utf-8")

            with self.assertRaises(ValueError):
                load_factor_rules({"project_dir": str(project_dir)})

    def test_invalid_top_level_payload_returns_empty_rules(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            examples_dir = project_dir / "examples"
            examples_dir.mkdir()
            rule_path = examples_dir / "factor_rules.json"
            rule_path.write_text(json.dumps("unexpected-string"), encoding="utf-8")

            rules, loaded_path = load_factor_rules({"project_dir": str(project_dir)})
            self.assertEqual(rules, [])
            self.assertEqual(Path(loaded_path), rule_path.resolve())

    def test_summarize_factor_rules_counts_biases(self):
        summary = summarize_factor_rules(
            [
                {"name": "Value", "signal": "bullish", "weight": "high"},
                {"name": "Momentum", "signal": "bearish", "weight": "medium"},
                {"name": "Quality", "signal": "neutral", "weight": "low"},
            ],
            ticker="AAPL",
            trade_date="2026-03-07",
        )

        self.assertIn("Loaded 3 manually curated factor rules.", summary)
        self.assertIn("- Bullish leaning rules: 1", summary)
        self.assertIn("- Bearish leaning rules: 1", summary)
        self.assertIn("- Neutral / mixed rules: 1", summary)

    def test_summarize_factor_rules_empty_list_warns_against_fabrication(self):
        summary = summarize_factor_rules([], ticker="MSFT", trade_date="2026-03-07")
        self.assertIn("No factor rules were loaded", summary)
        self.assertIn("do not fabricate rule-based signals", summary)

    def test_summarize_factor_rules_treats_signal_case_insensitively(self):
        summary = summarize_factor_rules(
            [
                {"name": "Value", "signal": "BULLISH"},
                {"name": "Quality", "signal": "Negative"},
                {"name": "Balance", "signal": "NeUtRaL"},
            ],
            ticker="NVDA",
            trade_date="2026-03-07",
        )

        self.assertIn("- Bullish leaning rules: 1", summary)
        self.assertIn("- Bearish leaning rules: 1", summary)
        self.assertIn("- Neutral / mixed rules: 1", summary)

    def test_summarize_factor_rules_counts_buy_sell_aliases(self):
        summary = summarize_factor_rules(
            [
                {"name": "Value", "signal": "buy"},
                {"name": "Quality", "signal": "sell"},
                {"name": "Balance", "signal": "hold"},
            ],
            ticker="TSLA",
            trade_date="2026-03-07",
        )

        self.assertIn("- Bullish leaning rules: 1", summary)
        self.assertIn("- Bearish leaning rules: 1", summary)
        self.assertIn("- Neutral / mixed rules: 1", summary)

    def test_summarize_factor_rules_includes_default_rule_name(self):
        summary = summarize_factor_rules(
            [{"signal": "bullish", "weight": "high"}],
            ticker="META",
            trade_date="2026-03-07",
        )

        self.assertIn("Rule 1: Rule 1", summary)
        self.assertIn("- Signal bias: bullish", summary)
        self.assertIn("- Weight: high", summary)

    def test_summarize_factor_rules_defaults_missing_conditions(self):
        summary = summarize_factor_rules(
            [{"name": "Liquidity", "signal": "neutral", "rationale": "No screen provided"}],
            ticker="AMD",
            trade_date="2026-03-07",
        )

        self.assertIn("- Conditions: No explicit conditions provided", summary)
        self.assertIn("- Rationale: No screen provided", summary)

    def test_summarize_factor_rules_stringifies_non_string_conditions(self):
        summary = summarize_factor_rules(
            [{"name": "Macro", "signal": "neutral", "conditions": [1, True, 3.14]}],
            ticker="QQQ",
            trade_date="2026-03-07",
        )

        self.assertIn("- Conditions: 1; True; 3.14", summary)

    def test_summarize_factor_rules_defaults_missing_thesis_to_empty_string(self):
        summary = summarize_factor_rules(
            [{"name": "Sentiment", "signal": "bullish", "rationale": "Momentum improving"}],
            ticker="AMZN",
            trade_date="2026-03-07",
        )

        self.assertIn("- Thesis: ", summary)
        self.assertIn("- Rationale: Momentum improving", summary)

    def test_summarize_factor_rules_defaults_missing_weight_to_medium(self):
        summary = summarize_factor_rules(
            [{"name": "Value", "signal": "bullish", "thesis": "Cheap relative to peers"}],
            ticker="NFLX",
            trade_date="2026-03-07",
        )

        self.assertIn("- Weight: medium", summary)
        self.assertIn("- Thesis: Cheap relative to peers", summary)

    def test_summarize_factor_rules_preserves_blank_rationale_line(self):
        summary = summarize_factor_rules(
            [{"name": "Carry", "signal": "neutral", "thesis": "Range-bound"}],
            ticker="SPY",
            trade_date="2026-03-07",
        )

        self.assertIn("- Rationale: ", summary)
        self.assertIn("- Thesis: Range-bound", summary)

    def test_summarize_factor_rules_preserves_blank_signal_line(self):
        summary = summarize_factor_rules(
            [{"name": "Carry", "weight": "low", "thesis": "Sideways"}],
            ticker="DIA",
            trade_date="2026-03-07",
        )

        self.assertIn("- Signal bias: neutral", summary)
        self.assertIn("- Weight: low", summary)

    def test_summarize_factor_rules_preserves_explicit_empty_conditions(self):
        summary = summarize_factor_rules(
            [{"name": "Carry", "signal": "neutral", "conditions": []}],
            ticker="IWM",
            trade_date="2026-03-07",
        )

        self.assertIn("- Conditions: No explicit conditions provided", summary)

    def test_summarize_factor_rules_preserves_explicit_empty_rationale(self):
        summary = summarize_factor_rules(
            [{"name": "Carry", "signal": "neutral", "rationale": ""}],
            ticker="XLF",
            trade_date="2026-03-07",
        )

        self.assertIn("- Rationale: ", summary)

    def test_summarize_factor_rules_preserves_empty_name_as_blank_label(self):
        summary = summarize_factor_rules(
            [{"name": "", "signal": "neutral"}],
            ticker="TLT",
            trade_date="2026-03-07",
        )

        self.assertIn("Rule 1: ", summary)
        self.assertIn("- Signal bias: neutral", summary)

    def test_summarize_factor_rules_defaults_missing_name_to_rule_index(self):
        summary = summarize_factor_rules(
            [{"signal": "neutral"}],
            ticker="GLD",
            trade_date="2026-03-07",
        )

        self.assertIn("Rule 1: Rule 1", summary)
        self.assertIn("- Signal bias: neutral", summary)

    def test_summarize_factor_rules_preserves_zero_weight_value(self):
        summary = summarize_factor_rules(
            [{"name": "Carry", "signal": "neutral", "weight": 0}],
            ticker="USO",
            trade_date="2026-03-07",
        )

        self.assertIn("- Weight: 0", summary)

    def test_summarize_factor_rules_preserves_false_weight_value(self):
        summary = summarize_factor_rules(
            [{"name": "Carry", "signal": "neutral", "weight": False}],
            ticker="SLV",
            trade_date="2026-03-07",
        )

        self.assertIn("- Weight: False", summary)

    def test_summarize_factor_rules_stringifies_dict_conditions(self):
        summary = summarize_factor_rules(
            [{"name": "Carry", "signal": "neutral", "conditions": [{"threshold": 5}]}],
            ticker="HYG",
            trade_date="2026-03-07",
        )

        self.assertIn("- Conditions: {'threshold': 5}", summary)

    def test_summarize_factor_rules_stringifies_tuple_conditions(self):
        summary = summarize_factor_rules(
            [{"name": "Carry", "signal": "neutral", "conditions": [("threshold", 5)]}],
            ticker="LQD",
            trade_date="2026-03-07",
        )

        self.assertIn("- Conditions: ('threshold', 5)", summary)

    def test_summarize_factor_rules_preserves_none_conditions_value(self):
        summary = summarize_factor_rules(
            [{"name": "Carry", "signal": "neutral", "conditions": [None, "fallback"]}],
            ticker="IEF",
            trade_date="2026-03-07",
        )

        self.assertIn("- Conditions: None; fallback", summary)

    def test_summarize_factor_rules_preserves_empty_condition_entries(self):
        summary = summarize_factor_rules(
            [{"name": "Carry", "signal": "neutral", "conditions": ["", "macro-ok"]}],
            ticker="IEF",
            trade_date="2026-03-07",
        )

        self.assertIn("- Conditions: ; macro-ok", summary)

    def test_summarize_factor_rules_preserves_empty_string_condition_entries(self):
        summary = summarize_factor_rules(
            [{"name": "Carry", "signal": "neutral", "conditions": ["", "fallback"]}],
            ticker="IEF",
            trade_date="2026-03-07",
        )

        self.assertIn("- Conditions: ; fallback", summary)

    def test_summarize_factor_rules_preserves_empty_string_condition(self):
        summary = summarize_factor_rules(
            [{"name": "Carry", "signal": "neutral", "conditions": [""]}],
            ticker="IEF",
            trade_date="2026-03-07",
        )

        self.assertIn("- Conditions: ", summary)


class GraphSetupSourceTests(unittest.TestCase):
    def test_setup_graph_avoids_mutable_default_selected_analysts(self):
        source = GRAPH_SETUP_PATH.read_text(encoding="utf-8")
        module = ast.parse(source)

        setup_graph = None
        for node in module.body:
            if isinstance(node, ast.ClassDef) and node.name == "GraphSetup":
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == "setup_graph":
                        setup_graph = item
                        break

        self.assertIsNotNone(setup_graph)
        self.assertEqual(len(setup_graph.args.defaults), 1)
        self.assertIsInstance(setup_graph.args.defaults[0], ast.Constant)
        self.assertIsNone(setup_graph.args.defaults[0].value)
        self.assertIn('selected_analysts = ["market", "social", "news", "fundamentals", "factor_rules"]', source)


class DefaultConfigSourceTests(unittest.TestCase):
    def test_default_headers_is_opt_in_none(self):
        source = DEFAULT_CONFIG_PATH.read_text(encoding="utf-8")
        module = ast.parse(source)

        default_config_value = None
        for node in module.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "DEFAULT_CONFIG":
                        default_config_value = node.value
                        break

        self.assertIsNotNone(default_config_value)
        self.assertIsInstance(default_config_value, ast.Dict)

        config_map = {}
        for key_node, value_node in zip(default_config_value.keys, default_config_value.values):
            if isinstance(key_node, ast.Constant):
                config_map[key_node.value] = value_node

        self.assertIn("default_headers", config_map)
        self.assertIsInstance(config_map["default_headers"], ast.Constant)
        self.assertIsNone(config_map["default_headers"].value)
        self.assertIn('"default_headers": None', source)


class FactorRuleAnalystSourceTests(unittest.TestCase):
    def test_factor_rule_analyst_short_circuits_when_rules_missing(self):
        source = FACTOR_RULE_ANALYST_PATH.read_text(encoding="utf-8")
        module = ast.parse(source)

        create_fn = None
        for node in module.body:
            if isinstance(node, ast.FunctionDef) and node.name == "create_factor_rule_analyst":
                create_fn = node
                break

        self.assertIsNotNone(create_fn)
        self.assertIn("if not rules:", source)
        self.assertIn('"messages": []', source)
        self.assertIn('"factor_rules_report": summary', source)


if __name__ == "__main__":
    unittest.main()

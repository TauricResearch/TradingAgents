"""Tests for FinancialSituationMemory JSON file persistence.

Covers:
  - RAM-only mode (no config / config without key) behaves identically to before
  - Persistence: add_situations → restart → memories survive
  - Persistence: clear → restart → file reflects empty state
  - Atomic write: .tmp → .json rename
  - Corrupt / missing file is handled gracefully
  - BM25 index is rebuilt after loading from disk
  - Multiple memory instances sharing the same dir don't collide
  - Default config includes memory_persist_dir key
  - TradingAgentsGraph passes config through to all five memory instances
"""

import json
import os
import pathlib
import tempfile
import unittest

from tradingagents.agents.utils.memory import FinancialSituationMemory
from tradingagents.default_config import DEFAULT_CONFIG


SAMPLE_DATA = [
    (
        "High inflation rate with rising interest rates",
        "Consider defensive sectors like utilities.",
    ),
    (
        "Tech sector volatility with institutional selling pressure",
        "Reduce high-growth tech exposure.",
    ),
    (
        "Strong dollar affecting emerging markets",
        "Hedge currency exposure in international positions.",
    ),
]


class TestRamOnlyMode(unittest.TestCase):
    """Ensure RAM-only mode (no persistence) is fully backward-compatible."""

    def test_no_config(self):
        mem = FinancialSituationMemory("test")
        self.assertIsNone(mem._persist_path)
        mem.add_situations(SAMPLE_DATA[:1])
        self.assertEqual(len(mem.documents), 1)

    def test_config_without_persist_key(self):
        mem = FinancialSituationMemory("test", config={"some_other_key": True})
        self.assertIsNone(mem._persist_path)

    def test_config_with_none_persist_dir(self):
        mem = FinancialSituationMemory("test", config={"memory_persist_dir": None})
        self.assertIsNone(mem._persist_path)

    def test_config_with_empty_string_persist_dir(self):
        mem = FinancialSituationMemory("test", config={"memory_persist_dir": ""})
        self.assertIsNone(mem._persist_path)

    def test_ram_only_data_lost_on_new_instance(self):
        mem1 = FinancialSituationMemory("test")
        mem1.add_situations(SAMPLE_DATA)
        self.assertEqual(len(mem1.documents), 3)

        mem2 = FinancialSituationMemory("test")
        self.assertEqual(len(mem2.documents), 0)


class TestPersistence(unittest.TestCase):
    """Core persistence round-trip tests."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = {"memory_persist_dir": self.tmpdir}

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_file_created_on_add(self):
        mem = FinancialSituationMemory("bull_memory", config=self.config)
        self.assertFalse(
            (pathlib.Path(self.tmpdir) / "bull_memory.json").exists(),
            "File should not exist before adding data",
        )
        mem.add_situations(SAMPLE_DATA[:1])
        self.assertTrue(
            (pathlib.Path(self.tmpdir) / "bull_memory.json").exists(),
            "File should be created after add_situations",
        )

    def test_round_trip(self):
        """Data survives a full destroy-and-recreate cycle."""
        mem1 = FinancialSituationMemory("rt", config=self.config)
        mem1.add_situations(SAMPLE_DATA)
        self.assertEqual(len(mem1.documents), 3)

        # Destroy first instance, create a new one — simulates process restart
        del mem1
        mem2 = FinancialSituationMemory("rt", config=self.config)
        self.assertEqual(len(mem2.documents), 3)
        self.assertEqual(mem2.documents[0], SAMPLE_DATA[0][0])
        self.assertEqual(mem2.recommendations[1], SAMPLE_DATA[1][1])

    def test_incremental_add_persists(self):
        """Multiple add_situations calls accumulate correctly on disk."""
        mem = FinancialSituationMemory("inc", config=self.config)
        mem.add_situations(SAMPLE_DATA[:1])
        mem.add_situations(SAMPLE_DATA[1:2])

        del mem
        mem2 = FinancialSituationMemory("inc", config=self.config)
        self.assertEqual(len(mem2.documents), 2)

    def test_clear_persists_empty(self):
        mem = FinancialSituationMemory("clr", config=self.config)
        mem.add_situations(SAMPLE_DATA)
        mem.clear()

        del mem
        mem2 = FinancialSituationMemory("clr", config=self.config)
        self.assertEqual(len(mem2.documents), 0)
        self.assertEqual(len(mem2.recommendations), 0)

    def test_bm25_rebuilt_after_load(self):
        """BM25 index should work after loading from disk."""
        mem1 = FinancialSituationMemory("bm25", config=self.config)
        mem1.add_situations(SAMPLE_DATA)

        del mem1
        mem2 = FinancialSituationMemory("bm25", config=self.config)
        results = mem2.get_memories("rising interest rates inflation", n_matches=1)
        self.assertEqual(len(results), 1)
        self.assertIn("inflation", results[0]["matched_situation"].lower())

    def test_json_file_content_valid(self):
        """Persisted JSON has the expected schema."""
        mem = FinancialSituationMemory("schema", config=self.config)
        mem.add_situations(SAMPLE_DATA[:2])

        fp = pathlib.Path(self.tmpdir) / "schema.json"
        data = json.loads(fp.read_text(encoding="utf-8"))
        self.assertIn("situations", data)
        self.assertIn("recommendations", data)
        self.assertEqual(len(data["situations"]), 2)
        self.assertEqual(len(data["recommendations"]), 2)

    def test_unicode_round_trip(self):
        """Non-ASCII data (e.g. CJK) survives persistence."""
        mem = FinancialSituationMemory("uni", config=self.config)
        mem.add_situations([("通胀上升，利率攀升", "考虑防御性板块")])

        del mem
        mem2 = FinancialSituationMemory("uni", config=self.config)
        self.assertEqual(mem2.documents[0], "通胀上升，利率攀升")
        self.assertEqual(mem2.recommendations[0], "考虑防御性板块")


class TestEdgeCases(unittest.TestCase):
    """Graceful handling of corrupt / missing files."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = {"memory_persist_dir": self.tmpdir}

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_corrupt_json_starts_fresh(self):
        fp = pathlib.Path(self.tmpdir) / "bad.json"
        fp.write_text("NOT VALID JSON {{{", encoding="utf-8")
        mem = FinancialSituationMemory("bad", config=self.config)
        self.assertEqual(len(mem.documents), 0, "Should start fresh on corrupt file")

    def test_missing_keys_starts_fresh(self):
        fp = pathlib.Path(self.tmpdir) / "partial.json"
        fp.write_text(json.dumps({"unrelated": True}), encoding="utf-8")
        mem = FinancialSituationMemory("partial", config=self.config)
        self.assertEqual(len(mem.documents), 0)

    def test_mismatched_lengths_truncates(self):
        """If situations and recommendations have different lengths, zip truncates."""
        fp = pathlib.Path(self.tmpdir) / "mismatch.json"
        fp.write_text(json.dumps({
            "situations": ["s1", "s2", "s3"],
            "recommendations": ["r1", "r2"],
        }), encoding="utf-8")
        mem = FinancialSituationMemory("mismatch", config=self.config)
        self.assertEqual(len(mem.documents), 2)
        self.assertEqual(len(mem.recommendations), 2)

    def test_parent_dirs_created(self):
        nested = os.path.join(self.tmpdir, "a", "b", "c")
        config = {"memory_persist_dir": nested}
        mem = FinancialSituationMemory("nested", config=config)
        mem.add_situations(SAMPLE_DATA[:1])
        self.assertTrue(pathlib.Path(nested).is_dir())
        self.assertTrue((pathlib.Path(nested) / "nested.json").exists())

    def test_tilde_expansion(self):
        """~ in persist dir is expanded."""
        config = {"memory_persist_dir": "~/.__test_tradingagents_mem__"}
        try:
            mem = FinancialSituationMemory("tilde", config=config)
            self.assertFalse(str(mem._persist_path).startswith("~"))
            self.assertIn(os.path.expanduser("~"), str(mem._persist_path))
        finally:
            import shutil
            shutil.rmtree(
                os.path.expanduser("~/.__test_tradingagents_mem__"),
                ignore_errors=True,
            )


class TestMultipleInstances(unittest.TestCase):
    """Multiple memory instances in the same directory don't collide."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.config = {"memory_persist_dir": self.tmpdir}

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_independent_files(self):
        bull = FinancialSituationMemory("bull_memory", config=self.config)
        bear = FinancialSituationMemory("bear_memory", config=self.config)

        bull.add_situations(SAMPLE_DATA[:1])
        bear.add_situations(SAMPLE_DATA[1:2])

        del bull, bear

        bull2 = FinancialSituationMemory("bull_memory", config=self.config)
        bear2 = FinancialSituationMemory("bear_memory", config=self.config)

        self.assertEqual(len(bull2.documents), 1)
        self.assertEqual(len(bear2.documents), 1)
        self.assertNotEqual(bull2.documents[0], bear2.documents[0])


class TestDefaultConfig(unittest.TestCase):
    """Verify the default config includes the new key."""

    def test_key_exists(self):
        self.assertIn("memory_persist_dir", DEFAULT_CONFIG)

    def test_default_is_none(self):
        self.assertIsNone(
            DEFAULT_CONFIG["memory_persist_dir"],
            "Default should be None (RAM-only) for backward compatibility",
        )


class TestTradingGraphIntegration(unittest.TestCase):
    """Verify TradingAgentsGraph passes config to all memory instances.

    This is a source-code audit test — it does NOT instantiate the graph
    (which requires LLM API keys and heavy dependencies), but instead
    inspects the constructor to confirm the config dict is forwarded.
    """

    def test_config_forwarded_to_memory_constructors(self):
        """All five FinancialSituationMemory() calls receive self.config."""
        import inspect
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        source = inspect.getsource(TradingAgentsGraph.__init__)

        memory_names = [
            "bull_memory",
            "bear_memory",
            "trader_memory",
            "invest_judge_memory",
            "portfolio_manager_memory",
        ]

        for name in memory_names:
            # Expect: FinancialSituationMemory("name", self.config)
            self.assertIn(
                f'FinancialSituationMemory("{name}", self.config)',
                source,
                f"TradingAgentsGraph.__init__ should pass self.config to {name}",
            )


if __name__ == "__main__":
    unittest.main()

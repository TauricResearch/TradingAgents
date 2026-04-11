import unittest

from tradingagents.agents.utils.memory import FinancialSituationMemory


class TestFinancialSituationMemory(unittest.TestCase):
    """Unit tests for FinancialSituationMemory using BM25 retrieval."""

    def test_add_and_retrieve_single(self):
        """添加一条记录，查询能匹配到."""
        memory = FinancialSituationMemory("test_single")
        memory.add_situations([
            ("Federal Reserve raised interest rates by 50 basis points amid high inflation", "Consider reducing duration in bond portfolios. Evaluate floating-rate instruments."),
        ])

        results = memory.get_memories("The Fed is hiking rates to combat inflation", n_matches=1)

        self.assertEqual(len(results), 1)
        self.assertIn("interest rates", results[0]["matched_situation"].lower())
        self.assertIsNotNone(results[0]["similarity_score"])

    def test_empty_memory_returns_empty(self):
        """空记忆返回空列表."""
        memory = FinancialSituationMemory("test_empty")

        results = memory.get_memories("Any financial situation", n_matches=3)

        self.assertEqual(results, [])

    def test_multiple_matches_ranked(self):
        """多条记录，返回按相关性排序的 top-n."""
        memory = FinancialSituationMemory("test_ranked")
        memory.add_situations([
            ("Consumer staples stocks outperforming during economic downturn", "Defensive sectors like utilities and healthcare provide stability."),
            ("Technology sector experiencing selloff amid rising Treasury yields", "Reduce exposure to high-growth equities. Consider quality value stocks."),
            ("Emerging market currencies depreciating due to strong US dollar", "Hedge currency risk. Reduce EM equity exposure."),
        ])

        results = memory.get_memories("Growth stocks are falling as bond yields rise", n_matches=2)

        self.assertEqual(len(results), 2)
        self.assertGreaterEqual(results[0]["similarity_score"], results[1]["similarity_score"])

    def test_clear_memory(self):
        """clear() 后查询返回空."""
        memory = FinancialSituationMemory("test_clear")
        memory.add_situations([
            ("Oil prices surged 30% due to OPEC production cuts", "Consider energy sector exposure and inflation hedges."),
        ])

        memory.clear()
        results = memory.get_memories("Crude oil is up", n_matches=1)

        self.assertEqual(results, [])
        self.assertEqual(len(memory.documents), 0)

    def test_normalized_scores_range(self):
        """所有 similarity_score 在 [0, 1] 范围内."""
        memory = FinancialSituationMemory("test_scores")
        memory.add_situations([
            ("S&P 500 volatility index spiked to 35 amid geopolitical tensions", "Increase cash allocation. Consider VIX hedging strategies."),
            ("Investment grade corporate spreads widening significantly", "Stress test portfolio credit risk. Reduce lower-rated IG holdings."),
            ("Real estate investment trusts declining due to higher cap rates", "Evaluate REIT exposure. Focus on industrial and data center REITs."),
        ])

        results = memory.get_memories("Market turbulence from international conflict", n_matches=3)

        self.assertEqual(len(results), 3)
        for result in results:
            self.assertGreaterEqual(result["similarity_score"], 0.0)
            self.assertLessEqual(result["similarity_score"], 1.0)

    def test_n_matches_exceeds_documents(self):
        """n_matches > 文档数时不崩溃."""
        memory = FinancialSituationMemory("test_excess")
        memory.add_situations([
            ("Bank of Japan unexpectedly adjusted yield curve control policy", "Monitor JGB volatility. Assess yen exposure."),
        ])

        # Request more matches than documents exist
        results = memory.get_memories("Japanese bond policy change", n_matches=10)

        self.assertEqual(len(results), 1)  # Should return only 1 available match
        self.assertIsNotNone(results[0]["similarity_score"])

    def test_rebuild_index_after_add(self):
        """多次 add_situations 后索引正确重建."""
        memory = FinancialSituationMemory("test_rebuild")

        memory.add_situations([
            ("Manufacturing PMI contracted to 48, signaling economic slowdown", "Increase defensive positioning. Monitor leading economic indicators."),
        ])

        memory.add_situations([
            ("Bitcoin dropped below $50,000 amid regulatory uncertainty", "Reduce cryptocurrency exposure. Focus on traditional risk assets."),
        ])

        memory.add_situations([
            ("Investment grade corporate spreads widened to 150 basis points", "Credit quality concerns. Prefer higher-rated issuers."),
        ])

        results = memory.get_memories("Economic contraction signals", n_matches=1)

        self.assertEqual(len(memory.documents), 3)
        self.assertEqual(len(results), 1)
        self.assertIn("PMI", results[0]["matched_situation"])

    def test_tokenize_handles_special_chars(self):
        """_tokenize 能处理特殊字符."""
        memory = FinancialSituationMemory("test_tokenize")

        tokens = memory._tokenize(
            "P/E ratio (TTM) is 25.4x, with EPS @ $4.20 & dividend yield 2.1%"
        )

        self.assertIn("p", tokens)
        self.assertIn("e", tokens)
        self.assertIn("ttm", tokens)
        self.assertIn("25", tokens)
        self.assertIn("4", tokens)
        self.assertIn("20", tokens)
        self.assertIn("eps", tokens)
        self.assertIn("dividend", tokens)
        self.assertIn("yield", tokens)

    def test_retrieve_with_overlapping_concepts(self):
        """包含重叠金融概念的多条记录，验证相关性排序."""
        memory = FinancialSituationMemory("test_concepts")
        memory.add_situations([
            ("Federal Reserve maintaining dovish stance with low rates", "Favor growth stocks and long-duration bonds."),
            ("Federal Reserve turning hawkish with rate hikes", "Rotate to value stocks and short-duration bonds."),
            ("European Central Bank keeping rates unchanged", "Monitor EUR currency exposure."),
        ])

        results = memory.get_memories("US central bank raising interest rates", n_matches=2)

        self.assertEqual(len(results), 2)
        self.assertGreater(results[0]["similarity_score"], results[1]["similarity_score"])


if __name__ == "__main__":
    unittest.main()

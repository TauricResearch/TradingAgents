import unittest

from cli.message_buffer import MessageBuffer


class MessageBufferTests(unittest.TestCase):
    def setUp(self):
        self.buffer = MessageBuffer()
        self.buffer.init_for_analysis(["market", "news"])

    def test_current_report_tracks_most_recent_updated_section(self):
        self.buffer.update_report_section("market_report", "Market content")
        self.assertIn("Market Analysis", self.buffer.current_report)

        self.buffer.update_report_section("news_report", "News content")
        self.assertIn("News Analysis", self.buffer.current_report)
        self.assertNotIn("Market Analysis", self.buffer.current_report)

    def test_init_resets_last_updated_section(self):
        self.buffer.update_report_section("market_report", "Market content")
        self.assertEqual(self.buffer._last_updated_section, "market_report")

        self.buffer.init_for_analysis(["fundamentals"])
        self.assertIsNone(self.buffer._last_updated_section)
        self.assertIsNone(self.buffer.current_report)


if __name__ == "__main__":
    unittest.main()

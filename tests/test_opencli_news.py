import subprocess
import unittest
from unittest.mock import patch

from tradingagents.dataflows.exceptions import DataVendorUnavailable
from tradingagents.dataflows.opencli_news import _resolve_company_aliases, get_global_news, get_news


class OpenCliNewsTests(unittest.TestCase):
    @patch("tradingagents.dataflows.tushare._get_pro_client")
    @patch("tradingagents.dataflows.tushare._classify_market", return_value="a_share")
    @patch("tradingagents.dataflows.tushare._normalize_ts_code", return_value="002155.SZ")
    def test_resolve_company_aliases_prefers_tushare_name(
        self,
        _mock_normalize,
        _mock_market,
        mock_pro_client,
    ):
        class _BasicFrame:
            empty = False

            class _Row(dict):
                def get(self, key, default=None):
                    return super().get(key, default)

            @property
            def iloc(self):
                class _ILoc:
                    def __getitem__(_self, _idx):
                        return _BasicFrame._Row({"name": "金博股份", "fullname": "湖南金博碳素股份有限公司"})

                return _ILoc()

        mock_pro_client.return_value.stock_basic.return_value = _BasicFrame()

        aliases = _resolve_company_aliases("002155.SZ")

        self.assertEqual(aliases[0], "金博股份")
        self.assertIn("湖南金博碳素股份有限公司", aliases)
        self.assertIn("湖南金博碳素", aliases)
        self.assertIn("002155.SZ", aliases)

    @patch(
        "tradingagents.dataflows.opencli_news._resolve_company_aliases",
        return_value=["金博股份", "002155.SZ", "002155"],
    )
    @patch("tradingagents.dataflows.opencli_news.shutil.which", return_value="/usr/bin/opencli-rs")
    @patch("tradingagents.dataflows.opencli_news.subprocess.run")
    def test_get_news_aggregates_multiple_sources(self, mock_run, _mock_which, _mock_aliases):
        def _dispatch(cmd, **_kwargs):
            if cmd[1:3] == ["xueqiu", "search"]:
                return subprocess.CompletedProcess(
                    args=[],
                    returncode=0,
                    stdout='[{"name":"金博股份","symbol":"002155"}]',
                    stderr="",
                )
            if cmd[1:3] == ["weibo", "search"]:
                return subprocess.CompletedProcess(
                    args=[],
                    returncode=0,
                    stdout='[{"text":"金博股份讨论热度上升","url":"https://example.com/weibo"}]',
                    stderr="",
                )
            if cmd[1:3] == ["xiaohongshu", "search"]:
                return subprocess.CompletedProcess(
                    args=[],
                    returncode=0,
                    stdout='[{"title":"金博股份观察","url":"https://example.com/xhs"}]',
                    stderr="",
                )
            if cmd[1:3] == ["sinafinance", "news"]:
                return subprocess.CompletedProcess(
                    args=[],
                    returncode=0,
                    stdout='[{"content":"金博股份公告带动碳基材料板块走强","time":"2026-04-01 10:00:00","views":"5万"}]',
                    stderr="",
                )
            if cmd[1:3] == ["google", "news"]:
                return subprocess.CompletedProcess(
                    args=[],
                    returncode=0,
                    stdout='[{"title":"金博股份 headline","source":"CNBC","date":"2026-04-01","url":"https://example.com/news"}]',
                    stderr="",
                )
            if cmd[1:3] == ["google", "search"]:
                return subprocess.CompletedProcess(
                    args=[],
                    returncode=0,
                    stdout='[{"title":"百度一下，你就知道 - 金博股份","url":"https://example.com/search"}]',
                    stderr="",
                )
            raise AssertionError(f"Unexpected command: {cmd}")

        mock_run.side_effect = _dispatch

        result = get_news("NVDA", "2026-03-25", "2026-04-01")

        self.assertIn("Xueqiu Search", result)
        self.assertIn("Weibo Search", result)
        self.assertIn("Xiaohongshu Search", result)
        self.assertIn("Sina Finance A-Share Flash", result)
        self.assertIn("Google News", result)
        self.assertIn("Google Search (ZH)", result)
        self.assertIn("金博股份 headline", result)
        first_call = mock_run.call_args_list[0].args[0]
        self.assertEqual(first_call[0:4], ["/usr/bin/opencli-rs", "xueqiu", "search", "金博股份"])

    @patch("tradingagents.dataflows.opencli_news.shutil.which", return_value="/usr/bin/opencli-rs")
    @patch("tradingagents.dataflows.opencli_news.subprocess.run")
    def test_get_global_news_aggregates_market_sources(self, mock_run, _mock_which):
        mock_run.side_effect = [
            subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout='[{"title":"Macro headline","source":"Reuters","date":"2026-04-01","url":"https://example.com/google"}]',
                stderr="",
            ),
            subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout='[{"content":"Flash item","time":"2026-04-01 15:50:00","views":"10万"}]',
                stderr="",
            ),
            subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout='[{"text":"Hot Xueqiu post","author":"alice","likes":12,"url":"https://example.com/xq"}]',
                stderr="",
            ),
            subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout='[{"word":"Top Weibo topic","category":"财经","hot_value":12345,"url":"https://example.com/wb"}]',
                stderr="",
            ),
        ]

        result = get_global_news("2026-04-01", 7, 5)

        self.assertIn("Google News Top Stories", result)
        self.assertIn("Sina Finance Flash News", result)
        self.assertIn("Xueqiu Hot Discussions", result)
        self.assertIn("Weibo Hot Topics", result)

    @patch("tradingagents.dataflows.opencli_news.shutil.which", return_value="/usr/bin/opencli-rs")
    @patch("tradingagents.dataflows.opencli_news.subprocess.run")
    def test_opencli_failures_surface_in_no_results_message(self, mock_run, _mock_which):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="",
            stderr="browser disconnected",
        )

        result = get_news("NVDA", "2026-03-25", "2026-04-01")

        self.assertIn("No relevant news found via opencli-rs", result)
        self.assertIn("browser disconnected", result)


if __name__ == "__main__":
    unittest.main()

"""The executor's accounts (ADR 0010): a profile says which account the executor is, and
with it the ledger, the lock, the throttle of the failure alerts, what follows a kill, the
label on every message, and the environment its client must be of."""

import pytest

from tests.test_demo_account import BTC, HOUR, T0, FakeExchange
from tests.test_demo_job import RUN0, Clock, Env
from tests.test_trader_paper import FakeOKX
from trader import backup
from trader.demo import job, report
from trader.demo.account import DEMO, DemoAccount, Profile
from trader.intraday.paper import HOUR_MS, IntradayPaper
from trader.ledger import Ledger
from trader.live import account as live
from trader.okx import OKXError
from trader.paper import Paper, _kill_alert
from trader.settings import Settings

# The live account's profile as the executor sees it, built here to test the executor on
# its own: trader.live.account holds the one the commands use.
LIVE = Profile("live", production=True, kill_final=True)


def live_account(env):
    """A live account beside ``env``'s demo, on a production client, opened like the demo."""
    ledger = Ledger(env.settings.live_ledger_path)
    ledger.initialize(10_000.0, T0 - HOUR_MS)
    ledger.set("setup_done", True)
    ledger.set("summarized_day", "2026-01-10")
    exchange = FakeExchange()
    exchange.simulated = False
    account = DemoAccount(ledger, env.okx, exchange, watchlist=(BTC,), sleep=lambda s: None, profile=LIVE)
    return account, exchange


def run(env, account, exchange, now_ms):
    clock = Clock(now_ms)
    exchange.now = now_ms
    job.run(env.settings, account, env.inbox, env.intraday, now_fn=clock.now, sleep=clock.sleep)


def test_each_account_has_its_own_ledger_lock_throttle_and_resume_command(tmp_path):
    settings = Settings(home=tmp_path)
    assert (DEMO.ledger_path(settings), DEMO.lock_path(settings)) == (settings.demo_ledger_path, settings.demo_lock_path)
    assert (LIVE.ledger_path(settings), LIVE.lock_path(settings)) == (
        tmp_path / "live" / "ledger.sqlite", tmp_path / "live" / "trader.lock",
    )
    assert settings.live_ledger_path in [tmp_path / rel for rel in backup.LEDGERS]
    assert (DEMO.alerted_key, LIVE.alerted_key) == ("demo_alerted_at", "live_alerted_at")
    assert (DEMO.resume_command, LIVE.resume_command) == (
        "python -m trader demo resume", "python -m trader live resume",
    )


def test_an_account_refuses_a_client_of_the_other_environment(tmp_path):
    ledger = Ledger(tmp_path / "ledger.sqlite")
    production = FakeExchange()
    production.simulated = False
    with pytest.raises(ValueError, match="demo account trades on OKX's simulated trading"):
        DemoAccount(ledger, FakeOKX(), production)
    with pytest.raises(ValueError, match="live account trades on OKX's production environment"):
        DemoAccount(ledger, FakeOKX(), FakeExchange(), profile=LIVE)
    assert DemoAccount(ledger, FakeOKX(), production, profile=LIVE).profile is LIVE
    assert DemoAccount(ledger, FakeOKX(), FakeExchange()).profile is DEMO


def test_a_live_run_labels_what_it_sends_and_keeps_to_its_own_lock_and_throttle(tmp_path):
    env = Env(tmp_path)
    account, exchange = live_account(env)
    env.decide(HOUR, "Long")
    run(env, account, exchange, RUN0)
    assert exchange.book[BTC.swap] == [10.0, 80_000.0]
    (text,) = env.inbox.sent
    assert text.startswith("【live】01-10 00:00 UTC\nBTC：Long → ")
    assert env.settings.live_lock_path.exists() and not env.settings.demo_lock_path.exists()

    def broken(ccy="USDT"):
        raise OKXError("balance failed with code 50001: service unavailable")

    exchange.balance = broken
    for now_ms in (RUN0 + HOUR_MS, RUN0 + 2 * HOUR_MS):
        with pytest.raises(OKXError):
            run(env, account, exchange, now_ms)
    assert env.inbox.sent[1:] == ["【live】运行失败：OKXError: balance failed with code 50001: service unavailable"]
    assert account.ledger.get("live_alerted_at") == RUN0 + HOUR_MS
    assert account.ledger.get("demo_alerted_at") is None and env.ledger.get("demo_alerted_at") is None


def test_the_events_and_reports_of_a_live_account_name_it(tmp_path):
    env = Env(tmp_path)
    account, exchange = live_account(env)
    run(env, account, exchange, RUN0)  # the intraday account never decides the hour
    assert report.full(account) == "live 账户还没开始：第一次执行之后才有绩效。"
    env.intraday.set("halted", True)
    run(env, account, exchange, RUN0 + HOUR_MS)  # followed with Flat: the first execution
    texts = [text for (text,) in account.ledger.db.execute("SELECT text FROM events ORDER BY id")]
    assert texts == ["日内账户到 00:25 还没决定 00:00 这个小时，live 本小时不交易", "日内账户熔断中，live 跟随平仓"]
    performance = report.full(account).splitlines()
    assert performance[0].startswith("live 绩效：自 2026-01-10 起") and performance[1].startswith("live（交易所权益）")
    account.ledger.set("halted", True)
    daily = report.daily(account, "2026-01-09", RUN0).splitlines()
    assert daily[:2] == ["日报 · 2026-01-09", "⚠ 熔断中：已平仓，不再下单。按 ADR 0010，live 熔断一次就不再解除，实验到此结束。"]


def test_a_live_kill_alert_says_the_experiment_is_over(tmp_path):
    env = Env(tmp_path)
    account, exchange = live_account(env)
    env.decide(HOUR, "Long")
    run(env, account, exchange, RUN0)
    exchange.mark[BTC.swap] = exchange.prices[BTC.swap] = 59_000.0
    env.decide(HOUR + HOUR_MS, "Long")
    run(env, account, exchange, RUN0 + HOUR_MS)
    assert account.ledger.get("halted") is True and exchange.book[BTC.swap][0] == 0
    (kill,) = [text for text in env.inbox.sent if text.startswith("【live】熔断：净值")]
    assert kill.endswith("停止交易；已对 BTC-USDT-SWAP 发出市价平仓。按 ADR 0010，live 熔断一次就不再解除，实验到此结束。")
    assert (DEMO.kill_final, LIVE.kill_final, live.LIVE.kill_final) == (False, True, True)


def test_each_paper_account_names_its_own_resume_command():
    assert Paper.resume_command == "python -m trader resume"
    assert IntradayPaper.resume_command == "python -m trader intraday resume"
    assert _kill_alert(8_000.0, 10_000.0, Paper.resume_command) == (
        "熔断：净值 8,000.00 比峰值 10,000.00 回撤 20.0%，已全部平仓并停止交易。"
        "确认后运行 python -m trader resume 恢复。"
    )

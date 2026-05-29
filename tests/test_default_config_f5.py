import pytest


@pytest.mark.unit
def test_default_config_has_f5_keys():
    from tradingagents.default_config import DEFAULT_CONFIG as C

    # Delivery channels + quiet hours
    assert C["delivery"]["enabled_channels"] == ["email", "cli"]
    assert C["delivery"]["quiet_hours"]["enabled"] is True
    assert C["delivery"]["quiet_hours"]["start"] == "22:00"
    assert C["delivery"]["quiet_hours"]["end"] == "07:00"
    assert C["delivery"]["digest_modes"]["telegram"] == "terse"
    assert C["delivery"]["digest_modes"]["email"] == "full"
    assert C["delivery"]["digest_modes"]["cli"] == "full"

    # Telegram bot — enabled, but restricted (deny-all until chat ids are
    # supplied via the TELEGRAM_BOT_ALLOWED_CHAT_IDS env var in .env)
    assert C["telegram_bot"]["enabled"] is True
    assert C["telegram_bot"]["allowed_chat_ids"] == []
    assert C["telegram_bot"]["poll_interval_seconds"] == 1

    # SMTP — opt-in
    assert C["smtp"]["enabled"] is False
    assert C["smtp"]["host"] == "smtp.gmail.com"
    assert C["smtp"]["port"] == 587

    # Morning digest
    assert C["morning_digest"]["schedule_local_time"] == "07:00"
    assert C["morning_digest"]["watchlist_source"] == "db"

    # Refinement
    assert C["refinement"]["max_depth"] == 3
    assert C["refinement"]["classifier_llm"] == "quick_think_llm"
    assert C["refinement"]["action_expires_hours"] == 24

    # Action handler
    assert C["action_handler"]["tick_interval_seconds"] == 5

    # Dashboard — opt-in
    assert C["dashboard"]["enabled"] is False
    assert C["dashboard"]["port"] == 8501
    assert C["dashboard"]["bind_address"] == "127.0.0.1"

    # F5 cost guards (still off per Appendix A)
    assert C["refinement_chain_budget"]["enabled"] is False
    assert C["refinement_chain_budget"]["max_usd_per_chain"] == 10.0
    assert C["morning_digest_token_ceiling"]["enabled"] is False
    assert C["morning_digest_token_ceiling"]["max_in_tokens"] == 500_000

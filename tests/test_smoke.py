def test_default_config_present():
    from tradingagents import default_config

    cfg = default_config.DEFAULT_CONFIG
    assert isinstance(cfg, dict)
    assert "results_dir" in cfg


def test_preflight_imports():
    import scripts.preflight_check as preflight

    assert callable(preflight.run)

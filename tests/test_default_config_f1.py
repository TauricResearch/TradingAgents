import pytest


@pytest.mark.unit
def test_default_config_has_f1_keys():
    from tradingagents.default_config import DEFAULT_CONFIG as C
    assert "iic_db_path" in C
    assert "iic_data_dir" in C
    assert "cost_guard_enabled" in C
    assert C["cost_guard_enabled"] is False  # per saved feedback: ship disabled


@pytest.mark.unit
def test_iic_paths_are_absolute():
    import os
    from tradingagents.default_config import DEFAULT_CONFIG as C
    assert os.path.isabs(C["iic_db_path"])
    assert os.path.isabs(C["iic_data_dir"])

from tradingagents.llm_clients.google_key_rotator import GoogleApiKeyRotator, parse_google_api_keys


def test_parse_google_api_keys_from_csv():
    assert parse_google_api_keys("a, b\n c") == ["a", "b", "c"]


def test_rotator_round_robin_persists_without_storing_raw_keys(tmp_path):
    state_path = tmp_path / "rotation.json"
    rotator = GoogleApiKeyRotator(["key-1", "key-2", "key-3", "key-4"], str(state_path))

    assert [rotator.next_key("quick") for _ in range(5)] == [
        "key-1",
        "key-2",
        "key-3",
        "key-4",
        "key-1",
    ]

    text = state_path.read_text(encoding="utf-8")
    assert "key-1" not in text
    assert "key-2" not in text
    assert "requests" in text

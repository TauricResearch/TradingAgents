from tradingagents.observability.canonical import canonical_sha256
from tradingagents.observability.redaction import (
    REDACTED_VALUE,
    redact_recursive,
    remove_credentials_recursive,
)


def test_nested_and_literal_dotted_credential_paths_share_manifest_rules():
    result = redact_recursive(
        {
            "headers": {"Cookie": "nested-cookie"},
            "headers.Cookie": "literal-cookie",
            "auth": {"proxy-authorization": "Bearer secret"},
        }
    )

    assert result.value["headers"]["Cookie"] == REDACTED_VALUE
    assert result.value["headers.Cookie"] == REDACTED_VALUE
    assert result.value["auth"]["proxy-authorization"] == REDACTED_VALUE
    assert [record.path for record in result.manifest] == [
        "auth.proxy_authorization",
        "headers.cookie",
    ]


def test_exact_suffix_and_provider_credentials_are_redacted():
    result = redact_recursive(
        {
            "OPENAI_API_KEY": "one",
            "api-key": "two",
            "client-secret": "three",
            "access_token": "four",
            "custom-private-key": "five",
        }
    )

    assert set(result.value.values()) == {REDACTED_VALUE}
    assert result.redacted is True


def test_semantic_token_and_secret_substrings_are_retained():
    safe = {
        "max_tokens": 8192,
        "token_budget": 2000,
        "news_article_limit": 20,
        "secretary_name": "Ada",
        "consistency_enabled": True,
    }

    result = redact_recursive(safe)

    assert result.value == safe
    assert result.manifest == ()


def test_additional_runtime_credential_name_is_exact_not_substring_based():
    result = redact_recursive(
        {"enterprise_credential": "hide", "enterprise_credential_hint": "keep"},
        additional_credential_names=("ENTERPRISE_CREDENTIAL",),
    )

    assert result.value == {
        "enterprise_credential": REDACTED_VALUE,
        "enterprise_credential_hint": "keep",
    }


def test_redaction_recurses_through_arrays_and_records_normalized_indices():
    result = redact_recursive([{"set cookie": "secret"}, {"value": 1}])

    assert result.value == [{"set cookie": REDACTED_VALUE}, {"value": 1}]
    assert result.manifest[0].path == "0.set_cookie"


def test_repo_provider_and_data_credential_names_all_redact_without_real_env_values():
    credential_names = [
        "OPENAI_API_KEY",
        "GOOGLE_API_KEY",
        "ANTHROPIC_API_KEY",
        "MIMO_API_KEY",
        "XAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "DASHSCOPE_API_KEY",
        "DASHSCOPE_CN_API_KEY",
        "ZHIPU_API_KEY",
        "ZHIPU_CN_API_KEY",
        "MINIMAX_API_KEY",
        "MINIMAX_CN_API_KEY",
        "OPENROUTER_API_KEY",
        "AZURE_OPENAI_API_KEY",
        "ALPHA_VANTAGE_API_KEY",
        "FRED_API_KEY",
        "TAVILY_API_KEY",
        "TUSHARE_TOKEN",
        "TUSHARE_API_KEY",
    ]
    payload = {name: f"fake-{index}" for index, name in enumerate(credential_names)}

    result = redact_recursive(payload)

    assert set(result.value.values()) == {REDACTED_VALUE}
    assert len(result.manifest) == len(credential_names)


def test_redaction_is_non_mutating_idempotent_and_manifest_never_contains_values():
    original = {"headers": {"Authorization": "fake-bearer"}, "max_tokens": 100}

    first = redact_recursive(original)
    second = redact_recursive(first.value)

    assert original["headers"]["Authorization"] == "fake-bearer"
    assert second.value == first.value
    assert second.manifest == first.manifest
    assert all("fake-bearer" not in record.path for record in first.manifest)


def test_fingerprint_removal_ignores_secret_presence_but_keeps_semantic_tokens():
    without_secret = {"model": {"max_tokens": 100}}
    with_secret = {"model": {"max_tokens": 100, "api_key": "fake-secret"}}
    changed_semantic = {"model": {"max_tokens": 200, "api_key": "other"}}

    first = remove_credentials_recursive(without_secret)
    second = remove_credentials_recursive(with_secret)
    third = remove_credentials_recursive(changed_semantic)

    assert canonical_sha256(first.value) == canonical_sha256(second.value)
    assert canonical_sha256(second.value) != canonical_sha256(third.value)
    assert second.manifest[0].path == "model.api_key"

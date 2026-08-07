"""Production build identity must come from the running platform image."""

import pytest

from tradingagents.research_protocol import (
    build_identity,
    content_id,
    runtime_build_manifest,
)

_DEPLOYMENT = "01KZAD8T2KXJJJXAM2JJW8E447"
_REVISION = "a" * 40


@pytest.mark.unit
def test_fly_runtime_image_cannot_be_masked_by_generic_build_override():
    env = {
        "FLY_APP_NAME": "tradagent-paper",
        "FLY_MACHINE_ID": "080d229a942408",
        "FLY_IMAGE_REF": (
            f"registry.fly.io/tradagent-paper:deployment-{_DEPLOYMENT}"
        ),
        "TRADINGAGENTS_BUILD_ID": "build_" + "f" * 24,
        "GIT_REVISION": "e" * 40,
    }

    manifest = runtime_build_manifest(env)

    assert manifest == {
        "schema_version": 1,
        "platform": "fly",
        "app_name": "tradagent-paper",
        "image_ref": f"registry.fly.io/tradagent-paper:deployment-{_DEPLOYMENT}",
        "deployment_id": _DEPLOYMENT,
    }
    assert content_id(manifest, prefix="build_").startswith("build_")


@pytest.mark.unit
def test_fly_git_image_requires_and_records_the_exact_embedded_revision(monkeypatch):
    image_ref = f"registry.fly.io/tradagent:git-{_REVISION}"
    env = {
        "FLY_APP_NAME": "tradagent",
        "FLY_MACHINE_ID": "080d229a942408",
        "FLY_IMAGE_REF": image_ref,
        "GIT_REVISION": _REVISION,
        "TRADINGAGENTS_BUILD_ID": "build_" + "f" * 24,
    }

    manifest = runtime_build_manifest(env)

    assert manifest == {
        "schema_version": 1,
        "platform": "fly",
        "app_name": "tradagent",
        "image_ref": image_ref,
        "git_revision": _REVISION,
    }
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    assert build_identity() == content_id(manifest, prefix="build_")


@pytest.mark.unit
@pytest.mark.parametrize(
    "revision",
    [
        None,
        "",
        "b" * 40,
        _REVISION.upper(),
        _REVISION[:-1],
        f" {_REVISION}x ",
    ],
)
def test_fly_git_image_fails_closed_without_its_exact_lowercase_revision(revision):
    env = {
        "FLY_APP_NAME": "tradagent",
        "FLY_MACHINE_ID": "080d229a942408",
        "FLY_IMAGE_REF": f"registry.fly.io/tradagent:git-{_REVISION}",
        "TRADINGAGENTS_BUILD_ID": _REVISION,
    }
    if revision is not None:
        env["GIT_REVISION"] = revision

    with pytest.raises(ValueError, match="exact lowercase GIT_REVISION"):
        runtime_build_manifest(env)


@pytest.mark.unit
@pytest.mark.parametrize(
    "env",
    [
        {"FLY_APP_NAME": "tradagent-paper", "FLY_MACHINE_ID": "machine"},
        {
            "FLY_APP_NAME": "tradagent-paper",
            "FLY_IMAGE_REF": "registry.fly.io/tradagent-paper:latest",
        },
        {
            "FLY_APP_NAME": "other-app",
            "FLY_IMAGE_REF": (
                f"registry.fly.io/tradagent-paper:deployment-{_DEPLOYMENT}"
            ),
        },
        {
            "FLY_APP_NAME": "other-app",
            "FLY_IMAGE_REF": f"registry.fly.io/tradagent:git-{_REVISION}",
            "GIT_REVISION": _REVISION,
        },
        {
            "FLY_APP_NAME": "tradagent",
            "FLY_IMAGE_REF": f"registry.fly.io/tradagent:git-{_REVISION[:-1]}",
            "GIT_REVISION": _REVISION,
        },
        {
            "FLY_APP_NAME": "tradagent",
            "FLY_IMAGE_REF": f"registry.fly.io/tradagent:git-{_REVISION.upper()}",
            "GIT_REVISION": _REVISION,
        },
    ],
)
def test_partial_mutable_or_cross_app_fly_identity_fails_closed(env):
    with pytest.raises(ValueError, match="Fly build identity"):
        runtime_build_manifest(env)


@pytest.mark.unit
def test_non_fly_explicit_identity_requires_content_addressed_material():
    assert runtime_build_manifest({"GIT_REVISION": "a" * 40}) == {
        "schema_version": 1,
        "platform": "explicit",
        "material": "a" * 40,
    }
    with pytest.raises(ValueError, match="full digest"):
        runtime_build_manifest({"TRADINGAGENTS_BUILD_ID": "release-latest"})


@pytest.mark.unit
def test_source_checkout_has_no_asserted_runtime_manifest():
    assert runtime_build_manifest({}) is None

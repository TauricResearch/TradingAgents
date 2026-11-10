"""Build identification (§2 of the P1 task).

The data lineage audit could not establish from outside whether a restart had
happened: a process started before a merge keeps the modules it loaded, and the
start time alone was insufficient evidence. These tests pin the two identifiers
that make the question answerable, and the fact that neither can break the
service.
"""

from __future__ import annotations

from tradingagents.build_info import LOADED_AT, build_info, commit_sha


class TestBuildIdentification:
    def test_a_commit_is_reported(self):
        """The SHA the tree reports, or `unknown` — never an exception."""
        sha = commit_sha()
        assert isinstance(sha, str)
        assert sha
        # In a checkout this is a real short SHA; in an sdist it is `unknown`.
        assert sha == "unknown" or len(sha) >= 7

    def test_the_load_time_is_captured(self):
        """When THIS process began running this code, distinct from start time."""
        assert LOADED_AT
        assert "T" in LOADED_AT

    def test_the_payload_names_the_commit_and_the_load_moment(self):
        info = build_info()
        assert set(info) >= {"commit", "loaded_at", "math_engine"}
        assert info["loaded_at"] == LOADED_AT

    def test_the_math_engine_is_reported_as_importable(self):
        """A health response that names the engine proves it is importable."""
        assert build_info()["math_engine"]["loaded"] is True

    def test_no_environment_values_leak(self):
        """A health endpoint is often openly reachable: no secrets, no paths."""
        payload = repr(build_info())
        for forbidden in ("API_KEY", "TOKEN", "PASSWORD", "/root", "/home"):
            assert forbidden not in payload

    def test_the_repository_root_is_inside_the_checkout(self):
        """A wrong root would silently report `unknown` for a real checkout."""
        from tradingagents import build_info as module

        assert (module._REPO_ROOT / "tradingagents").is_dir()
        assert (module._REPO_ROOT / "pyproject.toml").is_file()

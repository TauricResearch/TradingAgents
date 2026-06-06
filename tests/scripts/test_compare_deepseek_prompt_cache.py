import json
import subprocess
import sys


def test_compare_script_runs_legacy_and_optimized_prompt_shapes():
    result = subprocess.run(
        [
            sys.executable,
            "scripts/compare_deepseek_prompt_cache.py",
            "--json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["family"] == "sentiment"
    assert payload["legacy_prefix_equal"] is False
    assert payload["optimized_prefix_equal"] is True
    assert payload["optimized_has_dynamic_marker"] is True

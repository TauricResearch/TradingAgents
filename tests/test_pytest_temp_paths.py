import os
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def test_pytest_temp_paths_do_not_use_project_root_artifact_dirs(tmp_path):
    forbidden_roots = [
        PROJECT_ROOT / "ta_test_artifacts",
        PROJECT_ROOT / "ta_pytest_temp",
    ]
    observed_paths = [
        Path(tmp_path),
        Path(tempfile.gettempdir()),
        Path(os.environ["TMP"]),
        Path(os.environ["TEMP"]),
    ]

    for observed_path in observed_paths:
        assert not any(
            _is_relative_to(observed_path, forbidden_root)
            for forbidden_root in forbidden_roots
        )

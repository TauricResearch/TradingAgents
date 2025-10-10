from __future__ import annotations

import shutil
import tempfile

from ._errors import OperationFailed
from ._osfs import OSFS


class TempFS(OSFS):
    def __init__(self, auto_clean: bool = True, ignore_clean_errors: bool = True):
        self.auto_clean = auto_clean
        self.ignore_clean_errors = ignore_clean_errors
        self._temp_dir = tempfile.mkdtemp("__temp_fs__")
        self._cleaned = False
        super().__init__(self._temp_dir)

    def close(self):
        if self.auto_clean:
            self.clean()
        super().close()

    def clean(self):
        if self._cleaned:
            return

        try:
            shutil.rmtree(self._temp_dir)
        except Exception as e:
            if not self.ignore_clean_errors:
                raise OperationFailed(
                    f"failed to remove temporary directory: {self._temp_dir!r}"
                ) from e
        self._cleaned = True

import sys
import pytest

if __name__ == "__main__":
    sys.exit(pytest.main(["tests/test_continuous_e2e.py", "-v"]))

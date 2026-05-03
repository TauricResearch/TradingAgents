"""Console-script entrypoint for ``tradingagents-gui``.

Launches Streamlit pointing at ``gui/app.py``. We shell out to streamlit's
own CLI rather than calling ``streamlit.run()`` directly because Streamlit's
multipage discovery requires the entry script to be invoked normally.
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    try:
        from streamlit.web import cli as stcli  # type: ignore
    except ImportError:
        print(
            "streamlit is not installed. Install the GUI extras:\n"
            "    pip install '.[gui]'",
            file=sys.stderr,
        )
        return 1

    app_path = Path(__file__).resolve().parent / "app.py"
    args = sys.argv[1:]
    sys.argv = ["streamlit", "run", str(app_path), *args]
    return stcli.main()


if __name__ == "__main__":
    sys.exit(main())

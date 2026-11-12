"""Requests to OKX's production environment come from the live command group alone
(ADR 0010): only trader/live builds a production client, and the settings, the other
accounts, the daily jobs and the dashboard, whose processes must never hold the live
key, do not import trader.live."""

import ast
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / "trader" / "live"
# What runs without the live key, and so must not depend on the package that reads it.
KEYLESS = ("trader/settings.py", "trader/jobs.py", "trader/demo", "trader/intraday", "web")


def _sources(*parts: str) -> list[Path]:
    paths = [ROOT / part for part in parts]
    return [p for path in paths for p in ([path] if path.is_file() else sorted(path.rglob("*.py")))]


def _production_client_lines(source: str) -> list[int]:
    """The lines of ``source`` that may build a production client: a call passing
    ``simulated`` as anything but the literal True, and an OKXPrivate call that could
    pass it unnamed (a second positional argument, or ``**options``)."""
    lines = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        unnamed = name == "OKXPrivate" and (len(node.args) > 1 or any(k.arg is None for k in node.keywords))
        named = any(
            k.arg == "simulated" and not (isinstance(k.value, ast.Constant) and k.value.value is True)
            for k in node.keywords
        )
        if unnamed or named:
            lines.append(node.lineno)
    return sorted(lines)


def _live_import_lines(source: str, package: tuple[str, ...]) -> list[int]:
    """The lines of ``source``, a module of ``package``, that import trader.live or
    anything in it: at the top or inside a function, absolutely or relatively."""
    lines = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = package[: len(package) - node.level + 1] if node.level else ()
            module = ".".join([*base, *([node.module] if node.module else [])])
            names = [module, *(f"{module}.{alias.name}" for alias in node.names)]
        else:
            continue
        if any(name == "trader.live" or name.startswith("trader.live.") for name in names):
            lines.append(node.lineno)
    return sorted(lines)


def _offenders(paths: list[Path], lines_of) -> list[str]:
    """``file:line`` for every line ``lines_of(source, path)`` finds in ``paths``."""
    return [
        f"{path.relative_to(ROOT)}:{line}"
        for path in paths
        for line in lines_of(path.read_text(encoding="utf-8"), path)
    ]


def test_only_trader_live_builds_a_production_client():
    def scan(source, path):
        return _production_client_lines(source)

    outside = [path for path in _sources("trader", "web") if LIVE not in path.parents]
    assert _offenders(outside, scan) == []
    # The scan sees the one that exists: the factory on the live key file.
    inside = _offenders(_sources("trader/live"), scan)
    assert len(inside) == 1 and inside[0].startswith("trader/live/keys.py:")


def test_the_scan_flags_each_way_of_building_a_production_client():
    source = (
        "OKXPrivate(creds)\n"
        "OKXPrivate(creds, session=session, simulated=True, base_url=url)\n"
        "OKXPrivate(creds, simulated=False)\n"
        "okx_private.OKXPrivate(creds, simulated=flag)\n"
        "OKXPrivate(creds, session, False)\n"
        "OKXPrivate(creds, **options)\n"
        "partial(OKXPrivate, simulated=False)\n"
    )
    assert _production_client_lines(source) == [3, 4, 5, 6, 7]


def test_what_runs_without_the_live_key_does_not_import_trader_live():
    def scan(source, path):
        return _live_import_lines(source, path.relative_to(ROOT).parent.parts)

    sources = _sources(*KEYLESS)
    assert _offenders(sources, scan) == []
    # The scan sees an import that exists: the command line's, which runs the live commands.
    assert _offenders([ROOT / "trader" / "__main__.py"], scan) != []
    # Nor do they reach it through what they import: with all of them loaded, trader.live is not.
    modules = sorted(
        ".".join(path.relative_to(ROOT).with_suffix("").parts).removesuffix(".__init__")
        for path in sources if path.name != "__main__.py"
    )
    assert {"trader.settings", "trader.jobs", "trader.demo.job", "trader.intraday.job", "web.api.app"} <= set(modules)
    code = (
        f"import sys, importlib; [importlib.import_module(m) for m in {modules!r}];"
        " print(sorted(m for m in sys.modules if m.startswith('trader.live')))"
    )
    out = subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True, cwd=ROOT)
    assert out.stdout.strip() == "[]"


def test_the_scan_flags_each_spelling_of_the_import():
    source = (
        "import trader.ledger\n"
        "from trader import jobs, okx_private\n"
        "from trader.intraday import paper\n"
        "from . import settings\n"
        "import trader.live\n"
        "import trader.live.keys as live_keys\n"
        "from trader import live\n"
        "from trader.live import keys\n"
        "from trader.live.keys import load\n"
        "def lazily():\n"
        "    from trader.live import keys\n"
        "from ..live import keys\n"
        "from .. import live\n"
    )
    assert _live_import_lines(source, ("trader", "demo")) == [5, 6, 7, 8, 9, 11, 12, 13]

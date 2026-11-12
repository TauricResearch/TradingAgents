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
# What runs without the live key, and so must not depend on the package that reads it:
# among it the two modules that call the LLM, the daily research and the intraday signal.
KEYLESS = (
    "trader/settings.py", "trader/jobs.py", "trader/research.py", "trader/demo", "trader/intraday", "web",
)


def _sources(*parts: str) -> list[Path]:
    paths = [ROOT / part for part in parts]
    return [p for path in paths for p in ([path] if path.is_file() else sorted(path.rglob("*.py")))]


def _production_client_lines(source: str) -> list[int]:
    """The lines of ``source`` that may build a production client, or turn a client into
    one. ``simulated`` is passed to OKXPrivate by name only and cannot be set afterwards,
    so these are: a call passing ``simulated`` as anything but the literal True; an
    OKXPrivate call whose arguments are not all in sight (``*args``, ``**options``);
    OKXPrivate imported under another name, which would hide such a call from this
    scan; and an assignment to a client's ``simulated``."""
    lines = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            out_of_sight = name == "OKXPrivate" and (
                any(isinstance(arg, ast.Starred) for arg in node.args) or any(k.arg is None for k in node.keywords)
            )
            found = out_of_sight or any(
                k.arg == "simulated" and not (isinstance(k.value, ast.Constant) and k.value.value is True)
                for k in node.keywords
            )
        elif isinstance(node, ast.ImportFrom):
            found = any(a.name == "OKXPrivate" and a.asname not in (None, "OKXPrivate") for a in node.names)
        elif isinstance(node, ast.Assign | ast.AugAssign | ast.AnnAssign):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            found = any(
                isinstance(part, ast.Attribute) and isinstance(part.ctx, ast.Store)
                and part.attr in ("simulated", "_simulated")
                for target in targets for part in ast.walk(target)
            )
        else:
            continue
        if found:
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

    definition = ROOT / "trader" / "okx_private.py"
    outside = [path for path in _sources("trader", "web") if LIVE not in path.parents and path != definition]
    assert _offenders(outside, scan) == []
    # The scan sees the one that exists: the factory on the live key file.
    inside = _offenders(_sources("trader/live"), scan)
    assert len(inside) == 1 and inside[0].startswith("trader/live/keys.py:")
    # And the one line of OKXPrivate's own definition that sets what a client was built with.
    assert len(_offenders([definition], scan)) == 1


def test_the_scan_flags_each_way_of_building_a_production_client():
    source = (
        "OKXPrivate(creds)\n"
        "OKXPrivate(creds, session, clock=now, simulated=True, base_url=url)\n"
        "OKXPrivate(creds, simulated=False)\n"
        "okx_private.OKXPrivate(creds, simulated=flag)\n"
        "OKXPrivate(creds, **options)\n"
        "OKXPrivate(*args)\n"
        "partial(OKXPrivate, simulated=False)\n"
        "from trader.okx_private import OKXPrivate as Client\n"
        "client.simulated = False\n"
        "client._simulated = False\n"
        "spare, client._simulated = None, False\n"
        "from trader.okx_private import OKXPrivate, OKXPrivateError as Refused\n"
        "simulated = client.simulated\n"
        "seen[client.simulated] = True\n"
    )
    assert _production_client_lines(source) == [3, 4, 5, 6, 7, 8, 9, 10, 11]


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

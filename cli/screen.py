"""`tradingagents screen ...`: run stock screens over the India database's metrics snapshot.

    screen run "Market Capitalization > 500 AND ROCE > 20" [--as-of 2025-10-06] [--limit 25]
    screen list                 saved screens and the presets
    screen metrics [TEXT]       the metrics catalog, or the metrics whose name matches TEXT

Build the snapshot first with `tradingagents india build-snapshot`.
"""

from __future__ import annotations

import typer
from rich.markup import escape
from rich.table import Table

from cli.display import console
from tradingagents.screener import catalog, engine, screens
from tradingagents.screener.query import QueryError
from tradingagents.screener.snapshot import SnapshotError

app = typer.Typer(help="Stock screener: filter every Indian stock on its metrics (see README).",
                  no_args_is_help=True)


def _cell(value, column: dict) -> str:
    if value is None:
        return "[dim]—[/dim]"
    if column["kind"] == "text":
        return escape(str(value))
    digits = column["decimals"]
    return f"{value:,.{digits}f}"


@app.command("run")
def run(query: str = typer.Argument(..., help='The condition, e.g. "Market Capitalization > 500 AND ROCE > 20"; '
                                             "a newline (or AND) joins conditions"),
        as_of: str = typer.Option(None, "--as-of", help="Run on the historical snapshot of YYYY-MM-DD"),
        limit: int = typer.Option(25, "--limit", min=1, max=engine.MAX_PAGE_SIZE, help="Rows to show"),
        sort: str = typer.Option(None, "--sort", help="Metric key to sort by, e.g. roce (descending); "
                                                       "prefix with + for ascending"),
        columns: str = typer.Option(None, "--columns", help="Comma-separated metric keys to show")):
    """Run a screen and print the matching stocks."""
    user = screens.connect()
    try:
        order = None
        if sort:
            order = {"key": sort.lstrip("+-"), "dir": "asc" if sort.startswith("+") else "desc"}
        picked = [c.strip() for c in columns.split(",") if c.strip()] if columns else None
        result = engine.run(query, columns=picked, sort=order, page_size=limit, as_of=as_of, user_conn=user)
    except QueryError as exc:
        console.print(f"[red]{escape(str(exc))}[/red]", soft_wrap=True)
        line = query.splitlines()[exc.line - 1] if query.splitlines() else query
        console.print(f"  {escape(line)}\n  {' ' * (exc.col - 1)}[red]{'^' * max(1, min(exc.end - exc.start, len(line)))}[/red]")
        raise typer.Exit(code=1) from None
    except (screens.ScreenError, SnapshotError, engine.ScreenerUnavailable, engine.ScreenTimeout) as exc:
        console.print(f"[red]{escape(str(exc))}[/red]", soft_wrap=True)
        raise typer.Exit(code=1) from None
    finally:
        user.close()

    snap = result["snapshot"]
    title = (f"{result['total']:,} of {result['universe']:,} stocks match · snapshot {snap['as_of']} "
             f"(data to {snap['data_date']}, built {snap['built_at']})")
    table = Table(title=title, title_justify="left")
    cols = result["columns"]
    for c in cols:
        unit = f" ({c['unit']})" if c["unit"] else ""
        table.add_column(escape(c["name"] + unit), justify="left" if c["kind"] == "text" else "right",
                         overflow="fold")
    for r in result["rows"]:
        table.add_row(*[_cell(r["values"].get(c["id"]), c) for c in cols])
    if result["rows"]:
        table.add_section()
        table.add_row(*["[italic]Median[/italic]" if c["id"] == "name" else
                        ("" if c["kind"] == "text" else _cell(result["median"].get(c["id"]), c)) for c in cols])
    console.print(table)
    shown = len(result["rows"])
    notes = [f"Showing {shown:,} of {result['total']:,}" + (f", sorted by {result['sort']['key']} "
                                                            f"{result['sort']['dir']}" if shown else "")]
    if result["excluded"]:
        notes.append(f"{result['excluded']:,} stocks left out for missing data")
    notes.append(f"{result['elapsedMs']:,.0f} ms")
    console.print("[dim]" + " · ".join(notes) + "[/dim]")


@app.command("list")
def list_screens():
    """Your saved screens, then the presets."""
    user = screens.connect()
    try:
        saved = screens.list_screens(user)
    finally:
        user.close()
    table = Table(title="Screens", show_lines=True)
    for column in ("id", "name", "query"):
        table.add_column(column, overflow="fold")
    for s in [*saved, *screens.presets()]:
        table.add_row(str(s["id"]), escape(s["name"]), escape(s["query"]))
    console.print(table)
    console.print(f"[dim]{len(saved)} saved; presets are read-only. Run one with: "
                  "tradingagents screen run \"<query>\"[/dim]")


@app.command("metrics")
def metrics(search: str = typer.Argument(None, help="Show only metrics whose name, alias or key contains this")):
    """The metrics a query can use, with units and the names they answer to."""
    table = Table(title="Screener metrics")
    for column in ("category", "name", "unit", "also", "key"):
        table.add_column(column, overflow="fold")
    needle = (search or "").casefold()
    for m in catalog.catalog():
        names = [m["name"], *m["aliases"], m["key"]]
        if needle and not any(needle in n.casefold() for n in names):
            continue
        table.add_row(m["category"], escape(m["name"]), m["unit"], escape(", ".join(m["aliases"])), m["key"])
    console.print(table)

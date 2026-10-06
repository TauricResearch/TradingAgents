"""`tradingagents india ...`: fill and inspect the India database.

Every sync resumes where the last one stopped (``--force`` redoes what is
done), shows its progress, and logs each day or file it touches. A day or file
that fails is reported and the run goes on; the command exits non-zero only when
the run itself could not go on (a host refusing us, the network down, a bad
argument).
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import typer
from rich.markup import escape
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn
from rich.table import Table

from cli.display import console
from tradingagents.dataflows.vendors.india import store, sync as india_sync

app = typer.Typer(help="India data layer: NSE archives and saved XBRL filings in a local database.",
                  no_args_is_help=True)

SYMBOLS = typer.Option(None, "--symbols", help="Comma-separated NSE symbols or ISINs, e.g. RELIANCE,TCS")
UNIVERSE = typer.Option(None, "--universe", help="nifty50, nifty500 or all")
FORCE = typer.Option(False, "--force", help="Redo days or files already done")
PATHS = typer.Argument(..., help="XBRL files or folders of them")
INBOX = typer.Option(None, "--dir", help="Folder of XBRL files saved from NSE or BSE "
                                         "(default: <cache>/india/inbox)")


class _RichProgress(india_sync.Progress):
    def __init__(self, progress: Progress):
        self.progress, self.tasks = progress, {}

    def start(self, label, total):
        self.tasks[label] = self.progress.add_task(label, total=total or None, detail="")

    def advance(self, label, detail=""):
        self.progress.update(self.tasks[label], advance=1, detail=detail)

    def finish(self, label):
        self.progress.update(self.tasks[label], detail="done")


def _date(value: str | None, label: str, default: date | None = None) -> date:
    if not value:
        if default is None:
            raise typer.BadParameter(f"{label} is required, as YYYY-MM-DD")
        return default
    try:
        return date.fromisoformat(value) if len(value) > 4 else date(int(value), 1, 1)
    except ValueError:
        raise typer.BadParameter(f"{label} must be YYYY-MM-DD (or a year), not {value!r}") from None


def _symbols(value: str | None) -> list[str] | None:
    return [s.strip() for s in value.split(",") if s.strip()] if value else None


def _run(work, *, force: bool = False):
    """Open the database, run ``work(syncer)`` under a progress display, print what
    each job did, and turn a systemic failure into exit code 1."""
    conn = store.connect()
    try:
        with Progress(TextColumn("[bold]{task.description}"), BarColumn(), MofNCompleteColumn(),
                      TimeElapsedColumn(), TextColumn("[dim]{task.fields[detail]}"), console=console,
                      transient=False) as progress:
            syncer = india_sync.Syncer(conn, progress=_RichProgress(progress), force=force)
            try:
                results = work(syncer)
            except india_sync.SyncAborted as exc:
                progress.stop()
                console.print(f"[red]Stopped: {escape(str(exc))}[/red]")
                raise typer.Exit(code=1) from None
        _report(results if isinstance(results, list) else [results], syncer)
    finally:
        conn.close()


def _report(results, syncer) -> None:
    table = Table(title="India sync", show_lines=False)
    for column in ("job", "done", "skipped", "missing", "failed", "rows", "time"):
        table.add_column(column, justify="left" if column == "job" else "right")
    for r in results:
        table.add_row(r.job, str(r.done), str(r.skipped), str(r.missing),
                      f"[red]{r.failed}[/red]" if r.failed else "0", f"{r.rows:,}", f"{r.elapsed:,.0f}s")
    console.print(table)
    client = syncer.client
    console.print(f"Requests: {client.requests:,}; downloaded {client.downloaded / 1e6:,.1f} MB. "
                  f"Database: {store.db_path()} ({_size(store.db_path())}).", soft_wrap=True)
    for r in results:
        for note in r.notes:
            console.print(f"[dim]{r.job}: {escape(note)}[/dim]")
        for error in r.errors[:10]:
            console.print(f"[yellow]{r.job} failed:[/yellow] {escape(error)}", soft_wrap=True)
        if len(r.errors) > 10:
            console.print(f"[yellow]... and {r.failed - 10} more; see `tradingagents india status`[/yellow]")


def _size(path: Path) -> str:
    total = sum(p.stat().st_size for p in (path, Path(f"{path}-wal")) if p.exists())
    return f"{total / 1e6:,.1f} MB"


@app.command("sync-securities")
def sync_securities(force: bool = FORCE):
    """NSE's equity list and the industries from its index lists."""
    _run(lambda s: s.sync_securities(), force=force)


@app.command("sync-prices")
def sync_prices(start: str = typer.Option(..., "--from", help="First day, YYYY-MM-DD"),
                end: str = typer.Option(None, "--to", help="Last day, YYYY-MM-DD (default today)"),
                force: bool = FORCE):
    """Daily bhavcopies (OHLC, volume) and delivery files, for every NSE equity."""
    first, last = _date(start, "--from"), _date(end, "--to", date.today())
    _run(lambda s: s.sync_prices(first, last), force=force)


@app.command("sync-actions")
def sync_actions(start: str = typer.Option(None, "--from", help="First day, YYYY-MM-DD (default a year ago)"),
                 end: str = typer.Option(None, "--to", help="Last day, YYYY-MM-DD (default today)"),
                 force: bool = FORCE):
    """Corporate actions (splits, bonuses, rights, dividends) and shares issued, from NSE's daily PR files."""
    first = _date(start, "--from", date.today() - timedelta(days=365))
    last = _date(end, "--to", date.today())
    _run(lambda s: s.sync_actions(first, last), force=force)


def _import(syncer, kinds, symbols, universe, from_year, folder):
    folder = Path(folder) if folder else india_sync.inbox_dir()
    if not folder.exists():
        raise india_sync.SyncAborted(
            f"no folder {folder}. Save results or shareholding XBRL files from NSE's filing pages there "
            "(NSE serves them to browsers only), or pass --dir.")
    isins = syncer.universe(_symbols(symbols), universe)
    return syncer.import_files([folder], kinds=kinds, isins=isins, from_year=from_year)


@app.command("sync-results")
def sync_results(symbols: str = SYMBOLS, universe: str = UNIVERSE,
                 from_year: int = typer.Option(None, "--from", help="Earliest fiscal period year to import"),
                 folder: str = INBOX, force: bool = FORCE):
    """Import results XBRL (quarterly and annual, standalone and consolidated) saved in the inbox."""
    _run(lambda s: _import(s, {"results"}, symbols, universe, from_year, folder), force=force)


@app.command("sync-shareholding")
def sync_shareholding(symbols: str = SYMBOLS, universe: str = UNIVERSE,
                      from_year: int = typer.Option(None, "--from", help="Earliest quarter year to import"),
                      folder: str = INBOX, force: bool = FORCE):
    """Import shareholding-pattern XBRL saved in the inbox."""
    _run(lambda s: _import(s, {"shareholding"}, symbols, universe, from_year, folder), force=force)


@app.command("sync-documents")
def sync_documents(symbols: str = SYMBOLS, universe: str = typer.Option("nifty500", "--universe",
                   help="nifty50, nifty500 or all"),
                   start: str = typer.Option(None, "--from", help="First day, YYYY-MM-DD or a year (default a year ago)"),
                   end: str = typer.Option(None, "--to", help="Last day, YYYY-MM-DD (default today)"),
                   force: bool = FORCE):
    """Announcement and board-meeting links (results, annual reports, concalls, credit ratings) from NSE's PR files."""
    first = _date(start, "--from", date.today() - timedelta(days=365))
    last = _date(end, "--to", date.today())
    names = _symbols(symbols)

    def work(s):
        isins = s.universe(names, None if names else universe)
        label = "symbols:" + ",".join(sorted(isins)) if names else (universe or "all")
        return s.sync_announcements(first, last, isins, label)
    _run(work, force=force)


@app.command("import")
def import_files(paths: list[Path] = PATHS,
                 filed_at: str = typer.Option(None, "--filed-at",
                                              help="When these became public (YYYY-MM-DD or YYYY-MM-DDTHH:MM), "
                                                   "for files whose names do not carry NSE's submission time"),
                 force: bool = FORCE):
    """Import results or shareholding XBRL files, whatever folder they are in."""
    _run(lambda s: s.import_files(paths, filed_at=filed_at), force=force)


@app.command("sync-all")
def sync_all(universe: str = typer.Option("nifty500", "--universe",
                                          help="Universe for announcements: nifty50, nifty500 or all"),
             folder: str = INBOX, force: bool = FORCE):
    """The nightly run: securities, new days of prices, actions and announcements, and the inbox."""
    _run(lambda s: s.sync_all(universe=universe, inbox=Path(folder) if folder else None), force=force)


@app.command("status")
def status():
    """Row counts, date coverage, recent failures and unknown XBRL tags."""
    path = store.db_path()
    if not path.exists():
        console.print(f"No India database at {escape(str(path))} yet; run `tradingagents india sync-securities`.")
        raise typer.Exit(code=0)
    s = store.status(store.connect(path))
    console.print(f"Database: {escape(str(path))} ({_size(path)}); raw cache {_folder_size(india_sync.raw_dir())}",
                  soft_wrap=True)
    counts = Table(title="Rows")
    counts.add_column("table")
    counts.add_column("rows", justify="right")
    for name, n in s["counts"].items():
        counts.add_row(name, f"{n:,}")
    console.print(counts)
    cover = Table(title="Coverage")
    for column in ("data", "from", "to"):
        cover.add_column(column)
    for name, (low, high) in s["latest"].items():
        cover.add_row(name, str(low or "—"), str(high or "—"))
    console.print(cover)
    console.print(f"Companies with results: {s['companies_with_results']}")
    jobs = Table(title="Ingest log")
    for column in ("job", "status", "keys", "last run"):
        jobs.add_column(column)
    for job, state, n, last in s["jobs"]:
        jobs.add_row(job, state, f"{n:,}", str(last))
    console.print(jobs)
    for job, key, error, when in s["failures"]:
        console.print(f"[yellow]failed[/yellow] {job} {key} ({when}): {escape(str(error))}", soft_wrap=True)
    if s["unknown_tags"]:
        console.print("Unknown XBRL tags (add them to field_aliases if they matter): " + ", ".join(
            f"{tag} [{fmt}] x{n}" for tag, fmt, n in s["unknown_tags"]), soft_wrap=True)


def _folder_size(path: Path) -> str:
    if not path.exists():
        return "empty"
    total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return f"{total / 1e6:,.1f} MB in {path}"


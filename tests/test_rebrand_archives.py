"""Existing research remains identical when changing the archival UI wrapper."""

from tradingagents.paper.rebrand_archives import archive_reports, rebrand_html


def _old_report():
    return """<!doctype html><html><head>
<title>META 2026-10-21 Overweight: TradingAgents report</title>
<style>body{color:black}</style></head><body>
<header><a class="logo" href="https://tauric.ai" rel="noopener"
aria-label="Tauric Research"><svg><rect /></svg></a>
<h1>META Overweight</h1>
<dt>Version</dt><dd>TradingAgents 0.7.0</dd></header>
<main><section><h2>Research Manager</h2>
<p>Conditional entry above $716.08; no immediate buy.</p></section></main>
<footer class="credit"><a href="https://github.com/TauricResearch/TradingAgents">TradingAgents</a> powered by Tauric Research</footer>
</body></html>"""


def test_rebrand_preserves_original_decision_verbatim():
    output = rebrand_html(_old_report())
    assert "KORAL EQUITIES" in output
    assert "Tauric Research" not in output
    assert "TradingAgents report" not in output
    assert 'aria-label="Koral Equities"' in output
    assert "Research engine" in output
    assert "<p>Conditional entry above $716.08; no immediate buy.</p>" in output
    assert "Koral Equities | META" in output
    assert rebrand_html(output) == output


def test_archive_uses_dry_run_then_backups(tmp_path):
    directory = tmp_path / "reports" / "META_20261021"
    directory.mkdir(parents=True)
    file = directory / "complete_report.html"
    content = _old_report()
    file.write_text(content, encoding="utf-8")
    count, done = archive_reports(tmp_path, apply=False)
    assert (count, done) == (1, 0)
    assert file.read_text(encoding="utf-8") == content
    count, done = archive_reports(tmp_path, apply=True)
    assert (count, done) == (1, 1)
    assert (directory / "complete_report.html.upstream-backup").read_text() == content
    assert "Koral Equities" in file.read_text()
    assert archive_reports(tmp_path, apply=True) == (0, 0)


def test_unrecognised_report_is_left_alone():
    assert rebrand_html("<html><head><title>Unknown</title></head></html>") == (
        "<html><head><title>Unknown</title></head></html>"
    )

"""An optional HTML copy of the report, for readers who do not open Markdown (#1419).

It is one self-contained file: no script, no remote asset, nothing a report's
text can inject; the Markdown report is unchanged.
"""

import re

import pytest

from tradingagents.reporting import write_report_tree

SETTINGS = {"version": "1.2.3", "llm_provider": "openai", "deep_think_llm": "gpt-6-sol",
            "quick_think_llm": "gpt-6-luna", "analysts": ["market", "news"], "max_debate_rounds": 1,
            "max_risk_discuss_rounds": 1, "data_vendors": {"core_stock_apis": "yfinance"}}


def _state(**overrides):
    state = {"trade_date": "2026-09-26",
             "market_report": "# Market view\n\nPrice | Level\n--- | ---\nClose | 181.2\n",
             "news_report": "News text.",
             "final_trade_decision": "**Rating**: Overweight\n**Price Target**: 120\n\nAdd on weakness."}
    state.update(overrides)
    return state


def _html(tmp_path, **overrides):
    write_report_tree(_state(**overrides), "NVDA", tmp_path, settings=SETTINGS, html=True)
    return (tmp_path / "complete_report.html").read_text(encoding="utf-8")


@pytest.mark.unit
def test_the_html_page_is_written_unless_declined(tmp_path):
    write_report_tree(_state(), "NVDA", tmp_path / "plain", settings=SETTINGS, html=False)
    assert not (tmp_path / "plain" / "complete_report.html").exists()
    write_report_tree(_state(), "NVDA", tmp_path / "default", settings=SETTINGS)
    assert (tmp_path / "default" / "complete_report.html").exists()

    page = _html(tmp_path / "html")
    assert "<h1" in page and "NVDA" in page and "Overweight" in page and "2026-09-26" in page
    assert '<table>' in page and "181.2" in page


@pytest.mark.unit
def test_the_markdown_report_is_the_same_with_or_without_html(tmp_path):
    write_report_tree(_state(), "NVDA", tmp_path / "a", settings=SETTINGS, html=False)
    write_report_tree(_state(), "NVDA", tmp_path / "b", settings=SETTINGS)
    def undated(path):
        return re.sub(r"- Generated: .*\n", "", path.read_text(encoding="utf-8"))

    assert undated(tmp_path / "a" / "complete_report.md") == undated(tmp_path / "b" / "complete_report.md")


@pytest.mark.unit
def test_the_page_loads_nothing_and_runs_nothing(tmp_path):
    page = _html(tmp_path)
    assert "Content-Security-Policy" in page and "default-src 'none'" in page
    assert "<script" not in page.lower()
    assert not re.search(r'<(img|link|iframe|object|embed)\b', page, re.IGNORECASE)


@pytest.mark.unit
def test_report_text_cannot_inject_markup_or_fetch_anything(tmp_path):
    hostile = ("<script>alert(1)</script> <img src=x onerror=alert(1)>\n\n"
               "![pixel](https://tracker.example/p.png) [x](javascript:alert(1))")
    page = _html(tmp_path, news_report=hostile)
    assert "<script>alert" not in page and "<img" not in page.lower()
    assert "tracker.example/p.png" not in re.findall(r'(?:src|href)="([^"]*)"', page)
    assert 'href="javascript:' not in page


@pytest.mark.unit
def test_header_values_are_escaped(tmp_path):
    write_report_tree(_state(), "<b>NV</b>", tmp_path, settings={**SETTINGS, "deep_think_llm": "<i>m</i>"}, html=True)
    page = (tmp_path / "complete_report.html").read_text(encoding="utf-8")
    assert "<b>NV</b>" not in page and "&lt;b&gt;NV&lt;/b&gt;" in page and "<i>m</i>" not in page


@pytest.mark.unit
def test_an_agent_s_own_headings_sit_below_its_heading(tmp_path):
    page = _html(tmp_path)
    assert page.count("<h1") == 1                     # only the report's title
    assert re.search(r"<h4[^>]*>Market view</h4>", page)


def _fields(fragment):
    return re.findall(r'<span class="field">([^<]*)</span>', fragment)


@pytest.mark.unit
def test_run_details_show_each_value_as_its_own_field(tmp_path):
    settings = {**SETTINGS, "deep_think_provider": "anthropic", "deep_think_llm": "claude-opus-5-5",
                "data_vendors": {"core_stock_apis": "yfinance", "fundamental_data": "sec_edgar,yfinance"}}
    write_report_tree(_state(), "NVDA", tmp_path, settings=settings, html=True)
    page = (tmp_path / "complete_report.html").read_text(encoding="utf-8")
    header = page[page.index("<header"):page.index("</header>")]
    for value in ("anthropic", "claude-opus-5-5", "openai", "gpt-6-luna", "market", "news",
                  "sec_edgar", "yfinance"):
        assert value in _fields(header)
    # Vendors are named by what they serve, and a chain keeps its order.
    assert "Prices" in header and "Fundamentals" in header and "fundamental_data" not in header
    assert header.index(">sec_edgar<") < header.rindex(">yfinance<")


@pytest.mark.unit
def test_the_contents_name_each_section_once_and_list_its_agents_beneath(tmp_path):
    page = _html(tmp_path)
    nav = page[page.index('<nav class="contents"'):page.index("</nav>")]
    assert "<ol" not in nav                     # no list numbers beside the sections' own I-V
    assert re.search(r'<a href="#s1"><span class="num">I</span>\s*<span class="label">Analyst Team Reports</span></a>', nav)
    assert re.search(r'<a href="#s1-1"><span class="bar"></span>\s*<span class="label">Market Analyst</span></a>', nav)


@pytest.mark.unit
def test_the_section_rail_opens_on_hover_and_keyboard_focus(tmp_path):
    page = _html(tmp_path)
    css = page[page.index("<style>"):page.index("</style>")]
    # Wide screens: a rail centred on the left edge whose names are hidden from
    # sight only (still read by screen readers) until it is pointed at or focused.
    assert "top: 50%" in css and "translateY(-50%)" in css
    assert ".contents:hover .label" in css and ".contents:focus-within .label" in css
    assert "display: none" not in css.split(".contents .label", 1)[1].split("}", 1)[0]


@pytest.mark.unit
def test_the_sections_stay_within_reach(tmp_path):
    page = _html(tmp_path)
    nav = page[page.index('<nav class="contents"'):page.index("</nav>")]
    assert "<h2" not in nav                                         # the list needs no heading
    assert 'id="top"' in page and 'href="#top"' in page             # a way back on small screens
    assert ".contents { position: fixed;" in page                   # beside the text on wide ones


@pytest.mark.unit
def test_the_page_heading_is_the_ticker_and_its_rating(tmp_path):
    page = _html(tmp_path)
    heading = re.search(r"<h1>(.*?)</h1>", page).group(1)
    assert re.sub(r"<[^>]+>", "", heading).split() == ["NVDA", "Overweight"]


@pytest.mark.unit
def test_the_header_carries_the_official_logo_unaltered(tmp_path):
    from importlib.resources import files

    logo = files("tradingagents").joinpath("assets/tauric-logo.svg").read_text(encoding="utf-8").strip()
    page = _html(tmp_path)
    header = page[page.index("<header"):page.index("</header>")]
    assert logo in header                           # drawn in the page, nothing fetched
    assert 'href="https://tauric.ai"' in header and 'aria-label="Tauric Research"' in header
    assert header.index('class="logo"') < header.index("<h1")   # leads the header, above the title


@pytest.mark.unit
def test_the_page_credits_its_maker_in_a_line_of_text(tmp_path):
    page = _html(tmp_path)
    footer = page[page.index('<footer class="credit">'):page.index("</footer>")]
    assert re.sub(r"<[^>]+>", "", footer).split() == ["TradingAgents", "powered", "by", "Tauric", "Research"]
    # The logo already leads to tauric.ai; the credit leads to the project and the org.
    assert 'href="https://github.com/TauricResearch/TradingAgents"' in footer
    assert 'href="https://github.com/TauricResearch"' in footer and "tauric.ai" not in footer
    assert "<svg" not in footer and 'class="brand"' in footer
    assert page.index("</main>") < page.index('<footer class="credit">')


@pytest.mark.unit
def test_the_packaged_logo_stays_inert(tmp_path):
    # The logo is drawn inside every report, so it may only ever hold shapes:
    # no script, event handler, link, embedded document or external reference.
    from importlib.resources import files

    logo = files("tradingagents").joinpath("assets/tauric-logo.svg").read_text(encoding="utf-8")
    tags = set(re.findall(r"<\s*([a-zA-Z][\w:-]*)", logo))
    assert tags <= {"svg", "path", "rect", "circle", "g", "defs", "clipPath", "linearGradient", "stop"}
    assert not re.search(r"\son\w+\s*=|href|url\(|@import|javascript:|<!entity|<!doctype", logo, re.IGNORECASE)


@pytest.mark.unit
def test_normalized_html_matches_the_saved_markdown_outline_and_preserves_fences(tmp_path):
    from markdown_it import MarkdownIt

    body = ("# View\n## Trend\n### Detail\n#### Existing\n##### Nested\n###### Deep\n\n"
            "```markdown\n# Code heading\n```\n\n~~~markdown\n## Tilde code heading\n~~~\n\n"
            "Setext view\n===========\n\n> # Quoted view\n\n"
            "## I. Outlook\n\n### Market Analyst\n\n# After agent heading\n")
    report = write_report_tree(_state(market_report=body), "NVDA", tmp_path, settings=SETTINGS,
                               normalize_headings=True)
    markdown = report.read_text(encoding="utf-8")
    page = (tmp_path / "complete_report.html").read_text(encoding="utf-8")
    main = page.split("<main>", 1)[1].split("</main>", 1)[0]
    rendered_markdown = MarkdownIt("commonmark", {"html": False}).render(markdown)
    headings = r"<h([1-6])(?:\s[^>]*)?>(.*?)</h[1-6]>"

    assert re.findall(headings, main) == re.findall(headings, rendered_markdown)[1:]
    assert [(level, title) for level, title in re.findall(headings, main) if title in
            {"View", "Trend", "Detail", "Existing", "Nested", "Deep"}] == [
        ("4", "View"), ("4", "Trend"), ("4", "Detail"),
        ("4", "Existing"), ("5", "Nested"), ("6", "Deep"),
    ]
    # The fork's existing normalizer preserves these heading forms. HTML must
    # retain the same outline rather than applying another demotion pass.
    assert ("1", "Setext view") in re.findall(headings, main)
    assert ("1", "Quoted view") in re.findall(headings, main)
    assert ("2", "I. Outlook") in re.findall(headings, main)
    assert re.findall(headings, main).count(("3", "Market Analyst")) == 2
    assert ("4", "After agent heading") in re.findall(headings, main)
    assert "```markdown\n# Code heading\n```" in markdown
    assert "~~~markdown\n## Tilde code heading\n~~~" in markdown
    assert "# Code heading" in main and "## Tilde code heading" in main
    assert not re.search(r"<h[1-6][^>]*>(?:Code heading|Tilde code heading)</h[1-6]>", main)

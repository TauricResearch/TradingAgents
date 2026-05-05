from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


def _inline_markup(text: str) -> str:
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    if text.startswith("`") and text.endswith("`") and len(text) > 2:
        return f"<font name='Courier'>{text[1:-1]}</font>"
    return text


def markdown_to_story(md_path: Path):
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("H1", parent=styles["Heading1"], fontSize=18, leading=22, spaceAfter=8)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=14, leading=18, spaceBefore=8, spaceAfter=6)
    body = ParagraphStyle("Body", parent=styles["BodyText"], fontSize=10.5, leading=15, spaceAfter=4)
    bullet = ParagraphStyle("Bullet", parent=body, leftIndent=14, bulletIndent=5)

    story = []
    for raw in md_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            story.append(Spacer(1, 3))
            continue
        if line.startswith("# "):
            story.append(Paragraph(_inline_markup(line[2:].strip()), h1))
            continue
        if line.startswith("## "):
            story.append(Paragraph(_inline_markup(line[3:].strip()), h2))
            continue
        if line.startswith("### "):
            story.append(Paragraph(_inline_markup(line[4:].strip()), styles["Heading3"]))
            continue
        if line.startswith("- "):
            story.append(Paragraph(_inline_markup(line[2:].strip()), bullet, bulletText="•"))
            continue
        if raw.startswith("1. ") or raw.startswith("2. ") or raw.startswith("3. ") or raw[:2].isdigit():
            story.append(Paragraph(_inline_markup(line), body))
            continue
        story.append(Paragraph(_inline_markup(line), body))
    return story


def main() -> None:
    src = Path("docs/flint/WORK_PERFORMED_IO_ANALYSIS_REPORT_2026-05-01.md")
    out = Path("output/pdf/WORK_PERFORMED_IO_ANALYSIS_REPORT_2026-05-01.pdf")
    out.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(out),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="TradingAgents Flint Shadow Work Performed IO Analysis Report",
        author="Codex",
    )
    story = markdown_to_story(src)
    doc.build(story)
    print(out)


if __name__ == "__main__":
    main()

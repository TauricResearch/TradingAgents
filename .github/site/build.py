# Copyright 2026 Tauric Research
# SPDX-License-Identifier: Apache-2.0

"""Build the project site from README.md: English at the root and one folder per language.

Pages are rendered with GitHub's Markdown API and styled with Primer; relative links point to the
repository on GitHub. A translation is used only when it keeps the README's commands and links.
The output `complete` is true when every language has one.

usage: build.py <out dir> <translations dir> [lang ...]
env: GITHUB_TOKEN, GITHUB_REPOSITORY"""

import json
import os
import re
import sys
import urllib.request
from pathlib import Path

REPO = os.environ.get("GITHUB_REPOSITORY", "TauricResearch/TradingAgents")
BLOB = f"https://github.com/{REPO}/blob/main/"
RAW = f"https://raw.githubusercontent.com/{REPO}/main/"
PRIMER = "https://cdn.jsdelivr.net/npm/@primer"
STYLES = [
    f"{PRIMER}/primitives@11.10.0/dist/css/functional/themes/light.css",
    f"{PRIMER}/primitives@11.10.0/dist/css/functional/themes/dark.css",
    f"{PRIMER}/css@22.3.3/dist/primitives.css",
    f"{PRIMER}/css@22.3.3/dist/base.css",
    f"{PRIMER}/css@22.3.3/dist/markdown.css",
]
SYNTAX = "".join(
    f"{classes}{{color:var(--color-prettylights-syntax-{token})}}"
    for classes, token in [
        (".pl-c", "comment"),
        (".pl-c1,.pl-s .pl-v", "constant"),
        (".pl-e,.pl-en", "entity"),
        (".pl-ent", "entity-tag"),
        (".pl-k", "keyword"),
        (".pl-s,.pl-pds,.pl-sr", "string"),
        (".pl-smi,.pl-s .pl-s1", "storage-modifier-import"),
        (".pl-v,.pl-smw", "variable"),
    ]
)
TITLE = "TradingAgents: Towards Agentic Finance Research"


def render(markdown: str) -> str:
    body = json.dumps({"text": markdown, "mode": "markdown", "context": REPO}).encode()
    headers = {
        "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
        "Accept": "application/vnd.github+json",
    }
    req = urllib.request.Request("https://api.github.com/markdown", body, headers, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        html = resp.read().decode()

    def absolute(m: re.Match[str]) -> str:
        attr, path = m.group(1), m.group(2)
        if re.match(r"[a-z]+:|#|/", path):
            return m.group(0)
        return f'{attr}="{BLOB if attr == "href" else RAW}{path}"'

    return re.sub(r'\b(href|src|srcset)="([^"]+)"', absolute, html)


def page(body: str, lang: str) -> str:
    links = "\n".join(f'<link rel="stylesheet" href="{url}">' for url in STYLES)
    return f"""<!doctype html>
<html lang="{lang}" data-color-mode="auto" data-light-theme="light" data-dark-theme="dark">
<head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{TITLE}</title>
{links}
<style>.markdown-body{{box-sizing:border-box;max-width:980px;margin:0 auto;padding:32px 16px}}
.markdown-body a:not(.anchor){{text-decoration:underline;text-underline-offset:.2rem}}
{SYNTAX}</style>
</head><body><article class="markdown-body">
{body}
</article></body></html>
"""


CODE = re.compile(r"```.*?```", re.S)
LINK = re.compile(r'\]\(([^)\s]+)|(?:href|src|srcset)="([^"]+)"|(https?://[^\s)"\'<>]+)')


def targets(markdown: str) -> set[str]:
    return {next(g for g in m.groups() if g) for m in LINK.finditer(markdown)}


def commands(markdown: str) -> list[str]:
    """Code blocks without their comments, then inline code, as written."""
    blocks = [re.sub(r"[ \t]+#.*", "", block) for block in CODE.findall(markdown)]
    return blocks + sorted(re.findall(r"`[^`\n]+`", CODE.sub("", markdown)))


def translated(english: str, text: str) -> bool:
    """A translation is used when it is the whole README and only that, in another language:
    the same first line and closing link, the same link targets, the same commands in code
    blocks (their comments may be translated), and at most a fifth of the prose left as is."""
    lines, source = text.strip().splitlines(), english.strip().splitlines()
    if not lines or lines[0] != source[0] or targets(lines[-1]) != targets(source[-1]):
        return False
    if commands(text) != commands(english) or targets(text) != targets(english):
        return False
    prose = [
        p
        for p in CODE.sub("", english).splitlines()
        if len(p) > 30 and not p.lstrip().startswith("<")
    ]
    flat = " ".join(text.split())
    return sum(" ".join(p.split()) in flat for p in prose) <= len(prose) / 5


def main() -> None:
    out, translations, langs = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3:]
    english = Path("README.md").read_text(encoding="utf-8")
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(page(render(english), "en"), encoding="utf-8")
    missing = []
    for lang in langs:
        source = translations / f"{lang}.md"
        text = source.read_text(encoding="utf-8") if source.exists() else ""
        if not translated(english, text):
            missing.append(lang)
            continue
        (out / lang).mkdir(exist_ok=True)
        (out / lang / "index.html").write_text(page(render(text), lang), encoding="utf-8")
    if missing:
        print(f"::notice::No usable translation for {', '.join(missing)}: the site stays as it is")
    with open(os.environ.get("GITHUB_OUTPUT", os.devnull), "a", encoding="utf-8") as f:
        f.write(f"complete={'false' if missing else 'true'}\n")


if __name__ == "__main__":
    main()

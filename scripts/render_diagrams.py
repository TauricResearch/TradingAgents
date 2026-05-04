#!/usr/bin/env python3
"""Render all .dot and .mmd source files to .svg in docs/diagrams/.

Priority:
  1. .dot files  → dot (Graphviz, always reliable)
  2. .mmd files  → mmdc (Mermaid CLI, fallback via extract_mermaid.py)
"""
import subprocess, os, re, glob, sys

DIAGRAMS_DIR = "docs/diagrams"
HELPER = "scripts/extract_mermaid.py"


def run(cmd, capture=False):
    result = subprocess.run(cmd, capture_output=capture, text=True)
    if capture and result.returncode != 0:
        sys.stderr.write(result.stderr)
    return result.returncode == 0


def add_white_bg(svg_path):
    """Graphviz doesn't set a background; add a white rect as first child."""
    with open(svg_path) as fh:
        c = fh.read()
    if 'fill="white"' not in c:
        c = re.sub(r'(<svg[^>]+>\n)', r'\1<rect width="100%" height="100%" fill="white"/>\n', c)
        with open(svg_path, 'w') as fh:
            fh.write(c)


def render_dot(src, out):
    """Render .dot via graphviz dot command."""
    ok = run(["dot", "-Tsvg", src, "-o", out])
    if ok:
        add_white_bg(out)
    return ok


def render_mmd(src, out):
    """Render .mmd via mmdc, with front-matter strip as fallback."""
    ok = run(["mmdc", "-i", src, "-o", out, "-t", "neutral", "-b", "white"])
    if not ok:
        tmp = "/tmp/mmd-render.mmd"
        if run(["python3", HELPER, src, tmp]):
            ok = run(["mmdc", "-i", tmp, "-o", out, "-t", "neutral", "-b", "white"])
            try:
                os.remove(tmp)
            except OSError:
                pass
    return ok


print("Rendering diagrams...")
count = 0

for ext, render_fn in [(".dot", render_dot), (".mmd", render_mmd)]:
    for f in sorted(glob.glob(f"{DIAGRAMS_DIR}/*{ext}")):
        out = f.replace(ext, ".svg")
        name = os.path.basename(f)
        extname = ext.lstrip(".")
        print(f"  {name} ({extname}) -> {os.path.basename(out)}", end=" ... ")
        ok = render_fn(f, out)
        if ok:
            size = os.path.getsize(out)
            print(f"✓ {size:,}B")
            count += 1
        else:
            print("✗ FAILED")

print(f"\nDone. Generated {count} SVG file(s).")
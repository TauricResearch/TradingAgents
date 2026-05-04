#!/usr/bin/env python3
"""Render all .mmd Mermaid files to .svg in docs/diagrams/."""
import subprocess, os, glob, sys

DIAGRAMS_DIR = "docs/diagrams"
HELPER = "scripts/extract_mermaid.py"

def run(cmd, capture=False):
    result = subprocess.run(cmd, capture_output=capture, text=True)
    if capture and result.returncode != 0:
        sys.stderr.write(result.stderr)
    return result.returncode == 0

print("Rendering Mermaid diagrams...")
count = 0
for f in sorted(glob.glob(f"{DIAGRAMS_DIR}/*.mmd")):
    out = f.replace(".mmd", ".svg")
    name = os.path.basename(f)
    print(f"  {name} -> {os.path.basename(out)}")

    # Try direct render first (fast path — works when no front matter)
    ok = run(["mmdc", "-i", f, "-o", out, "-t", "neutral", "-b", "white"])

    if not ok:
        # Fall back: strip YAML front matter with helper, then render
        tmp = "/tmp/mmd-render.mmd"
        if run(["python3", HELPER, f, tmp]):
            ok = run(["mmdc", "-i", tmp, "-o", out, "-t", "neutral", "-b", "white"])
            try:
                os.remove(tmp)
            except OSError:
                pass

    if ok:
        size = os.path.getsize(out)
        print(f"    ✓ {size:,} bytes")
        count += 1
    else:
        print(f"    ✗ FAILED")

print(f"\nDone. Generated {count} SVG file(s).")
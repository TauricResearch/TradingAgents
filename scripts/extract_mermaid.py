#!/usr/bin/env python3
"""Extract mermaid block from a .mmd file (strips YAML front matter)."""
import re, sys

if len(sys.argv) != 3:
    print(f"Usage: {sys.argv[0]} <input.mmd> <output.mmd>", file=sys.stderr)
    sys.exit(1)

input_path, output_path = sys.argv[1], sys.argv[2]

with open(input_path) as f:
    content = f.read()

match = re.search(r'\x60\x60\x60mermaid\n(.*?)\n\x60\x60\x60', content, re.DOTALL)
if not match:
    print(f"No mermaid block in {input_path}", file=sys.stderr)
    sys.exit(1)

with open(output_path, 'w') as out:
    out.write(match.group(1))
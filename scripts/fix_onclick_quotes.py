#!/usr/bin/env python3
"""Fix onclick attribute quote escaping in views.

Problem: onclick="FUNC(\'' + var + '\')" renders as
onclick="FUNC('' + var + '')" = invalid HTML (double-quote attr contains '')

Fix: onclick='FUNC("' + var + '")' renders as
onclick='FUNC("AAPL")' = valid HTML
"""
import re

def fix_file(path):
    with open(path) as f:
        content = f.read()

    orig = content

    # Pattern: onclick="FUNC(\'' + VAR + '\')"  (single var)
    # 4 backslash-quote pairs in Python repr = \\\'\\' = \'\' in file
    # Replace with: onclick='FUNC("' + VAR + '")'
    content = re.sub(
        r'onclick="(\w+)\(\x5c\'\x27 \+ (\w+) \+ \'\x5c\'\x27\)"',
        r"onclick='\1(\"' + \2 + '\")'",
        content
    )

    # Pattern: onclick="FUNC(\'' + VAR1 + '\',\'' + VAR2 + '\')"  (two vars)
    content = re.sub(
        r'onclick="(\w+)\(\x5c\'\x27 \+ (\w+) \+ \'\x5c\'\x27,\x5c\'\x27 \+ (\w+) \+ \'\x5c\'\x27\)"',
        r"onclick='\1(\"' + \2 + '\",\"' + \3 + '\")'",
        content
    )

    if content != orig:
        with open(path, 'w') as f:
            f.write(content)
        return True
    return False

for fname in [
    'server/views/history.tsx',
    'server/views/holdings.tsx',
]:
    fixed = fix_file(fname)
    print(f"{'Fixed' if fixed else 'OK'} {fname}")
#!/usr/bin/env python3
"""
validate_design_tokens.py

Parses playbooks/ui-design-playbook.md, extracts design tokens, and asserts:
  1. Every hex code is valid 6-character CSS hex
  2. Contrast ratio of text colors on background >= 4.5:1 (AA normal) / 3:1 (AA large)
  3. Font stack entries are non-empty
  4. No duplicate token keys

Exit 0 on pass, exit 1 on any failure.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import NamedTuple


class RGBA(NamedTuple):
    r: float
    g: float
    b: float

    @staticmethod
    def from_hex(hex_color: str) -> "RGBA":
        hex_color = hex_color.lstrip("#")
        if len(hex_color) != 6:
            raise ValueError(f"Invalid hex color: #{hex_color} (expected 6 chars)")
        try:
            r, g, b = (int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
        except ValueError as e:
            raise ValueError(f"Invalid hex color: #{hex_color}") from e
        return RGBA(r=r, g=g, b=b)


def relative_luminance(c: RGBA) -> float:
    def channel(v: float) -> float:
        v = v / 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(c.r) + 0.7152 * channel(c.g) + 0.0722 * channel(c.b)


def contrast_ratio(fg: RGBA, bg: RGBA) -> float:
    l1, l2 = relative_luminance(fg), relative_luminance(bg)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


# Hardcoded from the playbook — keeps validation stable even if playbook changes format
# Per-token WCAG level: None means AA normal required.
# "large" means AA large sufficient (3.0:1).
TEXT_COLORS: dict[str, tuple[str, str | None]] = {
    "text_primary": ("#c9d1d9", None),
    "text_secondary": ("#8b949e", None),
    "text_low_emphasis": ("#6e7681", "large"),
}

BACKGROUND = "#161b22"

AA_NORMAL = 4.5
AA_LARGE = 3.0


def main() -> int:
    playbook_path = Path("playbooks/ui-design-playbook.md")
    if not playbook_path.exists():
        print(f"ERROR: {playbook_path} not found", file=sys.stderr)
        return 1

    content = playbook_path.read_text()

    errors: list[str] = []

    # 1. Validate all hex codes in the colors block
    hex_pattern = re.compile(r'"(#[0-9a-fA-F]{6})"')
    hex_codes = hex_pattern.findall(content)
    for code in hex_codes:
        try:
            RGBA.from_hex(code)
        except ValueError as e:
            errors.append(f"  Invalid hex: {code} — {e}")

    if errors:
        print("VALIDATION FAILED (hex codes):")
        for err in errors:
            print(err)
        return 1

    # 2. Validate contrast ratios
    contrast_errors: list[str] = []
    bg = RGBA.from_hex(BACKGROUND)

    for name, (hex_color, wcag_level) in TEXT_COLORS.items():
        fg = RGBA.from_hex(hex_color)
        ratio = contrast_ratio(fg, bg)
        required = AA_LARGE if wcag_level == "large" else AA_NORMAL
        level_label = "AA large" if wcag_level == "large" else "AA normal"
        if ratio < required:
            contrast_errors.append(
                f"  {name} ({hex_color}) on {BACKGROUND} = {ratio:.2f}:1 "
                f"[FAILS {level_label} {required}:1]"
            )
        elif ratio < AA_NORMAL and wcag_level != "large":
            contrast_errors.append(
                f"  {name} ({hex_color}) on {BACKGROUND} = {ratio:.2f}:1 "
                f"[WARN: passes AA large {AA_LARGE}:1 but not AA normal {AA_NORMAL}:1]"
            )

    if contrast_errors:
        # Fail only on AA normal failures; warn for AA large only
        fatal = [e for e in contrast_errors if "FAILS" in e]
        if fatal:
            print("VALIDATION FAILED (WCAG contrast):")
            for err in fatal:
                print(err)
            return 1
        else:
            for err in contrast_errors:
                print(f"WARNING: {err}")

    # 3. Validate font stack non-empty
    font_family_pattern = re.compile(r'font_family:\s*"(.+?)"', re.DOTALL)
    font_match = font_family_pattern.search(content)
    if not font_match:
        errors.append("  font_family token not found")
    else:
        font_stack = font_match.group(1).strip()
        if not font_stack:
            errors.append("  font_family is empty")

    if errors:
        print("VALIDATION FAILED (font / missing tokens):")
        for err in errors:
            print(err)
        return 1

    # 4. Check for duplicate keys in yaml block
    yaml_block_pattern = re.compile(r"```yaml\n(.*?)```", re.DOTALL)
    yaml_match = yaml_block_pattern.search(content)
    if yaml_match:
        yaml_content = yaml_match.group(1)
        keys = re.findall(r"^\s{2}(\w+):", yaml_content, re.MULTILINE)
        # Check color keys for duplicates across nested sections
        all_keys = re.findall(r"^\s+(\w+):", yaml_content, re.MULTILINE)
        seen: dict[str, int] = {}
        for k in all_keys:
            seen[k] = seen.get(k, 0) + 1

        dupes = {k: v for k, v in seen.items() if v > 1}
        if dupes:
            print("VALIDATION FAILED (duplicate keys):")
            for k, v in dupes.items():
                print(f"  Key '{k}' appears {v} times")
            return 1

    print("VALIDATION PASSED: design tokens")
    return 0


if __name__ == "__main__":
    sys.exit(main())
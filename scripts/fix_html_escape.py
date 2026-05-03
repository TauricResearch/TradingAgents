#!/usr/bin/env python3
"""Fix HTML escaping in workflow.tsx and exits.tsx.

Two bugs:
1. split('\n') uses literal backslash+n, not a newline → split fails
2. lesson/thesis/notes inserted into HTML without escaping → broken DOM
"""
import re

def html_escape(s):
    """Python-side HTML escape for strings going into JS template literals."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

# ── workflow.tsx ─────────────────────────────────────────────────────────────

with open("server/views/workflow.tsx", encoding="utf-8") as f:
    content = f.read()

# Fix 1: add _esc helper function + fix split('\n') → split with actual newline
old_split = """      if (item.hasPostMortem && item.lesson) {
        var short = (item.lesson.split('\\n')[0] || '').substring(0, 80);
        html += '<div class="card-thesis">' + short + (item.lesson.length > 80 ? '…' : '') + '</div>';
      }"""

new_split = """      if (item.hasPostMortem && item.lesson) {
        var _esc = function(s) { return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); };
        var parts = item.lesson.split(/\\r?\\n/);
        var short = (parts[0]||'').substring(0,80);
        html += '<div class="card-thesis">' + _esc(short) + (item.lesson.length > 80 ? '…' : '') + '</div>';
      }"""

# Fix 2: escape item.thesis in approved stage
old_thesis = "if (item.thesis) html += '<div class=\"card-thesis\">' + item.thesis + '</div>';"
new_thesis = "if (item.thesis) html += '<div class=\"card-thesis\">' + _esc(item.thesis) + '</div>';"

# The _esc function needs to be defined in the renderWorkflowCard scope
# We need to add it before the if (stageId === ...) blocks

if old_split in content:
    content = content.replace(old_split, new_split)
    print("Fixed: split + HTML escape in workflow")
else:
    print("NOT FOUND: split block in workflow")
    # Debug
    idx = content.find("split('")
    if idx >= 0:
        print("  Found 'split(' at:", repr(content[idx-5:idx+30]))

if old_thesis in content:
    content = content.replace(old_thesis, new_thesis)
    print("Fixed: thesis HTML escape in workflow")
else:
    print("NOT FOUND: thesis block in workflow")

with open("server/views/workflow.tsx", "w", encoding="utf-8") as f:
    f.write(content)

# ── exits.tsx ────────────────────────────────────────────────────────────────

with open("server/views/exits.tsx", encoding="utf-8") as f:
    content = f.read()

# Add _e helper + escape invThesis and notes
old_inv = "// Invalidation thesis (flat: invalidation_thesis, nested: invalidation.thesis)\n        const invThesis = p.invalidation?.thesis ?? p.invalidation_thesis ?? '—';\n        html += '<div><strong>Invalidation:</strong> ' + invThesis + '</div>';"
new_inv = "// Invalidation thesis (flat: invalidation_thesis, nested: invalidation.thesis)\n        var _e = function(s){return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');};\n        const invThesis = p.invalidation?.thesis ?? p.invalidation_thesis ?? '—';\n        html += '<div><strong>Invalidation:</strong> ' + _e(invThesis) + '</div>';"

old_notes = "if (p.notes) {\n          html += '<div class=\"notes\">' + p.notes + '</div>';\n        }"
new_notes = "if (p.notes) {\n          html += '<div class=\"notes\">' + _e(p.notes) + '</div>';\n        }"

if old_inv in content:
    content = content.replace(old_inv, new_inv)
    print("Fixed: invThesis escape in exits")
else:
    print("NOT FOUND: invThesis block in exits")

if old_notes in content:
    content = content.replace(old_notes, new_notes)
    print("Fixed: notes escape in exits")
else:
    print("NOT FOUND: notes block in exits")

# Also escape p.thesis in exits
old_thesis_exits = "html += '<div><strong>Thesis:</strong> ' + (p.thesis || '—') + '</div>';"
new_thesis_exits = "html += '<div><strong>Thesis:</strong> ' + _e(p.thesis || '—') + '</div>';"
if old_thesis_exits in content:
    content = content.replace(old_thesis_exits, new_thesis_exits)
    print("Fixed: thesis escape in exits")
else:
    print("NOT FOUND: thesis in exits")

with open("server/views/exits.tsx", "w", encoding="utf-8") as f:
    f.write(content)

print("All done.")
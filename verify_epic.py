#!/usr/bin/env python3
"""Verify epic state: blog registry separation."""
import json, os, subprocess

root = "/Users/petersmith/Dev/GitHub/TradingAgents"
os.chdir(root)

def load_jsonl(path):
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]

# 1. docs INDEX has no blog entries
docs = load_jsonl("docs/INDEX.jsonl")
blog_in_docs = [e for e in docs if "blog" in e.get("file", "")]
print(f"docs/INDEX.jsonl: {len(docs)} entries")
print(f"  Blog entries in docs INDEX: {len(blog_in_docs)} {'FAIL' if blog_in_docs else 'PASS'}")

# 2. blog INDEX has 2 entries
blog = load_jsonl("docs/blog/INDEX.jsonl")
print(f"docs/blog/INDEX.jsonl: {len(blog)} entries {'FAIL' if len(blog) != 2 else 'PASS'}")

# 3. Blog files on disk match index
blog_files = sorted([f.name for f in os.scandir("docs/blog") 
                     if f.is_file() and f.name.endswith(".md") and f.name != "INDEX.jsonl"])
indexed_blog = sorted([e["file"] for e in blog])
print(f"Blog files on disk: {blog_files}")
print(f"Blog indexed files: {indexed_blog}")
print(f"  Blog file/index match: {blog_files == indexed_blog} {'PASS' if blog_files == indexed_blog else 'FAIL'}")

# 4. No raw Database() outside src/lib/db.ts
result = subprocess.run(
    ["grep", "-r", "-l", "new Database", "src/"],
    capture_output=True, text=True
)
violations = [l for l in result.stdout.splitlines() if "src/lib/db.ts" not in l and l.strip()]
print(f"\nRaw Database() outside src/lib/db.ts: {violations or 'NONE'} {'FAIL' if violations else 'PASS'}")

# 5. just check passes
result2 = subprocess.run(["just", "check"], capture_output=True, text=True, timeout=60)
passed = result2.returncode == 0
print(f"\njust check: {'PASS' if passed else 'FAIL'}")
if not passed:
    print(result2.stderr[-500:])

# 6. reg-sync confirms
result3 = subprocess.run(["bun", "scripts/reg-sync.ts", "--all"], capture_output=True, text=True, timeout=30)
ok_all = "✓ up to date" in result3.stdout and result3.returncode == 0
print(f"reg-sync --all: {'PASS' if ok_all else 'FAIL'}")
if not ok_all:
    print(result3.stdout[-500:])

print("\n✅ Verification complete")
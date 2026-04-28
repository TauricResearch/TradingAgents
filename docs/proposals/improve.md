# Improvement Plan: COR_CLI.md — Drop `tmp/`, config at repo root

> **Companion to:** [COR_CLI.md](./COR_CLI.md)
> **Trigger:** User intent — *remove `tmp/` folder; config file lives directly
> in the project root.*
> **Status:** Action list, ready to apply.

This file lists every concrete edit needed so `COR_CLI.md` is internally
consistent with the "no `tmp/`, config at repo root" decision, plus the
follow-up decisions that the move forces (gitignore vs check-in, naming,
template file).

---

## 1. Why this exists

The current working copy of `COR_CLI.md` is half-migrated:

- §3.7 prose says the new default is `<repo>/cli_chain.json`.
- The Python helper in §3.7 (line 351) still writes to `Path.cwd() / "tmp" /
  "cli_chain.json"` — re-creates the folder we just removed.
- 8 other sections still describe `tmp/` paths or `tmp/`-specific behavior
  (e.g. *"Add `tmp/` to `.gitignore`"*).
- The doc no longer states whether the new repo-root file is checked into
  git or ignored — both are defensible, but undefined-behavior here is the
  worst option.

Code review of these edits classified the helper-vs-prose contradiction as
**Critical** and the 8 stale references as **High**. This file resolves both
in one consistent pass.

---

## 2. Required edits to `COR_CLI.md`

Apply in order. Line numbers refer to the current working copy (476 lines).

### 2.1 §3.7 — Helper code (Critical)

**Line 351** in the `_config_path()` snippet:

```diff
 def _config_path() -> Path:
     override = os.environ.get("TRADINGAGENTS_CHAIN_CONFIG")
     if override:
         return Path(override)
-    return Path.cwd() / "tmp" / "cli_chain.json"
+    return Path.cwd() / "cli_chain.json"
```

**Line 360–364** in `save_chain_order()`:

```diff
 def save_chain_order(order: list[str]) -> Path:
     path = _config_path()
-    path.parent.mkdir(parents=True, exist_ok=True)
+    # Only the env-var override may point into a non-existent dir.
+    if path.parent != Path.cwd():
+        path.parent.mkdir(parents=True, exist_ok=True)
     path.write_text(json.dumps({"version": 1, "order": order}, indent=2))
     return path
```

**Line 339** — remove the dangling import comment (`DEFAULT_ORDER` is defined
in `config.py`, not `runner.py`):

```diff
-from .runner import ChainRunner  # for DEFAULT_ORDER constant ref
```

### 2.2 §3.7 — Heading & prose (Medium)

**Line 297**:

```diff
-### 3.7 Config order ở `default path project`
+### 3.7 Vị trí file config (repo root)
```

**Line 299**:

```diff
-Theo yêu cầu: *"config mỗi list step run nên để ở root"*.
+Theo yêu cầu: *"config danh sách step run đặt ngay tại repo root, không
+dùng `tmp/`"*.
```

**Line 302**:

```diff
-- **Mặc định:** `<repo>/cli_chain.json` (default).
+- **Mặc định:** `<repo>/cli_chain.json` (repo root, gitignored — xem §2.5
+  của improve.md để biết lý do).
```

### 2.3 §2 Mục tiêu — Goal #3 (High)

**Line 50**:

```diff
-3. **Order step được khai báo data-driven**: lưu danh sách step run hiện tại
-   vào `tmp/` (theo yêu cầu), có thể chỉnh sửa trước mỗi run.
+3. **Order step được khai báo data-driven**: lưu danh sách step run hiện tại
+   vào `cli_chain.json` ở **repo root**, có thể chỉnh sửa trước mỗi run.
```

### 2.4 §3.1 Tree comment (Low)

**Line 74**:

```diff
-│   ├── config.py               # tmp/ load + save helpers
+│   ├── config.py               # cli_chain.json load + save helpers
```

### 2.5 §3.7 — Decide gitignore vs commit (High — new content)

**Add a new sub-section after the Schema block** (insert before "#### Helpers"):

```markdown
#### Gitignore vs commit

Quyết định: **gitignore** `cli_chain.json` ở repo root, kèm một file
`cli_chain.example.json` được check vào git làm template.

| Phương án                           | Khi nào nên dùng                               | Tại sao **không** chọn lúc này |
|-------------------------------------|------------------------------------------------|----------------------------------|
| Commit `cli_chain.json`             | Cả team luôn chạy cùng một order               | Mâu thuẫn với mục tiêu "user chỉnh trước mỗi run" — mỗi commit của một dev sẽ ép order lên người khác. |
| Gitignore `cli_chain.json` + commit `cli_chain.example.json` ✅ | Mỗi dev có order riêng; team có template chung | Đây là kịch bản hiện tại. |

Hành động cụ thể:

1. Thêm `cli_chain.json` vào `.gitignore`.
2. Commit `cli_chain.example.json` chứa `DEFAULT_ORDER` làm seed.
3. Subcommand `cli chain init` (xem §6) copy example → `cli_chain.json`.
```

### 2.6 §4 Edge cases (High)

**Line 413** — replace the table row:

```diff
-| Step name có trong `tmp/cli_chain.json` nhưng chưa import (ví dụ typo) | `ChainRunner._validate` raise rõ ràng kèm danh sách step hợp lệ      |
+| Step name có trong `cli_chain.json` nhưng chưa import (ví dụ typo)     | `ChainRunner._validate` raise rõ ràng kèm danh sách step hợp lệ      |
```

### 2.7 §5 Migration plan (High)

**Line 424** — PR 1:

```diff
-   - Không tạo `tmp/cli_chain.json` → load default.
+   - Không tạo `cli_chain.json` → load `DEFAULT_ORDER`.
```

**Line 429–430** — PR 2:

```diff
-   - Thêm `load_chain_order()` đọc `tmp/cli_chain.json`.
-   - Thêm `tmp/` vào `.gitignore` nếu chưa có.
+   - Thêm `load_chain_order()` đọc `<repo>/cli_chain.json`.
+   - Thêm `cli_chain.json` (single file, không phải folder) vào `.gitignore`.
+   - Commit `cli_chain.example.json` làm template.
```

**Line 435** — PR 3:

```diff
-   - Subcommand `cli chain edit` → mở `$EDITOR` trên `tmp/cli_chain.json`.
+   - Subcommand `cli chain init` → copy `cli_chain.example.json` → `cli_chain.json`.
+   - Subcommand `cli chain edit` → mở `$EDITOR` trên `<repo>/cli_chain.json`.
```

### 2.8 §8 Open questions (Medium)

**Line 473**:

```diff
-2. `tmp/cli_chain.json` có nên được auto-tạo (template) khi user lần đầu chạy
-   `cli chain edit` không? — đề xuất: có, dùng `DEFAULT_ORDER` làm template.
+2. Khi user chạy `cli chain edit` mà chưa có `cli_chain.json`, ta auto-init
+   từ `cli_chain.example.json` hay raise lỗi yêu cầu chạy `cli chain init`?
+   — đề xuất: auto-init để giảm ma sát; in một dòng cảnh báo "created from
+   example" để user biết chuyện gì xảy ra.
```

### 2.9 §4 worked example (Medium — restore)

The previous edit deleted §4 ("Ví dụ: thêm 1 step mới mà không break flow").
That section was the **proof** that the design satisfies goal #2. Restore a
condensed version (≈15 lines, not the original 50):

```markdown
## 4. Worked example: add a step without breaking flow

Thêm step `post-slack` sau `publish-notion`:

1. Tạo `cli/chain/steps/post_slack.py` với `@register_step` và
   `should_run` chỉ True khi `ctx.notion_page_url` đã có.
2. Sửa `cli_chain.json` ở repo root, chèn `"post-slack"` giữa
   `"publish-notion"` và `"display-report"`.

Không sửa `runner.py`, `context.py`, hay step nào khác. Nếu file
`cli_chain.json` không tồn tại → step `post-slack` đơn giản không chạy
(chain dùng `DEFAULT_ORDER` không bao gồm tên này).
```

Renumber sections after §4 accordingly: current §4 becomes §5, etc.

---

## 3. Checklist for the implementer

- [ ] Apply 2.1 (helper code — Critical)
- [ ] Apply 2.2 (heading + prose)
- [ ] Apply 2.3 (goal #3 wording)
- [ ] Apply 2.4 (tree comment)
- [ ] Apply 2.5 (gitignore decision — new content)
- [ ] Apply 2.6 (edge case table row)
- [ ] Apply 2.7 (migration plan PR 1, PR 2, PR 3)
- [ ] Apply 2.8 (open question rewording)
- [ ] Apply 2.9 (restore §4 worked example, renumber)
- [ ] Final: `grep -n "tmp/" docs/proposals/COR_CLI.md` returns **zero hits**
- [ ] Final: heading numbering goes §1 → §2 → §3 → §4 → §5 → §6 → §7 → §8
      with no gaps

---

## 4. Verification

After edits, run:

```bash
# Must return nothing
grep -nE 'tmp/|default path project' docs/proposals/COR_CLI.md

# Must show DEFAULT_ORDER and Path.cwd() / "cli_chain.json" close together
grep -nA1 'Path.cwd' docs/proposals/COR_CLI.md
```

Both checks must pass before merging the doc edits.

---

## 5. Implementation impact (when COR_CLI lands as code)

When the actual `cli/chain/` package is implemented per the corrected
proposal, the only path-related code is:

```python
# cli/chain/config.py
import json, os
from pathlib import Path

DEFAULT_ORDER: list[str] = [
    "collect-user-input", "build-config", "init-graph",
    "prepare-results-dir", "patch-message-buffer", "run-graph-stream",
    "save-report", "transform-chart", "publish-notion", "display-report",
]

CONFIG_FILENAME = "cli_chain.json"
EXAMPLE_FILENAME = "cli_chain.example.json"

def _config_path() -> Path:
    override = os.environ.get("TRADINGAGENTS_CHAIN_CONFIG")
    if override:
        return Path(override)
    return Path.cwd() / CONFIG_FILENAME

def load_chain_order() -> list[str]:
    path = _config_path()
    if not path.exists():
        return list(DEFAULT_ORDER)
    data = json.loads(path.read_text())
    return list(data["order"])

def save_chain_order(order: list[str]) -> Path:
    path = _config_path()
    if path.parent != Path.cwd():
        path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, "order": order}, indent=2))
    return path
```

And one `.gitignore` addition:

```gitignore
# Per-developer chain order; commit cli_chain.example.json instead.
cli_chain.json
```

Nothing else creates, references, or depends on `tmp/`.

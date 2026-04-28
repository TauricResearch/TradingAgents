# Proposal: Chain of Responsibility cho CLI

> **Status:** Draft
> **Author:** TradingAgents core
> **Scope:** Refactor `cli/main.py::run_analysis()` từ một monolithic function dài
> ~360 dòng thành một **Chain of Responsibility (CoR)** gồm các *step* có
> contract thống nhất, có thể thêm / bớt / hoán đổi mà không phá vỡ flow.

---

## 1. Vấn đề hiện tại

Hiện trong `cli/main.py`, hàm [`run_analysis()`](../../cli/main.py:935) là một
hàm tuyến tính dài, gom tất cả các giai đoạn vào một block duy nhất:

1. Thu thập input từ người dùng (`get_user_selections()`)
2. Build `config` từ selections
3. Khởi tạo `StatsCallbackHandler`, `TradingAgentsGraph`, `MessageBuffer`
4. Tạo thư mục `results_dir` / log file
5. Patch (decorator) `MessageBuffer` để ghi log
6. Chạy graph stream + cập nhật UI Live (rich layout)
7. Ghi report ra disk
8. Transform → JSON → vẽ chart PNG
9. (Tuỳ chọn) Publish lên Notion
10. (Tuỳ chọn) Hiển thị full report ra console

### Hệ quả

- **Khó thêm step mới**: muốn chèn ví dụ "gửi email", "upload S3", "log to
  Sentry", "post Slack" → phải sửa thẳng vào `run_analysis()`, dễ break flow.
- **Khó tắt / bật từng phần**: hiện tại chỉ có hardcoded `if save_choice`,
  `if notion_choice`. Mỗi feature bật/tắt phải sửa code.
- **Step không có tên**: không có cách reference "post-analysis: notion-publish"
  từ ngoài (CLI flag, config file, tmp file).
- **State chia sẻ ngầm qua biến local**: `final_state`, `chart_json`,
  `chart_png_path`, `save_path`… mỗi biến được dùng lại ở step sau dưới dạng
  local variable, không có struct rõ ràng → một step mới rất dễ shadow / quên
  truyền state.
- **Không có dry-run / pause / resume**: không thể "chạy lại từ step
  notion-publish" sau khi analysis đã xong.

---

## 2. Mục tiêu

1. **Mỗi step là một class có `name` duy nhất** (kebab-case, ví dụ
   `collect-user-input`, `render-chart`, `publish-notion`).
2. **Thêm / bỏ một step không phá vỡ flow** — step missing = skip, không crash.
3. **Order step được khai báo data-driven**: lưu danh sách step run hiện tại
   vào `tmp/` (theo yêu cầu), có thể chỉnh sửa trước mỗi run.
4. **Mỗi step nhận / trả `RunContext` thống nhất** — giống pattern middleware
   (Express / ASGI) thay vì nhiều positional arg.
5. **Step có thể `skip`, `halt`, hoặc `continue`** (3 outcome hợp lệ).
6. **Backward compatible**: `cli analyze` chạy mặc định ra y hệt hành vi hiện
   nay khi không có file config trong tmp.

---

## 3. Thiết kế chính

### 3.1 Module mới: `cli/chain/`

Theo coding rules (`.claude/rules/rules.md` — *Project Layout (Modular by
Responsibility)*), thêm package mới dưới `cli/`:

```
cli/
├── chain/
│   ├── __init__.py
│   ├── context.py              # RunContext dataclass
│   ├── base.py                 # Step ABC + StepResult enum
│   ├── registry.py             # STEP_REGISTRY (name → class) + decorator
│   ├── runner.py               # ChainRunner: load order + execute
│   ├── config.py               # tmp/ load + save helpers
│   └── steps/
│       ├── __init__.py         # auto-import → trigger @register_step
│       ├── collect_input.py    # collect-user-input
│       ├── build_config.py     # build-config
│       ├── init_graph.py       # init-graph
│       ├── prepare_results_dir.py  # prepare-results-dir
│       ├── patch_message_buffer.py # patch-message-buffer
│       ├── run_graph_stream.py # run-graph-stream
│       ├── save_report.py      # save-report
│       ├── transform_chart.py  # transform-chart
│       ├── publish_notion.py   # publish-notion
│       └── display_report.py   # display-report
└── main.py                     # giữ entry point Typer; gọi ChainRunner
```

Lý do đặt dưới `cli/` thay vì `tradingagents/`: chain này là chain **của CLI**
(nó orchestrate UI Live, prompts, file I/O, Notion publish…) — không phải core
graph logic. Đúng tinh thần `cli/ depends on tradingagents/, never the
reverse`.

### 3.2 `RunContext` — single source of truth

```python
# cli/chain/context.py
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

@dataclass
class RunContext:
    """State chia sẻ giữa các step trong chain.

    Mỗi step ĐỌC những gì cần và GHI vào field tương ứng. Không step nào được
    pop / mutate một field do step khác sở hữu (xem 3.5 ownership table).
    """
    # === Inputs (filled by collect-user-input) ===
    selections: dict[str, Any] = field(default_factory=dict)

    # === Build artifacts ===
    config: dict[str, Any] = field(default_factory=dict)
    selected_analyst_keys: list[str] = field(default_factory=list)

    # === Runtime objects ===
    graph: Any | None = None             # TradingAgentsGraph
    stats_handler: Any | None = None     # StatsCallbackHandler
    message_buffer: Any | None = None    # MessageBuffer (singleton import)

    # === I/O paths ===
    results_dir: Path | None = None
    report_dir: Path | None = None
    log_file: Path | None = None
    save_path: Path | None = None        # user-chosen save path (post-analysis)

    # === Stream output ===
    final_state: dict[str, Any] | None = None
    trace: list[dict[str, Any]] = field(default_factory=list)

    # === Post-processing artifacts ===
    chart_json: Any | None = None
    chart_png_path: Path | None = None
    notion_page_url: str | None = None
    notion_page_id: str | None = None

    # === Step bookkeeping ===
    skipped_steps: list[str] = field(default_factory=list)
    failed_steps: list[tuple[str, str]] = field(default_factory=list)  # (name, err)
```

Việc dùng `dataclass` (không `dict`) tuân thủ coding rule:
*"Use dataclasses or pydantic for structured data, not plain dicts."*

### 3.3 `Step` ABC + `StepResult`

```python
# cli/chain/base.py
from abc import ABC, abstractmethod
from enum import Enum
from .context import RunContext

class StepResult(str, Enum):
    CONTINUE = "continue"   # ok, go to next step
    SKIP = "skip"           # this step did nothing (e.g. user said "no")
    HALT = "halt"           # stop the entire chain (graceful)

class Step(ABC):
    """Base class for một mắt xích trong chain.

    Subclass MUST set `name` (unique kebab-case identifier).
    """
    name: str = ""           # e.g. "publish-notion"

    def should_run(self, ctx: RunContext) -> bool:
        """Override để skip điều kiện trước khi run.

        Trả False = step bị skip mà không log error.
        """
        return True

    @abstractmethod
    def run(self, ctx: RunContext) -> StepResult:
        """Thực thi step, đọc/ghi vào ctx, trả về kết quả."""
        ...
```

### 3.4 Registry + decorator

Dùng decorator để mỗi step file tự đăng ký với registry — không cần sửa file
trung tâm khi thêm step mới (tuân spirit "thêm step không break flow").

```python
# cli/chain/registry.py
from .base import Step

STEP_REGISTRY: dict[str, type[Step]] = {}

def register_step(cls: type[Step]) -> type[Step]:
    if not cls.name:
        raise ValueError(f"{cls.__name__} must define a non-empty `name`")
    if cls.name in STEP_REGISTRY:
        raise ValueError(f"Duplicate step name: {cls.name!r}")
    STEP_REGISTRY[cls.name] = cls
    return cls
```

Mỗi step file:

```python
# cli/chain/steps/publish_notion.py
from cli.chain.base import Step, StepResult
from cli.chain.context import RunContext
from cli.chain.registry import register_step

@register_step
class PublishNotionStep(Step):
    name = "publish-notion"

    def should_run(self, ctx: RunContext) -> bool:
        return ctx.final_state is not None

    def run(self, ctx: RunContext) -> StepResult:
        import typer
        choice = typer.prompt("\nPublish to Notion?", default="N").strip().upper()
        if choice not in ("Y", "YES"):
            return StepResult.SKIP
        # ... existing publish logic, write to ctx.notion_page_url ...
        return StepResult.CONTINUE
```

### 3.5 Ownership matrix (ai ghi field nào)

| Step                     | Reads                                | Writes                                          |
|--------------------------|--------------------------------------|-------------------------------------------------|
| `collect-user-input`     | —                                    | `selections`                                    |
| `build-config`           | `selections`                         | `config`, `selected_analyst_keys`               |
| `init-graph`             | `config`, `selected_analyst_keys`    | `graph`, `stats_handler`, `message_buffer`      |
| `prepare-results-dir`    | `config`, `selections`               | `results_dir`, `report_dir`, `log_file`         |
| `patch-message-buffer`   | `message_buffer`, `log_file`, `report_dir` | (mutates `message_buffer` methods)        |
| `run-graph-stream`       | `graph`, `stats_handler`, `selections`, `message_buffer` | `final_state`, `trace`         |
| `save-report`            | `final_state`, `selections`          | `save_path`                                     |
| `transform-chart`        | `final_state`, `selections`, `save_path`, `results_dir` | `chart_json`, `chart_png_path`|
| `publish-notion`         | `final_state`, `selections`, `chart_json`, `chart_png_path` | `notion_page_url`, `notion_page_id` |
| `display-report`         | `final_state`                        | —                                               |

**Quy tắc bất biến:** một field chỉ có **một writer** (ngoại trừ
`skipped_steps` / `failed_steps` do `ChainRunner` quản). Việc này khiến thêm
step không break step khác — bạn chỉ chèn được vào "khoảng trống" giữa các ô.

### 3.6 `ChainRunner`

```python
# cli/chain/runner.py
import logging
from .base import Step, StepResult
from .context import RunContext
from .registry import STEP_REGISTRY

logger = logging.getLogger(__name__)

class ChainRunner:
    def __init__(self, step_names: list[str]) -> None:
        self._validate(step_names)
        self.steps: list[Step] = [STEP_REGISTRY[name]() for name in step_names]

    @staticmethod
    def _validate(step_names: list[str]) -> None:
        if len(step_names) != len(set(step_names)):
            raise ValueError("Step names must be unique")
        unknown = [n for n in step_names if n not in STEP_REGISTRY]
        if unknown:
            raise ValueError(f"Unknown step(s): {unknown}")

    def run(self, ctx: RunContext | None = None) -> RunContext:
        ctx = ctx or RunContext()
        for step in self.steps:
            if not step.should_run(ctx):
                ctx.skipped_steps.append(step.name)
                logger.info("[chain] %s skipped (should_run=False)", step.name)
                continue
            try:
                result = step.run(ctx)
            except Exception as exc:
                ctx.failed_steps.append((step.name, repr(exc)))
                logger.exception("[chain] %s raised; continuing chain", step.name)
                continue
            if result == StepResult.HALT:
                logger.info("[chain] %s halted the chain", step.name)
                break
            if result == StepResult.SKIP:
                ctx.skipped_steps.append(step.name)
        return ctx
```

**Tính chất quan trọng:**

- Một step ném exception → **không crash chain**, chỉ ghi vào
  `ctx.failed_steps` và đi tiếp. Đây là cốt lõi của "thêm/bỏ không break flow":
  một step viết lỗi không kéo theo cả pipeline chết.
- Step kế tiếp nếu phụ thuộc field do step lỗi viết → `should_run()` của nó
  sẽ trả `False` (vì field còn `None`) → cũng skip. Cascading skip đúng nghĩa.
- `HALT` chỉ dành cho step phát hiện điều kiện không thể tiếp tục (ví dụ
  user huỷ ở `collect-user-input`).

### 3.7 Config order ở `tmp/`

Theo yêu cầu: *"config mỗi list step run nên để ở tmp"*.

#### Path
- **Mặc định:** `<repo>/tmp/cli_chain.json` (gitignored).
- Override: env var `TRADINGAGENTS_CHAIN_CONFIG=/path/to/json`.
- Nếu file **không tồn tại** → dùng `DEFAULT_ORDER` (xem 3.8) → CLI vẫn
  chạy ra hành vi cũ (backward compatible).

#### Schema (JSON)

```json
{
  "version": 1,
  "order": [
    "collect-user-input",
    "build-config",
    "init-graph",
    "prepare-results-dir",
    "patch-message-buffer",
    "run-graph-stream",
    "save-report",
    "transform-chart",
    "publish-notion",
    "display-report"
  ]
}
```

- Field `version`: phòng tương lai phải migrate.
- Field `order`: list step name. Validation:
  - Mỗi tên phải có trong `STEP_REGISTRY`.
  - Không trùng lặp.
  - Không bắt buộc đầy đủ — user có thể bỏ `publish-notion` nếu không cần.

#### Helpers

```python
# cli/chain/config.py
import json, os
from pathlib import Path
from .runner import ChainRunner  # for DEFAULT_ORDER constant ref

DEFAULT_ORDER: list[str] = [
    "collect-user-input", "build-config", "init-graph",
    "prepare-results-dir", "patch-message-buffer", "run-graph-stream",
    "save-report", "transform-chart", "publish-notion", "display-report",
]

def _config_path() -> Path:
    override = os.environ.get("TRADINGAGENTS_CHAIN_CONFIG")
    if override:
        return Path(override)
    return Path.cwd() / "tmp" / "cli_chain.json"

def load_chain_order() -> list[str]:
    path = _config_path()
    if not path.exists():
        return list(DEFAULT_ORDER)
    data = json.loads(path.read_text())
    return list(data["order"])

def save_chain_order(order: list[str]) -> Path:
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, "order": order}, indent=2))
    return path
```

### 3.8 `DEFAULT_ORDER`

Khớp 1-1 với behavior hiện tại của [`run_analysis()`](../../cli/main.py:935):

```
collect-user-input
build-config
init-graph
prepare-results-dir
patch-message-buffer
run-graph-stream
save-report
transform-chart
publish-notion
display-report
```

### 3.9 `cli/main.py` mới

```python
@app.command()
def analyze() -> None:
    from cli.chain.runner import ChainRunner
    from cli.chain.config import load_chain_order
    import cli.chain.steps  # noqa: F401  (trigger @register_step imports)

    runner = ChainRunner(load_chain_order())
    ctx = runner.run()
    if ctx.failed_steps:
        for name, err in ctx.failed_steps:
            console.print(f"[yellow]⚠ Step {name} failed: {err}[/yellow]")
```

`run_analysis()` cũ được **xoá hoàn toàn** — tránh dead code (rule:
*"Delete dead code; don't comment it out."*).

---

## 4. Ví dụ: thêm 1 step mới mà không break flow

Giả sử cần thêm step **`post-slack`** sau khi publish Notion thành công:

1. Tạo file `cli/chain/steps/post_slack.py`:

```python
import os
from cli.chain.base import Step, StepResult
from cli.chain.context import RunContext
from cli.chain.registry import register_step

@register_step
class PostSlackStep(Step):
    name = "post-slack"

    def should_run(self, ctx: RunContext) -> bool:
        return ctx.notion_page_url is not None and "SLACK_WEBHOOK_URL" in os.environ

    def run(self, ctx: RunContext) -> StepResult:
        import httpx
        httpx.post(
            os.environ["SLACK_WEBHOOK_URL"],
            json={"text": f"New analysis: {ctx.notion_page_url}"},
            timeout=10,
        )
        return StepResult.CONTINUE
```

2. Sửa `tmp/cli_chain.json`:

```json
{
  "version": 1,
  "order": [
    "collect-user-input", "build-config", "init-graph",
    "prepare-results-dir", "patch-message-buffer", "run-graph-stream",
    "save-report", "transform-chart", "publish-notion",
    "post-slack",
    "display-report"
  ]
}
```

Không có file `tmp/cli_chain.json`? → step `post-slack` đơn giản không chạy.
Không sửa code nào khác. Không break test cũ.

---

## 5. Edge cases & guarantees

| Tình huống                                            | Hành vi                                                              |
|--------------------------------------------------------|-----------------------------------------------------------------------|
| Step `transform-chart` raise `EnvironmentError`        | `failed_steps += [(transform-chart, ...)]`, `publish-notion.should_run()` thấy `chart_json is None` → skip nhánh chart, vẫn publish text |
| User bỏ `init-graph` ra khỏi order                     | `run-graph-stream.should_run()` thấy `ctx.graph is None` → skip; `final_state` vẫn `None` → các step sau cũng skip; chain kết thúc gracefully |
| Hai step trùng `name`                                  | `register_step` raise tại import time → fail-fast, không silently sai |
| Step name có trong `tmp/cli_chain.json` nhưng chưa import (ví dụ typo) | `ChainRunner._validate` raise rõ ràng kèm danh sách step hợp lệ      |
| User Ctrl+C giữa chừng                                 | Mỗi step nên là cancel-friendly. `run-graph-stream` đã streaming, lift KeyboardInterrupt ra ngoài runner để Typer xử lý exit code |

---

## 6. Migration plan

1. **PR 1 — scaffolding (no behavior change):**
   - Thêm `cli/chain/{base,context,registry,runner,config}.py`.
   - Thêm `cli/chain/steps/` chứa 10 step gói code hiện tại y hệt.
   - `cli/main.py::analyze()` chuyển sang dùng `ChainRunner(DEFAULT_ORDER)`.
   - Không tạo `tmp/cli_chain.json` → load default.
   - Test: `pytest tests/test_chain_default.py` — chạy `analyze()` mock và
     khẳng định `final_state`, `chart_png_path`, prompt order khớp baseline.

2. **PR 2 — config từ tmp:**
   - Thêm `load_chain_order()` đọc `tmp/cli_chain.json`.
   - Thêm `tmp/` vào `.gitignore` nếu chưa có.
   - Test: file thiếu → fallback default; file invalid → raise rõ ràng.

3. **PR 3 — quality of life:**
   - Subcommand `cli chain list` → in danh sách step + order hiện tại.
   - Subcommand `cli chain edit` → mở `$EDITOR` trên `tmp/cli_chain.json`.
   - Subcommand `cli chain reset` → xoá file tmp.

---

## 7. Testing strategy

Tuân `.claude/rules/rules.md` — *"Every public function should have at least
one test."* + flat `tests/` directory.

- `tests/test_chain_registry.py` — duplicate name raise; empty name raise.
- `tests/test_chain_runner.py` — exception trong step → next step vẫn chạy;
  HALT → break; SKIP → next step thấy field `None` → cascading skip.
- `tests/test_chain_config.py` — file missing → DEFAULT_ORDER; invalid JSON
  → raise; unknown step name → raise với message liệt kê tên hợp lệ.
- `tests/test_chain_steps_<name>.py` — mỗi step có ít nhất 1 test cho
  `should_run` và happy path. Mock I/O tại boundary (network, disk) đúng quy
  ước "*only mock at I/O boundaries*".

---

## 8. Non-goals

- **Không** thay LangGraph bằng chain này — chain chỉ orchestrate ở **CLI
  layer**. Bên trong `run-graph-stream`, vẫn dùng nguyên `TradingAgentsGraph`
  / LangGraph.
- **Không** tự động phân tích dependency giữa các step (như Airflow DAG).
  Order do user khai báo; ownership matrix giữ cho contract đơn giản.
- **Không** hỗ trợ song song hoá step. CLI là sequential pipeline.

---

## 9. Open questions

1. Có nên cho step **subscribe sự kiện** từ `run-graph-stream` (chunk-by-chunk)
   không? Hiện đang thiết kế "step chạy sau khi step trước done". Nếu cần
   real-time hook (ví dụ post từng analyst report ngay khi xong) → cần thêm
   pub/sub trong `RunContext`. Đề xuất: defer cho RFC tiếp theo.
2. `tmp/cli_chain.json` có nên được auto-tạo (template) khi user lần đầu chạy
   `cli chain edit` không? — đề xuất: có, dùng `DEFAULT_ORDER` làm template.
3. Có cần versioned migration của config khi đổi tên step? — version field
   đã được dự trù sẵn ở schema; chưa cần migrator vì chain còn nhỏ.

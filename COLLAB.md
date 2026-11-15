# 协作开发指南（COLLAB）

> 本文档是五人小组基于 `RE.md` 五个需求做并行开发的**协作手册**。目标：让每一位成员都能独立建分支、开发、测试、合并、处理冲突，且**互不阻塞、不互相踩脚**。
>
> 配套文件：`RE.md`（需求规格）。文档中所有命令均在当前仓库环境（Python 3.12 + `.venv` + pytest + ruff）实测可用。

---

## 0. 先看懂：一句话理解本项目

本项目是一个 **LLM 多智能体交易分析框架**（TradingAgents 的定制版）：你给它一个股票代码和日期，它模拟"分析师团队 → 多空辩论 → 交易员 → 风控 → 组合经理"，最后输出一个 **5 档评级**（Buy / Overweight / Hold / Underweight / Sell）。

`RE.md` 的 5 个需求就是在**不破坏这条主流程**的前提下，做 5 项独立的功能扩展。

---

## 1. 环境准备（每人只需做一次）

本仓库用 `uv` 管理 Python 3.12 虚拟环境（目录 `.venv`）。**所有命令都用 `./.venv/bin/python`，不要用系统自带 python。**

```bash
cd /home/lenovo/5351Project

# 确认 venv 存在
ls .venv/bin/python

# 确认测试工具已装（pytest / ruff）
.venv/bin/python -m pytest --version    # 能看到版本号即可
.venv/bin/ruff --version                # 能看到版本号即可
```

> 若某位成员换机器，需先重建环境。当前环境用 `uv` 创建，重建命令（供参考，未在本文档默认流程里反复出现）：
> ```bash
> uv venv --python 3.12 .venv
> uv pip install -e . --python .venv/bin/python
> uv pip install pytest pytest-subtests ruff --python .venv/bin/python
> ```

### 1.1 配置 git 身份（每人必做）

```bash
git config --global user.name  "你的GitHub用户名"
git config --global user.email "你的邮箱@example.com"
```

### 1.2 拉取最新代码并确认基线

```bash
git checkout main
git pull origin main
```

> ⚠️ 开发者**只能基于 `main` 派生新分支**，不要从别人的 feature 分支上再派生，否则合并时会互相缠绕。

---

## 2. ⭐ 开发顺序（先读这段，决定你从哪个需求开始）

这 5 个需求**不能全部完全并行**——存在"共享文件冲突"和"先后依赖"。下表是关键，请对照 `RE.md` 确认你负责的需求编号。

### 2.1 五个需求改动的文件一览（冲突地图）

| 需求 | 新增文件（彼此独立✅） | 改动已有文件（可能冲突⚠️） |
|------|----------------------|--------------------------|
| **R1 上下文预算化** | `tradingagents/graph/context_budget.py` | `bull/bear_researcher.py`、`research_manager.py`、`default_config.py` |
| **R2 辩论结构化** | `tradingagents/agents/utils/debate_skel.py` | `agents/schemas.py`、`bull/bear_researcher.py` |
| **R3 仓位映射** | `tradingagents/agents/utils/position.py` | `signal_processing.py`、`trading_graph.py`、`reporting.py`、`default_config.py` |
| **R4 成本感知收益** | （无，纯改） | `trading_graph.py`、`reflection.py`、`default_config.py` |
| **R5 成本仪表** | `tradingagents/llm_clients/usage_tracker.py` | `model_catalog.py`、`trading_graph.py`、`reporting.py`、`default_config.py` |

### 2.2 依赖关系（决定了先后）

- **R2 → R1 强依赖**：R2 先把辩论输出改成**结构化的论据**（`key_claims[]`、`stance_score` 等），R1 才能对"每条论据"做压缩/保留/废止。若 R1 先做，只能对一团文本粗暴截断，效果差。**且两者都改 `bull/bear_researcher.py`，必须串行。**
- **R4 最独立**：只改 `_fetch_returns` 这一个私有方法 + `reflection.py`，几乎不碰别人要改的地方，**最适合第一个启动。**
- **R3、R5 相对独立**：主要靠新增文件，但都动了 `trading_graph.py` / `reporting.py`，与 R4 有轻微交叉，需约定各改各的方法。

### 2.3 推荐分工与启动顺序

**阶段 0（1 天，全员）：定基线 & 契约**
- 统一定 `default_config.py` 里新增配置键的**命名规范**（建议前缀 `R<需求号>_`），避免 4 人同时加键互相覆盖。
- 冻结 R3/R4/R5 共同依赖的**接口字段命名**（如评级枚举、持仓结构）。

**阶段 1（可同时并行）——两条轨道：**

```
轨道 S（串行，辩论改造，2 人依次做）
  ├─ 成员A：R2 辩论结构化（先做，独占 bull/bear_researcher.py）
  └─ 成员C：R1 历史压缩（等 R2 合并后再做）

轨道 P（并行，相对独立，3 人同时做）
  ├─ 成员D：R4 成本感知收益（独立，先启动）
  ├─ 成员B：R5 成本仪表（增加独立文件）
  └─ 成员E：R3 仓位映射（增加独立文件）
```

> 建议：**成员A、D、B、E 可同时各自开分支**；**成员C 等 R2 合并后再开始**（或先做 R1 里不依赖结构化文本的"纯截断"部分，风险自担）。

---

## 3. 分支建立 SOP（每个人做项目前的固定动作）

### 3.1 从 main 新建你负责需求的分支

```bash
git checkout main                 # 回到主分支
git pull origin main              # 确保基于最新 main
git checkout -b feature/R2-debate-structure   # 换成你负责的需求名
```

分支命名规范：`feature/R<需求号>-<英文短名>`，例如：
- `feature/R1-context-budget`
- `feature/R2-debate-structure`
- `feature/R3-position-mapping`
- `feature/R4-cost-aware`
- `feature/R5-cost-meter`

### 3.2 确认你在正确分支

```bash
git branch --show-current         # 应输出 feature/R2-debate-structure
git status                        # 应显示在刚建的分支上，工作区干净
```

### 3.3 开发原则（写在开头，避免返工）

1. **只在你自己需求的新增文件里自由开发**；改共享文件（`default_config.py`、`trading_graph.py`、`reporting.py`、`bull/bear_researcher.py`、`schemas.py`）时，**只改你自己的那一段**，别动别人的。
2. 每完成一个小功能就**本地提交一次**，不要攒到最后一次提交。
3. 提交信息规范：`feat(R2): 添加辩论结构化 schema`、`fix(R1): 修复压缩时越界`。

---

## 4. 开发 & 提交 SOP

### 4.1 写代码时的自查

- 新增模块尽量是**纯函数**，方便独立测试。
- 改动已有函数时，**不要改变它的既有参数/返回值**，避免破坏别处调用（RE.md 反复强调"向后兼容"）。

### 4.2 提交（commit）

```bash
git add 文件1 文件2          # 只添加你自己改动的文件，不要 git add .
git commit -m "feat(R2): 新增 DebateTurn 结构化 schema"
```

> ⚠️ 不要 `git add .` 或 `git add -A`，否则可能把 `.env`（含 API key）、`.venv` 等误提交。`.env` 和 `.venv` 已被 `.gitignore` 忽略，但仍养成精确加文件的习惯。

### 4.3 提交到远端（push）

```bash
git push -u origin feature/R2-debate-structure
```
第一次用 `-u`（设置上游，之后直接 `git push` 即可）。

---

## 5. 测试 SOP（单元 / 集成 / 冒烟）

> 项目测试框架用 **pytest**，测试文件在 `tests/` 下。所有命令用 `.venv/bin/python` 运行。

### 5.1 单元测试（Unit）—— 你的主要测试方式

只测你新增的纯函数/模块，不依赖真实的 LLM 或网络。**没有额外的 LLM/网络调用，所以又快又免费。**

**（1）只跑你新写的测试文件：**
```bash
.venv/bin/python -m pytest tests/test_debate_skel.py -q
```

**（2）跑某个测试类或某条用例：**
```bash
.venv/bin/python -m pytest tests/test_debate_skel.py -q -k "test_stance_score_bounds"
```

**（3）跑全部分支测试（较快，排除集成）：**
```bash
.venv/bin/python -m pytest -q
```
> 项目默认 `-m "not integration"`，所以这条只会跑单元测试，不碰网络。

**（4）快速失败定位（打印详细输出）：**
```bash
.venv/bin/python -m pytest tests/test_debate_skel.py -q -v --tb=short
```

### 5.2 集成测试（Integration）—— 验证模块之间能对接

集成测试会真的调 LLM / 拉行情，**慢且花钱**，项目默认跳过。需要时可手动加上 `-m integration` 运行：

```bash
.venv/bin/python -m pytest -m integration -q
```

> 集成测试需要可用的 LLM 配置（本项目用 CityU Foundry，见 `.env`）。**建议在本地只跑单元测试，集成测试交给负责人集中跑。**

### 5.3 冒烟测试（Smoke）—— 确认主流程能跑通

这是验证"改动没把整条分析流程搞坏"的关键一步。因为要真实调用 LLM 和分析数据，较慢，**建议改动完自己跑一次**：

```bash
# 用配置好的 CityU Foundry 跑一次轻量分析（只选市场分析师，控制成本）
.venv/bin/python -c "
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph
config = DEFAULT_CONFIG.copy()
config['max_debate_rounds'] = 1
ta = TradingAgentsGraph(selected_analysts=('market',), config=config)
_, decision = ta.propagate('AAPL', '2024-05-10')
print('DECISION:', decision)
"
```
> 正常应输出一个评级（如 `Hold`），表示主流程未被破坏。

### 5.4 静态检查（ruff，代码规范）

项目用 ruff 做 lint（行宽 100，忽略 E501）：

```bash
.venv/bin/ruff check tradingagents/graph/context_budget.py   # 检查单个文件
```
> 若报错，按提示修改。`E501`（行太长）可忽略，不用改。

### 5.5 提交前必须强制的红线

> 🚨 **在提交前，务必保证：**
> 1. 你新增的测试文件 `pytest` 全绿。
> 2. `ruff check` 你改动/新增的文件无致命错误。
> 3. 冒烟测试能把主流程跑通（不破坏既有功能）。
>
> **未通过则不要提交，更不要 merge。**

---

## 6. 合并 SOP（Merge & PR）

### 6.1 合并前先同步主线（每人都要会）

在合并之前，**必须先把你分支上落后的 `main` 更新进来**。因为你做分支时 main 可能已经被别人更新了。

**推荐用 rebase（历史更干净）：**

```bash
git checkout feature/R2-debate-structure
git fetch origin main
git rebase origin/main
```

若 rebase 提示冲突 → 跳到第 7 节处理。

### 6.2 推到远端并开 Pull Request（PR）

```bash
git push origin feature/R2-debate-structure
```
然后到 GitHub 网页上 Open a Pull Request（PR 标题写需求名，正文写清改了什么、加了哪些测试）。

### 6.3 合并方式

- **推荐 PR 合并**（GitHub 网页操作），让负责人 review 后再 merge，避免直接把代码写进 main。
- 合并时选择 **Rebase and merge** 或 **Squash and merge**，保持 main 历史干净。
- **不要用 `git merge` 直接把分支并进 main**（除非你是维护人且已确认无冲突）。

---

## 7. 冲突修改 SOP（最让小白头疼，这里讲透）

> 冲突（conflict）**不是错误**，而是 git 发现"同一行代码被两个人改了，它不知道该保留谁的"。**正常情况，谁都能修。**

### 7.1 什么时候会遇到冲突

- `git rebase origin/main` 时（同步主线）
- `git merge` 时
- GitHub 网页合并 PR 提示"Can't merge"时

### 7.2 判断冲突的两种方式

**A. 本地 rebase/merge 时**，git 会停在冲突处并提示：
```
CONFLICT (content): Merge conflict in <文件>
```
此时用 `git status` 查看哪些文件有冲突。

**B. 先检查再操作**（不用真合并就能看冲突数）：
```bash
git merge-tree $(git merge-base HEAD origin/main) HEAD origin/main
```
> 若输出含 `<<<<<<<`，说明有冲突。

### 7.3 解决冲突的步骤（标准流程）

**第 1 步：看冲突文件**
```bash
git status                 # 找到 marked as conflict 的文件
```

**第 2 步：打开冲突文件，看到 git 的标记：**
```
<<<<<<< HEAD
你分支的代码
=======
main 分支的代码
>>>>>>> origin/main
```
- `<<<<<<< HEAD` 到 `=======` 之间 = **你（当前分支）的改动**
- `=======` 到 `>>>>>>>` 之间 = **对方（main/别的分支）的改动**

**第 3 步：手动决定保留哪份。** 把这三行标记删掉，只保留你要的代码。**两种常见处理：**
- 你俩改的是**不同地方** → 把两段都保留。
- 你俩改的是**同一行且冲突** → 和你需求负责人/对方沟通，协商保留谁的，或合并成一个折中版本。

**第 4 步：对每个冲突文件改好后，重新暂存并继续：**
```bash
git add 文件名                      # 标记冲突已解决
git rebase --continue              # 若你在 rebase 中
# 或 git merge --continue          # 若你在 merge 中
```

**第 5 步：确认无冲突残留**
```bash
git status                        # 应显示一切 clean / no conflicts
```

### 7.4 处理错了想撤销？别慌

```bash
git rebase --abort        # 放弃本次 rebase，回到 rebase 前
# 或
git merge --abort         # 放弃本次 merge
```
> 撤销后从 `7.1` 重新来，不会丢失已提交的代码。

### 7.5 冲突预防（最佳实践）

- **勤同步 main**：别一个分支工作一两个月才合并，每周至少 `git rebase origin/main` 一次，冲突会少很多。
- **只改自己需求的共享文件段**：见第 2 节"冲突地图"，多人同时改 `default_config.py` 第 40 行是冲突高发区，务必各加各的键、命名前缀隔离。

---

## 8. 常见 Git 救命命令速查

| 场景 | 命令 |
|------|------|
| 看当前分支 | `git branch --show-current` |
| 看所有分支 | `git branch -a` |
| 看改了什么 | `git status` / `git diff` |
| 新建并切到分支 | `git checkout -b feature/xxx` |
| 切回 main | `git checkout main` |
| 提交 | `git commit -m "feat: ..."` |
| 推远端（首次） | `git push -u origin feature/xxx` |
| 同步主线（rebase） | `git fetch origin main && git rebase origin/main` |
| 撤销 git add | `git reset HEAD 文件` |
| 撤销工作区改动 | `git checkout -- 文件` |
| 暂存不提交 | `git stash` / `git stash pop` |
| 跑测试 | `.venv/bin/python -m pytest tests/xxx.py -q` |
| 静态检查 | `.venv/bin/ruff check xxx.py` |

---

## 9. 五个需求验收对照（写代码前先对照 RE.md）

| 需求 | 期望新增文件 | 配套测试文件 | 关键验收 |
|------|-------------|-------------|---------|
| R1 | `graph/context_budget.py` | `tests/test_context_budget.py` | 压缩后 history ≤ 上限；关闭开关不破坏结构 |
| R2 | `agents/utils/debate_skel.py` | `tests/test_debate_skel.py` | 每轮输出含 stance_score/refuted_points |
| R3 | `agents/utils/position.py` | `tests/test_position.py` | 每评级映射出仓位；高波动降仓位 |
| R4 | （纯改） | `tests/test_cost_adjusted_returns.py` | 扣成本后 net ≤ gross；持有期可配置 |
| R5 | `llm_clients/usage_tracker.py` | `tests/test_usage_tracker.py` | 每次 run 生成成本 JSON；超预算熔断 |

> 每个需求的**详细验收标准**见 `RE.md` 对应小节。

---

## 10. 最终交付检查清单

- [ ] 你的分支 commit 提交信息清晰（`feat(Rn): ...`）
- [ ] 新增测试文件 `pytest` 全绿
- [ ] `ruff check` 无致命错误
- [ ] 冒烟测试主流程跑通
- [ ] 已同步最新 `main`（rebase）且无冲突
- [ ] PR 已开，正文说明改动 + 测试
- [ ] .env（含 key）未被提交（用 `git status` 确认，不见 `.env`）

---

> 有任何一步卡住：先 `git status` 看现状，再对照第 8 节速查表；冲突不慌，`--abort` 永远是你的后悔药。
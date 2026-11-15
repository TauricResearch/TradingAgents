# R5 · LLM 用量/成本仪表与预算熔断

> 对应 `RE.md` 需求 5（P5：用户对单次 run 的 token/成本无感知）。分支：`feature/cost-meter`。
> 本文只记录本轮实际完成的内容与实际测试结果；不含未经验证的真实服务结论。

## 1. 功能范围与使用

每次运行（API 的 `propagate()` 或 CLI `tradingagents`）都会：

- 聚合本轮所有 LLM 调用的输入/输出 token，并按价格表估算 USD；
- 在 `results_dir/costs/<ticker>_<date>.json` 写一份成本 JSON（成功、异常、预算停止都写；与是否保存报告无关）；
- 在 `complete_report.md` 顶部插入一行成本汇总；
- 设置预算后，达到阈值会**阻止后续的收费调用**（每次调用开始前检查），记录 `BUDGET_STOPPED`；已在途的请求仍会完成并计入，因此**总额可能略微超过阈值**。CLI 明确提示已发生费用与成本文件位置，且不把该 run 当作成功。

**预算配置**（二选一）：

- 配置文件：`max_run_budget_usd`（默认 `None` = 无上限；`0` 合法，首个计费调用即停；负数 / NaN / ±inf / 布尔 / 非数字会被拒绝）。
- 环境变量：`TRADINGAGENTS_RUN_BUDGET_USD`（数字字符串，显式解析校验，同样拒绝非法值），见 `.env.example`。

**用法**：

```bash
# 例如：单次运行不超过 0.50 美元
TRADINGAGENTS_RUN_BUDGET_USD=0.50 tradingagents --ticker NVDA --date 2026-01-09
```

程序化：

```python
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph
config = DEFAULT_CONFIG.copy()
config["max_run_budget_usd"] = 0.50
ta = TradingAgentsGraph(config=config)
state, signal = ta.propagate("NVDA", "2026-01-09")
print(state["llm_cost"])   # 成本汇总 dict
```

## 2. 主要设计

- **回调计量**：`llm_clients/usage_tracker.py` 的 `UsageTracker(BaseCallbackHandler)`，`raise_error=True`。同时覆盖 `on_llm_start` 与 `on_chat_model_start`；在 `on_llm_end` 聚合 token 与费用。handler 异常会真实中断底层请求（这是预算停止能"不发请求"的关键）。
- **模型识别**：`create_tier_client` 为每个 tier 的模型注入 `metadata={"ta_provider","ta_model"}`；各 provider client 的白名单放行 `metadata`。tracker 从 `on_*_start` 的 `metadata` 读取 provider/model；缺省回退到 serialized 的 `model_name`/`model`。
- **去重**：按 LangChain `run_id` 对 start 与 end 各去重一次（重试/流式重复事件只计一次）；end 缺失 start 也会被计为一次真实调用。
- **预算停止**：调用**开始前**检查 `spent >= budget`（`>=` 语义）；超限置 `stopped=True`、`stop_reason="BUDGET_STOPPED"` 并抛 `BudgetExceeded`。该异常在 `structured.py`（避免回退请求）、`settlement.py`（避免按瞬时失败重试）、`_memory_step`（避免吞掉）三处被显式放行。
- **成本保存**：`TradingAgentsGraph.write_costs()` 写 `results_dir/costs/<ticker>_<date>.json`；`_run_graph` 的 `try/finally` 保证成功/异常/停止都落盘，并把 `llm_cost` 注入返回的 state 供报告使用。CLI `run_analysis` 在 `finally` 中同样落盘、释放 checkpoint，并据 `budget_stopped` 区分成功收尾与停止收尾。

## 3. 验收标准 → 实现文件 → 实际测试函数

测试文件：`tests/test_usage_tracker.py`（全部为单元测试，离线、无网络）。

| 验收标准（RE.md 需求 5） | 实现文件 | 实际测试函数 |
|---|---|---|
| 每次 run 生成成本 JSON（成功/异常/停止；不保存报告也生成） | `graph/trading_graph.py`、`llm_clients/usage_tracker.py` | `test_api_run_writes_cost_json_via_propagate`、`test_api_run_writes_cost_json_when_the_run_raises`、`test_api_run_writes_cost_json_when_budget_stops`、`test_cli_run_writes_cost_json_via_run_analysis`、`test_cli_run_writes_cost_json_when_the_run_raises` |
| 报告汇总与 JSON 数值一致 | `reporting.py` | `test_report_header_matches_the_cost_json_amount` |
| 超限触发 `BUDGET_STOPPED` 且不再发新请求 | `llm_clients/usage_tracker.py`（真实回调分发 + 假模型请求计数） | `test_budget_stop_happens_before_the_next_real_request`、`test_budget_stop_after_a_billed_call_blocks_the_following_one`、`test_threshold_equality_stops` |
| CLI 停止路径清晰提示、释放 checkpoint、不报成功、不改动已真实完成的 agent 状态 | `cli/run.py` | `test_cli_reports_budget_stop_clearly_and_releases_the_checkpoint`、`test_budget_stop_does_not_mark_agents_completed_in_the_buffer`、`test_normal_finish_marks_agents_completed_in_the_buffer` |
| 计数不重复 | `llm_clients/usage_tracker.py` | `test_duplicate_start_events_for_one_run_id_count_once`、`test_duplicate_end_events_for_one_run_id_count_once`、`test_on_chat_model_start_is_counted`、`test_on_llm_start_is_counted_too` |
| 预算显式解析/校验（None 不转 float、拒绝 NaN/inf/负/bool/非数字） | `llm_clients/usage_tracker.py`、`default_config.py` | `test_none_budget_means_no_cap_and_is_not_coerced_to_float`、`test_zero_budget_is_legal`、`test_bad_budgets_are_rejected_loudly`、`test_numeric_string_budget_is_accepted_and_parsed`、`test_default_config_has_budget_none_and_env_override`、`test_env_budget_rejects_garbage` |
| 未知价格 → unknown，不冒充已知；本地默认未知；确认免费不阻断 | `llm_clients/usage_tracker.py`、`model_catalog.py` | `test_unknown_model_pricing_is_none_and_not_added`、`test_local_providers_are_unknown_unless_confirmed_free`、`test_confirmed_free_call_is_zero_and_does_not_block_a_zero_budget`、`test_price_table_accepts_an_overriding_provider_model_mapping` |
| 价格条目有官方来源与核对日期（快照，不联网） | `llm_clients/model_catalog.py` | `test_gpt_6_sol_price_is_the_verified_standard_short_context_rate`、`test_verified_entry_records_its_source_and_checked_date`、`test_every_shipped_price_has_a_source_entry` |
| provider/model 识别经真实 factory 与绑定后仍到达 tracker | `llm_clients/factory.py`、各 provider client | `test_metadata_reaches_the_model_through_create_tier_client`、`test_bound_model_still_delivers_metadata_to_the_tracker` |
| 预算异常不被回退/吞掉（structured / settlement / memory） | `agents/structured.py`、`memory/settlement.py`、`graph/trading_graph.py` | `test_structured_invoke_does_not_fall_back_on_budget_stop`、`test_settlement_reflection_budget_stop_is_not_swallowed`、`test_memory_step_does_not_swallow_budget_stop` |
| 在途请求在停止后仍计入 | `llm_clients/usage_tracker.py` | `test_in_flight_request_completing_after_stop_is_still_counted` |
| 每次运行独立计量（同图复用不继承费用/停止） | `graph/trading_graph.py`（`UsageTracker.reset()`） | `test_a_reused_graph_starts_each_run_with_a_fresh_meter` |
| 缺失 usage 记为不完整，不冒充已知零费用 | `llm_clients/usage_tracker.py`、`reporting.py` | `test_missing_usage_is_recorded_not_counted_as_known_zero`、`test_missing_usage_is_flagged_in_the_cost_json_and_report` |

## 4. 已知限制

- **未知价格**：价格表仅收录经核实的一条（`openai/gpt-6-sol`）。其余 `(provider, model)` 视为 `unknown`，其调用不计入金额（列入 `unknown_models`），不臆造价格。
- **缺失 usage**：若某次响应不带 `usage_metadata`，该调用计入 `missing_usage_calls`，汇总标记 `usage_complete=false`，JSON 与报告注明"tokens/cost 为下界"，**不**当作已知 $0.00。
- **在途请求可能超预算**：预算在调用**开始前**检查（`spent >= budget`），token 只有在调用**结束时**才可知；因此一个已在途的请求完成后可使总额略超上限（该完成仍被如实计入）。这是"准确记账优先于严格不超"的取舍。
- **计价范围**：金额按 **Standard（按需、非 Batch、非 Fast）短上下文（≤272K input）** 列表价估算；长上下文、Batch/Flex/Fast/缓存、区域/FedRAMP 附加价、促销价等**未建模**。实际账单位可能不同。
- **恢复执行的预算范围**：`UsageTracker.reset()` 在每次运行开始时清零，预算按**单次运行**计量；checkpoint 恢复会作为新一次运行重新计量，**不**累计中断前已花的金额。
- **真实服务尚未验证**：本轮所有验证均为**离线（假模型 + 固定价格快照）**；未调用真实 LLM，未核对真实账单，未在真实 provider 上验证 token 上报与价格一致性。

## 5. 本轮人工审查与修复记录（真实发生的，不含补造历史）

- 夹具修正：`CountingChatModel.bind_tools` 改为返回 `model_copy()`，绑定后仍走真实回调分发；E2E 假工厂保留 `callbacks` 并注入 provider/model 元数据，使固定价表命中；`selected_analysts` 正确传给 `Graph` 构造器。
- 静态审查发现（用户指出）：CLI 停止路径仍执行成功收尾（把全部 agent 标为 `completed` 并记录 "Completed analysis"）。已先补直接检查 `message_buffer` 消息与 `agent_status` 的测试，再修复为：成功收尾仅在正常完成执行；预算停止保留真实完成状态、记录停止原因。
- 价格核实（用户要求的提交前待办）：实际打开官方 `https://platform.openai.com/docs/pricing`，确认 `gpt-6-sol` Standard 短上下文为 input $2.00 / output $10.00；**修正了原表错误的 input 价 1.25**，并记录直接来源、核对日期（2026-11-14）与估算范围；补快照测试防回归。
- 修复过程中确认：`structured.py`、`settlement.py`、`_memory_step` 的宽泛 `except` 会吞掉 `BudgetExceeded`，已显式放行，避免触发回退请求或误记为瞬时失败。

## 6. 实际运行结果（本轮）

命令与结果（均在项目 `.venv` 内、离线运行，未联网、未调用真实 LLM）：

```
$ .venv/bin/python -m pytest tests/test_usage_tracker.py -q
48 passed

$ .venv/bin/python -m pytest -q          # 完整离线回归（默认 -m "not integration"）
1481 passed, 1 skipped, 1 deselected, 24 warnings, 100 subtests passed

$ .venv/bin/ruff check tradingagents cli tests/test_usage_tracker.py
All checks passed!
```

说明：`1 skipped` 为 `tests/test_bedrock_provider.py`（缺可选依赖 `langchain_aws`，与 R5 无关）；`1 deselected` 为默认排除的集成测试。

### 离线验证 vs 真实服务验证（区分）

- **本轮已验证（离线）**：回调计量、去重、预算停止（真实回调分发 + 假模型请求计数证明"无新请求"）、成本 JSON/报告落盘、CLI 成功/异常/停止三条路径、缺失 usage 标记、unknown 价格、价格快照与来源——均由上述 pytest/ruff 覆盖。
- **本轮未验证（真实服务）**：见下节“尚待小组完成的真实服务验证事项”。

### 尚待小组完成的真实服务验证事项

以下均需真实密钥与真实 provider，本轮未执行、未调用真实 LLM：

1. **token 上报真实性**：在真实 provider（含项目可能使用的 CityU Foundry / 学校 DS 端点，若启用）上确认 `usage_metadata` 被正确上报，计量与实际 token 相符。
2. **价格与账单一致性**：用一次小规模真实 run 的 token 数对照 provider 账单，验证 `MODEL_PRICING` 估算与实际扣费一致（当前仅核实 `openai/gpt-6-sol` 的 Standard 短上下文价）。
3. **`BUDGET_STOPPED` 真实时序**：在真实流式响应中确认预算阈值到达后**停止后无新的收费请求**；**在途请求的费用仍可能结算**（不影响"不再发起新请求"的结论）。
4. **checkpoint 恢复下的预算**：确认恢复执行会作为新一次运行重新计量（不累计中断前花费）符合预期，并在预算文档/提示中说明。
5. **缺失 usage 的真实表现**：确认某些真实 provider/模型在特定模式下确实不返回 usage 时，`missing_usage_calls`/`usage_complete=false` 的标记如实出现。

## 附录：导出原始 OpenCode 会话（供留存）

本机 OpenCode 版本为 `1.19.5`，以下命令均受支持（`opencode session list --format json`、`opencode export <sessionID>`、`opencode export <sessionID> --sanitize`）。导出步骤：

1. 列出会话并定位本次 R5 会话（按标题/工作目录匹配项目目录）：

   ```bash
   opencode session list --format json
   ```

2. 导出**原始 JSON**（保留不改，存入仓库外的课程归档目录）：

   ```bash
   opencode export <sessionID> > <archive-dir>/session-raw.json
   ```

3. 另生成**脱敏分享副本**（供组员查看；提交前核查是否适合外发）：

   ```bash
   opencode export <sessionID> --sanitize > <archive-dir>/session-sanitized.json
   ```

4. 只导出相关会话，**不要**复制整个会话数据库；原始 JSON 存仓库外，脱敏副本确认无密钥后再分享。**切勿**把任何含密钥的内容提交到仓库。

### 本次归档记录（R5）

- 会话 ID：`ses_e26ef51e1fferCCA3wNButQXCj`（标题 “R5 LLM 成本仪表与预算熔断只读分析”，目录为本项目）。
- 归档目录（仓库外）：`/mnt/c/Users/29440/CityU/SemA_CS5351_Software_Engineering/course-archive/R5-cost-meter/`
  - `session-raw.json`：原始导出，保留不改（未提交）。
  - `session-sanitized.json`：脱敏分享副本。
- 核查：两份文件均不含 `sk-`/JWT/AWS/GitHub/Bearer 令牌，且均不含当前 `DEEPSEEK_API_KEY` 的实际值；脱敏副本含大量脱敏标记，不含该 env 名。
- 校验（SHA-256）：
  - `session-raw.json`：`125e6bd7b61d65e568acc8ff13e0db6d2c0f1aab8156261f0858c75e2717cb42`
  - `session-sanitized.json`：`a3cce99a846ebb6749a65d2b6e2179d43413176a0ffdd545947604645856df49`

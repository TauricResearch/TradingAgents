# 可回放运行记录（安全边界）

每个本地分析 run 的目录可以包含三类互补记录：

- `events.jsonl`：版本化、追加式的生命周期事件，是状态和 SSE 回放的权威来源。
- `scratchpad.jsonl`：安全的调试标记流。每条记录只保留事件类型、稳定哈希、artifact 引用和少量数值元数据，并用 `event_id`/`event_sequence` 关联到 `events.jsonl`。
- `cycle-record/<sha256>.json`：单个 `CycleRecord` artifact，冻结该轮 query、非机密 spec 快照、事件范围和报告/scratchpad 引用，用于审计或离线 replay。

## 安全规则

`scratchpad.jsonl` 不是模型思考文本的存储位置。它不得持久化私有推理链、prompt、原始工具参数或原始工具结果；这些值仅被清洗后计算 SHA-256，并可指向已经过红化处理的 artifact。`thinking` 事件只表达 `private_reasoning_not_persisted`，因此可在回放中说明边界，而不会泄露模型内部推理。

当前注册的 scratchpad 生命周期事件为：`tool_limit`、`thinking`、`microcompact`、`compaction`、`context_cleared`。调用方应使用固定的 `detail_code` 和安全的计数/状态元数据，而不是任意文本。

## 当前范围

系统已提供 `DurableRunObserver.record_scratchpad(...)` 和 `record_cycle(...)`，供执行、上下文压缩与工具限额路径调用。CycleRecord 与 JSONL 均为本机文件系统审计功能；它们不上传，也不替代真实供应商/LLM 端到端评估。评判模型与目标模型隔离、contradiction 一票否决数据集及 source-alignment 投影仍需在对应评估路径接入。

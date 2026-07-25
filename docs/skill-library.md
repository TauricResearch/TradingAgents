# 本地研究 Skill Library

`tradingagents/skills/` 是内置、只读的方法论库，不是插件市场，也不会执行代码或新增工具。它解决的是“通用提示词缺少一致研究框架”，而不替代数据源、图编排或确定性的组合风控。

## 工作方式

1. `tradingagents/skills/registry.py` 的 `ROLE_SKILL_NAMES` 是唯一的角色到 skill 授权表；`ROLE_SKILL_TRIGGER_PATTERNS` 是唯一的、代码拥有的触发规则。
2. 每个 `library/<name>/SKILL.md` 都必须有受限 YAML frontmatter：`name`、`description`、`roles`、`triggers`、`output_schema`，随后是 Markdown 方法论正文。
3. Agent 每次启动都只注入该角色的 frontmatter 索引。只有已经存在于请求/公开报告中的文本命中代码拥有的确定性触发词时，才会从该角色的 allowlist 选择完整正文；默认最多一个（接口最高允许三个），未命中的正文不会进入 prompt。
4. 触发文本仅在 prompt 组装时短暂使用，不会写入 artifact、日志或 memory；它无法指定文件名、启用任意 skill 或改变工具权限。
5. 方法论只能约束研究结构。它不能注册工具、请求网络、运行脚本或把缺失数据变成事实；工具返回不可用时必须明确降级。

当前接入四个 analyst prompt，以及 Bull、Bear 和 Portfolio Manager。Skill 只规定研究与论证结构；Bull/Bear 仍是自由文本辩论，PM 仍使用既有 Pydantic 输出和确定性下单约束，skill 不改变这些合同。

`SkillRegistry.methodology_artifact(role, trigger_text=...)` 提供安全的结构化契约：角色、本轮实际选择的 skill 名称和要求字段。已有观察器上下文的运行还会把它写为通用 `methodology` artifact；它刻意不含触发文本、模型的逐步推理、草稿或理由。CLI 和普通单测无观察器时不写入任何 artifact。

四个 analyst 还各有一个代码拥有的 Pydantic 公共 scorecard：基本面（杜邦分解、Z/M 值、周期概率与红旗）、新闻（事件—传导—验证链和轮动）、市场（健康度、趋势/波动/参与度与轮动）和情绪（叙事—经营事实偏差）。自由文本报告仍是兼容路径；模型可在报告末尾给出 `methodology-artifact` JSON，只有通过 Pydantic 校验后才会从正文分离并在有观察器的运行中写成 `methodology_report` artifact。缺少、格式错误或超出 schema 的 JSON 一律保留原报告而不阻断流程。该 artifact 只允许公开结论、来源引用和数据限制，禁止逐步推理、提示词、草稿、工具调用轨迹和凭据。

主观阈值集中于 `DEFAULT_CONFIG["methodology_thresholds"]`（例如 Z/M 值、市场健康度和情绪偏差的解释边界），而非埋在 skill 文本中。它们只是解释参数，不会在数据缺失时替模型补造数值。

## 新增或修改 skill

将受评审的 `SKILL.md` 放在 `tradingagents/skills/library/<skill-name>/`。名称必须与目录名一致，只能用小写字母、数字和连字符。加载器拒绝：未知字段、空列表、未知角色、重复字段项、超 32 KiB 文档、符号链接和越出 library 的路径。

新增文件本身不会启用 skill。还必须显式、审查后同时修改 `ROLE_SKILL_NAMES` 和对应的 `ROLE_SKILL_TRIGGER_PATTERNS`；这保证 YAML preset 只启停/排序 analyst 角色，不能注入任意 prompt 或工具。运行 `pytest -q tests/test_skills_registry.py` 验证所有静态映射、触发上界和前端索引式加载规则。

## 当前范围

已覆盖财务质量、周期、新闻传导链、事件、行业轮动、市场状态、情绪偏差、增长假设和 PM 备忘录框架，也已提供上述 analyst 公共 Pydantic report schema。它不包含竞品文档所列的外部下载 skill、AKShare 脚本、LLM 动态技能选择或数据端点迁移；这些分别依赖数据层和可审计的运行时契约，不能通过提示词库冒充完成。

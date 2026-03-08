# TradingAgent 因子规则分析师改进计划

## 目标
为 TradingAgents 增加一个新的分析师：Factor Rule Analyst（因子规则分析师）。

## 里程碑
- [ ] 跑通 OpenCode ACP / acpx 直连链路
- [ ] 获取仓库并确认现有 analyst / graph / state 架构
- [ ] 设计手动导入的因子规则格式
- [ ] 实现因子规则加载与上下文注入
- [ ] 将新分析师接入分析流程
- [ ] 增加文档、示例与最小验证
- [ ] 本地 commit

## 已知约束
- Feishu 不支持 ACP thread binding，因此改用 acpx 直连 OpenCode
- 若 GitHub fork/push 无权限，可先完成本地 clone 与本地 commit

"""
交易决策记忆日志（Trading Memory Log）

在项目中的角色：
  - 实现 Agent 的「跨轮次记忆」能力 —— 每次交易决策都被记录，事后反思，下次运行时注入 Prompt
  - 是整个系统「越用越聪明」的数据基础
  - 采用纯 Markdown 文件存储（无数据库依赖），人类可读可编辑

核心设计：两阶段生命周期（Phase A / Phase B）
  ┌──────────────────────────────────────────────────────┐
  │  Phase A: 决策记录（propagate() 结束时调用）           │
  │    store_decision() → 追加一条 pending 状态的条目      │
  │    此时还不知道实际收益（因为刚做出决策）               │
  ├──────────────────────────────────────────────────────┤
  │  Phase B: 反思结算（下次同 ticker 运行时触发）          │
  │    _resolve_pending_entries() [trading_graph.py 调用]   │
  │      → _fetch_returns() 拉取实际收盘数据                │
  │      → Reflector.reflect_on_final_decision() LLM 反思  │
  │      → update_with_outcome() 将收益+反思写回条目        │
  ├──────────────────────────────────────────────────────┤
  │  读取（每次 propagate() 开始时调用）：                   │
  │    get_past_context() → 格式化历史条目注入 state        │
  └──────────────────────────────────────────────────────┘

文件格式示例：
    [2024-01-10 | AAPL | BUY | +2.0% | -1.0% | 5d]

    DECISION:
    基于技术面突破和基本面改善，建议买入...

    REFLECTION:
    当时忽略了美联储加息信号，导致 alpha 为负...

存储介质：
  - 单个 .md 文件（append-only），路径由 config["memory_log_path"] 指定
  - 条目间用 HTML 注释 <!-- ENTRY_END --> 分隔（LLM 不可能输出此标记，安全分隔符）
  - 更新操作使用「临时文件 + os.replace()」保证原子性（崩溃不损坏日志）

关键特性：
  - 幂等写入：同一 (date, ticker) 不重复追加
  - 条目轮转：resolved 条目超过 max_entries 时自动淘汰最旧的
  - pending 条目永不删除（代表未完成的工作）
"""

"""Append-only markdown decision log for TradingAgents."""

from typing import List, Optional
from pathlib import Path
import re

from tradingagents.agents.utils.rating import parse_rating


class TradingMemoryLog:
    """追加式交易决策记忆日志。

    用纯 Markdown 文件实现了一个简易但可靠的事件溯源（Event Sourcing）系统。
    不依赖数据库，文件即存储，人类可直接阅读和编辑。

    线程安全说明：
      - 单进程内安全（Python GIL 保证单次 write 原子性）
      - 多进程并发不安全（如需支持需加文件锁），当前设计为单进程串行调用
    """

    # HTML 注释作为硬分隔符：LLM 生成的文本中不可能出现此标记，
    # 因此可以安全地用它来切分条目而不会误伤内容
    _SEPARATOR = "\n\n<!-- ENTRY_END -->\n\n"
    # 预编译正则表达式 —— 避免每次 load_entries() 都重新编译
    _DECISION_RE = re.compile(r"DECISION:\n(.*?)(?=\nREFLECTION:|\Z)", re.DOTALL)
    _REFLECTION_RE = re.compile(r"REFLECTION:\n(.*?)$", re.DOTALL)

    def __init__(self, config: dict = None):
        """初始化记忆日志。

        Args:
            config: 配置字典，关键字段：
              - memory_log_path: 日志文件路径（None 则禁用所有功能）
              - memory_log_max_entries: 已解决条目的上限（None 表示不限）
        """
        cfg = config or {}
        self._log_path = None
        path = cfg.get("memory_log_path")
        if path:
            # 展开用户家目录（~）
            self._log_path = Path(path).expanduser()
            # 确保父目录存在（递归创建）
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
        # 可选的已解决条目上限。None 表示不启用轮转
        self._max_entries = cfg.get("memory_log_max_entries")

    # ═══════════════════════════════════════════
    # Phase A: 写入路径 —— 记录决策（propagate 结束时调用）
    # ═══════════════════════════════════════════

    def store_decision(
        self,
        ticker: str,
        trade_date: str,
        final_trade_decision: str,
    ) -> None:
        """在日志末尾追加一条 pending 状态的决策条目。

        调用时机：trading_graph.py 的 _run_graph() 末尾，图执行完毕后立即调用。
        此时还不知道实际收益，所以条目标记为 pending，等下次运行时再结算。

        幂等保证：先做快速文本扫描检查是否已存在同 (date, ticker) 的 pending 条目，
        避免重复运行导致重复追加。这是 O(n) 扫描但比完整解析快得多。

        条目格式：
            [2024-01-15 | AAPL | BUY | pending]

            DECISION:
            {final_trade_decision 内容}

            <!-- ENTRY_END -->

        Args:
            ticker: 标的代码
            trade_date: 交易日期
            final_trade_decision: LLM 输出的完整决策文本
        """
        if not self._log_path:
            return
        # 幂等守卫：快速原始文本扫描而非完整解析（性能考虑）
        if self._log_path.exists():
            raw = self._log_path.read_text(encoding="utf-8")
            for line in raw.splitlines():
                if line.startswith(f"[{trade_date} | {ticker} |") and line.endswith("| pending]"):
                    return
        rating = parse_rating(final_trade_decision)
        tag = f"[{trade_date} | {ticker} | {rating} | pending]"
        entry = f"{tag}\n\nDECISION:\n{final_trade_decision}{self._SEPARATOR}"
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write(entry)

    # ═══════════════════════════════════════════
    # 读取路径（Phase A + Phase B 都会用到）
    # ═══════════════════════════════════════════

    def load_entries(self) -> List[dict]:
        """从日志文件中解析所有条目并返回结构化列表。

        每次调用都重新读取和解析整个文件。对于小型日志文件（<1000 条）这足够快。
        如果未来需要高频读取可加内存缓存层。

        Returns:
            条目字典列表，每个字典包含 date/ticker/rating/pending/raw/alpha/holding/decision/reflection
        """
        if not self._log_path or not self._log_path.exists():
            return []
        text = self._log_path.read_text(encoding="utf-8")
        raw_entries = [e.strip() for e in text.split(self._SEPARATOR) if e.strip()]
        entries = []
        for raw in raw_entries:
            parsed = self._parse_entry(raw)
            if parsed:
                entries.append(parsed)
        return entries

    def get_pending_entries(self) -> List[dict]:
        """返回所有 pending 状态的条目（待结算决策）。

        被 trading_graph.py 的 _resolve_pending_entries() 调用，
        用于找出需要拉取实际收益数据并进行反思的决策记录。

        Returns:
            pending=True 的条目字典列表
        """
        return [e for e in self.load_entries() if e.get("pending")]

    def get_past_context(self, ticker: str, n_same: int = 5, n_cross: int = 3) -> str:
        """生成用于注入 Agent Prompt 的历史上下文字符串。

        这是「记忆注入」的核心方法。被 Propagator.create_initial_state() 调用，
        将结果写入 state["past_context"]，供 PM（投资组合管理）节点参考。

        策略：优先返回同一 ticker 的最近历史（n_same 条），再补充跨 ticker 教训（n_cross 条）。
        同 ticker 条目展示完整信息（决策+收益+反思），跨 ticker 只展示反思精华。

        为什么区分 same / cross？
          - 同 ticker 历史：高度相关，Agent 需要知道「这个股票上次怎么判的」
          - 跨 ticker 历史：「通用教训」，如「加息周期中不要追高成长股」

        Args:
            ticker: 当前分析的标的代码
            n_same: 返回的同 ticker 最大条目数（默认5）
            n_cross: 返回的跨 ticker 最大条目数（默认3）

        Returns:
            格式化的上下文字符串，无历史时返回空字符串
        """
        entries = [e for e in self.load_entries() if not e.get("pending")]
        if not entries:
            return ""

        same, cross = [], []
        # 从最新到最旧遍历，取最近的 n_same+n_cross 条
        for e in reversed(entries):
            if len(same) >= n_same and len(cross) >= n_cross:
                break
            if e["ticker"] == ticker and len(same) < n_same:
                same.append(e)
            elif e["ticker"] != ticker and len(cross) < n_cross:
                cross.append(e)

        if not same and not cross:
            return ""

        parts = []
        if same:
            parts.append(f"Past analyses of {ticker} (most recent first):")
            parts.extend(self._format_full(e) for e in same)
        if cross:
            parts.append("Recent cross-ticker lessons:")
            parts.extend(self._format_reflection_only(e) for e in cross)
        return "\n\n".join(parts)

    # ═══════════════════════════════════════════
    # Phase B: 更新路径 —— 结算收益 + 写入反思（下次运行时触发）
    # ═══════════════════════════════════════════

    def update_with_outcome(
        self,
        ticker: str,
        trade_date: str,
        raw_return: float,
        alpha_return: float,
        holding_days: int,
        reflection: str,
    ) -> None:
        """将一条 pending 条目更新为已解决状态（单条更新）。

        操作内容：
          1. 找到匹配 (trade_date, ticker) 的第一条 pending 条目
          2. 将标签从 [... | pending] 更新为 [... | +2.0% | -1.0% | 5d]
          3. 在条目末尾追加 REFLECTION 段

        原子性保证：使用「写入临时文件 → os.replace()」模式。
        如果在写入过程中崩溃，原文件完好无损（只有 .tmp 残留，无害）。

        Args:
            ticker: 标的代码
            trade_date: 交易日期
            raw_return: 原始收益率（小数，如 0.02 表示 +2%）
            alpha_return: 超额收益率（小数）
            holding_days: 实际持仓天数
            reflection: LLM 生成的反思文本
        """
        if not self._log_path or not self._log_path.exists():
            return

        text = self._log_path.read_text(encoding="utf-8")
        blocks = text.split(self._SEPARATOR)

        pending_prefix = f"[{trade_date} | {ticker} |"
        raw_pct = f"{raw_return:+.1%}"
        alpha_pct = f"{alpha_return:+.1%}"

        updated = False
        new_blocks = []
        for block in blocks:
            stripped = block.strip()
            if not stripped:
                new_blocks.append(block)
                continue

            lines = stripped.splitlines()
            tag_line = lines[0].strip()

            if (
                not updated
                and tag_line.startswith(pending_prefix)
                and tag_line.endswith("| pending]")
            ):
                # 从现有 pending 标签中解析出 rating 字段
                fields = [f.strip() for f in tag_line[1:-1].split("|")]
                rating = fields[2]
                new_tag = (
                    f"[{trade_date} | {ticker} | {rating}"
                    f" | {raw_pct} | {alpha_pct} | {holding_days}d]"
                )
                rest = "\n".join(lines[1:])
                new_blocks.append(
                    f"{new_tag}\n\n{rest.lstrip()}\n\nREFLECTION:\n{reflection}"
                )
                updated = True
            else:
                new_blocks.append(block)

        if not updated:
            return

        new_blocks = self._apply_rotation(new_blocks)
        new_text = self._SEPARATOR.join(new_blocks)
        # 原子写入：先写 .tmp 再 replace，保证不产生半写状态
        tmp_path = self._log_path.with_suffix(".tmp")
        tmp_path.write_text(new_text, encoding="utf-8")
        tmp_path.replace(self._log_path)

    def batch_update_with_outcomes(self, updates: List[dict]) -> None:
        """批量更新多条 pending 条目（单次读+单次原子写）。

        比逐条调用 update_with_outcome() 高效 —— 只读一次文件、只写一次文件，
        而非 N 次读+N 次 write。被 _resolve_pending_entries() 在处理完所有
        同 ticker 的 pending 条目后一次性调用。

        内部用字典做 O(1) 匹配查找，避免 N*M 的嵌套循环。

        Args:
            updates: 待更新的列表，每个元素必须包含键：
              ticker, trade_date, raw_return, alpha_return, holding_days, reflection
        """
        if not self._log_path or not self._log_path.exists() or not updates:
            return

        text = self._log_path.read_text(encoding="utf-8")
        blocks = text.split(self._SEPARATOR)

        # 构建 (date, ticker) → update_dict 的查找表，实现 O(1) 分发
        update_map = {(u["trade_date"], u["ticker"]): u for u in updates}

        new_blocks = []
        for block in blocks:
            stripped = block.strip()
            if not stripped:
                new_blocks.append(block)
                continue

            lines = stripped.splitlines()
            tag_line = lines[0].strip()

            matched = False
            for (trade_date, ticker), upd in list(update_map.items()):
                pending_prefix = f"[{trade_date} | {ticker} |"
                if tag_line.startswith(pending_prefix) and tag_line.endswith("| pending]"):
                    fields = [f.strip() for f in tag_line[1:-1].split("|")]
                    rating = fields[2]
                    raw_pct = f"{upd['raw_return']:+.1%}"
                    alpha_pct = f"{upd['alpha_return']:+.1%}"
                    new_tag = (
                        f"[{trade_date} | {ticker} | {rating}"
                        f" | {raw_pct} | {alpha_pct} | {upd['holding_days']}d]"
                    )
                    rest = "\n".join(lines[1:])
                    new_blocks.append(
                        f"{new_tag}\n\n{rest.lstrip()}\n\nREFLECTION:\n{upd['reflection']}"
                    )
                    del update_map[(trade_date, ticker)]
                    matched = True
                    break

            if not matched:
                new_blocks.append(block)

        new_blocks = self._apply_rotation(new_blocks)
        new_text = self._SEPARATOR.join(new_blocks)
        tmp_path = self._log_path.with_suffix(".tmp")
        tmp_path.write_text(new_text, encoding="utf-8")
        tmp_path.replace(self._log_path)

    # ═══════════════════════════════════════════
    # 辅助方法
    # ═══════════════════════════════════════════

    def _apply_rotation(self, blocks: List[str]) -> List[str]:
        """当已解决条目数超过 max_entries 时淘汰最旧的记录。

        轮转策略：
          - 只淘汰已解决（resolved）的条目 —— pending 条目代表未完成的工作，永不删除
          - 按「最早解决的先淘汰」原则（FIFO），保留最新的历史
          - 未启用上限或未超限时原样返回

        为什么不用 LRU？因为这是时序日志，天然按时间排序，FIFO 最合理。

        Args:
            blocks: 所有条目块列表（含空块）

        Returns:
            可能被裁剪后的条目块列表
        """
        if not self._max_entries or self._max_entries <= 0:
            return blocks

        # 给每个块打上 (是否已解决) 标签，通过解析 tag 行判断
        decisions = []
        for block in blocks:
            stripped = block.strip()
            if not stripped:
                decisions.append((block, False))
                continue
            tag_line = stripped.splitlines()[0].strip()
            is_resolved = (
                tag_line.startswith("[")
                and tag_line.endswith("]")
                and not tag_line.endswith("| pending]")
            )
            decisions.append((block, is_resolved))

        resolved_count = sum(1 for _, r in decisions if r)
        if resolved_count <= self._max_entries:
            return blocks

        to_drop = resolved_count - self._max_entries
        kept: List[str] = []
        for block, is_resolved in decisions:
            if is_resolved and to_drop > 0:
                to_drop -= 1
                continue
            kept.append(block)
        return kept

    def _parse_entry(self, raw: str) -> Optional[dict]:
        """将原始文本块解析为结构化字典。

        解析标签行格式：[date | ticker | rating | status_or_raw | alpha? | holding?]

        标签行的字段数量取决于状态：
          - pending:   [2024-01-15 | AAPL | BUY | pending]           → 4 字段
          - resolved:  [2024-01-15 | AAPL | BUY | +2.0% | -1.0% | 5d] → 6 字段

        同时用预编译正则提取 DECISION 和 REFLECTION 段的内容。

        Args:
            raw: 单个条目的原始文本（不含分隔符）

        Returns:
            解析后的字典，格式无效时返回 None
        """
        lines = raw.strip().splitlines()
        if not lines:
            return None
        tag_line = lines[0].strip()
        if not (tag_line.startswith("[") and tag_line.endswith("]")):
            return None
        fields = [f.strip() for f in tag_line[1:-1].split("|")]
        if len(fields) < 4:
            return None
        entry = {
            "date": fields[0],
            "ticker": fields[1],
            "rating": fields[2],
            "pending": fields[3] == "pending",
            "raw": fields[3] if fields[3] != "pending" else None,
            "alpha": fields[4] if len(fields) > 4 else None,
            "holding": fields[5] if len(fields) > 5 else None,
        }
        body = "\n".join(lines[1:]).strip()
        decision_match = self._DECISION_RE.search(body)
        reflection_match = self._REFLECTION_RE.search(body)
        entry["decision"] = decision_match.group(1).strip() if decision_match else ""
        entry["reflection"] = reflection_match.group(1).strip() if reflection_match else ""
        return entry

    def _format_full(self, e: dict) -> str:
        """将已解决条目格式化为完整展示文本（用于同 ticker 历史）。

        包含所有字段：标签、决策全文、反思全文。让 Agent 看到完整上下文。

        Args:
            e: 已解析的条目字典

        Returns:
            格式化的 markdown 文本
        """
        raw = e["raw"] or "n/a"
        alpha = e["alpha"] or "n/a"
        holding = e["holding"] or "n/a"
        tag = f"[{e['date']} | {e['ticker']} | {e['rating']} | {raw} | {alpha} | {holding}]"
        parts = [tag, f"DECISION:\n{e['decision']}"]
        if e["reflection"]:
            parts.append(f"REFLECTION:\n{e['reflection']}")
        return "\n\n".join(parts)

    def _format_reflection_only(self, e: dict) -> str:
        """将跨 ticker 条目格式化为精简展示文本（用于跨 ticker 教训）。

        有反思时只展示反思精华（最有价值的部分）；
        无反思时截取决策前300字作为备选（跨 ticker 不需要看完整决策）。

        截断原因：Prompt token 有限，跨 ticker 信息优先级低于同 ticker。

        Args:
            e: 已解析的条目字典

        Returns:
            格式化的精简文本
        """
        tag = f"[{e['date']} | {e['ticker']} | {e['rating']} | {e['raw'] or 'n/a'}]"
        if e["reflection"]:
            return f"{tag}\n{e['reflection']}"
        text = e["decision"][:300]
        suffix = "..." if len(e["decision"]) > 300 else ""
        return f"{tag}\n{text}{suffix}"

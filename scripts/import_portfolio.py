"""
一键同步脚本：从 financial-management 项目动态读取持仓和交易记录，
全量导入到 TradingAgents 的 PortfolioStore 中。

用法:
    python scripts/import_portfolio.py
"""

import json
import sys
from datetime import datetime
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════════════
# 配置常量 - 两个项目保持平级目录结构
# TradingAgents/  <-- 本项目
# financial-management/  <-- 持仓数据源
# ═══════════════════════════════════════════════════════════════════════════════
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
FINANCIAL_MGMT_ROOT = _PROJECT_ROOT.parent / "financial-management"
PARSED_DATA_DIR = FINANCIAL_MGMT_ROOT / "data" / "parsed"
STATE_PORTFOLIO = FINANCIAL_MGMT_ROOT / "state" / "portfolio.json"

# ═══════════════════════════════════════════════════════════════════════════════

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tradingagents.portfolio import PortfolioStore, PositionRecord, Transaction


def infer_market_suffix(symbol: str, market: str = "") -> str:
    """根据 market 字段或 symbol 编码规则推断 .SH / .SZ 后缀。

    规则:
    - market 包含 '上海' → .SH
    - market 包含 '深圳' → .SZ
    - 6位 symbol 以 5/6/9 开头 → .SH (上交所)
    - 6位 symbol 以 0/1/2/3 开头 → .SZ (深交所)
    - 其他情况不加后缀（如货币基金等）
    """
    if "上海" in market:
        return f"{symbol}.SH"
    if "深圳" in market:
        return f"{symbol}.SZ"

    # 根据 symbol 编码规则推断
    if len(symbol) == 6:
        first = symbol[0]
        if first in ("5", "6", "9"):
            return f"{symbol}.SH"
        if first in ("0", "1", "2", "3"):
            return f"{symbol}.SZ"

    # 无法判断，返回原始 symbol
    return symbol


def find_latest_month_dir(parsed_dir: Path) -> Path | None:
    """扫描 parsed 目录，返回最新月份的子目录路径。

    目录格式: YYYY-MM (如 2026-05)
    """
    if not parsed_dir.exists():
        return None

    month_dirs = []
    for d in parsed_dir.iterdir():
        if d.is_dir() and len(d.name) == 7 and d.name[4] == "-":
            try:
                # 验证是合法的年-月格式
                datetime.strptime(d.name, "%Y-%m")
                month_dirs.append(d)
            except ValueError:
                continue

    if not month_dirs:
        return None

    # 按名称排序，最新的在最后
    month_dirs.sort(key=lambda x: x.name)
    return month_dirs[-1]


def load_json(path: Path) -> list | dict:
    """加载 JSON 文件。"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_avg_cost_map(state_portfolio_path: Path) -> dict[str, float]:
    """从 portfolio.json 的 buckets 中提取每个持仓的 avg_cost。

    返回 {symbol: avg_cost} 字典。
    """
    if not state_portfolio_path.exists():
        return {}

    try:
        data = load_json(state_portfolio_path)
    except (json.JSONDecodeError, OSError):
        return {}

    cost_map: dict[str, float] = {}
    buckets = data.get("buckets", {})

    for bucket_name, bucket_data in buckets.items():
        if bucket_name.startswith("_"):
            continue
        subs = bucket_data.get("sub", {})
        for sub_name, sub_data in subs.items():
            for holding in sub_data.get("holdings", []):
                symbol = holding.get("symbol", "")
                avg_cost = holding.get("avg_cost", 0.0)
                if symbol and avg_cost > 0:
                    cost_map[symbol] = avg_cost

    return cost_map


def build_positions(
    holdings: list[dict],
    avg_cost_map: dict[str, float],
    month_str: str,
) -> list[PositionRecord]:
    """将 holdings.json 数据映射为 PositionRecord 列表。"""
    positions = []
    # 使用月份第一天作为 entry_date
    entry_date = f"{month_str}-01"

    for h in holdings:
        symbol = h.get("symbol", "")
        market = h.get("market", "")
        qty = h.get("qty", 0.0)
        name = h.get("name", "")
        category = h.get("category", "")

        if not symbol or qty <= 0:
            continue

        ticker = infer_market_suffix(symbol, market)

        # 优先使用 portfolio.json 中的 avg_cost，其次从 cost_basis/qty 计算
        if symbol in avg_cost_map:
            entry_price = avg_cost_map[symbol]
        else:
            cost_basis = h.get("cost_basis", 0.0)
            entry_price = cost_basis / qty if qty > 0 else 0.0

        if entry_price <= 0:
            continue

        note_parts = [name]
        if category:
            note_parts.append(category)
        note = " / ".join(note_parts)

        positions.append(PositionRecord(
            ticker=ticker,
            entry_date=entry_date,
            entry_price=round(entry_price, 6),
            quantity=qty,
            side="long",
            note=note,
        ))

    return positions


def build_transactions(txns: list[dict]) -> list[Transaction]:
    """将 transactions.json 数据映射为 Transaction 列表。

    只处理 type=="trade" 的记录（真正的买卖交易）。
    """
    transactions = []

    for t in txns:
        tx_type = t.get("type", "")
        if tx_type != "trade":
            continue

        symbol = t.get("symbol", "")
        side = t.get("side", "")
        price = t.get("price", 0.0)
        qty = t.get("qty", 0.0)
        ts_str = t.get("ts", "")
        name = t.get("name", "")

        if not symbol or not side or price <= 0 or qty <= 0:
            continue

        # 推断 ticker 后缀（transactions 没有 market 字段）
        ticker = infer_market_suffix(symbol)

        # 映射 action
        action = "buy" if side == "buy" else "sell"

        # 提取日期 (从 ISO 时间戳)
        try:
            date = datetime.fromisoformat(ts_str).strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            date = "unknown"

        # 构建 note
        note_parts = []
        if name:
            note_parts.append(name)
        memo = t.get("source_file_memo", "") or t.get("memo", "")
        if memo:
            note_parts.append(memo)
        bucket = t.get("bucket", "")
        if bucket:
            note_parts.append(f"[{bucket}]")
        note = " / ".join(note_parts) if note_parts else ""

        transactions.append(Transaction(
            ticker=ticker,
            action=action,
            date=date,
            price=price,
            quantity=qty,
            note=note,
        ))

    return transactions


def main():
    print("=" * 60)
    print("  TradingAgents 持仓同步工具")
    print("  数据源: financial-management")
    print("=" * 60)

    # ── 1. 检查 financial-management 项目是否存在 ──
    if not FINANCIAL_MGMT_ROOT.exists():
        print(f"\n[错误] financial-management 项目不存在:")
        print(f"  路径: {FINANCIAL_MGMT_ROOT}")
        print(f"\n请确认路径是否正确，或修改脚本顶部的 FINANCIAL_MGMT_ROOT 常量。")
        sys.exit(1)

    if not PARSED_DATA_DIR.exists():
        print(f"\n[错误] 解析数据目录不存在: {PARSED_DATA_DIR}")
        sys.exit(1)

    # ── 2. 找到最新月份目录 ──
    month_dir = find_latest_month_dir(PARSED_DATA_DIR)
    if month_dir is None:
        print(f"\n[错误] 未找到任何月份目录: {PARSED_DATA_DIR}")
        sys.exit(1)

    month_str = month_dir.name
    print(f"\n  最新数据月份: {month_str}")
    print(f"  数据目录:     {month_dir}")

    # ── 3. 加载 holdings.json ──
    holdings_path = month_dir / "holdings.json"
    if not holdings_path.exists():
        # 尝试查找最近有 holdings.json 的月份
        print(f"\n  [警告] {month_str} 目录下无 holdings.json，向前查找...")
        all_dirs = sorted(
            [d for d in PARSED_DATA_DIR.iterdir() if d.is_dir()],
            key=lambda x: x.name,
            reverse=True,
        )
        found = False
        for d in all_dirs:
            candidate = d / "holdings.json"
            if candidate.exists():
                holdings_path = candidate
                month_dir = d
                month_str = d.name
                found = True
                print(f"  [信息] 使用 {month_str} 的 holdings.json")
                break
        if not found:
            print(f"\n[错误] 所有月份目录中均未找到 holdings.json")
            sys.exit(1)

    holdings_data = load_json(holdings_path)
    print(f"  holdings.json: {len(holdings_data)} 条记录")

    # ── 4. 加载所有月份的 transactions.json ──
    transactions_data = []
    all_month_dirs = sorted(
        [d for d in PARSED_DATA_DIR.iterdir()
         if d.is_dir() and len(d.name) == 7 and d.name[4] == "-"],
        key=lambda x: x.name,
    )
    for m_dir in all_month_dirs:
        tx_path = m_dir / "transactions.json"
        if tx_path.exists():
            month_txns = load_json(tx_path)
            transactions_data.extend(month_txns)
            print(f"  transactions.json ({m_dir.name}): {len(month_txns)} 条记录")
    if not transactions_data:
        print(f"  transactions.json: 未找到任何交易记录")

    # ── 5. 加载 portfolio.json 获取精确 avg_cost ──
    avg_cost_map: dict[str, float] = {}
    if STATE_PORTFOLIO.exists():
        avg_cost_map = load_avg_cost_map(STATE_PORTFOLIO)
        print(f"  portfolio.json:  已加载 {len(avg_cost_map)} 个持仓成本")
    else:
        print(f"  portfolio.json:  未找到（将从 holdings 计算成本价）")

    # ── 6. 数据映射 ──
    positions = build_positions(holdings_data, avg_cost_map, month_str)
    transactions = build_transactions(transactions_data)

    print(f"\n  映射结果:")
    print(f"    持仓: {len(positions)} 条")
    print(f"    交易: {len(transactions)} 条 (仅含 trade 类型)")

    # ── 7. 全量同步到 PortfolioStore ──
    store = PortfolioStore()
    store.clear()

    for pos in positions:
        store.add_position(pos)

    for txn in transactions:
        store.add_transaction(txn)

    # ── 8. 打印导入摘要 ──
    print(f"\n{'─' * 60}")
    print(f"  同步完成！数据已写入: {store.path}")
    print(f"{'─' * 60}")

    print(f"\n  ┌─ 当前持仓 ({len(positions)} 条) ─────────────────────────")
    total_cost = 0.0
    for p in positions:
        cost = p.entry_price * p.quantity
        total_cost += cost
        print(f"  │ {p.ticker:<12} {p.quantity:>10,.0f} 份 × {p.entry_price:.4f}"
              f"  成本 ¥{cost:>12,.2f}  [{p.note}]")
    print(f"  │{'─' * 56}")
    print(f"  │ 总成本: ¥{total_cost:,.2f}")
    print(f"  └{'─' * 56}")

    if transactions:
        print(f"\n  ┌─ 交易记录 ({len(transactions)} 条) ───────────────────────")
        for t in transactions:
            action_str = "买入" if t.action == "buy" else "卖出"
            print(f"  │ {t.date} {action_str} {t.ticker:<12}"
                  f" {t.quantity:>8,.0f} 份 × {t.price:.4f}  [{t.note}]")
        print(f"  └{'─' * 56}")

    print(f"\n  完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()

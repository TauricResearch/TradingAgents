# TradingAgents Dashboard UI 开发规范

适用范围：`tradingbot/dashboard/`（Streamlit + Plotly 的自动交易仪表盘）。
新页面、新组件、改造现有视图，都以本规范为准。所有约定均来自当前仓库的现有实现。

---

## 1. 技术栈与文件分层

| 层 | 内容 | 位置 |
|---|---|---|
| 入口 | `st.set_page_config` + sidebar + 路由分发 | `tradingbot/dashboard/app.py` |
| 国际化 | 单字典 `TRANSLATIONS` + `t()` + `language_selector()` | `tradingbot/dashboard/i18n.py` |
| 页面组件 | 每页一个 `*_view.py`，对外只暴露 `render(...)` | `tradingbot/dashboard/components/` |
| 启动器 | `run_dashboard.py` / `start.sh` | 仓库根 |

**强约束**

- 组件文件**只导出一个函数 `render(...)`**，参数是上层注入的 `broker / portfolio_manager / db / config / trading_graph`，组件内部不再调 `st.cache_resource` 或读 `TRADINGBOT_CONFIG`。
- 跨页复用的私有函数（如 `_render_signal_header`、`_render_agent_tabs`、`_normalize_state`、`_extract_signal`）放在拥有它的 view 里，其它 view **从那个 view import**，不另立 utils 模块（参考 `trades_view.py` 复用 `signals_view.py` 的做法）。
- 新增页面流程：
  1. 在 `i18n.py` 加 key（同时补 `zh` 和 `en`）；
  2. 新建 `components/xxx_view.py` 实现 `render(...)`；
  3. 在 `app.py` 的 `PAGE_KEYS` 加 `nav.xxx`，并在 `main()` 的分发 `if/elif` 里加分支。

## 2. 缓存与单例

- 所有重对象（broker、db、portfolio manager、TradingAgentsGraph）通过 `@st.cache_resource` 装饰的 `_get_xxx()` 在 `app.py` 内创建，**view 不允许自己实例化**。
- `_get_config()` 不缓存，每次读 `tradingbot.config.TRADINGBOT_CONFIG`，保证配置改动即时生效。
- 提供"刷新数据"按钮：`st.cache_resource.clear() + st.rerun()`，这是当前唯一允许的清缓存路径。

## 3. 国际化（i18n）

- **默认语言中文（`zh`）**，可选 `en`；存在 `st.session_state["lang"]`。
- 文案一律走 `t("xxx.key")`，**禁止把硬编码中文/英文写到组件里**（包括图表的 `xaxis_title`、`labels`、`name`、`text` 等）。
- key 命名空间按页面前缀：`app.* / nav.* / qt.* / pv.* / perf.* / risk.* / sig.* / tv.*`，新页面沿用同样的两段式前缀。
- 含变量的字符串用 Python `str.format` 占位：
  `"qt.success": "订单已成交：{qty} 股 @ ${price}"`，调用 `t("qt.success", qty=..., price=...)`。
- `t()` 找不到 key 时返回 key 本身（fail-soft），方便定位漏译。
- 表格列名也走 `t()`，先把列名 `col_xxx = t(...)` 取出来再组 dict，避免在 `style.applymap(subset=[...])` 时拼错。

## 4. 页面骨架

每个 view 必须保持的顺序：

```
st.subheader(t("xxx.subheader"))         # 页面标题
[可选] st.caption(...)                    # 简介
KPI 区  st.columns(4) + st.metric         # 顶部指标卡
数据为空时 st.info(t("xxx.empty")) 并 return
主体    表格 / 图表 / 详情区
```

`signals_view` 多一层模式切换（`st.radio(... horizontal=True, label_visibility="collapsed")` + `st.markdown("---")`）。新页面如果有"实时 vs 历史"类切换，沿用此模式。

## 5. 视觉规范

**语义化颜色（必须复用，禁止自取色值）**

| 语义 | 主色 | 浅背景 |
|---|---|---|
| 盈利 / 安全 / 买入 / Paper | `#4CAF50` | `#E8F5E9` |
| 亏损 / 风险 / 卖出 / Live | `#F44336` | `#FFEBEE` |
| 信息 / 净值线 | `#2196F3` | `rgba(33,150,243,0.08)` |
| 警告 | — | `#FFF9C4` / `#FFF3E0` |
| 中性 / HOLD | `#37474F` | `#ECEFF1` |
| 研究裁判（紫） | `#7B1FA2` / `#4A148C` | `#F3E5F5` |
| 风险裁判（蓝） | `#0D47A1` | `#E3F2FD` |
| 5 档信号 | 见 `_SIGNAL_COLOURS` / `_SIGNAL_BG`（BUY/OVERWEIGHT/HOLD/UNDERWEIGHT/SELL） | 同 |

**金额 / 百分比着色规则**：定义局部 `colour_pnl(val: str)`，剥掉 `$ , % +` 后按 `>=0` 绿 / `<0` 红，再 `df.style.applymap(colour_pnl, subset=[...])`。所有 P&L 列必须用这个着色器。

**数字格式**

- 金额：`f"${x:,.2f}"`
- 带符号金额：`f"${x:+,.2f}"`
- 百分比：`f"{x*100:+.2f}%"`
- 股数：`round(x, 4)`
- `profit_factor == inf → "∞"`

## 6. 组件惯例

- **KPI**：四个一行 `st.columns(4) + st.metric`，需要趋势用 `delta=...`，反向色用 `delta_color="inverse"`。
- **表格**：先转 `pd.DataFrame(rows)`，对带符号列做 `style.applymap(colour_pnl, subset=[...])`，再 `st.dataframe(styled, use_container_width=True)`。带辅助对象（如完整 trade 行）的列以 `_` 开头并在显示前 `drop`。
- **Plotly 图表**：
  - 折线 / 区域用 `go.Figure() + go.Scatter`，主色 `#2196F3`、`fill="tozeroy"`、`fillcolor` 用半透明 rgba；副线 `dash="dot"`。
  - 回撤用 `#F44336` + `rgba(244,67,54,0.2)` 填充。
  - 柱状图涨绿跌红：`["#4CAF50" if v>=0 else "#F44336" for v in ...]`。
  - 风险仪表用 `go.Indicator(mode="gauge+number+delta")`，三段 step 颜色 `#E8F5E9 / #FFF9C4 / #FFEBEE`，阈值线 `red`。
  - `update_layout(hovermode="x unified", legend=dict(orientation="h", y=1.02))` 用于时间序列。
  - 每个图必须 `st.plotly_chart(fig, use_container_width=True)`。
- **Sidebar 状态徽章**（如 PAPER/LIVE）用内联 HTML + `unsafe_allow_html=True`，但**仅限**单色背景圆角块这种 Streamlit 原生无法表达的样式；普通文案禁用 HTML。
- **信号卡片**（5 档买卖信号、研究 / 风险裁判头）统一走 `_render_signal_header`，不要在新 view 里另写 HTML。

## 7. 交互细节

- 主按钮：`st.button(..., type="primary", use_container_width=True)`。
- 表单提交后必须有反馈：`st.success / st.error / st.warning / st.info`，文案走 `t()`。
- 长任务：`with st.spinner(t("xxx.spinner", ...)):`，异常用 `try/except` 包住并 `st.error(t("xxx.failed", err=str(exc)))`。
- 历史明细类列表：用 `st.expander(label, expanded=False)`，label 含 emoji 状态图标（`🟢/🔴/✅/📋/📄`）+ 关键字段，并通过 `t("xxx.expander.label", ...)` 拼接。
- 表单控件**必须传 `key=`**（如 `key="qt_ticker"`、`key="live_ticker"`、`key="hist_date"`），避免重复渲染时状态错乱。
- 涉及股票代码统一 `.upper().strip()`。

## 8. 数据与配置

- 配置只通过传入的 `config: dict` 读，关键 key：
  `broker / paper_trading / watchlist / db_path / results_dir / max_total_exposure_pct / max_single_position_pct / daily_loss_limit_pct / min_cash_reserve`。
  比例字段是 0–1 浮点，乘 100 后显示。
- 日志 / 历史文件路径用 `Path` 拼接，模板固定为：
  `results_dir / TICKER / TradingAgentsStrategy_logs / full_states_log_{YYYY-MM-DD}.json`。
- 实时 LangGraph state 与历史 JSON log 的 key 不一致时，必须经过 `_normalize_state()` 再渲染。

## 9. 提交前自检清单

1. 文案是否全部走 `t()`，i18n 同时补 `zh` 和 `en`。
2. 是否复用了 `_SIGNAL_COLOURS / _SIGNAL_BG / colour_pnl`，没有自取新色值。
3. 是否复用了 `_render_signal_header / _render_agent_tabs / _normalize_state / _extract_signal`。
4. 重对象是否走 `app.py` 的 `_get_xxx()` 注入，没在 view 里新建。
5. 空数据有 `st.info(t("xxx.empty"))` + `return`，异常有 `try/except` + `st.error`。
6. 所有控件有 `key=`，所有图表 `use_container_width=True`。
7. 没新建无意义的 utils 模块，跨 view 复用通过 import。

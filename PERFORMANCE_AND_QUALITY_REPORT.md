# Performance & Quality Deep-Dive: Comparative Analysis

**Runs Analyzed:**
- **Baseline (Run A)**: `2026-03-30/01KN1HVP4SMBXWMTX2N67J35DY` (Ticker: SYY)
- **Optimized (Run B)**: `2026-03-31/01KN1RAXZSF0D81K9FB683CKGK` (Ticker: AAPL)

## 1. Performance Timeline & Call Counts

| Metric | Baseline (Run A - SYY) | Optimized (Run B - AAPL) | Delta |
| :--- | :--- | :--- | :--- |
| **Total Pipeline Duration** | 1,472.1s (24.5m) | 2,054.9s (34.2m) | **+39.5% (Slower)** |
| **Total LLM Calls** | 32 | 29 | -9.3% |
| **Tokens In** | 75,826 | 31,041 | **-59.0% (Better)** |
| **Tokens Out** | 50,418 | 41,845 | -17.0% |
| **Tool Calls** | 15 | 8 | **-46.6% (Better)** |

### Finding: "The Optimization Paradox"
Run B (AAPL) is significantly more token-efficient and makes fewer tool calls, yet it takes **10 minutes longer** to complete. This confirms the "stuck" feeling reported.

## 2. Most Time-Consuming Tools & Nodes

1.  **Risk Debate Summary (Node)**: In Run B, this node was the single largest bottleneck. Due to the 2-round (6-step) sequential dependency on `qwen3.5:9b`, it added ~10 minutes of sequential wait time.
2.  **get_indicators (Tool)**: Averaged 30-50ms, but was called 7 times. Not a bottleneck.
3.  **Fundamental Data Fetching**: Run B suffered from a "parse failure" in foundational data (TTM analysis), which triggered manual `get_cashflow` calls. While the tool itself is fast, the LLM reasoning time to decide to call it added latency.

## 3. Tool Usage & Importance Rating

| Tool | Importance | Rating | Notes |
| :--- | :--- | :--- | :--- |
| `get_indicators` | **Critical** | 5/5 | Provides the technical backbone for the Market Analyst. |
| `get_cashflow` | **High** | 4/5 | Critical for AAPL due to the TTM parse failure in Run B. |
| `get_earnings_calendar` | **Medium** | 3/5 | Used in scan; important for catalyst timing. |

## 4. Prompt & Report Quality Analysis

### Run A (SYY) - Quality: 4/5
- **Strengths**: Very precise technical levels ($84.51 SMA, $77.50 stop). News analyst correctly identified Nordea stake change (+38.8%).
- **Weaknesses**: Slightly repetitive in the final PM decision.

### Run B (AAPL) - Quality: 4.5/5
- **Strengths**: **Superior logic**. Despite being slower, the AAPL report correctly identified the "Transition Paradox" where China shipments are down but global revenue growth of +15.7% compensates.
- **Improved Prompting**: The prompts in Run B resulted in a much more nuanced "Investment Thesis" section, explicitly weighting regional drag vs. fundamental efficiency.
- **Rating**: The report quality has **increased** despite the performance regression. The agents are "thinking" deeper and producing more "decision-ready" content.

## 5. Conclusion & Verdict

**Performance: 2/5 (Regression)**
The sequential debate cycle is too slow for production. The hardware/model tiering for `Risk Debate Summary` needs immediate correction (already applied in PR).

**Quality: 5/5 (Improved)**
The content produced for AAPL is professional-grade. The trade sizing logic (phased 50%/25% entry) is significantly more sophisticated than previous versions.

**Verdict**: The system is smarter but slower. We have optimized **cost** (59% fewer input tokens) but failed on **latency**. Applying the QA recommendation to move summarization to Mid-Think LLM will resolve this imbalance.

---
*Report by Senior QA Engineer*

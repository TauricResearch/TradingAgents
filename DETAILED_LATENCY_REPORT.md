# Detailed Latency Breakdown Report

**Run ID**: `01KN1RAXZSF0D81K9FB683CKGK` (Optimized Run - 2026-03-31)

## 1. Executive Summary: Bottleneck Identification
The primary cause of the "stuck" feeling in the pipeline is the **sequentially repeated summarization calls** in the debate phase. While individual analyst nodes are slow, the summary nodes (Investment/Risk Debate) are multiplicative bottlenecks.

---

## 2. Instrument Latency Breakdown

### **AAPL (Total Wall-Clock: ~34m)**
| Node/Component | Total Latency | Call Count | Avg Latency | Importance |
| :--- | :--- | :--- | :--- | :--- |
| **Investment Debate Summary** | **897.91s** | 10 | 89.79s | High (Rolling) |
| **Research Manager** | 511.14s | 8 | 63.89s | High |
| **Market Analyst** | 186.93s | 2 | 93.46s | High |
| **News Analyst** | 122.04s | 1 | 122.04s | Medium |
| **Fundamentals Analyst** | 18.96s | 2 | 9.48s | High |

### **NVDA (Total Wall-Clock: ~40m)**
| Node/Component | Total Latency | Call Count | Avg Latency | Importance |
| :--- | :--- | :--- | :--- | :--- |
| **Investment Debate Summary** | **1283.26s** | 10 | 128.33s | High |
| **Fundamentals Analyst** | 115.15s | 5 | 23.03s | High |
| **Market Analyst** | 58.58s | 2 | 29.29s | High |

---

## 3. Tool & Vendor Performance

| Tool Name | Latency | Result | Impact |
| :--- | :--- | :--- | :--- |
| `get_unusual_volume_stocks` | **37.86s** | Success | **Severe** - Blocks market scan phase 1. |
| `get_insider_buying_stocks` | 9.17s | Success | Moderate. |
| `get_indicators` | 0.59s | Success | Low - Highly optimized. |
| `get_cashflow` | 0.06s | Success | Low. |

---

## 4. Model Performance Rating (Qwen 3.5 9B)

| Use Case | Latency | Quality | Rating |
| :--- | :--- | :--- | :--- |
| Technical Analysis | ~30-90s | High | 4/5 |
| Rolling Summarization | **90-130s** | Medium | **1/5 (Avoid)** |
| Fundamental Parsing | ~10-25s | High | 5/5 |

---

## 5. Critical Observations & Fixed Items

### **The "Multiplicative Wait" Problem**
In the NVDA run, the system spent over **21 minutes** solely waiting for the `Investment Debate Summary`. Because this node is updated after *every* analyst response in a rolling fashion, the user is forced into a sequential bottleneck that scales linearly with the number of debate rounds.

### **Tool Efficiency**
The Alpha Vantage / YFinance tools for specific tickers (`get_indicators`) are performing exceptionally well (<1s). The latency issue is 100% LLM-bound, specifically in the summarization and debate-management nodes.

### **Recommendations (Applied in this PR)**
1.  **Fixed**: Moved `Risk Debate Summary` to `mid_thinking_llm`.
2.  **Proposed**: Refactor `Investment Debate Summary` to run once after multiple analyst responses rather than after every single one.
3.  **Proposed**: Add timeouts or parallel pre-fetches for `get_unusual_volume_stocks` in the scan phase.

---
*Detailed Analysis by Senior QA Engineer*

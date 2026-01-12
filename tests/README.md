# Trading Agents Verification Suite

This folder contains unit tests and verification scripts to validate the functionality of the Trading Agents system.

## Available Tests


## Core Logic Tests

1.  **`test_regime_detection.py`**
    *   **Purpose:** Validates mathematical components (ADX, Volatility, Hurst) of the `RegimeDetector`.
    *   **Usage:** `python tests/test_regime_detection.py`

2.  **`test_market_node.py`**
    *   **Purpose:** End-to-end verification of `market_analyst_node`. Checks data fetching logic and regime integration.
    *   **Usage:** `python tests/test_market_node.py`

3.  **`test_override.py`**
    *   **Purpose:** Unit tests for "Don't Fight the Tape" safety logic. Verifies protection of growth leaders.
    *   **Usage:** `python tests/test_override.py`

## Integration & API Tests

4.  **`test_global_news.py`**
    *   **Purpose:** Verifies news fetching capabilities.
    *   **Usage:** `python tests/test_global_news.py`

5.  **`test_google_api.py`** & **`verify_google_key.py`**
    *   **Purpose:** Validates Google Gemini API connectivity and key validity.
    *   **Usage:** `python tests/test_google_api.py`

6.  **`verify_alpaca.py`**
    *   **Purpose:** Checks Alpaca trading API connection.
    *   **Usage:** `python tests/verify_alpaca.py`

## Infrastructure & Performance

7.  **`verify_local_embeddings.py`** & **`verify_ollama_embeddings.py`**
    *   **Purpose:** Validates local embedding models (Ollama/TEI) for RAG.
    *   **Usage:** `python tests/verify_local_embeddings.py`

8.  **`verify_tei_native.py`**
    *   **Purpose:** Tests Text Embeddings Inference (TEI) native endpoint.
    *   **Usage:** `python tests/verify_tei_native.py`

9.  **`bench_yfinance.py`**
    *   **Purpose:** Benchmarks yfinance data fetch performance (latency/throughput).
    *   **Usage:** `python tests/bench_yfinance.py`

10. **`verify_regime_integration.py`**
    *   **Purpose:** Integration test for regime detection within the broader graph context.
    *   **Usage:** `python tests/verify_regime_integration.py`

11. **`test_finance_args.py`**
    *   **Purpose:** Verifies robustness of financial tools against extraneous LLM arguments and type mismatches.
    *   **Usage:** `python tests/test_finance_args.py`

## How to Run

Ensure your virtual environment is activated:

```bash
source .venv/bin/activate
export PYTHONPATH=$PYTHONPATH:.
python tests/test_market_node.py
```

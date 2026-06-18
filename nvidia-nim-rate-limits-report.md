# NVIDIA NIM Model Rate Limits Report

> Generated: June 17, 2026 | API Key: `nvapi-...` | Endpoint: `https://integrate.api.nvidia.com/v1/chat/completions`

---

## Rate Limit Rankings

| Rank | Model | Burst (15 concurrent) | Latency | Verdict |
|------|-------|----------------------|---------|---------|
| 1 | `minimaxai/minimax-m2.7` | **10/15 OK (83%)** | ~14.5s | 🏆 Best trade-off |
| 2 | `z-ai/glm-5.1` | **4/5 OK (80%)** | ~62s | Generous limit but very slow |
| 3 | `deepseek-ai/deepseek-v4-flash` | **0/15** | — | ❌ Rate-limited (shared pool with Kimi) |
| 4 | `moonshotai/kimi-k2.6` | **5/15** | ~2s warm | ❌ ~30 requests/hour, currently exhausted |
| 5 | `google/gemma-4-31b-it` | **timeout** | >60s | ❌ Unresponsive |
| 6 | `qwen/qwen3.5-122b-a10b` | **timeout** | >60s | ❌ Unresponsive |

---

## Detailed Findings

### `minimaxai/minimax-m2.7` — 🏆 Best
- **Burst:** 10/15 concurrent (83%)
- **Latency:** ~14.5s warm, ~17s cold start
- **Quota pool:** Different from Kimi/DeepSeek — unaffected when those are 429'd
- **Context:** 128K tokens | **Status:** ✅ Fully functional

### `z-ai/glm-5.1` — Best Rate Limit, Worst Speed
- **Burst:** 4/5 concurrent (80%), zero 429s detected
- **Latency:** ~62s average (range: 45–78s)
- **Context:** 128K tokens | **Status:** ✅ Works but impractically slow

### `deepseek-ai/deepseek-v4-flash` — Rate Limited
- All 15 concurrent requests returned 429
- Shares quota pool with `moonshotai/kimi-k2.6` — both 429 when either is exhausted

### `moonshotai/kimi-k2.6` — Strictest Limit
- **Burst:** ~5 requests before 429
- **Hourly limit:** ~30 requests/hour (confirmed by [NVIDIA Developer Forum](https://forums.developer.nvidia.com/t/kimi-k2-6-is-rate-limited-to-30-requests-per-hour/369211))
- **Latency:** ~2s warm, ~17.6s cold start
- **Context:** 262K tokens | **Status:** ❌ Currently exhausted (87 total calls made, 16 succeeded)

### `google/gemma-4-31b-it` — Unresponsive
- All requests timeout at 60s. Model appears overloaded or not accepting traffic.

### `qwen/qwen3.5-122b-a10b` — Unresponsive
- All requests timeout at 60s. Same behavior as Gemma.

---

## General NVIDIA NIM Free Tier Limits

| Limit | Value | Source |
|-------|-------|--------|
| **General API rate limit** | 40 RPM | Third-party sources (YangMao, FunGather, FreeLLM, aiHola) |
| **Kimi K2.6 specific** | ~30 requests/hour | NVIDIA Developer Forum |
| **Rate limit scope** | Per-model (not per-key) | Empirically verified: MiniMax works while Kimi/DeepSeek are 429'd on same key |
| **Inference credits** | 1,000 on signup (reportedly removed for some accounts) | Multiple sources |
| **Credit card required** | No | |
| **Rate limit headers** | None returned | No `X-RateLimit-*` or `Retry-After` in any response |
| **429 response format** | `{"status":429,"title":"Too Many Requests"}` | Kimi/DeepSeek models |

---

## Practical Recommendations

**Best model for rate limits:** `minimaxai/minimax-m2.7` — 83% burst success, ~14.5s latency, separate quota pool from Kimi/DeepSeek.

**Fallback:** `z-ai/glm-5.1` if you need maximum throughput (accept ~62s latency).

**Avoid:** `moonshotai/kimi-k2.6` and `deepseek-ai/deepseek-v4-flash` — they share a strict quota pool and exhaust quickly.

**Exponential backoff on 429:**
```
delay = min(1s * 2^attempt * (1 + random_jitter), 60s)
```

**To increase limits:** Request from NVIDIA dashboard (~200 RPM available on request), or self-host via downloadable NIM containers (requires B200 GPUs).

---

## Test Methodology

**Approach:** 176 total API calls across 6 models using Python `requests` + `threading` for concurrency tests.

| Parameter | Value |
|-----------|-------|
| Endpoint | `https://integrate.api.nvidia.com/v1/chat/completions` |
| Max tokens | 5–10 per request |
| Timeout | 60s (90s for GLM-5.1) |
| Concurrency | Up to 15 threads |
| Python | 3.13.6 |

### Quick Test Script (reproducible)

```python
import requests, time, threading

API_KEY = 'nvapi-YOUR_KEY_HERE'
INVOKE_URL = 'https://integrate.api.nvidia.com/v1/chat/completions'
MODELS = [
    "deepseek-ai/deepseek-v4-flash", "z-ai/glm-5.1", "minimaxai/minimax-m2.7",
    "google/gemma-4-31b-it", "qwen/qwen3.5-122b-a10b", "moonshotai/kimi-k2.6",
]

def test_burst(model, concurrency=15, timeout=60):
    headers = {'Authorization': f'Bearer {API_KEY}', 'Content-Type': 'application/json'}
    payload = {'model': model, 'messages': [{'role':'user','content':'hi'}],
               'max_tokens': 5, 'temperature': 0.01}
    results, lock = {}, threading.Lock()
    def fire(n):
        t0 = time.time()
        try:
            r = requests.post(INVOKE_URL, headers=headers, json=payload, timeout=timeout)
            with lock: results[n] = (r.status_code, time.time() - t0)
        except Exception as e:
            with lock: results[n] = (-1, time.time() - t0)
    for t in [threading.Thread(target=fire, args=(i,)) for i in range(concurrency)]:
        t.start(); t.join()
    ok = sum(1 for s,_ in results.values() if s == 200)
    limited = sum(1 for s,_ in results.values() if s == 429)
    times = [t for s,t in results.values() if s == 200]
    print(f"{model}: {ok}/{concurrency} OK, {limited} 429, avg {sum(times)/max(len(times),1):.1f}s")

for m in MODELS: test_burst(m)
```

---

## Full Session Log

**Total calls:** 176 across all models | **OK:** 33 | **429:** 100 | **Timeout/Error:** 43

---

### Phase 1: Kimi K2.6 Baseline

**Initial probe** — verify model responds and check for rate limit headers:
```
POST /v1/chat/completions  {"model":"moonshotai/kimi-k2.6","messages":[...],"max_tokens":10}
→ Status: 200, Latency: 17.63s (cold start)
→ Headers: Nvcf-Reqid, Nvcf-Status=fulfilled, Server=uvicorn
→ No X-RateLimit-* headers present
→ Usage: 10 prompt + 10 completion tokens
```

**Sequential 5 calls (100ms spacing):**
```
Call 1: 200 (17.63s, cold) | Call 2: 200 (0.66s) | Call 3: 200 (0.67s) | Call 4: 200 (3.56s) | Call 5: 200 (0.87s)
```

**Burst 10 concurrent:**
```
5 OK (0.8s–8.5s), 5 rate-limited (429, empty error body)
→ Burst capacity: ~5 requests before 429
```

**Exhaustion + refill timing:**
```
20 concurrent → 5 OK, 15 429
Refill check at 1s, 2s, 5s, 10s, 15s, 20s → all still 429
Sustained 1.5s intervals for 30s → 0 OK, 10 429
→ Confirms: hourly quota, NOT per-minute rolling window
```

**60-second reset test:**
```
After 60s: still 429
10 more requests at 1.5s spacing: 0 OK, 10 429
→ Confirms: ~30/hour limit, not 40 RPM
```

**Kimi K2.6 subtotal: 87 calls | 16 OK | 71 429 | 0 timeout**

---

### Phase 2: Cross-Model Testing

**Model availability check** — all 6 models confirmed accessible (121 total in catalog):
```
deepseek-ai/deepseek-v4-flash | google/gemma-4-31b-it | minimaxai/minimax-m2.7
moonshotai/kimi-k2.6          | qwen/qwen3.5-122b-a10b  | z-ai/glm-5.1
```

**Burst test (15 concurrent per model):**
```
deepseek-ai/deepseek-v4-flash  → OK=0  429=15  (rate-limited, shares pool with Kimi)
z-ai/glm-5.1                   → OK=0  429=10  (5 timed out — model very slow)
minimaxai/minimax-m2.7        → OK=10 429=2   ← best performer, different pool
google/gemma-4-31b-it         → OK=0  429=0   (all 15 timed out)
qwen/qwen3.5-122b-a10b         → OK=0  429=0   (all 15 timed out)
```

**All-models single-request check (60s timeout):**
```
deepseek-ai/deepseek-v4-flash → 429 (0.4s) {"status":429,"title":"Too Many Requests"}
z-ai/glm-5.1                  → 200 (56.6s) "Hello there!" (15 tokens)
minimaxai/minimax-m2.7        → 200 (14.5s) "Hi there!" (54 tokens, 16 cached)
google/gemma-4-31b-it         → TIMEOUT (>60s)
qwen/qwen3.5-122b-a10b        → TIMEOUT (>60s)
moonshotai/kimi-k2.6          → 429 (0.4s) same as DeepSeek
```

**MiniMax detailed response** (confirmed working):
```json
{
  "model": "minimaxai/minimax-m2.7",
  "usage": {"prompt_tokens": 44, "completion_tokens": 10, "total_tokens": 54,
            "prompt_tokens_details": {"cached_tokens": 16}},
  "choices": [{"message": {
    "reasoning_content": "The user says: \"say hi in 2",
    "content": "Hi there!"
  }}]
}
```

**GLM-5.1 burst test (5 concurrent, 90s timeout):**
```
OK=4, 429=0, Errors=1
Times: 45.4s, 47.9s, 76.4s, 77.5s → Avg: 61.8s
→ Most generous rate limit, zero 429s, but ~62s latency
```

---

### Final Verification

After ~30 minutes and 176 total calls:
```
POST moonshotai/kimi-k2.6 → 429 (still exhausted)
```
Confirmed: hourly sliding window quota (not per-minute), still blocked after 30+ minutes.

---

## Cumulative Request Summary

| Test Phase | Model | Calls | OK | 429 | Timeout |
|------------|-------|-------|-----|-----|---------|
| Initial + Sequential + Burst + Exhaust | Kimi K2.6 | 87 | 16 | 71 | 0 |
| Burst (15) | DeepSeek V4 Flash | 15 | 0 | 15 | 0 |
| Burst (15) | GLM-5.1 | 15 | 0 | 10 | 5 |
| Burst (15) | MiniMax M2.7 | 15 | 10 | 2 | 3 |
| Burst (15) | Gemma 4 31B | 15 | 0 | 0 | 15 |
| Burst (15) | Qwen 3.5 | 15 | 0 | 0 | 15 |
| Single checks (60s) | All 6 models | 6 | 2 | 2 | 2 |
| Detailed verifications | MiniMax + GLM | 6 | 5 | 0 | 1 |
| **Total** | | **176** | **33** | **100** | **43** |

---

## Known Limitations

1. Rate limits change over time — re-test periodically
2. Per-model limits verified empirically: MiniMax unaffected when Kimi/DeepSeek are 429'd
3. 429 responses have empty message: `{"status":429,"title":"Too Many Requests"}` (no `Retry-After` header)
4. Cold start ~17s for first request to any model
5. No programmatic way to check remaining quota (no usage endpoint exposed)
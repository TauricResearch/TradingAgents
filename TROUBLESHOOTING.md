# Troubleshooting

Solutions to the most common issues when installing and running **TradingAgents**,
with notes for Windows users, networks behind a proxy, domestic (China) LLM
providers, and A-share tickers.

> The framework is for research purposes only and does not constitute financial advice.

---

## 1. Installation

### 1.1 Python version
Python **3.11 or newer** is required (3.12 recommended). Check with
`python --version`. To create an isolated environment:

```bash
conda create -n tradingagents python=3.12
conda activate tradingagents
```

### 1.2 `pip install` is slow or times out
If you are behind a slow mirror, install from a regional index:

```bash
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple .
```

### 1.3 `tradingagents` command not found after install
Make sure you ran `pip install .` from the repository root, or launch from source:

```bash
python -m cli.main
```

---

## 2. Models and API keys

### 2.1 No paid API key / want to run fully local
Use **Ollama**:

```bash
ollama pull qwen3:8b
```

Select `ollama` as the provider when prompted. For a remote Ollama host set
`OLLAMA_BASE_URL` (default `http://localhost:11434`).

### 2.2 Using a domestic (China) provider
Set the key for your provider. Note the China (`*_CN_*`) endpoints differ from
the international ones.

```bash
# bash (Linux / macOS)
export DEEPSEEK_API_KEY="your-key"
export ZHIPU_CN_API_KEY="your-key"      # GLM via open.bigmodel.cn
export DASHSCOPE_CN_API_KEY="your-key"  # Qwen via dashscope.aliyuncs.com
export MOONSHOT_API_KEY="your-key"      # Kimi
```

```powershell
# PowerShell (Windows)
$env:DEEPSEEK_API_KEY="your-key"
$env:ZHIPU_CN_API_KEY="your-key"
$env:DASHSCOPE_CN_API_KEY="your-key"
$env:MOONSHOT_API_KEY="your-key"
```

### 2.3 Authentication error / 401 / key not picked up
- Ensure the key has no extra spaces and the variable name is correct;
- **restart the terminal** after setting it;
- China users should use the `*_CN_*` variables (China endpoints).

---

## 3. Platform notes

### 3.1 Windows: garbled text / encoding errors (UTF-8)
Force Python into UTF-8 mode for the session:

```powershell
$env:PYTHONUTF8="1"
```

Alternatively enable *Control Panel → Region → Administrative →
Change system locale → "Beta: Use Unicode UTF-8" and reboot.

### 3.2 Windows: "running scripts is disabled"
Relax the policy for the current PowerShell session:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

---

## 4. Proxy and network

### 4.1 A-share data endpoints fail with SSL errors while a VPN/proxy is on
Symptoms: requests to Eastmoney / THS fail with
`SSL: DECRYPTION_FAILED_OR_BAD_RECORD_MAC`, connection resets, or anti-crawler
blocks. Domestic traffic is being routed overseas. Add the domestic hosts to
`NO_PROXY`:

```bash
# bash
export NO_PROXY="localhost,127.0.0.1,.eastmoney.com,.10jqka.com.cn,.sina.com.cn,.cn"
```

```powershell
# PowerShell
$env:NO_PROXY="localhost,127.0.0.1,.eastmoney.com,.10jqka.com.cn,.sina.com.cn,.cn"
```

> A system-wide TUN/transparent proxy (e.g. Clash TUN mode) may ignore these
> variables; add the domains to the proxy's direct-connection rules instead.

### 4.2 Overseas model APIs are unreachable
OpenAI / Anthropic / Google endpoints need the proxy in the other direction:

```bash
export HTTPS_PROXY="http://127.0.0.1:7890"   # use your proxy's actual port
```

---

## 5. A-shares

### 5.1 Ticker format
- Shanghai: `600519.SS` (Kweichow Moutai)
- Shenzhen: `000001.SZ` (Ping An Bank)

### 5.2 Output shows `DATA_UNAVAILABLE` / `NO_DATA_AVAILABLE`
This is a safeguard, not a crash. When a vendor is temporarily unavailable or
has no data for a symbol, the system reports it explicitly **instead of
fabricating numbers**. Retry later or switch the network/vendor; do not treat it
as any judgement about the instrument.

### 5.3 Some AKShare endpoints fail
A few AKShare endpoints are incompatible with newer pandas/PyArrow. Upgrade to
the latest release:

```bash
pip install -U akshare
```

Full A-share support is still under community development — see the related
pull requests.

---

## 6. Where run artifacts live
Caches, checkpoints, and logs default to `~/.tradingagents/`:

- Decision memory: `~/.tradingagents/memory/trading_memory.md`
- Checkpoints: `~/.tradingagents/cache/checkpoints/`

Override with `TRADINGAGENTS_CACHE_DIR` and `TRADINGAGENTS_MEMORY_LOG_PATH`.

---

## 7. Still stuck? Open an issue
Open an issue using the appropriate template and include:
- TradingAgents version and operating system;
- how you run it (CLI / Docker) and the provider/model names;
- the ticker and analysis date;
- the full error output and steps to reproduce.

Complete information makes the issue much easier to help with.

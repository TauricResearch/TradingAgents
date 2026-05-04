## GitHub Issue #720 Response (for maintainer or community use)

> **Comment on:** https://github.com/TauricResearch/TradingAgents/issues/720

---

The issue is `curl_cffi` failing to import on macOS due to an OpenSSL symbol mismatch. Python version (3.12 vs 3.13) is not the cause — this happens on both.

### Root Cause

`yfinance` → `curl_cffi` → compiled against a newer OpenSSL than macOS ships. At import time, `curl_cffi` tries to resolve `_SCDynamicStoreCopyProxies` (a SystemConfiguration function) from the system OpenSSL, which doesn't have it. This is a macOS-specific incompatibility — Linux and Windows are unaffected.

### Fix: Use Homebrew OpenSSL

```bash
# Install Homebrew OpenSSL
brew install opensql

# Reinstall curl_cffi against it
uv pip install curl_cffi --force-reinstall \
  --config-settings LDFLAGS="-L/opt/homebrew/opt/openssl@3/lib" \
  --config-settings CPPFLAGS="-I/opt/homebrew/opt/openssl@3/include"

# Verify
python -c "import curl_cffi; print('OK')"

# Re-sync all packages
uv sync
```

### Alternative: Downgrade yfinance

If the above is too involved, use an older `yfinance` that doesn't require `curl_cffi`:

```bash
uv pip install "yfinance<0.2.30"
```

### Why this isn't in the README

This appears to be a known macOS issue in the Python ecosystem that the upstream project hasn't documented. If you're able to submit a PR to add this to the README's troubleshooting section, that would help future macOS users significantly.

---

*Note: This response is from a fork maintainer (pjsvis/TradingAgents) who maintains a local Playbook documenting this and similar macOS setup issues. The fix may also be helpful for the upstream project.*
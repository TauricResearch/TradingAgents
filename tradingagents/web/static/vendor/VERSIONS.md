# Vendored frontend libraries

| Library | Version | File | Source |
|---|---|---|---|
| DOMPurify | 3.2.7 (exact pin) | purify.min.js | https://cdn.jsdelivr.net/npm/dompurify@3.2.7/dist/purify.min.js |
| marked | 16.4.1 | marked.min.js | https://cdn.jsdelivr.net/npm/marked@16.4.1/lib/marked.umd.min.js |

## Bump-on-advisory (DOMPurify)

DOMPurify has a history of sanitizer-bypass CVEs (e.g. CVE-2024-45801,
CVE-2024-47875). When an advisory lands for the pinned version:

1. Pick the fixed release from https://github.com/cure53/DOMPurify/releases.
2. Replace `purify.min.js` with that exact version's `dist/purify.min.js`
   and update `purify.LICENSE` and this table.
3. Re-run the web test suite (`pytest tests/test_web_*.py`) and the manual
   smoke checklist before shipping.

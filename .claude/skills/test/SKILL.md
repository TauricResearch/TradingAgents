---
name: test
description: Generate missing pytest tests for a module, function, or domain
allowed-tools: Read, Grep, Glob, Bash
---

Generate or complete tests for $ARGUMENTS (file, function, or domain name).

**Steps:**
1. Read the target source file(s) to understand the public interface.
2. Check `tests/` for any existing test file to avoid duplication.
3. Write tests following the project layout: `tests/<domain>/test_<module>.py`.

**Each test must cover:**
- Happy path
- Edge cases (empty input, boundary values, None)
- Expected failures / exceptions

**Rules:**
- Use `pytest` with fixtures for shared setup.
- No global state — isolate each test.
- Mock only at I/O boundaries (network, disk, external APIs, time).
- Use `pydantic` models or `dataclass` instances as test data, not raw dicts.
- Name tests: `test_<function>_<scenario>` (e.g. `test_run_returns_empty_on_no_input`).

After writing, run `pytest --tb=short <test_file>` to verify all tests pass.

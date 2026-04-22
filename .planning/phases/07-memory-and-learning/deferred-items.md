# Phase 7 - Deferred Items

Out-of-scope items found during execution but not fixed. These are tracked
for later cleanup; they do not block the plan they were discovered in.

## 07-00: uv/macOS editable-install `.pth` UF_HIDDEN flag

**Found during:** Plan 07-00 Task 3 verification (`uv run pytest ...`)

**Symptom:** `uv run pytest tests/memory/test_wave0_scaffold.py -q` fails with
`ModuleNotFoundError: No module named 'ai_hedge_fund'` (affects root
`tests/conftest.py` which imports `ai_hedge_fund.db.models`).

**Root cause:** When the project directory path contains a space (`AI Hedgefund`),
`uv sync` installs the editable `.pth` files with the macOS `UF_HIDDEN`
flag set. Python 3.13's `site.py` line 177-180 skips `.pth` files whose
`st_flags` has `UF_HIDDEN` set, so the editable install never adds
`src/` to `sys.path`. This also affects the pre-existing `_virtualenv.pth`.

**Verified verbosely:**
```
$ .venv/bin/python -v -c "pass" 2>&1 | grep hidden
Skipping hidden .pth file: '.../site-packages/_editable_impl_ai_hedge_fund.pth'
Skipping hidden .pth file: '.../site-packages/_virtualenv.pth'
Skipping hidden .pth file: '.../site-packages/ai_hedge_fund_editable.pth'
```

**Upstream bug:** astral-sh/uv issue (known regression on macOS with spaces
in paths).

**Workaround (used in 07-00 verification, must be applied before every
`uv run pytest` until upstream is fixed):**
```bash
chflags nohidden .venv/lib/python3.13/site-packages/*.pth
uv run --no-sync pytest ...  # OR use .venv/bin/python -m pytest ...
```
`uv run` WITHOUT `--no-sync` re-installs the editable package and re-applies
the UF_HIDDEN flag, re-breaking the import.

**Why deferred:** This is an upstream environment bug not caused by Phase 7
work. Fixing it requires one of:
1. Renaming the project directory to remove the space (destructive; user
   decision).
2. Pinning a uv version that doesn't exhibit the bug.
3. Adding a project-local `sitecustomize.py` or pre-commit hook that
   strips the hidden flag automatically.

Recommend user evaluates options 1-3 and picks one. Not in scope for
Phase 7 memory-and-learning.

**Impact on 07-00 verification:** 6/6 smoke tests pass under the
workaround; acceptance criteria satisfied.

## 07-04: pytest-asyncio missing for two pre-existing integration tests

**Found during:** Plan 07-04 Task 3 cross-phase regression
(`pytest tests/graph tests/integration tests/memory tests/risk -q`).

**Symptom:** `tests/integration/test_research_pipeline.py::test_research_agent_with_test_model`
and `::test_signal_agent_with_test_model` fail with "async def functions
are not natively supported. You need to install a suitable plugin for
your async framework". `pyproject.toml` references `asyncio_mode` (hence
the `PytestConfigWarning: Unknown config option: asyncio_mode` warning)
but `pytest-asyncio` is not installed in the venv.

**Why deferred:** Pre-existing failure on main (verified via `git stash` +
run without plan changes -- both tests fail). Unrelated to Phase-7
memory-and-learning scope. The Phase-7 tests written in this plan use
`asyncio.run(...)` directly on synchronous test functions, which sidesteps
the plugin entirely -- all 5 Task-3 tests pass without pytest-asyncio.

**Fix (out of scope):** Either add `pytest-asyncio>=0.23` to dev
dependencies, or convert the two failing tests to call `asyncio.run(...)`
inside synchronous test bodies like Plan 07-04 does.

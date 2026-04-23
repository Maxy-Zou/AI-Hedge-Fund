# Phase 8 - Deferred Items

Out-of-scope items found during execution but not fixed. Tracked for later
cleanup; they do not block the plan they were discovered in.

## 08-00: pre-existing test_checkpointer.py collection error

**Found during:** Plan 08-00 Task 2 verification
(`uv run --no-sync pytest tests/integration --collect-only -q`).

**Symptom:** `tests/integration/test_checkpointer.py` fails at import time with
`pydantic_ai.exceptions.UserError: Set the 'ANTHROPIC_API_KEY' environment
variable...`. The module imports `ai_hedge_fund.agents.__init__` which
eagerly instantiates `analysis_agent`; without `ANTHROPIC_API_KEY` in the
environment pytest collection fails before any test runs.

**Why deferred:** Pre-existing on `main` (verified via `git stash` + re-run
without plan changes -- same error). Unrelated to Plan 08-00 scope
(Phase-8 Wave-0 scaffold). The canonical fix pattern is already used by
`tests/integration/test_phase7_e2e.py`:

    os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-unit-tests")

applied at module top BEFORE `from ai_hedge_fund.agents...` imports. A
future chore commit should add the same line to `test_checkpointer.py`.

**Workaround used in 08-00 verification:**
`uv run --no-sync pytest tests/integration --collect-only -q --ignore=tests/integration/test_checkpointer.py`
collects 66 tests cleanly.

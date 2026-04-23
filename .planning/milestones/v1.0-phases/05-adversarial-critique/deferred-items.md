# Phase 05 Deferred Items

Discovered during Plan 05-03 execution. These are out-of-scope
(pre-existing issues not caused by Plan 05-03 changes) and are logged
here per the executor's scope-boundary rule.

## tests/integration/test_checkpointer.py collection error

**Discovered:** 2026-04-22 during Plan 05-03 Task 2 `uv run pytest` full-suite run.

**Symptom:** `pytest` full-suite collection fails with
`pydantic_ai.exceptions.UserError: Set the ANTHROPIC_API_KEY environment
variable ...` when it imports `tests/integration/test_checkpointer.py`.

**Root cause:** The test module imports `ai_hedge_fund.graph.pipeline`
(for `build_pipeline`), which triggers a full import chain that
instantiates several PydanticAI `Agent` objects at module-top-level
(e.g., `analysis_agent = create_agent(...)`). PydanticAI validates the
Anthropic provider at `Agent.__init__` time, raising `UserError` when
`ANTHROPIC_API_KEY` is unset.

**Confirmed pre-existing:** Verified by checking out `pipeline.py` and
`__init__.py` at commit `6880c87` (the HEAD before Plan 05-03 began)
and re-running the test -- the error reproduces identically. Plan 05-03
did not introduce this issue.

**Every other test module** in `tests/unit/` and `tests/integration/`
that imports agent code sets `os.environ.setdefault("ANTHROPIC_API_KEY",
"test-key-for-unit-tests")` BEFORE the first `from ai_hedge_fund...`
import -- this is the project convention (see `tests/unit/test_debate_nodes.py`
header as the latest example). `test_checkpointer.py` is missing that
line.

**Suggested fix (future plan, NOT Plan 05-03):** Add the two-line
`os.environ.setdefault(...)` bootstrap at the top of
`tests/integration/test_checkpointer.py` immediately after `import os`
and mark all downstream `from ai_hedge_fund...` imports with `# noqa: E402`.
~5-minute change; belongs in a test-hygiene plan or a Phase-1 test cleanup.

## tests/integration/test_research_pipeline.py async test failures

**Discovered:** 2026-04-22 during Plan 05-03 Task 2 full-suite pytest.

**Symptom:** Two tests fail with
`async def functions are not natively supported. You need to install a
suitable plugin ... pytest-asyncio ...`:
- `test_research_agent_with_test_model`
- `test_signal_agent_with_test_model`

**Root cause:** These tests use bare `async def test_...` without either
(a) an `@pytest.mark.asyncio` decorator + installed pytest-asyncio plugin,
or (b) the `asyncio.run(_invoke())` sync-wrapper pattern used by
`tests/integration/test_multi_agent_pipeline.py` and the new Plan 05-03
`tests/integration/test_debate_pipeline.py`. The project configuration
references `asyncio_mode` as a pytest option but pytest-asyncio is not
installed, so the `async def` tests are silently skipped-as-failed.

**Confirmed pre-existing:** Verified by `git stash` + re-running -- the
failures reproduce at the pre-Plan-05-03 HEAD. The tests were committed
at `95de498 test(03-03): add integration tests for research pipeline`
and have been failing since.

**Suggested fix (future plan, NOT Plan 05-03):** Either (a) add
`pytest-asyncio` to the dev dependencies and decorate these tests with
`@pytest.mark.asyncio`, or (b) refactor them to the `asyncio.run()`
sync-wrapper pattern used by the Phase-4 / Phase-5 integration tests.
Option (b) is lower-risk since the other integration tests already use it.

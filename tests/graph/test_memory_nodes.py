"""Tests for MemoryDeps, memory_recall_node, and episodic_store_node (07-03).

Structure mirrors ``tests/graph/test_risk_node.py``:
- Task-1 block: MemoryDeps immutability + DebatePipelineState schema introspection.
- Task-2 block: memory_recall_node + episodic_store_node behaviour (short-circuit,
  temporal filter, MEM-03 read path, VETOED persistence, missing-belief tolerance).

No real LLM calls. Fixtures come from ``tests/memory/conftest.py`` via the
re-export shim in ``tests/graph/conftest.py``.
"""

from __future__ import annotations

import os
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import get_type_hints

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-unit-tests")

import pytest  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from ai_hedge_fund.graph.memory_deps import MemoryDeps  # noqa: E402
from ai_hedge_fund.schemas.state import DebatePipelineState  # noqa: E402

# ---------------------------------------------------------------------------
# Task 1 — MemoryDeps + DebatePipelineState schema
# ---------------------------------------------------------------------------


def test_memory_deps_is_frozen(memory_db_session: Session, beliefs_tmp_dir: Path) -> None:
    deps = MemoryDeps(db_session=memory_db_session, beliefs_path=beliefs_tmp_dir)
    assert deps.recall_limit == 10
    with pytest.raises(FrozenInstanceError):
        deps.recall_limit = 5  # type: ignore[misc]


def test_memory_deps_accepts_custom_recall_limit(
    memory_db_session: Session, beliefs_tmp_dir: Path
) -> None:
    deps = MemoryDeps(
        db_session=memory_db_session,
        beliefs_path=beliefs_tmp_dir,
        recall_limit=3,
    )
    assert deps.recall_limit == 3


def test_debate_pipeline_state_has_memory_keys() -> None:
    hints = get_type_hints(DebatePipelineState)
    assert "episodic_hits" in hints
    assert "beliefs_consulted" in hints
    assert "episodic_stored_id" in hints


def test_memory_state_keys_are_single_writer() -> None:
    """Single-writer means no ``Annotated[..., operator.add]`` reducer.

    A reducer on these keys would silently accumulate across writers; there
    are no parallel writers in the 07-03 topology, but we lock the invariant
    so a future hand cannot introduce one without updating this test.
    """
    hints = get_type_hints(DebatePipelineState, include_extras=True)
    for key in ("episodic_hits", "beliefs_consulted", "episodic_stored_id"):
        hint = hints[key]
        assert not hasattr(hint, "__metadata__"), (
            f"{key} must be single-writer (no Annotated reducer)"
        )

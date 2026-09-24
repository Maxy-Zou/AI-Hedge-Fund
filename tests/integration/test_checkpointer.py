"""Integration tests for PostgreSQL checkpointer.

All tests require a running PostgreSQL instance (via docker-compose).
Tests are skipped if PostgreSQL is not available.

The pipeline runs via ``ainvoke``, so a run with Postgres persistence must use
``create_async_checkpointer`` (``AsyncPostgresSaver``): the sync
``PostgresSaver`` does not implement ``aget_tuple`` and raises
``NotImplementedError`` inside the async loop.
"""

from __future__ import annotations

import os
import subprocess
import uuid

import pytest
from pydantic_ai.models.test import TestModel

from ai_hedge_fund.agents.analysis import analysis_agent
from ai_hedge_fund.agents.extraction import extraction_agent
from ai_hedge_fund.graph.checkpointer import create_async_checkpointer, create_checkpointer
from ai_hedge_fund.graph.pipeline import build_pipeline


def docker_available() -> bool:
    """Check if docker-compose postgres is running."""
    try:
        result = subprocess.run(
            ["docker", "compose", "ps", "--status=running", "--format=json"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return "postgres" in result.stdout.lower()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


requires_db = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL") and not docker_available(),
    reason="PostgreSQL not available -- skipping checkpointer test",
)


@requires_db
def test_create_checkpointer_yields_postgres_saver():
    """create_checkpointer() context manager yields a PostgresSaver instance."""
    from langgraph.checkpoint.postgres import PostgresSaver

    with create_checkpointer() as checkpointer:
        assert isinstance(checkpointer, PostgresSaver)


@requires_db
def test_build_pipeline_with_checkpointer():
    """build_pipeline() compiles successfully with a checkpointer."""
    with create_checkpointer() as checkpointer:
        graph = build_pipeline(checkpointer=checkpointer)
        assert graph is not None
        assert hasattr(graph, "ainvoke")


@requires_db
async def test_create_async_checkpointer_yields_async_postgres_saver():
    """create_async_checkpointer() yields the AsyncPostgresSaver ainvoke needs."""
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    async with create_async_checkpointer() as checkpointer:
        assert isinstance(checkpointer, AsyncPostgresSaver)


@requires_db
async def test_checkpoint_resume():
    """Graph with checkpointer persists state and can be queried after run.

    Agents are stubbed with ``TestModel`` -- this test covers Postgres
    checkpoint persistence, not LLM output (real-LLM runs of the same pipeline
    live in ``test_graph.py`` behind a real-key guard).
    """
    with (
        extraction_agent.override(model=TestModel(call_tools=[])),
        analysis_agent.override(model=TestModel(call_tools=[])),
    ):
        async with create_async_checkpointer() as checkpointer:
            graph = build_pipeline(checkpointer=checkpointer)

            thread_id = f"test-checkpoint-resume-{uuid.uuid4()}"
            config = {"configurable": {"thread_id": thread_id}}

            state = await graph.ainvoke(
                {
                    "ticker": "MSFT",
                    "raw_text": "Revenue: $211B, Net Income: $72B",
                },
                config,
            )

            # Verify state was populated
            assert "extraction" in state
            assert "analysis" in state

            # Verify checkpoint was stored by checking state via get_state
            stored = await graph.aget_state(config)
            assert stored is not None
            assert stored.values.get("ticker") == "MSFT"
            assert stored.values.get("analysis") == state["analysis"]

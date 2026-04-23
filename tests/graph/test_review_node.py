"""Plan 08-03 Task 1: human_review_node tests (SIG-03).

Exercises the LangGraph ``interrupt()`` primitive in isolation via a tiny
single-node graph. The fixture compiles a ``StateGraph`` with an
``InMemorySaver`` checkpointer (Pitfall I -- the interrupt primitive
requires a checkpointer) and resumes via ``Command(resume=...)``.

Threat mitigations:
    T-08-03 (silent bypass): :func:`test_interrupt_primitive_is_invoked_in_source`
        greps the source to assert ``interrupt(`` literally appears inside
        the ``human_review_node`` body.
    T-08-04 (malformed resume): :func:`test_malformed_resume_raises` resumes
        with an invalid status; ``ReviewDecision.model_validate`` raises.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from pydantic import ValidationError

from ai_hedge_fund.graph.nodes import human_review_node
from ai_hedge_fund.schemas.state import DebatePipelineState


def _compile_review_only_graph() -> CompiledStateGraph:
    """Tiny graph used to exercise the interrupt primitive in isolation."""
    builder = StateGraph(DebatePipelineState)
    builder.add_node("review", human_review_node)
    builder.add_edge(START, "review")
    builder.add_edge("review", END)
    return builder.compile(checkpointer=InMemorySaver())


def _base_state() -> dict:
    return {
        "ticker": "AAPL",
        "as_of_date": "2026-04-20",
        "final_signal": {
            "ticker": "AAPL",
            "as_of_date": "2026-04-20",
            "direction": "long",
            "conviction": 85,
            "thesis_summary": "Bullish.",
            "risk_score": 30,
            "thesis_link": "episodic://7",
            "policy_sha": "a" * 64,
            "review_policy_sha": "b" * 64,
            "episodic_id": 7,
            "review_status": "NOT_REQUIRED",
        },
        "thesis": {"confidence": 85, "bull_case": "x", "bear_case": "y"},
        "bull_case": {"claims": []},
        "bear_case": {"claims": []},
        "rebuttal": {},
        "final_arguments": {},
        "debate_synthesis": {},
        "risk_assessment": {"status": "APPROVED", "policy_sha": "a" * 64},
    }


def test_interrupt_payload_contains_expected_keys() -> None:
    graph = _compile_review_only_graph()
    cfg = {"configurable": {"thread_id": "t-1"}}
    result = asyncio.run(graph.ainvoke(_base_state(), config=cfg))

    interrupts = result.get("__interrupt__")
    assert interrupts, "interrupt() must fire — state carries a final_signal"
    payload = interrupts[0].value
    for key in (
        "ticker",
        "signal",
        "thesis",
        "debate",
        "risk_assessment",
        "episodic_hits",
        "beliefs_consulted",
        "as_of_date",
    ):
        assert key in payload, f"missing key {key!r} in interrupt payload"


def test_valid_resume_writes_review_decision() -> None:
    graph = _compile_review_only_graph()
    cfg = {"configurable": {"thread_id": "t-2"}}
    asyncio.run(graph.ainvoke(_base_state(), config=cfg))

    decision = {
        "status": "APPROVED",
        "reviewer_id": "maxzou",
        "reviewer_note": "thesis holds.",
        "reviewed_at": datetime.now(UTC).isoformat(),
        "review_policy_sha": "b" * 64,
    }
    final = asyncio.run(graph.ainvoke(Command(resume=decision), config=cfg))
    assert final["review_decision"]["status"] == "APPROVED"
    assert final["review_decision"]["reviewer_id"] == "maxzou"


def test_malformed_resume_raises() -> None:
    """T-08-04 mitigation -- malformed resume fails loudly."""
    graph = _compile_review_only_graph()
    cfg = {"configurable": {"thread_id": "t-3"}}
    asyncio.run(graph.ainvoke(_base_state(), config=cfg))

    with pytest.raises(ValidationError):
        asyncio.run(graph.ainvoke(Command(resume={"status": "MAYBE"}), config=cfg))


def test_short_circuits_on_state_error() -> None:
    graph = _compile_review_only_graph()
    cfg = {"configurable": {"thread_id": "t-4"}}
    state = _base_state()
    state["error"] = "upstream failed"
    final = asyncio.run(graph.ainvoke(state, config=cfg))
    assert "review_decision" not in final or final.get("review_decision") is None
    assert final.get("__interrupt__") is None


def test_returns_error_on_missing_final_signal() -> None:
    graph = _compile_review_only_graph()
    cfg = {"configurable": {"thread_id": "t-5"}}
    state = _base_state()
    del state["final_signal"]
    final = asyncio.run(graph.ainvoke(state, config=cfg))
    assert final.get("error") and "No final_signal" in final["error"]


def test_interrupt_primitive_is_invoked_in_source() -> None:
    """T-08-03 defense-in-depth: grep verifies the primitive literally in source."""
    src = Path("src/ai_hedge_fund/graph/nodes.py").read_text()
    node_start = src.find("async def human_review_node")
    assert node_start > 0, "human_review_node not found"
    next_def = src.find("\nasync def ", node_start + 10)
    if next_def < 0:
        next_def = src.find("\ndef ", node_start + 10)
    assert next_def > node_start
    body = src[node_start:next_def]
    assert "interrupt(" in body, "human_review_node must call interrupt()"


def test_structlog_emits_human_review_decision_received() -> None:
    from structlog.testing import capture_logs

    graph = _compile_review_only_graph()
    cfg = {"configurable": {"thread_id": "t-6"}}
    asyncio.run(graph.ainvoke(_base_state(), config=cfg))

    decision = {
        "status": "APPROVED",
        "reviewer_id": "maxzou",
        "reviewer_note": "ok",
        "reviewed_at": datetime.now(UTC).isoformat(),
        "review_policy_sha": "b" * 64,
    }
    with capture_logs() as events:
        asyncio.run(graph.ainvoke(Command(resume=decision), config=cfg))
    event_names = [e.get("event") for e in events]
    assert "human_review_decision_received" in event_names

"""Plan 08-04 Task 1: run_analysis CLI + workhorse tests.

Dependency-injected: the tests pass a fake ``pipeline_factory`` that returns a
``_FakeGraph`` with pre-baked results (no real LLM calls) and a fake
``reviewer_io`` callable so we never block stdin. This verifies:

    * Below-threshold happy path (no interrupt, no reviewer_io call).
    * Above-threshold APPROVED flow (interrupt fires, reviewer_io invoked,
      Command(resume=...) called, final state surfaces review_decision).
    * Above-threshold REJECTED flow.
    * Malformed reviewer_io payload propagates (ValidationError bubbles).
    * Markdown / JSON output formatting.
    * thread_id carries the uuid4 suffix (Pitfall J).
    * VETOED path renders BLOCKED BY RISK without firing reviewer_io.
    * ``_review_threshold`` seeded from ReviewPolicy.conviction_threshold.
    * CLI-level missing-required-arg behaviour.
    * Pipeline ValueError surfaced to caller.
    * ``run_analysis_complete`` structlog event emitted (T-08-33).
"""

from __future__ import annotations

import os

# Match the documented Phase-7 workaround: the graph package eagerly
# instantiates PydanticAI agents at import time, which require
# ``ANTHROPIC_API_KEY``. The tests never call real agents but the import
# chain triggers the provider check; set a dummy key before any
# ``ai_hedge_fund`` import (same pattern as tests/integration/test_phase7_e2e.py).
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-phase8-run-analysis")

import asyncio
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from ai_hedge_fund.review.policy import ReviewPolicy, compute_review_policy_sha
from ai_hedge_fund.risk.policy import load_policy
from ai_hedge_fund.scripts.run_analysis import (
    _format_output,
    _main,
    run_analysis,
)


def _mk_final_state(
    conviction: int = 50,
    review_status: str = "NOT_REQUIRED",
) -> dict[str, Any]:
    """Fake post-pipeline state mirroring what output_node + review_store_node emit."""
    return {
        "ticker": "AAPL",
        "as_of_date": "2026-04-20",
        "final_signal": {
            "ticker": "AAPL",
            "as_of_date": "2026-04-20",
            "direction": "long",
            "conviction": conviction,
            "thesis_summary": "Bullish thesis based on margin expansion.",
            "risk_score": 30,
            "thesis_link": "episodic://7",
            "policy_sha": "a" * 64,
            "review_policy_sha": "b" * 64,
            "episodic_id": 7,
            "review_status": review_status,
        },
        "risk_assessment": {
            "status": "APPROVED",
            "policy_sha": "a" * 64,
            "observed": 4.0,
            "limit": 8.0,
            "rationale": "within limits",
        },
        "review_decision": None,
        "episodic_stored_id": 7,
        "review_stored_id": 8,
    }


class _FakeInterrupt:
    """Mirror the LangGraph Interrupt value-bearing wrapper."""

    def __init__(self, value: dict[str, Any]) -> None:
        self.value = value


def _mk_interrupt_state() -> dict[str, Any]:
    """State the pipeline returns when the human-review interrupt fires."""
    return {
        "__interrupt__": [
            _FakeInterrupt(
                {
                    "ticker": "AAPL",
                    "as_of_date": "2026-04-20",
                    "signal": {
                        "direction": "long",
                        "conviction": 85,
                        "thesis_summary": "High conviction long.",
                    },
                    "thesis": {
                        "confidence": 85,
                        "bull_case": "bullish",
                        "bear_case": "bearish",
                    },
                    "debate": {},
                    "risk_assessment": {"status": "APPROVED", "policy_sha": "a" * 64},
                    "episodic_hits": [],
                    "beliefs_consulted": [],
                }
            )
        ]
    }


class _FakeGraph:
    """Fake compiled pipeline that returns canned results from ainvoke()."""

    def __init__(self, results: list[dict[str, Any]]) -> None:
        self._results = list(results)
        self.invocations: list[tuple[Any, Any]] = []

    async def ainvoke(
        self, state: Any, config: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        self.invocations.append((state, config))
        if not self._results:
            raise AssertionError("_FakeGraph called more times than canned results")
        return self._results.pop(0)


def _fake_factory(results: list[dict[str, Any]]):
    """Build a pipeline_factory that always returns the same _FakeGraph instance.

    Exposes the graph on the factory as ``factory.graph`` so tests can inspect
    the recorded invocations after run_analysis returns.
    """
    graph = _FakeGraph(results)

    def factory(*args: Any, **kwargs: Any) -> _FakeGraph:
        return graph

    factory.graph = graph  # type: ignore[attr-defined]
    return factory


@pytest.fixture
def deps(portfolio_db_session: Session, tmp_path: Path) -> dict[str, Any]:
    """Common dependency bundle consumed by run_analysis test calls."""
    return {
        "session": portfolio_db_session,
        "beliefs_dir": tmp_path / "beliefs",
        "review_policy": ReviewPolicy(
            conviction_threshold=70,
            reviewer_id_default="test",
        ),
        "risk_policy": load_policy(Path("config/risk_policy.yaml")),
    }


# ---------------------------------------------------------------------------
# Test 1 - below-threshold happy path
# ---------------------------------------------------------------------------


def test_below_threshold_happy_path(deps: dict[str, Any]) -> None:
    """conviction<threshold -> no interrupt, reviewer_io never called."""
    factory = _fake_factory([_mk_final_state(conviction=50)])
    reviewer_io = MagicMock(
        side_effect=AssertionError("reviewer_io must NOT be called below threshold")
    )

    final = asyncio.run(
        run_analysis(
            ticker="AAPL",
            as_of_date="2026-04-20",
            sector="Technology",
            pipeline_factory=factory,
            reviewer_io=reviewer_io,
            **deps,
        )
    )
    assert final["final_signal"]["conviction"] == 50
    assert reviewer_io.call_count == 0
    assert len(factory.graph.invocations) == 1  # single pass; no resume


# ---------------------------------------------------------------------------
# Test 2 - above-threshold interrupt -> APPROVED resume
# ---------------------------------------------------------------------------


def test_above_threshold_approved(deps: dict[str, Any]) -> None:
    """conviction>=threshold -> interrupt fires; APPROVED decision resumes graph."""
    sha = compute_review_policy_sha(deps["review_policy"])
    decision = {
        "status": "APPROVED",
        "reviewer_id": "maxzou",
        "reviewer_note": "ok",
        "reviewed_at": datetime.now(UTC).isoformat(),
        "review_policy_sha": sha,
    }
    post_state = _mk_final_state(conviction=85, review_status="APPROVED")
    post_state["review_decision"] = decision

    factory = _fake_factory([_mk_interrupt_state(), post_state])
    reviewer_io = MagicMock(return_value=decision)

    final = asyncio.run(
        run_analysis(
            ticker="AAPL",
            as_of_date="2026-04-20",
            sector="Technology",
            pipeline_factory=factory,
            reviewer_io=reviewer_io,
            **deps,
        )
    )
    assert reviewer_io.call_count == 1
    # first invocation is the initial state; second is Command(resume=...)
    assert len(factory.graph.invocations) == 2
    assert final["review_decision"]["status"] == "APPROVED"


# ---------------------------------------------------------------------------
# Test 3 - above-threshold interrupt -> REJECTED resume
# ---------------------------------------------------------------------------


def test_above_threshold_rejected(deps: dict[str, Any]) -> None:
    """conviction>=threshold -> REJECTED decision also resumes graph."""
    sha = compute_review_policy_sha(deps["review_policy"])
    decision = {
        "status": "REJECTED",
        "reviewer_id": "maxzou",
        "reviewer_note": "concerns about leverage",
        "reviewed_at": datetime.now(UTC).isoformat(),
        "review_policy_sha": sha,
    }
    post_state = _mk_final_state(conviction=85, review_status="REJECTED")
    post_state["review_decision"] = decision

    factory = _fake_factory([_mk_interrupt_state(), post_state])
    reviewer_io = MagicMock(return_value=decision)

    final = asyncio.run(
        run_analysis(
            ticker="AAPL",
            as_of_date="2026-04-20",
            sector="Technology",
            pipeline_factory=factory,
            reviewer_io=reviewer_io,
            **deps,
        )
    )
    assert final["review_decision"]["status"] == "REJECTED"


# ---------------------------------------------------------------------------
# Test 4 - malformed reviewer_io payload -> ValidationError bubbles
# ---------------------------------------------------------------------------


def test_malformed_reviewer_io_bubbles(deps: dict[str, Any]) -> None:
    """A malformed decision should bubble out of run_analysis (not be swallowed)."""

    class _RaisingGraph:
        def __init__(self) -> None:
            self.first_call = True

        async def ainvoke(
            self, state: Any, config: dict[str, Any] | None = None
        ) -> dict[str, Any]:
            if self.first_call:
                self.first_call = False
                return _mk_interrupt_state()
            # Simulate ReviewDecision.model_validate raising on resume.
            raise ValidationError.from_exception_data("ReviewDecision", [])

    def factory(*args: Any, **kwargs: Any) -> _RaisingGraph:
        return _RaisingGraph()

    reviewer_io = MagicMock(return_value={"status": "MAYBE"})

    with pytest.raises(ValidationError):
        asyncio.run(
            run_analysis(
                ticker="AAPL",
                as_of_date="2026-04-20",
                sector="Technology",
                pipeline_factory=factory,
                reviewer_io=reviewer_io,
                **deps,
            )
        )


# ---------------------------------------------------------------------------
# Test 5 - JSON output
# ---------------------------------------------------------------------------


def test_format_output_json() -> None:
    """--json path emits valid JSON parseable into a dict with FinalSignal keys."""
    state = _mk_final_state(conviction=85)
    out = _format_output(state, as_json=True)
    parsed = json.loads(out)
    assert parsed["ticker"] == "AAPL"
    assert parsed["conviction"] == 85


# ---------------------------------------------------------------------------
# Test 6 - markdown is the default
# ---------------------------------------------------------------------------


def test_format_output_markdown_default() -> None:
    """Default path emits the compact ``# Signal:`` markdown header."""
    state = _mk_final_state(conviction=85)
    out = _format_output(state, as_json=False)
    assert out.startswith("# Signal:")


# ---------------------------------------------------------------------------
# Test 7 - thread_id has uuid4 suffix (Pitfall J)
# ---------------------------------------------------------------------------


def test_thread_id_uuid_suffix(
    deps: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """thread_id MUST match ^AAPL-2026-04-20-[0-9a-f]{8}$."""
    factory = _fake_factory([_mk_final_state(conviction=50)])
    fake_hex = "deadbeefcafef00dba5eba11feedface"  # 32-char hex

    class _FakeUUID:
        hex = fake_hex

    monkeypatch.setattr(
        "ai_hedge_fund.scripts.run_analysis.uuid.uuid4", lambda: _FakeUUID()
    )

    asyncio.run(
        run_analysis(
            ticker="AAPL",
            as_of_date="2026-04-20",
            sector="Technology",
            pipeline_factory=factory,
            reviewer_io=MagicMock(),
            **deps,
        )
    )
    config = factory.graph.invocations[0][1]
    tid = config["configurable"]["thread_id"]
    assert re.fullmatch(r"AAPL-2026-04-20-[0-9a-f]{8}", tid)
    assert tid.endswith(fake_hex[:8])


# ---------------------------------------------------------------------------
# Test 8 - VETOED path renders BLOCKED BY RISK and does NOT fire reviewer_io
# ---------------------------------------------------------------------------


def test_vetoed_no_signal_formats_blocked(deps: dict[str, Any]) -> None:
    """VETOED final state -> no final_signal; markdown shows ``BLOCKED BY RISK``."""
    vetoed_state = {
        "ticker": "AAPL",
        "as_of_date": "2026-04-20",
        "final_signal": None,
        "risk_assessment": {
            "status": "VETOED",
            "rationale": "sector excluded per policy",
            "policy_sha": "a" * 64,
        },
        "episodic_stored_id": 5,
    }
    factory = _fake_factory([vetoed_state])
    reviewer_io = MagicMock(
        side_effect=AssertionError("reviewer_io must not fire on VETOED path")
    )

    final = asyncio.run(
        run_analysis(
            ticker="AAPL",
            as_of_date="2026-04-20",
            sector="Technology",
            pipeline_factory=factory,
            reviewer_io=reviewer_io,
            **deps,
        )
    )
    out = _format_output(final, as_json=False)
    assert "BLOCKED BY RISK" in out
    assert reviewer_io.call_count == 0


# ---------------------------------------------------------------------------
# Test 9 - _review_threshold injected into initial state
# ---------------------------------------------------------------------------


def test_review_threshold_injected(deps: dict[str, Any]) -> None:
    """initial_state['_review_threshold'] == ReviewPolicy.conviction_threshold."""
    factory = _fake_factory([_mk_final_state(conviction=50)])
    asyncio.run(
        run_analysis(
            ticker="AAPL",
            as_of_date="2026-04-20",
            sector="Technology",
            pipeline_factory=factory,
            reviewer_io=MagicMock(),
            **deps,
        )
    )
    initial_state = factory.graph.invocations[0][0]
    assert (
        initial_state["_review_threshold"]
        == deps["review_policy"].conviction_threshold
    )


# ---------------------------------------------------------------------------
# Test 10 - CLI missing --ticker exits non-zero
# ---------------------------------------------------------------------------


def test_cli_missing_ticker_exits_nonzero() -> None:
    """argparse required=True -> SystemExit non-zero when --ticker is absent."""
    with pytest.raises(SystemExit) as excinfo:
        _main([])
    code = excinfo.value.code
    # argparse sets code to int 2 on missing required arg; any non-zero is fine.
    assert code is None or code != 0


# ---------------------------------------------------------------------------
# Test 11 - pipeline ValueError surfaced
# ---------------------------------------------------------------------------


def test_pipeline_valueerror_surfaced(deps: dict[str, Any]) -> None:
    """A pipeline_factory ValueError propagates through run_analysis."""

    def failing_factory(*args: Any, **kwargs: Any) -> Any:
        raise ValueError("bad pipeline config")

    with pytest.raises(ValueError, match="bad pipeline config"):
        asyncio.run(
            run_analysis(
                ticker="AAPL",
                as_of_date="2026-04-20",
                sector="Technology",
                pipeline_factory=failing_factory,
                reviewer_io=MagicMock(),
                **deps,
            )
        )


# ---------------------------------------------------------------------------
# Test 12 - run_analysis_complete structlog event emitted (T-08-33)
# ---------------------------------------------------------------------------


def test_structlog_run_analysis_complete_emitted(deps: dict[str, Any]) -> None:
    """Audit evidence: ``run_analysis_complete`` event fires at end of run."""
    from structlog.testing import capture_logs

    factory = _fake_factory([_mk_final_state(conviction=50)])
    with capture_logs() as events:
        asyncio.run(
            run_analysis(
                ticker="AAPL",
                as_of_date="2026-04-20",
                sector="Technology",
                pipeline_factory=factory,
                reviewer_io=MagicMock(),
                **deps,
            )
        )
    event_names = [e.get("event") for e in events]
    assert "run_analysis_complete" in event_names
    complete_event = next(
        e for e in events if e.get("event") == "run_analysis_complete"
    )
    assert complete_event.get("ticker") == "AAPL"
    assert complete_event.get("conviction") == 50

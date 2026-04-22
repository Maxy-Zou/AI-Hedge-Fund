"""Tests for the Phase-5 debate nodes (graph/nodes.py).

Covers the 5 debate nodes added in Plan 05-03:
    - bull_node: BullCase writer; requires state['thesis'].
    - bear_node: BearCase writer; requires state['thesis'] AND state['bull_case'].
    - rebuttal_node: RebuttalAct writer; requires bull_case AND bear_case.
    - final_arguments_node: FinalArguments writer; requires rebuttal (+bull/bear).
    - debate_synthesis_node: DebateSynthesis writer that OVERWRITES the LLM-
      produced quality_score with compute_quality_score() AND overwrites
      pre_debate_confidence with state['thesis']['confidence'] BEFORE the
      agent runs (Pitfall-3 mitigation). Returns BOTH ``debate_synthesis``
      AND ``thesis`` keys; thesis is replaced by ``revised_thesis.model_dump()``
      so the downstream signal node consumes the post-debate version unchanged.

TestModel from pydantic_ai.models.test produces schema-valid placeholder
values for all outputs, so we can exercise happy paths without real LLM
calls. Error paths are tested by passing state dicts missing the required
precondition keys.
"""

from __future__ import annotations

import asyncio
import inspect
import os

# Set dummy API key before importing agents (PydanticAI validates at construction).
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-for-unit-tests")

from pydantic_ai.models.test import TestModel  # noqa: E402

from ai_hedge_fund.agents.bear import bear_agent  # noqa: E402
from ai_hedge_fund.agents.bull import bull_agent  # noqa: E402
from ai_hedge_fund.agents.debate_synthesis import (  # noqa: E402
    debate_synthesis_agent,
)
from ai_hedge_fund.agents.final_arguments import final_arguments_agent  # noqa: E402
from ai_hedge_fund.agents.rebuttal import rebuttal_agent  # noqa: E402
from ai_hedge_fund.graph.nodes import (  # noqa: E402
    bear_node,
    bull_node,
    debate_synthesis_node,
    final_arguments_node,
    rebuttal_node,
)

# ---------------------------------------------------------------------------
# Seed helpers — minimal valid dicts matching the Phase-5 schemas.
# ---------------------------------------------------------------------------


def _seed_thesis(confidence: int = 60) -> dict:
    """Minimal ThesisOutput-shaped dict (bull_case/bear_case min_length=3)."""
    return {
        "ticker": "AAPL",
        "bull_case": [
            {"claim": "c1", "evidence": "e1", "source_tool": "t1"},
            {"claim": "c2", "evidence": "e2", "source_tool": "t2"},
            {"claim": "c3", "evidence": "e3", "source_tool": "t3"},
        ],
        "bear_case": [
            {"claim": "c1", "evidence": "e1", "source_tool": "t1"},
            {"claim": "c2", "evidence": "e2", "source_tool": "t2"},
            {"claim": "c3", "evidence": "e3", "source_tool": "t3"},
        ],
        "confidence": confidence,
        "risk_factors": ["r1", "r2"],
    }


def _seed_bull_case() -> dict:
    """Minimal BullCase-shaped dict (claims min_length=3)."""
    return {
        "ticker": "AAPL",
        "claims": [
            {"claim": "c1", "evidence": "e1", "source_analyst": "fundamental"},
            {"claim": "c2", "evidence": "e2", "source_analyst": "fundamental"},
            {"claim": "c3", "evidence": "e3", "source_analyst": "fundamental"},
        ],
        "headline": "Bull headline",
    }


def _seed_bear_case() -> dict:
    """Minimal BearCase-shaped dict (claims min_length=3, addressed min_length=2)."""
    return {
        "ticker": "AAPL",
        "claims": [
            {
                "claim": "c1",
                "evidence": "e1",
                "source_analyst": "sentiment",
                "addresses_bull_claim": "c1",
            },
            {
                "claim": "c2",
                "evidence": "e2",
                "source_analyst": "sentiment",
                "addresses_bull_claim": "c2",
            },
            {
                "claim": "c3",
                "evidence": "e3",
                "source_analyst": "sentiment",
                "addresses_bull_claim": None,
            },
        ],
        "addressed_bull_claims": ["c1", "c2"],
        "headline": "Bear headline",
    }


def _seed_rebuttal() -> dict:
    """Minimal RebuttalAct-shaped dict (both sides min_length=2)."""
    return {
        "ticker": "AAPL",
        "bull_rebuttals": [
            {
                "point": "p1",
                "targets_claim": "bear-c1",
                "source_analyst": "fundamental",
            },
            {
                "point": "p2",
                "targets_claim": "bear-c2",
                "source_analyst": "fundamental",
            },
        ],
        "bear_rebuttals": [
            {
                "point": "p1",
                "targets_claim": "bull-c1",
                "source_analyst": "sentiment",
            },
            {
                "point": "p2",
                "targets_claim": "bull-c2",
                "source_analyst": "sentiment",
            },
        ],
    }


def _seed_final_arguments() -> dict:
    """Minimal FinalArguments-shaped dict."""
    return {
        "ticker": "AAPL",
        "bull_closing": "Bull final closing argument text.",
        "bear_closing": "Bear final closing argument text.",
        "bull_citation_count": 3,
        "bear_citation_count": 3,
    }


# ---------------------------------------------------------------------------
# TestDebateNodesAreAsync
# ---------------------------------------------------------------------------


class TestDebateNodesAreAsync:
    """All 5 debate nodes are async coroutines."""

    def test_bull_node_is_async(self) -> None:
        assert inspect.iscoroutinefunction(bull_node)

    def test_bear_node_is_async(self) -> None:
        assert inspect.iscoroutinefunction(bear_node)

    def test_rebuttal_node_is_async(self) -> None:
        assert inspect.iscoroutinefunction(rebuttal_node)

    def test_final_arguments_node_is_async(self) -> None:
        assert inspect.iscoroutinefunction(final_arguments_node)

    def test_debate_synthesis_node_is_async(self) -> None:
        assert inspect.iscoroutinefunction(debate_synthesis_node)


# ---------------------------------------------------------------------------
# TestDebateNodesShortCircuitOnError
# ---------------------------------------------------------------------------


class TestDebateNodesShortCircuitOnError:
    """Each debate node returns {} when state carries an upstream error."""

    def _errored_state(self) -> dict:
        return {
            "ticker": "AAPL",
            "as_of_date": "2024-01-02",
            "error": "upstream failure",
        }

    def test_bull_node_short_circuits(self) -> None:
        result = asyncio.run(bull_node(self._errored_state()))
        assert result == {}

    def test_bear_node_short_circuits(self) -> None:
        result = asyncio.run(bear_node(self._errored_state()))
        assert result == {}

    def test_rebuttal_node_short_circuits(self) -> None:
        result = asyncio.run(rebuttal_node(self._errored_state()))
        assert result == {}

    def test_final_arguments_node_short_circuits(self) -> None:
        result = asyncio.run(final_arguments_node(self._errored_state()))
        assert result == {}

    def test_debate_synthesis_node_short_circuits(self) -> None:
        result = asyncio.run(debate_synthesis_node(self._errored_state()))
        assert result == {}


# ---------------------------------------------------------------------------
# TestBullNode
# ---------------------------------------------------------------------------


class TestBullNodeHappyPath:
    def test_returns_bull_case_dict(self) -> None:
        state: dict = {
            "ticker": "AAPL",
            "as_of_date": "2024-01-02",
            "analyst_reports": [
                {
                    "analyst": "fundamental",
                    "analysis": {"ticker": "AAPL", "valuation_assessment": "fair"},
                    "tokens_used": 1000,
                }
            ],
            "thesis": _seed_thesis(),
        }
        with bull_agent.override(model=TestModel()):
            result = asyncio.run(bull_node(state))
        assert "bull_case" in result
        assert isinstance(result["bull_case"], dict)


class TestBullNodeMissingThesis:
    def test_missing_thesis_returns_error(self) -> None:
        state: dict = {
            "ticker": "AAPL",
            "as_of_date": "2024-01-02",
        }
        result = asyncio.run(bull_node(state))
        assert "error" in result
        assert "thesis" in result["error"].lower()

    def test_thesis_is_none_returns_error(self) -> None:
        state: dict = {
            "ticker": "AAPL",
            "as_of_date": "2024-01-02",
            "thesis": None,
        }
        result = asyncio.run(bull_node(state))
        assert "error" in result


# ---------------------------------------------------------------------------
# TestBearNode
# ---------------------------------------------------------------------------


class TestBearNodeHappyPath:
    def test_returns_bear_case_dict(self) -> None:
        state: dict = {
            "ticker": "AAPL",
            "as_of_date": "2024-01-02",
            "analyst_reports": [],
            "thesis": _seed_thesis(),
            "bull_case": _seed_bull_case(),
        }
        with bear_agent.override(model=TestModel()):
            result = asyncio.run(bear_node(state))
        assert "bear_case" in result
        assert isinstance(result["bear_case"], dict)


class TestBearNodeMissingBullCase:
    def test_missing_bull_case_returns_error(self) -> None:
        state: dict = {
            "ticker": "AAPL",
            "as_of_date": "2024-01-02",
            "thesis": _seed_thesis(),
        }
        result = asyncio.run(bear_node(state))
        assert "error" in result
        assert "bull" in result["error"].lower()


# ---------------------------------------------------------------------------
# TestRebuttalNode
# ---------------------------------------------------------------------------


class TestRebuttalNodeHappyPath:
    def test_returns_rebuttal_dict(self) -> None:
        state: dict = {
            "ticker": "AAPL",
            "as_of_date": "2024-01-02",
            "bull_case": _seed_bull_case(),
            "bear_case": _seed_bear_case(),
        }
        with rebuttal_agent.override(model=TestModel()):
            result = asyncio.run(rebuttal_node(state))
        assert "rebuttal" in result
        assert isinstance(result["rebuttal"], dict)


class TestRebuttalNodeMissingPrerequisite:
    def test_missing_bull_returns_error(self) -> None:
        state: dict = {
            "ticker": "AAPL",
            "as_of_date": "2024-01-02",
            "bear_case": _seed_bear_case(),
        }
        result = asyncio.run(rebuttal_node(state))
        assert "error" in result

    def test_missing_bear_returns_error(self) -> None:
        state: dict = {
            "ticker": "AAPL",
            "as_of_date": "2024-01-02",
            "bull_case": _seed_bull_case(),
        }
        result = asyncio.run(rebuttal_node(state))
        assert "error" in result


# ---------------------------------------------------------------------------
# TestFinalArgumentsNode
# ---------------------------------------------------------------------------


class TestFinalArgumentsNodeHappyPath:
    def test_returns_final_arguments_dict(self) -> None:
        state: dict = {
            "ticker": "AAPL",
            "as_of_date": "2024-01-02",
            "bull_case": _seed_bull_case(),
            "bear_case": _seed_bear_case(),
            "rebuttal": _seed_rebuttal(),
        }
        with final_arguments_agent.override(model=TestModel()):
            result = asyncio.run(final_arguments_node(state))
        assert "final_arguments" in result
        assert isinstance(result["final_arguments"], dict)


class TestFinalArgumentsNodeMissingRebuttal:
    def test_missing_rebuttal_returns_error(self) -> None:
        state: dict = {
            "ticker": "AAPL",
            "as_of_date": "2024-01-02",
            "bull_case": _seed_bull_case(),
            "bear_case": _seed_bear_case(),
        }
        result = asyncio.run(final_arguments_node(state))
        assert "error" in result
        assert "rebuttal" in result["error"].lower()


# ---------------------------------------------------------------------------
# TestDebateSynthesisNode -- DEBATE-04 load-bearing tests.
# ---------------------------------------------------------------------------


class TestDebateSynthesisNode:
    """debate_synthesis_node overwrites BOTH quality_score and pre_debate_confidence."""

    def _full_state(self, confidence: int = 60) -> dict:
        return {
            "ticker": "AAPL",
            "as_of_date": "2024-01-02",
            "thesis": _seed_thesis(confidence=confidence),
            "bull_case": _seed_bull_case(),
            "bear_case": _seed_bear_case(),
            "rebuttal": _seed_rebuttal(),
            "final_arguments": _seed_final_arguments(),
        }

    def test_happy_path_returns_debate_synthesis_and_thesis(self) -> None:
        """Node returns BOTH 'debate_synthesis' and 'thesis'; thesis == revised_thesis."""
        state = self._full_state()
        with debate_synthesis_agent.override(model=TestModel()):
            result = asyncio.run(debate_synthesis_node(state))
        assert "debate_synthesis" in result
        assert "thesis" in result
        # thesis was OVERWRITTEN with revised_thesis dump so signal_node sees
        # the post-debate version unchanged.
        assert result["thesis"] == result["debate_synthesis"]["revised_thesis"]

    def test_quality_score_is_recomputed(self) -> None:
        """quality_score == round(0.4*evidence + 0.3*logic + 0.3*risk) -- DEBATE-04."""
        state = self._full_state()
        with debate_synthesis_agent.override(model=TestModel()):
            result = asyncio.run(debate_synthesis_node(state))
        synth = result["debate_synthesis"]
        expected = round(
            0.4 * synth["evidence_strength"]
            + 0.3 * synth["logical_consistency"]
            + 0.3 * synth["risk_coverage"]
        )
        assert synth["quality_score"] == expected, (
            f"quality_score {synth['quality_score']} must equal deterministic "
            f"weighted mean {expected} of sub-scores "
            f"(evidence={synth['evidence_strength']}, "
            f"logic={synth['logical_consistency']}, "
            f"risk={synth['risk_coverage']})"
        )

    def test_pre_debate_confidence_sourced_from_state(self) -> None:
        """pre_debate_confidence == state['thesis']['confidence'] -- Pitfall-3."""
        state = self._full_state(confidence=42)
        with debate_synthesis_agent.override(model=TestModel()):
            result = asyncio.run(debate_synthesis_node(state))
        assert result["debate_synthesis"]["pre_debate_confidence"] == 42, (
            "pre_debate_confidence must be sourced from state['thesis']['confidence'], "
            "NOT from LLM output (TestModel would otherwise produce 0)."
        )

    def test_missing_final_arguments_returns_error(self) -> None:
        state = self._full_state()
        state.pop("final_arguments")
        result = asyncio.run(debate_synthesis_node(state))
        assert "error" in result
        assert "final" in result["error"].lower()

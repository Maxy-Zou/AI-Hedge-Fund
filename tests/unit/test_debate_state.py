"""Tests for the Phase-5 DebatePipelineState TypedDict schema.

Verifies:
- DebatePipelineState carries the required, Phase-4, and debate-specific
  fields expected by Plan 05-03's pipeline builder.
- analyst_reports retains its operator.add reducer (fan-in from parallel
  analysts -- same contract as MultiAgentPipelineState).
- The 5 debate-act fields (bull_case, bear_case, rebuttal,
  final_arguments, debate_synthesis) have NO reducer metadata --
  single-writer overwrite semantics enforced by contract.
- DebatePipelineState is importable from the schemas namespace.
"""

from __future__ import annotations

import operator
import typing

from ai_hedge_fund.schemas.state import DebatePipelineState


class TestDebatePipelineStateFields:
    """Verify DebatePipelineState declares all required fields."""

    def test_state_has_required_fields(self) -> None:
        """ticker and as_of_date are declared (via Required[str])."""
        hints = typing.get_type_hints(DebatePipelineState, include_extras=True)
        for field in ("ticker", "as_of_date"):
            assert field in hints, f"Required field missing: {field}"

    def test_state_has_phase4_fields(self) -> None:
        """The Phase-4 fields (analyst_reports, thesis, signal, error) are present."""
        hints = typing.get_type_hints(DebatePipelineState, include_extras=True)
        for field in ("analyst_reports", "thesis", "signal", "error"):
            assert field in hints, f"Phase-4 field missing: {field}"

    def test_state_has_debate_fields(self) -> None:
        """The 5 debate-act fields are present."""
        hints = typing.get_type_hints(DebatePipelineState, include_extras=True)
        for field in (
            "bull_case",
            "bear_case",
            "rebuttal",
            "final_arguments",
            "debate_synthesis",
        ):
            assert field in hints, f"Debate field missing: {field}"


class TestDebatePipelineStateReducers:
    """Verify reducer contracts (fan-in on analyst_reports, single-writer on debate fields)."""

    def test_analyst_reports_keeps_operator_add_reducer(self) -> None:
        """analyst_reports MUST retain its operator.add reducer -- fan-in from analysts."""
        hints = typing.get_type_hints(DebatePipelineState, include_extras=True)
        hint = hints["analyst_reports"]
        metadata = typing.get_args(hint)
        assert operator.add in metadata, (
            "analyst_reports must carry operator.add reducer (fan-in semantics)"
        )

    def test_debate_fields_have_no_reducer(self) -> None:
        """Debate-act fields MUST be single-writer (no operator.add).

        Silent accumulation via a reducer would turn each act into an
        append-only list across reruns, breaking the 5-act protocol's
        overwrite-on-retry semantics. This contract is enforced here so
        a future refactor cannot accidentally add a reducer.
        """
        hints = typing.get_type_hints(DebatePipelineState, include_extras=True)
        for field in (
            "bull_case",
            "bear_case",
            "rebuttal",
            "final_arguments",
            "debate_synthesis",
        ):
            hint = hints[field]
            metadata = typing.get_args(hint)
            assert operator.add not in metadata, (
                f"{field} must NOT carry operator.add reducer -- "
                "single-writer overwrite semantics. See RESEARCH.md Anti-Patterns."
            )


class TestDebatePipelineStateImportable:
    """DebatePipelineState is re-exported from the schemas package."""

    def test_available_from_schemas_namespace(self) -> None:
        from ai_hedge_fund.schemas import DebatePipelineState as ImportedState

        assert ImportedState is DebatePipelineState

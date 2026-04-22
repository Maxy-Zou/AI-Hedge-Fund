"""Tests for Phase-5 debate act output schemas (Plan 05-01, Task 1).

Covers: BullClaim, BullCase, BearClaim, BearCase, RebuttalPoint, RebuttalAct,
FinalArguments, DebateSynthesis.

Key enforcement targets:
- DEBATE-01: BullCase.claims requires min_length=3; BullClaim.source_analyst is a Literal.
- DEBATE-02: BearCase.addressed_bull_claims requires min_length=2 (this IS the
  schema-level enforcement of "bear must address at least 2 bull claims").
- DEBATE-03: Every substantive act field enforces non-emptiness via min_length,
  so "skipping an act or producing an empty act" raises ValidationError -- see
  TestEmptyActRaisesValidationError.
- DEBATE-04: DebateSynthesis sub-score and quality_score fields use ge=0/le=100.

DebateSynthesis.revised_thesis is typed as ThesisOutput (imported, not redefined).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError


def _valid_thesis_output_kwargs() -> dict:
    """Return kwargs that construct a minimal valid ThesisOutput."""
    return {
        "ticker": "AAPL",
        "bull_case": [
            {
                "claim": f"Bull point {i}",
                "evidence": f"Evidence {i}",
                "source_tool": "get_financials",
            }
            for i in range(3)
        ],
        "bear_case": [
            {
                "claim": f"Bear point {i}",
                "evidence": f"Evidence {i}",
                "source_tool": "get_financials",
            }
            for i in range(3)
        ],
        "confidence": 60,
        "risk_factors": ["Risk A", "Risk B"],
    }


class TestBullClaim:
    """Tests for BullClaim sub-model."""

    def test_valid_claim(self) -> None:
        """BullClaim validates with all required fields."""
        from ai_hedge_fund.schemas.debate import BullClaim

        c = BullClaim(
            claim="Revenue grew 20% YoY",
            evidence="FY23 10-K income statement, $394B vs $329B",
            source_analyst="fundamental",
        )
        assert c.claim == "Revenue grew 20% YoY"
        assert c.source_analyst == "fundamental"

    def test_rejects_empty_claim(self) -> None:
        """BullClaim rejects empty claim string (min_length=1)."""
        from ai_hedge_fund.schemas.debate import BullClaim

        with pytest.raises(ValidationError):
            BullClaim(claim="", evidence="x", source_analyst="fundamental")

    def test_rejects_empty_evidence(self) -> None:
        """BullClaim rejects empty evidence string (min_length=1)."""
        from ai_hedge_fund.schemas.debate import BullClaim

        with pytest.raises(ValidationError):
            BullClaim(claim="c", evidence="", source_analyst="fundamental")

    def test_rejects_invalid_source_analyst(self) -> None:
        """BullClaim rejects source_analyst not in the Literal set."""
        from ai_hedge_fund.schemas.debate import BullClaim

        with pytest.raises(ValidationError):
            BullClaim(claim="c", evidence="e", source_analyst="marketing")

    def test_accepts_manager_as_source_analyst(self) -> None:
        """BullClaim accepts 'manager' -- bulls may cite manager synthesis."""
        from ai_hedge_fund.schemas.debate import BullClaim

        c = BullClaim(claim="c", evidence="e", source_analyst="manager")
        assert c.source_analyst == "manager"


class TestBullCase:
    """Tests for BullCase top-level act schema."""

    def _valid_claims(self, count: int = 3) -> list[dict]:
        return [
            {
                "claim": f"Claim {i}",
                "evidence": f"Evidence {i}",
                "source_analyst": "fundamental",
            }
            for i in range(count)
        ]

    def test_valid_with_three_claims(self) -> None:
        """BullCase validates at minimum claims length (3)."""
        from ai_hedge_fund.schemas.debate import BullCase

        case = BullCase(
            ticker="AAPL",
            claims=self._valid_claims(3),
            headline="Apple is a buy on margin expansion",
        )
        assert case.ticker == "AAPL"
        assert len(case.claims) == 3

    def test_rejects_fewer_than_three_claims(self) -> None:
        """BullCase rejects claims list with fewer than 3 items (min_length=3)."""
        from ai_hedge_fund.schemas.debate import BullCase

        with pytest.raises(ValidationError):
            BullCase(
                ticker="AAPL",
                claims=self._valid_claims(2),
                headline="Bull headline",
            )

    def test_rejects_empty_claims(self) -> None:
        """BullCase rejects empty claims list."""
        from ai_hedge_fund.schemas.debate import BullCase

        with pytest.raises(ValidationError):
            BullCase(ticker="AAPL", claims=[], headline="Bull headline")

    def test_rejects_empty_headline(self) -> None:
        """BullCase rejects empty headline (min_length=1)."""
        from ai_hedge_fund.schemas.debate import BullCase

        with pytest.raises(ValidationError):
            BullCase(ticker="AAPL", claims=self._valid_claims(3), headline="")


class TestBearClaim:
    """Tests for BearClaim sub-model."""

    def test_valid_with_addresses_bull_claim_none(self) -> None:
        """BearClaim validates with addresses_bull_claim defaulting to None."""
        from ai_hedge_fund.schemas.debate import BearClaim

        c = BearClaim(
            claim="Gross margin is contracting",
            evidence="10-K MD&A section",
            source_analyst="fundamental",
        )
        assert c.addresses_bull_claim is None

    def test_valid_with_addresses_bull_claim_set(self) -> None:
        """BearClaim validates when addresses_bull_claim is provided."""
        from ai_hedge_fund.schemas.debate import BearClaim

        c = BearClaim(
            claim="Margin guidance is stale",
            evidence="Q1 earnings call",
            source_analyst="sentiment",
            addresses_bull_claim="Margins are expanding",
        )
        assert c.addresses_bull_claim == "Margins are expanding"

    def test_rejects_empty_claim(self) -> None:
        """BearClaim rejects empty claim (min_length=1)."""
        from ai_hedge_fund.schemas.debate import BearClaim

        with pytest.raises(ValidationError):
            BearClaim(claim="", evidence="e", source_analyst="fundamental")


class TestBearCase:
    """Tests for BearCase top-level act schema (DEBATE-02 enforcement site)."""

    def _valid_claims(self, count: int = 3) -> list[dict]:
        return [
            {
                "claim": f"Bear claim {i}",
                "evidence": f"Evidence {i}",
                "source_analyst": "fundamental",
            }
            for i in range(count)
        ]

    def test_valid_happy_path(self) -> None:
        """BearCase validates with 3 claims and 2 addressed_bull_claims."""
        from ai_hedge_fund.schemas.debate import BearCase

        case = BearCase(
            ticker="AAPL",
            claims=self._valid_claims(3),
            addressed_bull_claims=[
                "Revenue grew 20% YoY",
                "Services margin expanding",
            ],
            headline="Apple overvalued on saturated hardware",
        )
        assert len(case.addressed_bull_claims) == 2

    def test_rejects_fewer_than_two_addressed_bull_claims(self) -> None:
        """BearCase rejects addressed_bull_claims with 0 or 1 items (DEBATE-02)."""
        from ai_hedge_fund.schemas.debate import BearCase

        # Empty list rejected.
        with pytest.raises(ValidationError):
            BearCase(
                ticker="AAPL",
                claims=self._valid_claims(3),
                addressed_bull_claims=[],
                headline="h",
            )

        # Single-item list rejected.
        with pytest.raises(ValidationError):
            BearCase(
                ticker="AAPL",
                claims=self._valid_claims(3),
                addressed_bull_claims=["only one"],
                headline="h",
            )

    def test_rejects_fewer_than_three_claims(self) -> None:
        """BearCase rejects claims list with fewer than 3 items."""
        from ai_hedge_fund.schemas.debate import BearCase

        with pytest.raises(ValidationError):
            BearCase(
                ticker="AAPL",
                claims=self._valid_claims(2),
                addressed_bull_claims=["a", "b"],
                headline="h",
            )

    def test_rejects_empty_headline(self) -> None:
        """BearCase rejects empty headline (min_length=1)."""
        from ai_hedge_fund.schemas.debate import BearCase

        with pytest.raises(ValidationError):
            BearCase(
                ticker="AAPL",
                claims=self._valid_claims(3),
                addressed_bull_claims=["a", "b"],
                headline="",
            )

    def test_rejects_empty_string_in_addressed_bull_claims(self) -> None:
        """WR-02 regression: addressed_bull_claims element type is NonEmptyStr.

        Field(min_length=2) on a list[str] only constrains list length, so
        `["", ""]` would pass a naive schema. The element-level NonEmptyStr
        constraint rejects empty-string entries so a schema-compliant but
        semantically hollow bear case cannot slip through.
        """
        from ai_hedge_fund.schemas.debate import BearCase

        # Two empty strings: list length passes, but each element fails.
        with pytest.raises(ValidationError):
            BearCase(
                ticker="AAPL",
                claims=self._valid_claims(3),
                addressed_bull_claims=["", ""],
                headline="h",
            )

        # One valid + one empty: element check rejects the empty entry.
        with pytest.raises(ValidationError):
            BearCase(
                ticker="AAPL",
                claims=[
                    {
                        "claim": f"Bear claim {i}",
                        "evidence": f"Evidence {i}",
                        "source_analyst": "fundamental",
                        "addresses_bull_claim": "Revenue grew 20% YoY",
                    }
                    for i in range(3)
                ],
                addressed_bull_claims=["Revenue grew 20% YoY", ""],
                headline="h",
            )


class TestRebuttalPoint:
    """Tests for RebuttalPoint sub-model."""

    def test_valid(self) -> None:
        """RebuttalPoint validates with all required fields."""
        from ai_hedge_fund.schemas.debate import RebuttalPoint

        r = RebuttalPoint(
            point="Margin expansion relied on one-time pricing",
            targets_claim="Margins are expanding",
            source_analyst="fundamental",
        )
        assert r.source_analyst == "fundamental"

    def test_rejects_empty_point(self) -> None:
        """RebuttalPoint rejects empty point (min_length=1)."""
        from ai_hedge_fund.schemas.debate import RebuttalPoint

        with pytest.raises(ValidationError):
            RebuttalPoint(point="", targets_claim="t", source_analyst="fundamental")

    def test_rejects_empty_targets_claim(self) -> None:
        """RebuttalPoint rejects empty targets_claim (min_length=1)."""
        from ai_hedge_fund.schemas.debate import RebuttalPoint

        with pytest.raises(ValidationError):
            RebuttalPoint(point="p", targets_claim="", source_analyst="fundamental")


class TestRebuttalAct:
    """Tests for RebuttalAct top-level act schema."""

    def _valid_rebuttals(self, count: int = 2) -> list[dict]:
        return [
            {
                "point": f"Point {i}",
                "targets_claim": f"Claim {i}",
                "source_analyst": "fundamental",
            }
            for i in range(count)
        ]

    def test_valid(self) -> None:
        """RebuttalAct validates with 2 rebuttals on each side."""
        from ai_hedge_fund.schemas.debate import RebuttalAct

        act = RebuttalAct(
            ticker="AAPL",
            bull_rebuttals=self._valid_rebuttals(2),
            bear_rebuttals=self._valid_rebuttals(2),
        )
        assert len(act.bull_rebuttals) == 2
        assert len(act.bear_rebuttals) == 2

    def test_rejects_empty_bull_rebuttals(self) -> None:
        """RebuttalAct rejects empty bull_rebuttals (min_length=2)."""
        from ai_hedge_fund.schemas.debate import RebuttalAct

        with pytest.raises(ValidationError):
            RebuttalAct(
                ticker="AAPL",
                bull_rebuttals=[],
                bear_rebuttals=self._valid_rebuttals(2),
            )

    def test_rejects_empty_bear_rebuttals(self) -> None:
        """RebuttalAct rejects empty bear_rebuttals (min_length=2)."""
        from ai_hedge_fund.schemas.debate import RebuttalAct

        with pytest.raises(ValidationError):
            RebuttalAct(
                ticker="AAPL",
                bull_rebuttals=self._valid_rebuttals(2),
                bear_rebuttals=[],
            )

    def test_rejects_one_bull_rebuttal(self) -> None:
        """RebuttalAct rejects bull_rebuttals with only 1 item (min_length=2)."""
        from ai_hedge_fund.schemas.debate import RebuttalAct

        with pytest.raises(ValidationError):
            RebuttalAct(
                ticker="AAPL",
                bull_rebuttals=self._valid_rebuttals(1),
                bear_rebuttals=self._valid_rebuttals(2),
            )


class TestFinalArguments:
    """Tests for FinalArguments top-level act schema."""

    def test_valid(self) -> None:
        """FinalArguments validates with non-empty closings and non-negative counts."""
        from ai_hedge_fund.schemas.debate import FinalArguments

        fa = FinalArguments(
            ticker="AAPL",
            bull_closing="We cited 5 analyst data points showing...",
            bear_closing="Counter-evidence includes 3 risk factors...",
            bull_citation_count=5,
            bear_citation_count=3,
        )
        assert fa.bull_citation_count == 5

    def test_rejects_empty_bull_closing(self) -> None:
        """FinalArguments rejects empty bull_closing (min_length=1)."""
        from ai_hedge_fund.schemas.debate import FinalArguments

        with pytest.raises(ValidationError):
            FinalArguments(
                ticker="AAPL",
                bull_closing="",
                bear_closing="b",
                bull_citation_count=1,
                bear_citation_count=1,
            )

    def test_rejects_empty_bear_closing(self) -> None:
        """FinalArguments rejects empty bear_closing (min_length=1)."""
        from ai_hedge_fund.schemas.debate import FinalArguments

        with pytest.raises(ValidationError):
            FinalArguments(
                ticker="AAPL",
                bull_closing="b",
                bear_closing="",
                bull_citation_count=1,
                bear_citation_count=1,
            )

    def test_rejects_negative_citation_count(self) -> None:
        """FinalArguments rejects negative bull_citation_count (ge=0)."""
        from ai_hedge_fund.schemas.debate import FinalArguments

        with pytest.raises(ValidationError):
            FinalArguments(
                ticker="AAPL",
                bull_closing="b",
                bear_closing="c",
                bull_citation_count=-1,
                bear_citation_count=1,
            )


class TestDebateSynthesis:
    """Tests for DebateSynthesis top-level act schema (DEBATE-04)."""

    def test_valid_happy_path(self) -> None:
        """DebateSynthesis validates with a full nested ThesisOutput."""
        from ai_hedge_fund.schemas.debate import DebateSynthesis

        synth = DebateSynthesis(
            ticker="AAPL",
            revised_thesis=_valid_thesis_output_kwargs(),
            pre_debate_confidence=60,
            post_debate_confidence=55,
            evidence_strength=70,
            logical_consistency=80,
            risk_coverage=65,
            quality_score=72,
            synthesis_notes="Bull case was narrower than initial thesis suggested.",
        )
        assert synth.quality_score == 72
        assert synth.revised_thesis.ticker == "AAPL"

    def test_rejects_out_of_range_sub_score(self) -> None:
        """DebateSynthesis rejects evidence_strength=101 (le=100)."""
        from ai_hedge_fund.schemas.debate import DebateSynthesis

        with pytest.raises(ValidationError):
            DebateSynthesis(
                ticker="AAPL",
                revised_thesis=_valid_thesis_output_kwargs(),
                pre_debate_confidence=50,
                post_debate_confidence=50,
                evidence_strength=101,
                logical_consistency=50,
                risk_coverage=50,
                quality_score=50,
                synthesis_notes="notes",
            )

    def test_rejects_negative_quality_score(self) -> None:
        """DebateSynthesis rejects quality_score=-1 (ge=0)."""
        from ai_hedge_fund.schemas.debate import DebateSynthesis

        with pytest.raises(ValidationError):
            DebateSynthesis(
                ticker="AAPL",
                revised_thesis=_valid_thesis_output_kwargs(),
                pre_debate_confidence=50,
                post_debate_confidence=50,
                evidence_strength=50,
                logical_consistency=50,
                risk_coverage=50,
                quality_score=-1,
                synthesis_notes="notes",
            )

    def test_rejects_empty_synthesis_notes(self) -> None:
        """DebateSynthesis rejects empty synthesis_notes (min_length=1)."""
        from ai_hedge_fund.schemas.debate import DebateSynthesis

        with pytest.raises(ValidationError):
            DebateSynthesis(
                ticker="AAPL",
                revised_thesis=_valid_thesis_output_kwargs(),
                pre_debate_confidence=50,
                post_debate_confidence=50,
                evidence_strength=50,
                logical_consistency=50,
                risk_coverage=50,
                quality_score=50,
                synthesis_notes="",
            )

    def test_rejects_out_of_range_pre_debate_confidence(self) -> None:
        """DebateSynthesis rejects pre_debate_confidence > 100 (le=100)."""
        from ai_hedge_fund.schemas.debate import DebateSynthesis

        with pytest.raises(ValidationError):
            DebateSynthesis(
                ticker="AAPL",
                revised_thesis=_valid_thesis_output_kwargs(),
                pre_debate_confidence=150,
                post_debate_confidence=50,
                evidence_strength=50,
                logical_consistency=50,
                risk_coverage=50,
                quality_score=50,
                synthesis_notes="notes",
            )


class TestEmptyActRaisesValidationError:
    """DEBATE-03 success-criterion-3 enforcement: skipping or producing an
    empty act output raises ValidationError.

    This class documents the schema-level guarantee that every debate act
    schema has at least one ``min_length`` (or ``min_length=1``) substantive
    field such that an "empty" output -- missing claims, missing rebuttals,
    missing headline/closing/notes -- fails validation at ``agent.run()`` time.
    """

    def test_empty_bull_case_raises(self) -> None:
        """BullCase() with no claims raises ValidationError."""
        from ai_hedge_fund.schemas.debate import BullCase

        with pytest.raises(ValidationError):
            BullCase(ticker="AAPL", claims=[], headline="h")

    def test_empty_bear_case_raises(self) -> None:
        """BearCase() with no claims AND no addressed_bull_claims raises."""
        from ai_hedge_fund.schemas.debate import BearCase

        with pytest.raises(ValidationError):
            BearCase(
                ticker="AAPL",
                claims=[],
                addressed_bull_claims=[],
                headline="h",
            )

    def test_empty_rebuttal_act_raises(self) -> None:
        """RebuttalAct() with empty sides raises."""
        from ai_hedge_fund.schemas.debate import RebuttalAct

        with pytest.raises(ValidationError):
            RebuttalAct(ticker="AAPL", bull_rebuttals=[], bear_rebuttals=[])

    def test_empty_final_arguments_raises(self) -> None:
        """FinalArguments() with empty closings raises."""
        from ai_hedge_fund.schemas.debate import FinalArguments

        with pytest.raises(ValidationError):
            FinalArguments(
                ticker="AAPL",
                bull_closing="",
                bear_closing="",
                bull_citation_count=0,
                bear_citation_count=0,
            )

    def test_empty_debate_synthesis_notes_raises(self) -> None:
        """DebateSynthesis with empty synthesis_notes raises (min_length=1)."""
        from ai_hedge_fund.schemas.debate import DebateSynthesis

        with pytest.raises(ValidationError):
            DebateSynthesis(
                ticker="AAPL",
                revised_thesis=_valid_thesis_output_kwargs(),
                pre_debate_confidence=50,
                post_debate_confidence=50,
                evidence_strength=50,
                logical_consistency=50,
                risk_coverage=50,
                quality_score=50,
                synthesis_notes="",
            )

"""PydanticAI output schemas for the Phase-5 adversarial debate acts.

Each debate act produces a typed, validated output model. Constraints enforce
the Phase-5 requirements at the validation boundary -- no custom validator
code is needed:

- ``min_length`` on every substantive list field prevents empty / under-populated
  act outputs (DEBATE-01, DEBATE-02, DEBATE-03 success criterion 3).
- ``min_length=1`` on every substantive string field (claim, evidence, headline,
  closing, synthesis_notes) prevents an agent from returning a blank act.
- ``Literal["fundamental", "sentiment", "technical", "manager"]`` on
  ``source_analyst`` ensures the citation points to a real upstream producer --
  a bull or bear advocate cannot invent an analyst.
- ``ge=0, le=100`` on every sub-score / confidence / quality_score field rejects
  out-of-range integers from the LLM.

``DebateSynthesis.revised_thesis`` reuses ``ThesisOutput`` from
``ai_hedge_fund.schemas.agents`` (imported, NOT redefined) so the downstream
signal node consumes the post-debate thesis without any schema translation.

Threat mitigations:
    T-05-01: Tampering -- ``min_length`` on every substantive list + ``ge/le``
             on every numeric + Literal on ``source_analyst`` prevent the LLM
             from emitting short, empty, or fabricated-source act outputs.
    T-05-02: Information disclosure -- N/A. Debate consumes only already-
             validated analyst evidence from state; no PII or secret surface
             is introduced by these schemas.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, model_validator

from ai_hedge_fund.schemas.agents import ThesisOutput

AnalystName = Literal["fundamental", "sentiment", "technical", "manager"]

NonEmptyStr = Annotated[str, StringConstraints(min_length=1)]
"""Element type for `list[str]` fields where empty strings are semantically
meaningless. `Field(min_length=N)` on a `list[str]` only constrains list
length, NOT element length -- an LLM can satisfy `min_length=2` with
`["", ""]`. Use `list[NonEmptyStr]` to reject that failure mode.
"""


class BullClaim(BaseModel):
    """One bull-side claim with a specific data citation.

    Each claim must cite the analyst whose evidence grounds it
    (``source_analyst``). This mirrors the ``source_tool`` pattern on
    ``ThesisPoint`` from Phase 4 and is the schema-level enforcement of
    DEBATE-01's "each claim cites its source analyst".
    """

    claim: str = Field(
        min_length=1,
        description="The investment argument",
    )
    evidence: str = Field(
        min_length=1,
        description="Specific data point supporting the claim (number, date, filing section)",
    )
    source_analyst: AnalystName = Field(
        description="Which analyst produced the evidence",
    )


class BullCase(BaseModel):
    """DEBATE-01: the positive investment case assembled by the Bull Advocate.

    Contains at least 3 ``BullClaim`` entries (``min_length=3``) plus a
    one-sentence headline. An empty or under-populated bull case raises
    ``ValidationError`` at ``agent.run()`` time (success criterion 3).
    """

    ticker: str = Field(description="Stock ticker symbol")
    claims: list[BullClaim] = Field(
        min_length=3,
        description="Bull claims with evidence citations (minimum 3)",
    )
    headline: str = Field(
        min_length=1,
        description="One-sentence bull headline",
    )


class BearClaim(BaseModel):
    """One bear-side claim; either counter-evidence or a direct rebuttal of
    a specific bull claim.

    ``addresses_bull_claim`` is optional -- when set, it should contain the
    verbatim (or near-verbatim) text of the bull claim being rebutted. When
    unset, the bear is offering independent counter-evidence.
    """

    claim: str = Field(min_length=1)
    evidence: str = Field(min_length=1)
    source_analyst: AnalystName
    addresses_bull_claim: str | None = Field(
        default=None,
        description=(
            "Verbatim or near-verbatim text of the bull claim this bear claim "
            "rebuts; None if the bear claim is independent counter-evidence."
        ),
    )


class BearCase(BaseModel):
    """DEBATE-02: the opposing case; MUST address at least 2 bull claims.

    ``addressed_bull_claims: list[str] = Field(min_length=2)`` is the schema-
    level enforcement of DEBATE-02 ("the Bear Advocate directly addresses and
    rebuts at least 2 specific bull claims"). Verbatim-ness is enforced by the
    Bear system prompt; the schema only enforces ``len >= 2`` (see
    05-RESEARCH.md assumption A3).
    """

    ticker: str
    claims: list[BearClaim] = Field(min_length=3)
    addressed_bull_claims: list[NonEmptyStr] = Field(
        min_length=2,
        description=(
            "Verbatim text of at least 2 bull claims that this bear case "
            "directly rebuts -- per DEBATE-02. Element type is NonEmptyStr "
            'so `["", ""]` is rejected (WR-02).'
        ),
    )
    headline: str = Field(min_length=1)

    @model_validator(mode="after")
    def each_addressed_claim_has_rebutter(self) -> BearCase:
        """WR-01: every `addressed_bull_claims` entry must be referenced by at
        least one ``BearClaim.addresses_bull_claim``.

        DEBATE-02's spirit ("bear directly addresses at least 2 specific bull
        claims") is not met if a bear can list two bull-claim strings in
        ``addressed_bull_claims`` while every ``BearClaim.addresses_bull_claim``
        is ``None``. Enforce the cross-link at validation time so ``retries=2``
        on the bear agent can self-correct an offending LLM output (T-05-05
        threat-model intent).
        """
        rebutters = {
            c.addresses_bull_claim for c in self.claims if c.addresses_bull_claim is not None
        }
        missing = [text for text in self.addressed_bull_claims if text not in rebutters]
        if missing:
            raise ValueError(
                "addressed_bull_claims must each be rebutted by at least one "
                "BearClaim.addresses_bull_claim; missing rebutters for: "
                f"{missing}"
            )
        return self


class RebuttalPoint(BaseModel):
    """One rebuttal argument targeting a specific opposing claim."""

    point: str = Field(min_length=1, description="The rebuttal argument")
    targets_claim: str = Field(
        min_length=1,
        description="Verbatim text of the opposing claim this rebuts",
    )
    source_analyst: AnalystName


class RebuttalAct(BaseModel):
    """DEBATE-03 Act 3: balanced bidirectional rebuttals.

    Both sides must produce at least 2 rebuttals so the act covers each side's
    strongest points -- matching the assumption A2 in 05-RESEARCH.md that a
    single node emits both directions.
    """

    ticker: str
    bull_rebuttals: list[RebuttalPoint] = Field(
        min_length=2,
        description="Bull-side rebuttals of bear points (minimum 2)",
    )
    bear_rebuttals: list[RebuttalPoint] = Field(
        min_length=2,
        description="Bear-side rebuttals of bull points (minimum 2)",
    )


class FinalArguments(BaseModel):
    """DEBATE-03 Act 4: each side's closing argument.

    ``bull_citation_count`` / ``bear_citation_count`` are LLM-produced integers
    recording how many distinct evidence citations each closing contains.
    Downstream analysis can sanity-check closings against this count.
    """

    ticker: str
    bull_closing: str = Field(
        min_length=1,
        description="Bull side's closing argument citing final evidence",
    )
    bear_closing: str = Field(
        min_length=1,
        description="Bear side's closing argument citing final evidence",
    )
    bull_citation_count: int = Field(
        ge=0,
        description="Number of distinct evidence citations in bull_closing",
    )
    bear_citation_count: int = Field(
        ge=0,
        description="Number of distinct evidence citations in bear_closing",
    )


class DebateSynthesis(BaseModel):
    """DEBATE-04 Act 5: revised thesis plus decomposed quality score.

    ``revised_thesis`` is a full ``ThesisOutput`` (imported, not redefined) --
    the downstream signal node consumes it without any translation.
    ``pre_debate_confidence`` is sourced from ``state["thesis"]["confidence"]``
    by ``debate_synthesis_node`` BEFORE the agent runs (not from the LLM), so
    DEBATE-04 success criterion 4 compares the original manager confidence
    against the post-debate number.
    ``quality_score`` is populated by ``compute_quality_score()`` in the
    node, not by the LLM -- CLAUDE.md tool-first rule.
    """

    ticker: str
    revised_thesis: ThesisOutput = Field(
        description="Post-debate thesis; may be identical to pre-debate or revised",
    )
    pre_debate_confidence: int = Field(
        ge=0,
        le=100,
        description=(
            "Manager's pre-debate confidence; sourced from state, not LLM. "
            "Overwritten by debate_synthesis_node after the agent runs."
        ),
    )
    post_debate_confidence: int = Field(
        ge=0,
        le=100,
        description="Confidence after the debate -- MUST be re-evaluated from scratch",
    )
    evidence_strength: int = Field(
        ge=0,
        le=100,
        description="LLM judgment: how strong is the evidence backing the thesis?",
    )
    logical_consistency: int = Field(
        ge=0,
        le=100,
        description="LLM judgment: how internally consistent is the debate?",
    )
    risk_coverage: int = Field(
        ge=0,
        le=100,
        description="LLM judgment: how well are risks identified and covered?",
    )
    quality_score: int = Field(
        ge=0,
        le=100,
        description=(
            "Computed (not LLM-generated) weighted mean of the three sub-scores. "
            "Populated by compute_quality_score() in debate_synthesis_node "
            "before writing to state."
        ),
    )
    synthesis_notes: str = Field(
        min_length=1,
        description="Rationale for revised_thesis changes and confidence delta",
    )

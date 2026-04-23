"""FinalSignalOutput -- investor-facing signal contract (Phase 8 SIG-01).

No nullable required fields. Assembled in Python by
``assemble_final_signal`` at the end of the pipeline; the LLM NEVER authors
this schema (tool-first invariant per CLAUDE.md).

Distinct from the Phase-5 ``SignalOutput`` in ``schemas/agents.py``
(``thesis_summary`` + ``direction`` + ``supporting_arguments`` -- the LLM
output from ``multi_agent_signal_node``). ``FinalSignalOutput`` wraps that
signal plus risk + memory + review audit metadata for the investor-facing
surface.

Threat mitigations (see ``08-01-PLAN.md::threat_model``):
    T-08-11: Schema subversion via Optional required field -- every field
             declared below is required (no Optional union on any required
             field); ``extra="forbid"`` + ``frozen=True``.
    T-08-12: LLM-authored risk_score -- this schema accepts an ``int`` in
             [0, 100]; the assembler / derive helper populate it
             deterministically from the ``RiskAssessment``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FinalSignalOutput(BaseModel):
    """SIG-01 contract: direction, conviction, thesis_summary, risk_score,
    thesis_link all populated. Plus audit metadata (policy_sha,
    review_policy_sha, episodic_id) and review_status.

    Frozen + ``extra="forbid"``. Any field omission raises
    ``ValidationError``; no field may be ``None``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    # Signal identity
    ticker: str = Field(
        min_length=1,
        max_length=10,
        description="Stock ticker symbol",
    )
    as_of_date: str = Field(
        min_length=10,
        max_length=10,
        description="ISO YYYY-MM-DD; analysis cutoff date",
    )

    # SIG-01 required fields (no nulls)
    direction: Literal["long", "short", "neutral"] = Field(
        description="Trade direction (no nullable alternative)",
    )
    conviction: int = Field(
        ge=0,
        le=100,
        description="Integer 0-100 sourced from ThesisOutput.confidence",
    )
    thesis_summary: str = Field(
        min_length=1,
        max_length=2000,
        description="One-paragraph (<=2000 char) thesis summary",
    )
    risk_score: int = Field(
        ge=0,
        le=100,
        description="Derived risk score; 0=no risk, 100=maximum (VETOED)",
    )
    thesis_link: str = Field(
        min_length=1,
        description="Reference to the stored thesis (episodic://<id> URI)",
    )

    # Audit metadata (required, not nullable)
    policy_sha: str = Field(
        min_length=64,
        max_length=64,
        description="Risk policy SHA-256 at decision time (Phase-6 fingerprint)",
    )
    review_policy_sha: str = Field(
        min_length=64,
        max_length=64,
        description="Review policy SHA-256 at decision time (Phase-8 fingerprint)",
    )
    episodic_id: int = Field(
        ge=1,
        description="Primary key of the stored analysis row in episodic_memory",
    )
    review_status: Literal["NOT_REQUIRED", "APPROVED", "REJECTED"] = Field(
        description=(
            "Human-review gate outcome. NOT_REQUIRED = conviction below "
            "threshold; APPROVED/REJECTED = reviewer decision (SIG-03)."
        ),
    )

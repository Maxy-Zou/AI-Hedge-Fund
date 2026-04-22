"""Belief + CritiqueEvent Pydantic schemas (MEM-02, MEM-04).

Every belief YAML under ``beliefs/`` validates against :class:`Belief`.
Unknown keys raise ``ValidationError`` (Pitfall 4 -- typo ``confidance``
does NOT silently overwrite ``confidence``). :class:`CritiqueEvent` is
frozen (like :class:`ai_hedge_fund.schemas.risk.Violation`) because an
event, once appended, is history and must not mutate in place.

:class:`Belief` is deliberately NOT frozen: the writer in
``ai_hedge_fund.memory.beliefs.write_belief`` produces a new raw-dict for
atomic file replacement; Pydantic immutability would force unnecessary
re-validation churn on each patch. The human-edit contract (MEM-03) is
enforced by the writer, not by pydantic.

Threat mitigations:
    T-07-14 (DoS via huge YAML payload): ``thesis`` is bounded to
            10_000 chars and ``CritiqueEvent.rationale`` to 2_000 chars
            (Shared Pattern F). Oversize YAML documents are rejected at
            validation time before any downstream processing.
    Pitfall 4 (typo-masked overwrite): ``ConfigDict(extra="forbid")``
            ensures a stray ``confidance: 72`` cannot silently replace
            ``confidence``; the schema raises ``ValidationError``.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class CritiqueEvent(BaseModel):
    """One immutable entry in a belief's ``critique_history``.

    Frozen so an event, once appended, cannot be edited in place. Mirrors
    the :class:`ai_hedge_fund.schemas.risk.Violation` immutability contract
    for audit records.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    as_of_date: date = Field(
        description="Business date of the outcome this critique evaluates",
    )
    outcome_pct: float = Field(
        description="Realised outcome in percent (e.g., 4.2 = +4.2%)",
    )
    old_confidence: int = Field(
        ge=0,
        le=100,
        description="Confidence before the critique (0..100)",
    )
    new_confidence: int = Field(
        ge=0,
        le=100,
        description="Confidence after the critique (0..100)",
    )
    rationale: str = Field(
        min_length=1,
        max_length=2000,
        description="Human-readable explanation (max 2000 chars; DoS guard)",
    )
    source: str = Field(
        pattern=r"^(self_critique|human)$",
        description="Either 'self_critique' (machine) or 'human' (operator)",
    )


class Belief(BaseModel):
    """A ticker- or sector-level investment belief stored as YAML.

    Human-readable (CLAUDE.md non-negotiable). Unknown YAML keys raise
    ``ValidationError`` at load time -- the only way a typo survives is
    if the field is a legitimate schema field, which it by definition
    isn't.

    NOT frozen because the writer
    (``ai_hedge_fund.memory.beliefs.write_belief``) rewrites the YAML
    via the round-trip raw object; the Pydantic model is a validation
    projection, not the persisted state.
    """

    model_config = ConfigDict(extra="forbid")  # NOT frozen -- writer replaces

    ticker: str = Field(
        min_length=1,
        max_length=10,
        description="Ticker symbol or sector key this belief applies to",
    )
    sector: str = Field(
        description="GICS sector name for grouping and sector-level recall",
    )
    version: int = Field(
        ge=1,
        description="Monotone-increasing write counter (starts at 1)",
    )
    thesis: str = Field(
        min_length=1,
        max_length=10_000,
        description="Plain-language investment thesis (max 10k chars; DoS guard)",
    )
    confidence: int = Field(
        ge=0,
        le=100,
        description="Confidence in the thesis on a 0..100 scale",
    )
    human_edited: bool = Field(
        default=False,
        description=(
            "Global human-override flag. When true, the writer skips thesis "
            "and confidence patches (MEM-03). Machines NEVER set this."
        ),
    )
    edited_at: date | None = Field(
        default=None,
        description="Date the human last edited this belief (optional)",
    )
    critique_history: list[CritiqueEvent] = Field(
        default_factory=list,
        description="Append-only history of critique events",
    )
    field_locks: dict[str, bool] = Field(
        default_factory=dict,
        description=(
            "Per-field human overrides. ``field_locks[f] is True`` vetoes "
            "a machine write to ``f`` (MEM-03 field-level lock)."
        ),
    )

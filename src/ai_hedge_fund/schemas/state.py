"""LangGraph state schemas for the research pipeline.

PipelineState is a TypedDict used as the state type for LangGraph
StateGraph. It carries data through the pipeline nodes (extraction,
analysis, debate, synthesis). Required fields must be set at graph
invocation; optional fields are populated by pipeline nodes.

ResearchPipelineState is the Phase-3 successor that drives the
research -> signal flow: the research agent produces a thesis from
tool calls and the signal agent converts that thesis into a trade
signal. It intentionally does NOT carry raw_text -- the research
agent calls data tools directly rather than being handed a filing blob.

MultiAgentPipelineState (Phase-4) carries the fan-out/fan-in state for
the specialist analysts + research manager pipeline. It uses an
``operator.add`` reducer on ``analyst_reports`` so each parallel analyst
can append its report without overwriting peers -- LangGraph merges the
lists returned from each node.

DebatePipelineState (Phase-5) extends MultiAgentPipelineState with five
single-writer debate-act fields: ``bull_case``, ``bear_case``,
``rebuttal``, ``final_arguments``, ``debate_synthesis``. Each is written
exactly once by its owning node with overwrite semantics -- NO ``operator.add``
reducer so silent accumulation is impossible. The ``thesis`` field is written
by manager_node and OVERWRITTEN by debate_synthesis_node with the
post-debate ``revised_thesis`` so the downstream signal_node consumes the
debated version without knowing the debate happened.
"""

from __future__ import annotations

import operator
from typing import Annotated, Required, TypedDict

from pydantic import BaseModel, ConfigDict, Field


class CandidateMetadata(BaseModel):
    """Sector + instrument type injected into ``DebatePipelineState``.

    ``ThesisOutput`` (Phase-3 immutable schema) carries ``ticker``,
    ``bull_case``, ``bear_case``, ``confidence``, and ``risk_factors``; it
    does NOT carry a ``sector`` or ``instrument_type`` field. Phase 6's
    ``risk_manager_node`` needs both to run the exclusion + sector-
    concentration checks, so upstream callers (pipeline entry point or
    research manager) set this explicit state key BEFORE the risk node
    executes.

    When the candidate_metadata field is absent or None, the node treats
    ``sector`` as ``"Unknown"`` and ``instrument_type`` as ``"equity"``.
    "Unknown" never matches ``excluded_sectors`` and never matches a
    sector-concentration threshold, so the safe default degrades to
    position-size / correlation / drawdown enforcement only.
    """

    model_config = ConfigDict(frozen=True)

    sector: str = Field(
        min_length=1,
        description="Sector the candidate belongs to (e.g., 'Technology').",
    )
    instrument_type: str = Field(
        default="equity",
        description=(
            "Instrument type for exclusion checks. Default is 'equity'; "
            "pass 'SPAC' / 'OTC' / 'ETF' when applicable."
        ),
    )


class PipelineState(TypedDict, total=False):
    """State flowing through the legacy LangGraph research pipeline.

    Required fields:
        ticker: Stock ticker symbol being analyzed.
        raw_text: Raw filing or document text for analysis.

    Optional fields (populated by pipeline nodes):
        extraction: Extracted data from the filing (dict from ExtractionOutput.model_dump()).
        analysis: Analysis results (dict from AnalysisOutput.model_dump()).
        error: Error message if any pipeline step failed.
    """

    ticker: Required[str]
    raw_text: Required[str]
    extraction: dict | None
    analysis: dict | None
    error: str | None


class ResearchPipelineState(TypedDict, total=False):
    """State flowing through the Phase-3 research pipeline (research -> signal).

    Required fields must be provided at graph invocation; optional fields
    are populated by pipeline nodes. ``total=False`` allows partial dicts
    so each node can return a small update without having to forward every
    field it doesn't change.

    Required fields:
        ticker: Stock ticker symbol being analyzed.
        as_of_date: Temporal cutoff as an ISO-format date string (e.g.
            ``"2024-01-01"``). Kept as a string (not ``datetime.date``)
            so the state is JSON-serialisable for LangGraph checkpoints.

    Optional fields (populated by pipeline nodes):
        thesis: ThesisOutput.model_dump() produced by ``research_node``.
        signal: SignalOutput.model_dump() produced by ``signal_node``.
        error: Error message if any pipeline step failed; downstream nodes
            should skip when this is set.
    """

    ticker: Required[str]
    as_of_date: Required[str]
    thesis: dict | None
    signal: dict | None
    error: str | None


class MultiAgentPipelineState(TypedDict, total=False):
    """State flowing through the Phase-4 multi-agent pipeline.

    Uses ``Annotated[list, operator.add]`` on ``analyst_reports`` so each
    parallel analyst node can append its single-element list without
    overwriting peers -- LangGraph concatenates the lists returned from
    all parallel nodes before the manager node executes.

    Required fields:
        ticker: Stock ticker symbol being analyzed.
        as_of_date: Temporal cutoff as an ISO-format date string (e.g.
            ``"2024-01-01"``). Kept as a string so the state is
            JSON-serialisable for LangGraph checkpoints.

    Optional fields (populated by pipeline nodes):
        analyst_reports: Accumulated analyst outputs appended via the
            ``operator.add`` reducer. Each entry is a dict with keys
            ``analyst`` (Literal["fundamental","sentiment","technical"]),
            ``analysis`` (dict), ``tokens_used`` (int), and optionally
            ``error`` (str).
        thesis: ``ThesisOutput.model_dump()`` produced by ``manager_node``.
        signal: ``SignalOutput.model_dump()`` produced by the
            multi-agent signal node.
        error: Error message if a post-fan-in node (manager/signal)
            failed; analyst-level errors live inside ``analyst_reports``.
    """

    ticker: Required[str]
    as_of_date: Required[str]
    analyst_reports: Annotated[list[dict], operator.add]
    thesis: dict | None
    signal: dict | None
    error: str | None


class DebatePipelineState(TypedDict, total=False):
    """State flowing through the Phase-5 debate pipeline.

    Extends MultiAgentPipelineState by adding five single-writer debate-act
    fields. TypedDict multiple-inheritance with Annotated reducer fields is
    fragile, so the MultiAgentPipelineState fields are duplicated here
    rather than inherited (per RESEARCH.md Pattern 5).

    Required fields:
        ticker: Stock ticker symbol being analyzed.
        as_of_date: Temporal cutoff as an ISO-format date string.

    Optional fields:
        analyst_reports: Accumulated analyst outputs via ``operator.add``
            reducer (fan-in from parallel analysts -- same as Phase 4).
        thesis: ``ThesisOutput.model_dump()`` -- written by manager_node,
            OVERWRITTEN by debate_synthesis_node with the revised thesis.
        bull_case: ``BullCase.model_dump()`` -- single-writer bull_node.
        bear_case: ``BearCase.model_dump()`` -- single-writer bear_node.
        rebuttal: ``RebuttalAct.model_dump()`` -- single-writer rebuttal_node.
        final_arguments: ``FinalArguments.model_dump()`` -- single-writer
            final_arguments_node.
        debate_synthesis: ``DebateSynthesis.model_dump()`` -- single-writer
            debate_synthesis_node.
        signal: ``SignalOutput.model_dump()`` -- written by signal adapter
            node (debate_signal_node in Plan 05-03, reuses signal_agent).
        risk_assessment: Optional ``RiskAssessment.model_dump()`` written by
            Phase-6 ``risk_manager_node``. On VETOED the conditional router
            ``route_after_risk`` ends the graph without calling ``signal``.
        candidate_metadata: Optional ``CandidateMetadata.model_dump()``
            -- sector + instrument_type injected by the pipeline caller
            BEFORE the risk node runs. NOT extracted from ``ThesisOutput``,
            which is a Phase-3 immutable schema that carries no sector
            field. If absent, ``risk_manager_node`` treats sector as
            ``"Unknown"`` (safe default -- never matches excluded_sectors
            and never matches a sector-concentration threshold).
        error: Propagates upstream error; debate nodes short-circuit when set.
    """

    ticker: Required[str]
    as_of_date: Required[str]
    analyst_reports: Annotated[list[dict], operator.add]
    thesis: dict | None
    bull_case: dict | None
    bear_case: dict | None
    rebuttal: dict | None
    final_arguments: dict | None
    debate_synthesis: dict | None
    signal: dict | None
    risk_assessment: dict | None
    candidate_metadata: dict | None
    error: str | None

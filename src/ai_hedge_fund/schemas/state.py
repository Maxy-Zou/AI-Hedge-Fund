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
"""

from __future__ import annotations

import operator
from typing import Annotated, Required, TypedDict


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

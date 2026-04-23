"""Phase-8 markdown rendering for signals + review requests.

No templating library -- stdlib f-strings only. Plain-text friendly (no
emoji) to match CLAUDE.md rendering-consistency preference. The CLI
prints ``format_review_request_md(...)`` to stdout before calling
``input()`` for the human reviewer's decision.

Threat mitigations:
    T-08-14 (accept): ``policy_sha`` / ``review_policy_sha`` are truncated
             to their first 12 chars + ``...`` in the rendered output.
             The full SHA remains in the DB for audit.
"""

from __future__ import annotations

from typing import Any

_DIR_LABEL = {
    "long": "LONG (up)",
    "short": "SHORT (down)",
    "neutral": "NEUTRAL",
}


def _short_sha(sha: str | None) -> str:
    """Truncate a 64-char SHA to its first 12 chars + ellipsis (T-08-14)."""
    if not sha:
        return "-"
    return f"{sha[:12]}..."


def _fmt_value(value: Any) -> str:
    """Render a field value for markdown display.

    Maps None -> "-", empty list -> "(none)", empty dict -> "(empty)",
    else ``str(value)``.
    """
    if value is None:
        return "-"
    if isinstance(value, list) and not value:
        return "(none)"
    if isinstance(value, dict) and not value:
        return "(empty)"
    return str(value)


def _fmt_risk(risk: Any) -> str:
    """Render a risk_assessment dict for the reviewer packet (T-08-14).

    Replaces ``str(dict)`` rendering so the 64-char ``policy_sha`` is
    truncated to its first 12 chars + ellipsis -- matching the
    ``format_signal_md`` Audit section. Unknown keys present on the dict
    are rendered verbatim (non-SHA fields are already short).
    """
    if risk is None:
        return "-"
    if not isinstance(risk, dict):
        return str(risk)
    if not risk:
        return "(empty)"
    lines = [
        f"- status: {risk.get('status', '-')}",
        f"- constraint_violated: {risk.get('constraint_violated', '-')}",
        f"- rationale: {risk.get('rationale', '-')}",
        f"- policy_sha: {_short_sha(risk.get('policy_sha'))}",
    ]
    # Preserve additional fields (observed/limit/etc) without leaking SHAs.
    rendered_keys = {"status", "constraint_violated", "rationale", "policy_sha"}
    for key, value in risk.items():
        if key in rendered_keys:
            continue
        lines.append(f"- {key}: {_fmt_value(value)}")
    return "\n".join(lines)


def _fmt_hit(hit: Any) -> str:
    """Render a single episodic_hits / beliefs_consulted entry (T-08-14).

    For dict entries, truncates any field whose key ends in ``_sha`` so the
    reviewer packet never displays a full 64-char policy hash inline. For
    scalar entries, falls through to ``str(hit)``.
    """
    if not isinstance(hit, dict):
        return str(hit)
    parts: list[str] = []
    for key, value in hit.items():
        if isinstance(value, str) and key.endswith("_sha"):
            parts.append(f"{key}={_short_sha(value)}")
        else:
            parts.append(f"{key}={value}")
    return "{" + ", ".join(parts) + "}"


def format_signal_md(final_signal: dict) -> str:
    """Render a FinalSignalOutput (as dict) into compact markdown (~25-30 lines).

    Args:
        final_signal: Dict-shaped ``FinalSignalOutput``
            (``.model_dump(mode='json')``).

    Returns:
        Markdown string with a ``# Signal: {ticker}`` header, an at-a-glance
        bullet list, an Audit section with truncated SHAs, and a Thesis
        Summary section.
    """
    direction = final_signal.get("direction", "")
    direction_label = _DIR_LABEL.get(direction, direction or "-")
    lines: list[str] = [
        f"# Signal: {final_signal.get('ticker', '-')}",
        "",
        f"- as_of_date: {final_signal.get('as_of_date', '-')}",
        f"- direction: {direction_label}",
        f"- conviction: {final_signal.get('conviction', '-')}/100",
        f"- risk_score: {final_signal.get('risk_score', '-')}/100",
        f"- review_status: {final_signal.get('review_status', '-')}",
        f"- thesis_link: {final_signal.get('thesis_link', '-')}",
        f"- episodic_id: {final_signal.get('episodic_id', '-')}",
        "",
        "## Audit",
        "",
        f"- risk_policy_sha: {_short_sha(final_signal.get('policy_sha'))}",
        f"- review_policy_sha: {_short_sha(final_signal.get('review_policy_sha'))}",
        "",
        "## Thesis Summary",
        "",
        _fmt_value(final_signal.get("thesis_summary")),
    ]
    return "\n".join(lines)


def format_review_request_md(review_request: dict) -> str:
    """Render a review_request dict (packaged by human_review_node) as markdown.

    Shown to the reviewer on stdout before the ``input()`` prompt. The
    final section ends with an Action Required block prompting the
    reviewer to approve (y) or reject (n).

    Args:
        review_request: dict with keys ticker, as_of_date, signal, thesis,
            debate, risk_assessment, episodic_hits, beliefs_consulted.

    Returns:
        Markdown string suitable for stdout rendering.
    """
    ticker = review_request.get("ticker", "-")
    as_of = review_request.get("as_of_date", "-")
    signal = review_request.get("signal") or {}
    thesis = review_request.get("thesis") or {}
    debate = review_request.get("debate") or {}
    risk = review_request.get("risk_assessment")
    hits = review_request.get("episodic_hits") or []
    beliefs = review_request.get("beliefs_consulted") or []

    lines: list[str] = [
        f"# Review Requested: {ticker} ({as_of})",
        "",
        "## Proposed Signal",
        "",
        f"- direction: {signal.get('direction', '-')}",
        f"- conviction: {signal.get('conviction', '-')}",
        f"- thesis_summary: {_fmt_value(signal.get('thesis_summary'))}",
        "",
        "## Thesis",
        "",
        f"- confidence: {thesis.get('confidence', '-')}",
        f"- bull_case: {_fmt_value(thesis.get('bull_case'))}",
        f"- bear_case: {_fmt_value(thesis.get('bear_case'))}",
        "",
        "## Debate",
        "",
        "### Bull",
        _fmt_value(debate.get("bull_case")),
        "",
        "### Bear",
        _fmt_value(debate.get("bear_case")),
        "",
        "### Rebuttal",
        _fmt_value(debate.get("rebuttal")),
        "",
        "### Final Arguments",
        _fmt_value(debate.get("final_arguments")),
        "",
        "### Synthesis",
        _fmt_value(debate.get("synthesis")),
        "",
        "## Risk Assessment",
        "",
        _fmt_risk(risk),
        "",
        f"## Episodic Hits ({len(hits)})",
        "",
        _fmt_value(hits) if not hits else "\n".join(f"- {_fmt_hit(h)}" for h in hits),
        "",
        f"## Beliefs Consulted ({len(beliefs)})",
        "",
        (
            _fmt_value(beliefs)
            if not beliefs
            else "\n".join(f"- {_fmt_hit(b)}" for b in beliefs)
        ),
        "",
        "---",
        "",
        "## Action Required",
        "",
        "Approve (y) or reject (n)? A note is also required.",
    ]
    return "\n".join(lines)

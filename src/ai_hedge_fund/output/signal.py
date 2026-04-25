"""Phase-8 signal assembly (SIG-01): pure-Python, tool-first.

``assemble_final_signal`` composes ``FinalSignalOutput`` from authoritative
pipeline state: the Phase-5 signal dict (``state['signal']``), the Phase-5
post-debate thesis dict (``state['thesis']``), and the Phase-6
``risk_assessment`` dict (``state['risk_assessment']``). NO LLM invocation
-- CLAUDE.md tool-first invariant; the LLM never authors these fields.

``derive_risk_score`` is a deterministic function of the risk assessment.
Rules (per 08-RESEARCH.md A9 resolution):
    * VETOED -> 100
    * APPROVED -> ``round(utilization * 100)`` (clamped to [0, 100])
    * any other / unknown status -> 50 (middle-ground; anomalous)

Threat mitigations:
    T-08-12: LLM-authored risk_score -- ``derive_risk_score`` has zero LLM
             invocations and is deterministic; no PydanticAI Agent calls
             anywhere in this subpackage. ``utilization`` is sourced from
             :class:`RiskAssessment` (which is Python-authored) so the
             score never depends on free-form LLM output.
"""

from __future__ import annotations

from typing import Literal

from ai_hedge_fund.schemas.signal_output import FinalSignalOutput


def derive_risk_score(risk_assessment: dict) -> int:
    """Map a ``RiskAssessment`` dict into a 0-100 integer risk score.

    Deterministic; zero LLM. Rules:
        * ``status == "VETOED"`` -> 100
        * ``status == "APPROVED"`` -> ``int(round(utilization * 100))``
          clamped to [0, 100]. The ``utilization`` field is the
          deterministic max-ratio across all checks (see
          :class:`ai_hedge_fund.schemas.risk.RiskAssessment` and
          ``risk_manager_node`` in ``graph/nodes.py``).
        * Legacy fallback: when ``utilization`` is missing on the
          assessment dict (older Phase-6 records pre-dating the schema
          field), recompute from ``observed`` / ``limit`` to keep
          backwards compatibility with replay tests. Missing observed +
          limit -> 0; unrecognised status -> 50.

    Args:
        risk_assessment: A dict-shaped ``RiskAssessment`` (from
            ``state['risk_assessment']``).

    Returns:
        Integer risk score in [0, 100].
    """
    status = risk_assessment.get("status")
    if status == "VETOED":
        return 100
    if status != "APPROVED":
        # Unknown / anomalous status -- middle-ground fallback.
        return 50

    if "utilization" in risk_assessment and risk_assessment["utilization"] is not None:
        utilization = float(risk_assessment["utilization"])
        utilization = max(0.0, min(1.0, utilization))
        return int(round(utilization * 100))

    # Legacy / pre-utilization assessments fall back to observed/limit.
    observed_raw = risk_assessment.get("observed")
    limit_raw = risk_assessment.get("limit")
    if observed_raw is None or limit_raw is None:
        return 0
    observed = float(observed_raw)
    limit = float(limit_raw)
    if limit <= 0:
        limit = 1e-9
    ratio = max(0.0, min(1.0, observed / limit))
    return int(round(ratio * 100))


def assemble_final_signal(
    state: dict,
    *,
    review_policy_sha: str,
    episodic_id: int,
    review_status: Literal["NOT_REQUIRED", "APPROVED", "REJECTED"] = "NOT_REQUIRED",
) -> FinalSignalOutput:
    """Assemble a ``FinalSignalOutput`` from authoritative pipeline state.

    Pure function, no I/O, no LLM calls. Raises ``ValidationError`` if
    state is missing any field required by ``FinalSignalOutput`` -- fail
    loudly so the SIG-01 contract holds.

    Args:
        state: DebatePipelineState dict carrying ticker, as_of_date, signal,
            thesis, risk_assessment.
        review_policy_sha: 64-char SHA of the ReviewPolicy used for this run.
        episodic_id: Primary key of the analysis row in episodic_memory.
        review_status: NOT_REQUIRED (below threshold) / APPROVED / REJECTED.

    Returns:
        FinalSignalOutput -- frozen, validated, ready for serialization.
    """
    signal = state["signal"]
    thesis = state["thesis"]
    risk = state.get("risk_assessment") or {}

    return FinalSignalOutput(
        ticker=state["ticker"],
        as_of_date=state["as_of_date"],
        direction=signal["direction"],
        conviction=int(thesis["confidence"]),
        thesis_summary=signal["thesis_summary"],
        risk_score=derive_risk_score(risk),
        thesis_link=f"episodic://{episodic_id}",
        # Intentional: empty policy_sha will raise ValidationError (fail-loud)
        policy_sha=risk.get("policy_sha") or "",
        review_policy_sha=review_policy_sha,
        episodic_id=episodic_id,
        review_status=review_status,
    )

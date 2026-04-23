"""Phase-8 Wave-0 smoke: structlog audit coverage proves A7 assumption.

If this test goes red, a subsequent refactor dropped an audit field; Plan 08-05
gap-fill discovery happens here, not in a live compliance review.
"""

from __future__ import annotations

import asyncio

import pytest

from scripts.verify_langfuse_spans import (
    REQUIRED_FIELDS_PER_AGENT,
    audit_coverage,
    run_stubbed_pipeline,
)


@pytest.mark.slow  # takes ~2s -- composed pipeline under TestModel (run twice)
def test_phase7_composed_pipeline_emits_sig04_fields_for_every_agent() -> None:
    events = asyncio.run(run_stubbed_pipeline())
    gaps = audit_coverage(events)
    if gaps:
        gap_msg = "\n".join(f"{k}: {sorted(v)}" for k, v in gaps.items())
        pytest.fail(f"SIG-04 audit gaps (A7 invalid):\n{gap_msg}")
    emitted_names = {e.get("event") for e in events if e.get("event") in REQUIRED_FIELDS_PER_AGENT}
    assert set(REQUIRED_FIELDS_PER_AGENT.keys()).issubset(emitted_names)

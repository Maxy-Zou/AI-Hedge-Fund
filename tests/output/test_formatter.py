"""Plan 08-01 Task 3: formatter tests.

Verifies markdown rendering of FinalSignalOutput (compact signal summary)
and the review_request packet (full context shown to the human reviewer
before input() prompt). T-08-14: SHAs are truncated for readability.
"""

from __future__ import annotations

from ai_hedge_fund.output.formatter import format_review_request_md, format_signal_md

SIGNAL = {
    "ticker": "AAPL",
    "as_of_date": "2026-04-20",
    "direction": "long",
    "conviction": 85,
    "risk_score": 30,
    "thesis_summary": "Bullish on iPhone cycle.",
    "thesis_link": "episodic://42",
    "policy_sha": "a" * 64,
    "review_policy_sha": "b" * 64,
    "episodic_id": 42,
    "review_status": "APPROVED",
}


def test_signal_md_contains_all_fields() -> None:
    """Test 1: output contains ticker, date, conviction, risk, link, status, sha-prefix."""
    out = format_signal_md(SIGNAL)
    for needle in (
        "AAPL",
        "2026-04-20",
        "85",
        "30",
        "episodic://42",
        "APPROVED",
        "aaaaaaaaaaaa",  # short SHA prefix
    ):
        assert needle in out, f"missing: {needle}"


def test_signal_md_header_structure() -> None:
    """Test 2: starts with `# Signal: AAPL`; has >= 5 bullet rows."""
    out = format_signal_md(SIGNAL)
    assert out.startswith("# Signal: AAPL")
    assert out.count("\n- ") >= 5


def test_signal_md_is_compact() -> None:
    """Test 3: output is <= 35 lines (~30-line spec)."""
    assert len(format_signal_md(SIGNAL).splitlines()) <= 35


def test_signal_md_direction_labels() -> None:
    """Test 4: long/short/neutral each render a recognizable label."""
    assert "LONG" in format_signal_md({**SIGNAL, "direction": "long"})
    assert "SHORT" in format_signal_md({**SIGNAL, "direction": "short"})
    assert "NEUTRAL" in format_signal_md({**SIGNAL, "direction": "neutral"})


def test_signal_md_truncates_shas() -> None:
    """Test 5: T-08-14 -- full 64-char SHA is NOT rendered; truncated form IS."""
    out = format_signal_md(SIGNAL)
    assert "a" * 64 not in out  # full risk SHA not rendered
    assert "b" * 64 not in out  # full review SHA not rendered
    assert "aaaaaaaaaaaa..." in out  # truncated form rendered
    assert "bbbbbbbbbbbb..." in out


REVIEW_REQUEST = {
    "ticker": "AAPL",
    "as_of_date": "2026-04-20",
    "signal": {"direction": "long", "conviction": 85, "thesis_summary": "Bullish."},
    "thesis": {"confidence": 85, "bull_case": "strong", "bear_case": "weak"},
    "debate": {
        "bull_case": "bull cites 10-K",
        "bear_case": "bear cites supply risk",
        "rebuttal": "bull rebuts",
        "final_arguments": "both close",
        "synthesis": "net bullish",
    },
    "risk_assessment": {"status": "APPROVED", "observed": 4.0, "limit": 8.0},
    "episodic_hits": [],
    "beliefs_consulted": [],
}


def test_review_request_md_renders_all_top_level_keys() -> None:
    """Test 6: output renders ticker, date, and every top-level section."""
    out = format_review_request_md(REVIEW_REQUEST)
    for needle in (
        "AAPL",
        "2026-04-20",
        "Proposed Signal",
        "Thesis",
        "Debate",
        "Risk Assessment",
        "Episodic Hits",
        "Beliefs Consulted",
    ):
        assert needle in out, f"missing: {needle}"


def test_review_request_md_renders_debate_subsections() -> None:
    """Test 7: each of the 5 debate acts gets its own sub-heading."""
    out = format_review_request_md(REVIEW_REQUEST)
    for needle in (
        "### Bull",
        "### Bear",
        "### Rebuttal",
        "### Final Arguments",
        "### Synthesis",
    ):
        assert needle in out, f"missing: {needle}"


def test_review_request_md_empty_lists_show_none() -> None:
    """Test 8: empty episodic_hits/beliefs_consulted render as '(none)'."""
    out = format_review_request_md(REVIEW_REQUEST)
    assert "(none)" in out


def test_review_request_md_none_values_show_dash() -> None:
    """Test 9: None values render as '-' (not the string 'None')."""
    out = format_review_request_md({**REVIEW_REQUEST, "risk_assessment": None})
    # The placeholder "-" must appear under the Risk Assessment heading.
    # The rendered value appears on its own line between blank lines.
    assert "\n-\n" in out or out.strip().endswith("-")
    # And the literal string "None" must not appear as the risk-assessment value
    # (it may appear in unrelated sections).
    risk_section = out.split("## Risk Assessment")[1].split("## ")[0]
    assert "None" not in risk_section


def test_review_request_md_ends_with_action_prompt() -> None:
    """Test 10: final section prompts the reviewer to approve or reject."""
    out = format_review_request_md(REVIEW_REQUEST)
    assert "Approve" in out and "reject" in out


def test_review_request_md_populated_hits_and_beliefs() -> None:
    """Smoke: non-empty lists render as bullet lists, not '(none)'."""
    req = {
        **REVIEW_REQUEST,
        "episodic_hits": ["hit-1", "hit-2"],
        "beliefs_consulted": ["belief-a"],
    }
    out = format_review_request_md(req)
    assert "- hit-1" in out
    assert "- hit-2" in out
    assert "- belief-a" in out

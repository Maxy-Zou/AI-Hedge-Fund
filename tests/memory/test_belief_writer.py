"""Tests for the MEM-03 belief-writer chokepoint.

Covers the full contract of ``write_belief``: comment preservation
(MEM-02 cornerstone), human-edit skip (MEM-03 global flag), field-level
lock skip (MEM-03 per-field), override-meta blacklist (never-clear-human-
flag invariant), atomic tmp+rename crash safety, path-traversal guard
(Pitfall 9), and version monotonicity.

All writes go through :func:`write_belief` — no other codepath is
permitted to touch a belief YAML. Nothing in this test file edits a
belief file directly except the seed comparisons that read original text.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

from ai_hedge_fund.memory.beliefs import (
    belief_path_for_ticker,
    load_belief,
    write_belief,
)
from ai_hedge_fund.schemas.memory import Belief


# --------------------------------------------------------------------------
# Test 1: comment preservation (THE MEM-02 contract)
# --------------------------------------------------------------------------


def test_comment_preserved_after_write(beliefs_tmp_dir: Path) -> None:
    """Round-trip preserves inline `# flagged` comment (MEM-03 cornerstone)."""
    path = beliefs_tmp_dir / "tickers" / "AAPL.yaml"
    original_text = path.read_text()
    assert "# flagged" in original_text

    belief, raw = load_belief(path)
    assert belief.human_edited is False
    assert belief.confidence == 72

    outcome = write_belief(path, raw, patches={"confidence": 75})
    assert outcome["applied"] == ["confidence"]
    assert outcome["skipped"] == {}

    new_text = path.read_text()
    assert "# flagged" in new_text  # MEM-03 contract

    # Re-load to confirm confidence and version update
    fresh_belief, _ = load_belief(path)
    assert fresh_belief.confidence == 75
    assert fresh_belief.version == 4  # incremented from 3


# --------------------------------------------------------------------------
# Test 2: MEM-03 human_edited global flag blocks thesis + confidence writes
# --------------------------------------------------------------------------


def test_human_edited_blocks_machine_write(beliefs_tmp_dir: Path) -> None:
    """`human_edited=true` vetoes thesis + confidence patches; version unchanged."""
    path = beliefs_tmp_dir / "tickers" / "AAPL_human.yaml"
    belief, raw = load_belief(path)
    assert belief.human_edited is True
    assert belief.confidence == 20
    original_version = belief.version

    outcome = write_belief(
        path,
        raw,
        patches={"confidence": 99, "thesis": "machine rewrite"},
    )
    assert outcome["applied"] == []
    assert outcome["skipped"] == {
        "confidence": "human_edited_global_flag_set",
        "thesis": "human_edited_global_flag_set",
    }

    fresh_belief, _ = load_belief(path)
    assert fresh_belief.confidence == 20
    assert "I disagree with the machine view" in fresh_belief.thesis
    assert fresh_belief.version == original_version  # NO bump when nothing applied


# --------------------------------------------------------------------------
# Test 3: MEM-03 per-field lock skips only the locked field
# --------------------------------------------------------------------------


def test_field_lock_blocks_targeted_field(beliefs_tmp_dir: Path) -> None:
    """`field_locks.confidence=true` skips confidence, allows others."""
    path = beliefs_tmp_dir / "tickers" / "AAPL_locked.yaml"
    belief, raw = load_belief(path)
    assert belief.human_edited is False
    assert belief.field_locks["confidence"] is True
    original_version = belief.version

    new_event = {
        "as_of_date": "2026-04-20",
        "outcome_pct": 1.5,
        "old_confidence": 55,
        "new_confidence": 55,
        "rationale": "skip test",
        "source": "self_critique",
    }
    outcome = write_belief(
        path,
        raw,
        patches={"confidence": 80, "critique_history": [new_event]},
    )
    assert outcome["applied"] == ["critique_history"]
    assert outcome["skipped"] == {"confidence": "field_locked_by_human"}

    fresh_belief, _ = load_belief(path)
    assert fresh_belief.confidence == 55  # unchanged (locked)
    assert len(fresh_belief.critique_history) == 1
    assert fresh_belief.version == original_version + 1


# --------------------------------------------------------------------------
# Test 4: writer never touches override-meta keys
# --------------------------------------------------------------------------


def test_writer_rejects_override_meta(beliefs_tmp_dir: Path) -> None:
    """`human_edited`, `edited_at`, `field_locks` are NEVER written."""
    path = beliefs_tmp_dir / "tickers" / "AAPL.yaml"
    belief, raw = load_belief(path)
    original_human_edited = belief.human_edited

    outcome = write_belief(
        path,
        raw,
        patches={
            "human_edited": True,
            "edited_at": "2099-01-01",
            "field_locks": {"confidence": True},
        },
    )
    assert outcome["applied"] == []
    assert outcome["skipped"] == {
        "human_edited": "writer_never_touches_override_meta",
        "edited_at": "writer_never_touches_override_meta",
        "field_locks": "writer_never_touches_override_meta",
    }

    fresh_belief, _ = load_belief(path)
    assert fresh_belief.human_edited is original_human_edited


# --------------------------------------------------------------------------
# Test 5: atomic tmp+rename -- mid-write crash leaves original intact
# --------------------------------------------------------------------------


def test_atomic_write_rollback_on_crash(
    beliefs_tmp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulated mid-dump exception does NOT corrupt the target file."""
    path = beliefs_tmp_dir / "tickers" / "AAPL.yaml"
    original_text = path.read_text()
    _, raw = load_belief(path)

    # Force YAML.dump to raise AFTER load_belief succeeds. The writer must
    # catch the exception, clean up the .tmp file, and re-raise -- with the
    # original target file unchanged.
    from ai_hedge_fund.memory import beliefs as beliefs_module

    original_yaml = beliefs_module._yaml

    def _exploding_yaml() -> YAML:
        y = original_yaml()

        def _boom(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("simulated crash during dump")

        y.dump = _boom  # type: ignore[assignment]
        return y

    monkeypatch.setattr(beliefs_module, "_yaml", _exploding_yaml)

    with pytest.raises(RuntimeError, match="simulated crash"):
        write_belief(path, raw, patches={"confidence": 99})

    # Original file unchanged byte-for-byte (atomic contract).
    assert path.read_text() == original_text
    # No stray .tmp file leaked.
    tmp = path.with_suffix(path.suffix + ".tmp")
    assert not tmp.exists()


# --------------------------------------------------------------------------
# Test 6: no unsafe yaml.load anywhere in the module (T-07-10)
# --------------------------------------------------------------------------


def test_no_unsafe_yaml_load_in_beliefs_module() -> None:
    """T-07-10: the module must not call ``yaml.load(`` (RCE guard)."""
    source = (
        Path(__file__).parent.parent.parent
        / "src"
        / "ai_hedge_fund"
        / "memory"
        / "beliefs.py"
    ).read_text()
    # Zero occurrences of the unsafe-loader call pattern. ``YAML().load`` from
    # ruamel is a different symbol and does not match this regex.
    assert "yaml.load(" not in source, "Unsafe yaml.load( found in beliefs.py"


# --------------------------------------------------------------------------
# Test 7: path-traversal guard (Pitfall 9)
# --------------------------------------------------------------------------


def test_path_traversal_guard(tmp_path: Path) -> None:
    """`belief_path_for_ticker` regex-rejects invalid tickers."""
    beliefs_dir = tmp_path / "beliefs"

    # Happy path
    result = belief_path_for_ticker(beliefs_dir, "AAPL")
    assert result == beliefs_dir / "tickers" / "AAPL.yaml"

    # Path-traversal attempt
    with pytest.raises(ValueError):
        belief_path_for_ticker(beliefs_dir, "../../etc/passwd")

    # Lowercase rejected
    with pytest.raises(ValueError):
        belief_path_for_ticker(beliefs_dir, "aapl")

    # Over-length rejected
    with pytest.raises(ValueError):
        belief_path_for_ticker(beliefs_dir, "A" * 11)

    # Empty rejected
    with pytest.raises(ValueError):
        belief_path_for_ticker(beliefs_dir, "")

    # Slash rejected
    with pytest.raises(ValueError):
        belief_path_for_ticker(beliefs_dir, "AAPL/BAD")

    # Valid edge: dot (class-A shares) and dash tickers allowed
    assert belief_path_for_ticker(beliefs_dir, "BRK.B") == (
        beliefs_dir / "tickers" / "BRK.B.yaml"
    )
    assert belief_path_for_ticker(beliefs_dir, "RDS-A") == (
        beliefs_dir / "tickers" / "RDS-A.yaml"
    )


# --------------------------------------------------------------------------
# Test 8: version monotonicity
# --------------------------------------------------------------------------


def test_version_monotone(beliefs_tmp_dir: Path) -> None:
    """Version bumps iff at least one field was applied."""
    path = beliefs_tmp_dir / "tickers" / "AAPL.yaml"

    # First write: applied -> bump
    belief, raw = load_belief(path)
    assert belief.version == 3
    write_belief(path, raw, patches={"confidence": 80})
    belief2, raw2 = load_belief(path)
    assert belief2.version == 4

    # Second write: applied -> bump again
    write_belief(path, raw2, patches={"confidence": 81})
    belief3, raw3 = load_belief(path)
    assert belief3.version == 5

    # Third write: all patches skipped (override-meta only) -> NO bump
    outcome = write_belief(
        path, raw3, patches={"human_edited": True, "edited_at": "2099-01-01"}
    )
    assert outcome["applied"] == []
    belief4, _ = load_belief(path)
    assert belief4.version == 5


# --------------------------------------------------------------------------
# Test 9: full writable case (no locks, no human_edited)
# --------------------------------------------------------------------------


def test_fully_writable_when_unlocked(beliefs_tmp_dir: Path) -> None:
    """All three patchable fields succeed; version += 1."""
    path = beliefs_tmp_dir / "tickers" / "AAPL.yaml"
    belief, raw = load_belief(path)
    original_version = belief.version
    new_event = {
        "as_of_date": "2026-04-21",
        "outcome_pct": 2.7,
        "old_confidence": 72,
        "new_confidence": 78,
        "rationale": "writable test",
        "source": "self_critique",
    }
    patches = {
        "thesis": "Refined machine thesis",
        "confidence": 78,
        "critique_history": [*raw["critique_history"], new_event],
    }
    outcome = write_belief(path, raw, patches=patches)
    assert set(outcome["applied"]) == {"thesis", "confidence", "critique_history"}
    assert outcome["skipped"] == {}

    fresh, _ = load_belief(path)
    assert fresh.thesis == "Refined machine thesis"
    assert fresh.confidence == 78
    assert len(fresh.critique_history) == 3  # two originals + one new
    assert fresh.version == original_version + 1


# --------------------------------------------------------------------------
# Test 10: load_belief returns a ruamel CommentedMap (round-trip-capable)
# --------------------------------------------------------------------------


def test_load_belief_returns_round_trip_object(beliefs_tmp_dir: Path) -> None:
    """`raw` is a ruamel CommentedMap (has .ca comment anchors)."""
    path = beliefs_tmp_dir / "tickers" / "AAPL.yaml"
    _, raw = load_belief(path)
    # CommentedMap type identifies the round-trip loader; .ca is the
    # "comment anchor" attribute ruamel.yaml attaches to parsed nodes.
    assert isinstance(raw, CommentedMap)
    assert hasattr(raw, "ca")


# --------------------------------------------------------------------------
# Extra: empty file raises ValueError (defensive)
# --------------------------------------------------------------------------


def test_load_empty_file_raises(tmp_path: Path) -> None:
    empty = tmp_path / "empty.yaml"
    empty.write_text("")
    with pytest.raises(ValueError):
        load_belief(empty)


# --------------------------------------------------------------------------
# Extra: skip_if_human_edited=False bypass (offline operator repair)
# --------------------------------------------------------------------------


def test_skip_if_human_edited_false_bypasses_global_flag(
    beliefs_tmp_dir: Path,
) -> None:
    """`skip_if_human_edited=False` lets writes through; field locks still apply."""
    path = beliefs_tmp_dir / "tickers" / "AAPL_human.yaml"
    _, raw = load_belief(path)
    assert raw["human_edited"] is True

    outcome = write_belief(
        path,
        raw,
        patches={"confidence": 99},
        skip_if_human_edited=False,
    )
    assert outcome["applied"] == ["confidence"]

    fresh, _ = load_belief(path)
    assert fresh.confidence == 99


# --------------------------------------------------------------------------
# Extra: ticker regex also matches common SEC edge-case tickers
# --------------------------------------------------------------------------


def test_ticker_regex_matches_real_edge_cases() -> None:
    """Spot-check a sample of production ticker shapes."""
    pattern = re.compile(r"^[A-Z0-9.\-]{1,10}$")
    for ok in ("AAPL", "BRK.B", "BRK-B", "RDS.A", "GOOG", "SPY", "A", "1010"):
        assert pattern.fullmatch(ok), ok
    for bad in ("aapl", "", "TOO_LONG_NAME", "AAPL ", "AA/PL", "AA|PL"):
        assert not pattern.fullmatch(bad), bad

"""Wave-0 smoke test: prove every Phase 7 fixture loads.

This is the only test in the Wave-0 plan. It exists so downstream plans
(07-01..07-05) can assume fixtures work. If this test is red, Wave-1
does not start.
"""

from __future__ import annotations

import csv
from pathlib import Path

from ruamel.yaml import YAML


def test_wave0_belief_fixtures_load(
    sample_belief_yaml_path: Path,
    sample_belief_human_edited_path: Path,
    sample_belief_field_locked_path: Path,
) -> None:
    yaml = YAML()
    plain = yaml.load(sample_belief_yaml_path)
    edited = yaml.load(sample_belief_human_edited_path)
    locked = yaml.load(sample_belief_field_locked_path)

    # Plain belief: required keys present, human_edited false.
    assert plain["ticker"] == "AAPL"
    assert plain["human_edited"] is False
    assert plain["field_locks"]["sector"] is True
    assert isinstance(plain["critique_history"], list)
    assert len(plain["critique_history"]) == 2

    # Human-edited: confidence pinned, flag set.
    assert edited["human_edited"] is True
    assert edited["confidence"] == 20

    # Field-locked: confidence locked but flag false.
    assert locked["human_edited"] is False
    assert locked["field_locks"]["confidence"] is True
    assert locked["field_locks"]["thesis"] is False


def test_wave0_belief_plain_preserves_comment(sample_belief_yaml_path: Path) -> None:
    # Pitfall-1 / MEM-03 regression: the "# flagged" comment must exist
    # in the raw file bytes so Plan 07-02's round-trip test can assert
    # survival after write.
    text = sample_belief_yaml_path.read_text()
    assert "# flagged" in text


def test_wave0_episodic_csv_rows(sample_episodic_csv_path: Path) -> None:
    with sample_episodic_csv_path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) >= 10
    required_cols = {
        "ticker",
        "sector",
        "record_type",
        "as_of_date",
        "signal_direction",
        "confidence",
        "outcome_pct",
        "policy_sha",
    }
    assert required_cols <= set(rows[0].keys())
    sectors = {r["sector"] for r in rows}
    assert len(sectors) >= 3  # at least Technology, Healthcare, Financials
    record_types = {r["record_type"] for r in rows}
    assert record_types >= {"analysis", "outcome"}
    # Temporal-leakage regression seed: at least one future-dated row.
    assert any(r["as_of_date"].startswith("2099") for r in rows)


def test_wave0_outcomes_yaml(sample_outcomes_yaml_path: Path) -> None:
    yaml = YAML(typ="safe")
    data = yaml.load(sample_outcomes_yaml_path)
    assert "outcomes" in data
    assert len(data["outcomes"]) >= 3
    for row in data["outcomes"]:
        assert {"ticker", "as_of_date", "outcome_pct", "linked_signal_direction"} <= set(row.keys())


def test_wave0_beliefs_tmp_dir_has_three_files(beliefs_tmp_dir: Path) -> None:
    tickers_dir = beliefs_tmp_dir / "tickers"
    assert tickers_dir.is_dir()
    assert (tickers_dir / "AAPL.yaml").is_file()
    assert (tickers_dir / "AAPL_human.yaml").is_file()
    assert (tickers_dir / "AAPL_locked.yaml").is_file()
    assert (beliefs_tmp_dir / "sectors").is_dir()


def test_wave0_memory_db_session_isolation(memory_db_session) -> None:
    # Smoke: sqlite in-memory session is live.
    from sqlalchemy import text

    assert memory_db_session.execute(text("SELECT 1")).scalar() == 1

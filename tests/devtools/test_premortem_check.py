"""Pre-mortem manifest check for the phase-exec gate.

Phase 10 named five pre-mortem tests that were never written (10-SUMMARY);
this check makes "the test exists" mechanical instead of a reviewer's job.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_hedge_fund.devtools.premortem_check import (
    ManifestError,
    check_manifest,
    parse_manifest,
)

TEST_FILE = """
import pytest


def test_top_level():
    assert True


async def test_async_one():
    assert True


class TestGroup:
    def test_in_class(self):
        assert True


def helper():
    pass
"""


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    (tmp_path / "tests" / "x").mkdir(parents=True)
    (tmp_path / "tests" / "x" / "test_mod.py").write_text(TEST_FILE)
    return tmp_path


def _entry(pid: str, test: str | list[str], **extra: str) -> dict:
    return {"id": pid, "failure": "f", "invariant": "i", "test": test, **extra}


def _missing(repo: Path, raw: list[dict]) -> list[str]:
    return [r.test_id for r in check_manifest(parse_manifest(raw), repo) if not r.found]


def test_existing_tests_found(repo: Path) -> None:
    raw = [
        _entry("PM1", "tests/x/test_mod.py::test_top_level"),
        _entry("PM2", "tests/x/test_mod.py::test_async_one"),
        _entry("PM3", "tests/x/test_mod.py::TestGroup::test_in_class"),
        _entry("PM4", "tests/x/test_mod.py::test_top_level[param-a]"),
    ]
    assert _missing(repo, raw) == []


def test_missing_function_reported(repo: Path) -> None:
    raw = [_entry("PM1", "tests/x/test_mod.py::test_never_written")]
    assert _missing(repo, raw) == ["tests/x/test_mod.py::test_never_written"]


def test_missing_file_reported(repo: Path) -> None:
    raw = [_entry("PM1", "tests/x/test_gone.py::test_top_level")]
    assert _missing(repo, raw) == ["tests/x/test_gone.py::test_top_level"]


def test_non_test_function_does_not_count(repo: Path) -> None:
    raw = [_entry("PM1", "tests/x/test_mod.py::helper")]
    assert _missing(repo, raw) == ["tests/x/test_mod.py::helper"]


def test_method_outside_its_class_does_not_count(repo: Path) -> None:
    raw = [_entry("PM1", "tests/x/test_mod.py::test_in_class")]
    assert _missing(repo, raw) == ["tests/x/test_mod.py::test_in_class"]


def test_multiple_tests_per_entry_all_checked(repo: Path) -> None:
    raw = [_entry("PM1", ["tests/x/test_mod.py::test_top_level", "tests/x/test_mod.py::nope"])]
    assert _missing(repo, raw) == ["tests/x/test_mod.py::nope"]


def test_deferred_entry_skipped_but_reported(repo: Path) -> None:
    raw = [_entry("PM1", "tests/x/test_mod.py::nope", deferred="TECH-DEBT: needs live broker")]
    results = check_manifest(parse_manifest(raw), repo)
    assert len(results) == 1
    assert results[0].deferred
    assert results[0].found is False


def test_parse_rejects_bare_filename_without_node(repo: Path) -> None:
    with pytest.raises(ManifestError, match="PM1.*tests/"):
        parse_manifest([_entry("PM1", "test_mod.py::test_top_level")])


def test_parse_rejects_missing_node_separator() -> None:
    with pytest.raises(ManifestError, match="PM1.*::"):
        parse_manifest([_entry("PM1", "tests/x/test_mod.py")])


def test_parse_rejects_missing_fields() -> None:
    with pytest.raises(ManifestError, match="PM1.*invariant"):
        parse_manifest([{"id": "PM1", "failure": "f", "test": "tests/a.py::test_x"}])


def test_parse_rejects_duplicate_ids() -> None:
    raw = [_entry("PM1", "tests/a.py::test_x"), _entry("PM1", "tests/a.py::test_y")]
    with pytest.raises(ManifestError, match="duplicate.*PM1"):
        parse_manifest(raw)


def test_parse_rejects_empty_manifest() -> None:
    with pytest.raises(ManifestError, match="empty"):
        parse_manifest([])


def test_path_traversal_rejected() -> None:
    with pytest.raises(ManifestError, match="PM1"):
        parse_manifest([_entry("PM1", "tests/../../etc/passwd::test_x")])


def test_cli_exit_codes(repo: Path) -> None:
    from ai_hedge_fund.devtools.premortem_check import main

    good = repo / "GOOD.md"
    good.write_text(
        "```yaml phase-premortem\n"
        "- id: PM1\n  failure: f\n  invariant: i\n"
        "  test: tests/x/test_mod.py::test_top_level\n```\n"
    )
    bad = repo / "BAD.md"
    bad.write_text(
        "```yaml phase-premortem\n"
        "- id: PM1\n  failure: f\n  invariant: i\n"
        "  test: tests/x/test_mod.py::test_missing\n```\n"
    )
    assert main([str(good), "--root", str(repo)]) == 0
    assert main([str(bad), "--root", str(repo)]) == 1
    assert main([str(repo / "NOPE.md"), "--root", str(repo)]) == 2


# --- review round 1 (2026-09-25): types, collectability, filters ---------------

COLLECT_FILE = """
class TestOuter:
    class TestInner:
        def test_deep(self):
            assert True


class Helper:
    def test_not_collected(self):
        assert True


def test_shadowed():
    assert True


test_shadowed = None
"""


@pytest.fixture()
def repo2(repo: Path) -> Path:
    (repo / "tests" / "x" / "test_collect.py").write_text(COLLECT_FILE)
    (repo / "tests" / "x" / "helpers.py").write_text("def test_in_helper():\n    pass\n")
    return repo


@pytest.mark.parametrize("bad", [None, 5, True, {"a": 1}, []])
def test_test_field_type_validated(bad: object) -> None:
    with pytest.raises(ManifestError, match="PM1.*test"):
        parse_manifest([_entry("PM1", bad)])  # type: ignore[arg-type]


def test_nested_test_classes_found(repo2: Path) -> None:
    raw = [_entry("PM1", "tests/x/test_collect.py::TestOuter::TestInner::test_deep")]
    assert _missing(repo2, raw) == []


@pytest.mark.parametrize(
    "node",
    [
        "tests/x/helpers.py::test_in_helper",
        "tests/x/test_collect.py::Helper::test_not_collected",
        "tests/x/test_collect.py::test_shadowed",
    ],
)
def test_uncollectable_tests_reported_missing(repo2: Path, node: str) -> None:
    assert _missing(repo2, [_entry("PM1", node)]) == [node]


@pytest.mark.parametrize("reason", ["no", "yes", "   "])
def test_deferred_must_cite_tech_debt(reason: str) -> None:
    with pytest.raises(ManifestError, match="PM1.*TECH-DEBT"):
        parse_manifest([_entry("PM1", "tests/a.py::test_x", deferred=reason)])


@pytest.mark.parametrize("bad_id", [1, None, ""])
def test_entry_ids_must_be_strings(bad_id: object) -> None:
    raw = [{"id": bad_id, "failure": "f", "invariant": "i", "test": "tests/a.py::test_x"}]
    with pytest.raises(ManifestError, match="id"):
        parse_manifest(raw)


def test_cli_done_filter_checks_only_finished_tasks(repo: Path) -> None:
    from ai_hedge_fund.devtools.premortem_check import main

    plan = repo / "PLAN.md"
    plan.write_text(
        "```yaml phase-tasks\n"
        "- id: T1\n  title: a\n  owns: [src/a.py, tests/x/test_mod.py]\n"
        "- id: T2\n  title: b\n  owns: [src/b.py, tests/x/test_later.py]\n```\n\n"
        "```yaml phase-premortem\n"
        "- id: PM1\n  failure: f\n  invariant: i\n"
        "  test: tests/x/test_mod.py::test_top_level\n"
        "- id: PM2\n  failure: f\n  invariant: i\n"
        "  test: tests/x/test_later.py::test_not_yet\n```\n"
    )
    assert main([str(plan), "--root", str(repo), "--done", "T1"]) == 0
    assert main([str(plan), "--root", str(repo), "--done", "T1", "T2"]) == 1
    assert main([str(plan), "--root", str(repo)]) == 1
    assert main([str(plan), "--root", str(repo), "--done", "T9"]) == 1

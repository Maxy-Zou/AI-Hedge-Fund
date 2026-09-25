"""Wave planning for the phase-split skill.

Invariants (from the workflow redesign, 2026-09-25):
- a task never shares a wave with a task it depends on (transitively);
- two tasks owning the same file never share a wave (overlap forces order);
- a task owning a shared hotspot (lockfile, migrations, config, models,
  conftest, __init__ exports) runs alone;
- no wave exceeds max_parallel;
- invalid plans fail loudly instead of producing a schedule.
"""

from __future__ import annotations

from typing import Any

import pytest

from ai_hedge_fund.devtools.waves import (
    PlanError,
    Task,
    is_hotspot,
    parse_tasks,
    plan_waves,
)


def _raw(tid: str, owns: list[str], depends: list[str] | None = None, **extra: Any) -> dict:
    return {"id": tid, "title": f"task {tid}", "owns": owns, "depends": depends or [], **extra}


def _ids(waves: tuple) -> list[list[str]]:
    return [[t.id for t in wave.tasks] for wave in waves]


# --- parse_tasks -----------------------------------------------------------


def test_parse_builds_immutable_tasks() -> None:
    tasks = parse_tasks([_raw("T1", ["src/a.py"], reads=["src/b.py"])])
    assert tasks == (
        Task(id="T1", title="task T1", owns=("src/a.py",), reads=("src/b.py",), depends=()),
    )
    with pytest.raises(AttributeError):
        tasks[0].id = "T9"  # type: ignore[misc]


def test_parse_rejects_duplicate_ids() -> None:
    with pytest.raises(PlanError, match="duplicate.*T1"):
        parse_tasks([_raw("T1", ["a.py"]), _raw("T1", ["b.py"])])


def test_parse_rejects_unknown_dependency() -> None:
    with pytest.raises(PlanError, match="T2.*unknown.*T7"):
        parse_tasks([_raw("T1", ["a.py"]), _raw("T2", ["b.py"], ["T7"])])


def test_parse_rejects_missing_owns() -> None:
    with pytest.raises(PlanError, match="T1.*owns"):
        parse_tasks([_raw("T1", [])])


def test_parse_rejects_unknown_keys() -> None:
    with pytest.raises(PlanError, match="T1.*onws"):
        parse_tasks([{"id": "T1", "title": "x", "onws": ["a.py"]}])


def test_parse_rejects_cycle() -> None:
    with pytest.raises(PlanError, match="cycle"):
        parse_tasks([_raw("T1", ["a.py"], ["T2"]), _raw("T2", ["b.py"], ["T1"])])


def test_parse_rejects_self_dependency() -> None:
    with pytest.raises(PlanError, match="cycle"):
        parse_tasks([_raw("T1", ["a.py"], ["T1"])])


# --- hotspots --------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "uv.lock",
        "pyproject.toml",
        "alembic/versions/007_add_x.py",
        "src/ai_hedge_fund/config.py",
        "src/ai_hedge_fund/db/models.py",
        "src/ai_hedge_fund/execution/__init__.py",
        "tests/conftest.py",
        "tests/execution/conftest.py",
        "src/ai_hedge_fund/graph/pipeline.py",
        "src/ai_hedge_fund/schemas/state.py",
        ".planning/ROADMAP.md",
    ],
)
def test_hotspots_detected(path: str) -> None:
    assert is_hotspot(path)


@pytest.mark.parametrize(
    "path", ["src/ai_hedge_fund/execution/sizing.py", "tests/execution/test_sizing.py"]
)
def test_leaf_modules_are_not_hotspots(path: str) -> None:
    assert not is_hotspot(path)


# --- plan_waves ------------------------------------------------------------


def test_independent_leaf_tasks_share_a_wave() -> None:
    tasks = parse_tasks([_raw("T1", ["src/x/a.py"]), _raw("T2", ["src/x/b.py"])])
    assert _ids(plan_waves(tasks)) == [["T1", "T2"]]


def test_dependency_forces_later_wave() -> None:
    tasks = parse_tasks([_raw("T1", ["src/x/a.py"]), _raw("T2", ["src/x/b.py"], ["T1"])])
    assert _ids(plan_waves(tasks)) == [["T1"], ["T2"]]


def test_shared_owned_file_forces_order_in_plan_order() -> None:
    tasks = parse_tasks(
        [_raw("T1", ["src/x/errors.py", "src/x/a.py"]), _raw("T2", ["src/x/errors.py"])]
    )
    waves = plan_waves(tasks)
    assert _ids(waves) == [["T1"], ["T2"]]
    assert any("src/x/errors.py" in note for note in waves[1].notes)


def test_reader_runs_after_owner_even_when_listed_first() -> None:
    tasks = parse_tasks(
        [_raw("T1", ["src/x/b.py"], reads=["src/x/a.py"]), _raw("T2", ["src/x/a.py"])]
    )
    waves = plan_waves(tasks)
    assert _ids(waves) == [["T2"], ["T1"]]
    assert any("reads src/x/a.py" in note for note in waves[1].notes)


def test_hotspot_owner_runs_alone_before_parallel_peers() -> None:
    tasks = parse_tasks(
        [
            _raw("T1", ["src/x/a.py"]),
            _raw("T2", ["alembic/versions/008_x.py"]),
            _raw("T3", ["src/x/b.py"]),
        ]
    )
    waves = plan_waves(tasks)
    assert _ids(waves) == [["T2"], ["T1", "T3"]]
    assert waves[0].serial
    assert not waves[1].serial


def test_explicit_serial_flag_runs_alone() -> None:
    tasks = parse_tasks([_raw("T1", ["src/x/a.py"], serial=True), _raw("T2", ["src/x/b.py"])])
    assert _ids(plan_waves(tasks)) == [["T1"], ["T2"]]


def test_max_parallel_caps_wave_width() -> None:
    tasks = parse_tasks([_raw(f"T{i}", [f"src/x/m{i}.py"]) for i in range(5)])
    assert _ids(plan_waves(tasks, max_parallel=2)) == [["T0", "T1"], ["T2", "T3"], ["T4"]]


def test_max_parallel_must_be_positive() -> None:
    with pytest.raises(PlanError, match="max_parallel"):
        plan_waves(parse_tasks([_raw("T1", ["a.py"])]), max_parallel=0)


def test_no_wave_contains_a_dependency_pair() -> None:
    raw = [
        _raw("T0", ["src/ai_hedge_fund/config.py"]),
        _raw("T1", ["src/x/a.py"], ["T0"]),
        _raw("T2", ["src/x/b.py"], ["T0"]),
        _raw("T3", ["src/x/c.py"], ["T1"]),
        _raw("T4", ["src/x/a.py"]),
        _raw("T5", ["src/x/d.py"], ["T2", "T3"]),
    ]
    tasks = parse_tasks(raw)
    waves = plan_waves(tasks)
    position = {t.id: i for i, w in enumerate(waves) for t in w.tasks}
    assert sorted(position) == [t.id for t in tasks]
    for task in tasks:
        for dep in task.depends:
            assert position[dep] < position[task.id]
    for wave in waves:
        owned = [p for t in wave.tasks for p in t.owns]
        assert len(owned) == len(set(owned))


def test_render_markdown_lists_waves() -> None:
    from ai_hedge_fund.devtools.waves import render_markdown

    tasks = parse_tasks([_raw("T1", ["uv.lock"]), _raw("T2", ["src/x/a.py"], ["T1"])])
    text = render_markdown(plan_waves(tasks))
    assert "Wave 1 (serial)" in text
    assert "Wave 2 (parallel x1)" in text
    assert "T2" in text


def test_cli_exit_codes(tmp_path) -> None:
    from ai_hedge_fund.devtools.waves import main

    good = tmp_path / "PLAN.md"
    good.write_text(
        "```yaml phase-tasks\n"
        "- id: T1\n  title: a\n  owns: [src/x/a.py]\n"
        "- id: T2\n  title: b\n  owns: [src/x/b.py]\n  depends: [T1]\n```\n"
    )
    bad = tmp_path / "BAD.md"
    bad.write_text("```yaml phase-tasks\n- id: T1\n  title: a\n  owns: []\n```\n")
    assert main([str(good)]) == 0
    assert main([str(good), "--json"]) == 0
    assert main([str(bad)]) == 1
    assert main([str(tmp_path / "NOPE.md")]) == 2


def test_phase_plan_template_task_block_schedules() -> None:
    """The template shipped with the phase-plan skill must stay valid input for phase-split."""
    from pathlib import Path

    from ai_hedge_fund.devtools.phase_doc import extract_yaml_block

    template = Path(__file__).parents[2] / ".claude/skills/phase-plan/template.md"
    tasks = parse_tasks(extract_yaml_block(template.read_text(), "phase-tasks"))
    waves = plan_waves(tasks)
    assert waves[0].serial and waves[0].tasks[0].id == "T0"


# --- review round 1 (2026-09-25): path spelling, silent reads, id types --------


@pytest.mark.parametrize(
    "spelling", ["./src/x/a.py", "src/x/a.py ", "src/x/../x/a.py", "src/X/A.py"]
)
def test_same_file_spelled_differently_still_conflicts(spelling: str) -> None:
    tasks = parse_tasks([_raw("T1", ["src/x/a.py"]), _raw("T2", [spelling])])
    assert _ids(plan_waves(tasks)) == [["T1"], ["T2"]]


def test_paths_are_stored_normalised() -> None:
    (task,) = parse_tasks([_raw("T1", ["./src/x/a.py "], reads=["./src/x/b.py"])])
    assert task.owns == ("src/x/a.py",)
    assert task.reads == ("src/x/b.py",)


def test_dot_slash_hotspot_still_runs_alone() -> None:
    tasks = parse_tasks([_raw("T1", ["./uv.lock"]), _raw("T2", ["src/x/a.py"])])
    assert plan_waves(tasks)[0].serial


@pytest.mark.parametrize(
    "bad", ["src/x/*", "src/x/", "src/x/a?.py", "/abs/a.py", "../outside.py", "src/[ab].py"]
)
def test_globs_directories_and_escapes_rejected(bad: str) -> None:
    with pytest.raises(PlanError, match="T1"):
        parse_tasks([_raw("T1", [bad])])


def test_read_against_existing_order_raises() -> None:
    raw = [_raw("A", ["src/x/a.py"], reads=["src/x/b.py"]), _raw("B", ["src/x/b.py"], ["A"])]
    with pytest.raises(PlanError, match="A.*reads.*src/x/b.py"):
        plan_waves(parse_tasks(raw))


def test_mutual_reads_raise() -> None:
    raw = [
        _raw("A", ["src/x/a.py"], reads=["src/x/b.py"]),
        _raw("B", ["src/x/b.py"], reads=["src/x/a.py"]),
    ]
    with pytest.raises(PlanError, match="reads"):
        plan_waves(parse_tasks(raw))


@pytest.mark.parametrize("bad_id", [1, None, ""])
def test_ids_must_be_non_empty_strings(bad_id: object) -> None:
    with pytest.raises(PlanError, match="id"):
        parse_tasks([{"id": bad_id, "title": "x", "owns": ["a.py"]}])


def test_package_level_models_module_is_hotspot() -> None:
    assert is_hotspot("src/ai_hedge_fund/models.py")

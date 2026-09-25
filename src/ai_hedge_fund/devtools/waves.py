"""Turn a phase's task list into parallel execution waves (phase-split skill).

Each task declares the files it ``owns`` (writes), the files it ``reads``, and
the tasks it ``depends`` on. Ordering rules, applied in this order:

1. Explicit ``depends`` edges.
2. Two tasks owning the same file are ordered by plan position.
3. A task reading a file another task owns runs after the owner.
4. A task owning a shared hotspot (lockfile, migrations, config, ORM models,
   graph state/wiring, conftest, ``__init__`` exports, planning docs) or
   flagged ``serial`` runs alone -- these are the contracts parallel tasks
   build on, and where the GSD-era worktree merges conflicted.

Tasks are then layered by longest dependency path; each layer becomes serial
waves (one task each) followed by parallel waves of at most ``max_parallel``.

Usage: ``uv run python -m ai_hedge_fund.devtools.waves PLAN.md [--json]``
"""

from __future__ import annotations

import argparse
import json
import posixpath
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

from ai_hedge_fund.devtools.phase_doc import PhaseDocError, extract_yaml_block

BLOCK_NAME = "phase-tasks"
DEFAULT_MAX_PARALLEL = 4

HOTSPOT_PATTERNS: tuple[str, ...] = (
    "uv.lock",
    "pyproject.toml",
    "alembic/env.py",
    "alembic/versions/*",
    "src/ai_hedge_fund/config.py",
    "src/ai_hedge_fund/models.py",
    "src/ai_hedge_fund/db/models.py",
    "src/ai_hedge_fund/schemas/state.py",
    "src/ai_hedge_fund/graph/pipeline.py",
    "__init__.py",
    "*/__init__.py",
    "conftest.py",
    "*/conftest.py",
    ".planning/*",
    "docs/PROGRESS.md",
    "CLAUDE.md",
    ".env.example",
)

_GLOB_CHARS = frozenset("*?[]")
_REQUIRED_KEYS = frozenset({"id", "title", "owns"})
_ALLOWED_KEYS = _REQUIRED_KEYS | {"reads", "depends", "serial"}


class PlanError(ValueError):
    """The task list cannot be scheduled."""


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    owns: tuple[str, ...]
    reads: tuple[str, ...] = ()
    depends: tuple[str, ...] = ()
    serial: bool = False


@dataclass(frozen=True)
class Wave:
    tasks: tuple[Task, ...]
    serial: bool
    notes: tuple[str, ...] = ()


def is_hotspot(path: str) -> bool:
    return any(fnmatchcase(path, pattern) for pattern in HOTSPOT_PATTERNS)


def _normalise_path(path: str, tid: str, key: str) -> str:
    """One canonical spelling per file, so './a.py', 'a.py ' and 'x/../a.py' collide."""
    cleaned = path.strip()
    if _GLOB_CHARS & set(cleaned) or cleaned.endswith("/") or cleaned.startswith("/"):
        raise PlanError(
            f"task {tid}: '{key}' entry {path!r} must be one repo-relative file, "
            "not a glob, directory, or absolute path"
        )
    normal = posixpath.normpath(cleaned)
    if normal == ".." or normal.startswith("../"):
        raise PlanError(f"task {tid}: '{key}' entry {path!r} escapes the repository")
    return normal


def _str_tuple(value: Any, tid: str, key: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        raise PlanError(f"task {tid}: '{key}' must be a list of non-empty strings")
    return tuple(value)


def _path_tuple(value: Any, tid: str, key: str) -> tuple[str, ...]:
    return tuple(_normalise_path(p, tid, key) for p in _str_tuple(value, tid, key))


def _parse_one(index: int, raw: Mapping[str, Any]) -> Task:
    tid = raw.get("id")
    if not isinstance(tid, str) or not tid.strip():
        raise PlanError(f"task #{index + 1}: 'id' must be a non-empty string, got {tid!r}")
    unknown = set(raw) - _ALLOWED_KEYS
    if unknown:
        raise PlanError(f"task {tid}: unknown keys {sorted(unknown)}")
    missing = _REQUIRED_KEYS - set(raw)
    if missing:
        raise PlanError(f"task {tid}: missing keys {sorted(missing)}")
    owns = _path_tuple(raw["owns"], tid, "owns")
    if not owns:
        raise PlanError(f"task {tid}: 'owns' must list at least one file")
    serial = raw.get("serial", False)
    if not isinstance(serial, bool):
        raise PlanError(f"task {tid}: 'serial' must be true or false")
    return Task(
        id=tid,
        title=str(raw["title"]),
        owns=owns,
        reads=_path_tuple(raw.get("reads"), tid, "reads"),
        depends=_str_tuple(raw.get("depends"), tid, "depends"),
        serial=serial,
    )


def _check_acyclic(tasks: Sequence[Task]) -> None:
    deps = {t.id: t.depends for t in tasks}
    state: dict[str, int] = {}  # 1 = visiting, 2 = done

    def visit(tid: str, trail: tuple[str, ...]) -> None:
        if state.get(tid) == 2:
            return
        if state.get(tid) == 1:
            raise PlanError(f"dependency cycle: {' -> '.join((*trail, tid))}")
        state[tid] = 1
        for dep in deps[tid]:
            visit(dep, (*trail, tid))
        state[tid] = 2

    for task in tasks:
        visit(task.id, ())


def parse_tasks(raw: Iterable[Mapping[str, Any]]) -> tuple[Task, ...]:
    """Validate raw task mappings into immutable ``Task`` objects."""
    tasks = tuple(_parse_one(i, item) for i, item in enumerate(raw))
    if not tasks:
        raise PlanError("task list is empty")
    seen: set[str] = set()
    for task in tasks:
        if task.id in seen:
            raise PlanError(f"duplicate task id {task.id}")
        seen.add(task.id)
    for task in tasks:
        unknown = [d for d in task.depends if d not in seen]
        if unknown:
            raise PlanError(f"task {task.id} depends on unknown task(s) {unknown}")
    _check_acyclic(tasks)
    return tasks


def _reaches(edges: Mapping[str, set[str]], start: str, target: str) -> bool:
    """True if ``target`` is a (transitive) dependency of ``start``."""
    stack, seen = [start], set()
    while stack:
        node = stack.pop()
        if node == target:
            return True
        if node not in seen:
            seen.add(node)
            stack.extend(edges[node])
    return False


def _shared(first: Sequence[str], second: Sequence[str]) -> list[str]:
    """Paths in both lists, compared case-insensitively (macOS filesystems are)."""
    folded = {p.casefold() for p in second}
    return sorted(p for p in set(first) if p.casefold() in folded)


def _implicit_edges(
    tasks: Sequence[Task],
) -> tuple[dict[str, set[str]], dict[str, list[str]]]:
    """Dependency edges including file-overlap ordering, plus a note per added edge."""
    edges = {t.id: set(t.depends) for t in tasks}
    notes: dict[str, list[str]] = {t.id: [] for t in tasks}

    def order(before: Task, after: Task, reason: str) -> None:
        if _reaches(edges, after.id, before.id) or _reaches(edges, before.id, after.id):
            return
        edges[after.id].add(before.id)
        notes[after.id].append(f"{after.id} after {before.id}: {reason}")

    for i, first in enumerate(tasks):
        for second in tasks[i + 1 :]:
            for path in _shared(first.owns, second.owns):
                order(first, second, f"both own {path}")
    for owner in tasks:
        for reader in tasks:
            if reader.id == owner.id:
                continue
            for path in _shared(reader.reads, owner.owns):
                if _reaches(edges, owner.id, reader.id):
                    raise PlanError(
                        f"task {reader.id} reads {path} owned by {owner.id}, but {owner.id} "
                        f"must run after {reader.id}; fix 'depends' or move the shared edit to T0"
                    )
                order(owner, reader, f"reads {path}")
    return edges, notes


def _levels(tasks: Sequence[Task], edges: Mapping[str, set[str]]) -> dict[str, int]:
    level: dict[str, int] = {}

    def depth(tid: str) -> int:
        if tid not in level:
            level[tid] = 1 + max((depth(d) for d in edges[tid]), default=-1)
        return level[tid]

    for task in tasks:
        depth(task.id)
    return level


def _is_serial(task: Task) -> bool:
    return task.serial or any(is_hotspot(path) for path in task.owns)


def plan_waves(tasks: Sequence[Task], max_parallel: int = DEFAULT_MAX_PARALLEL) -> tuple[Wave, ...]:
    """Schedule ``tasks`` into ordered waves; tasks within a wave may run concurrently."""
    if max_parallel < 1:
        raise PlanError(f"max_parallel must be >= 1, got {max_parallel}")
    edges, notes = _implicit_edges(tasks)
    level = _levels(tasks, edges)
    waves: list[Wave] = []
    for lvl in range(max(level.values()) + 1):
        layer = [t for t in tasks if level[t.id] == lvl]
        for task in (t for t in layer if _is_serial(t)):
            waves.append(Wave(tasks=(task,), serial=True, notes=tuple(notes[task.id])))
        parallel = [t for t in layer if not _is_serial(t)]
        for start in range(0, len(parallel), max_parallel):
            chunk = tuple(parallel[start : start + max_parallel])
            chunk_notes = tuple(n for t in chunk for n in notes[t.id])
            waves.append(Wave(tasks=chunk, serial=False, notes=chunk_notes))
    return tuple(waves)


def render_markdown(waves: Sequence[Wave]) -> str:
    lines: list[str] = []
    for number, wave in enumerate(waves, start=1):
        kind = "serial" if wave.serial else f"parallel x{len(wave.tasks)}"
        lines.append(f"### Wave {number} ({kind})")
        for task in wave.tasks:
            lines.append(f"- **{task.id}** {task.title} -- owns: {', '.join(task.owns)}")
        lines.extend(f"  - note: {note}" for note in wave.notes)
        lines.append("")
    return "\n".join(lines)


def _as_json(waves: Sequence[Wave]) -> str:
    payload = [
        {
            "wave": number,
            "serial": wave.serial,
            "tasks": [{"id": t.id, "title": t.title, "owns": list(t.owns)} for t in wave.tasks],
            "notes": list(wave.notes),
        }
        for number, wave in enumerate(waves, start=1)
    ]
    return json.dumps(payload, indent=2)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan parallel waves from a phase PLAN.md")
    parser.add_argument("plan", type=Path)
    parser.add_argument("--max-parallel", type=int, default=DEFAULT_MAX_PARALLEL)
    parser.add_argument("--json", action="store_true", help="emit JSON instead of markdown")
    args = parser.parse_args(argv)
    if not args.plan.is_file():
        print(f"error: {args.plan} not found", file=sys.stderr)
        return 2
    try:
        tasks = parse_tasks(extract_yaml_block(args.plan.read_text(), BLOCK_NAME))
        waves = plan_waves(tasks, args.max_parallel)
    except (PlanError, PhaseDocError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(_as_json(waves) if args.json else render_markdown(waves))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

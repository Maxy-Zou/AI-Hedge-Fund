"""Verify every pre-mortem failure mode has a test that actually exists.

The pre-mortem lives in the phase PLAN.md as a ```yaml phase-premortem``` block::

    - id: PM1
      severity: C            # optional: C / H / M
      failure: what went wrong
      invariant: what it violates
      test: tests/execution/test_submit.py::test_vetoed_refused_zero_broker_calls
      deferred: "TECH-DEBT: reason"   # optional; skipped but reported

``test`` may be one pytest node id or a list. The check is static (AST), so it
runs without importing test modules or touching a database. It requires what
pytest would collect: a ``test_*.py``/``*_test.py`` file, ``Test*`` classes
(nesting allowed), and a ``test*`` function still bound to that name at the end
of its scope. Parametrize ids (``[...]``) are not checked, and tests defined by
inheritance or inside ``if`` blocks read as missing -- name the concrete node.
Whether the test *can fail* is still the reviewer's job; whether it *exists* is not.

Usage: ``uv run python -m ai_hedge_fund.devtools.premortem_check PLAN.md [--done T0 T1]``
``--done`` limits the check to tests in files owned by those tasks (mid-phase gates).
Exit codes: 0 all present, 1 missing tests or invalid manifest, 2 file not found.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_hedge_fund.devtools.phase_doc import PhaseDocError, extract_yaml_block
from ai_hedge_fund.devtools.waves import BLOCK_NAME as TASKS_BLOCK
from ai_hedge_fund.devtools.waves import PlanError, parse_tasks

BLOCK_NAME = "phase-premortem"

_NODE_ID = re.compile(
    r"^(?P<file>tests/[\w/.-]+\.py)::(?P<scope>(?:[A-Za-z_]\w*::)*[A-Za-z_]\w*)(?:\[.*\])?$"
)
_COLLECTABLE_FILE = re.compile(r"^(test_\w*|\w*_test)\.py$")
_REQUIRED_KEYS = frozenset({"id", "failure", "invariant", "test"})
_ALLOWED_KEYS = _REQUIRED_KEYS | {"severity", "deferred"}


class ManifestError(ValueError):
    """The pre-mortem manifest is malformed."""


@dataclass(frozen=True)
class Entry:
    id: str
    failure: str
    invariant: str
    tests: tuple[str, ...]
    deferred: str | None = None


@dataclass(frozen=True)
class Result:
    entry_id: str
    test_id: str
    found: bool
    deferred: bool


def _validate_node_id(entry_id: str, test_id: str) -> None:
    match = _NODE_ID.match(test_id)
    if match is None:
        raise ManifestError(
            f"{entry_id}: '{test_id}' must be a full node id like "
            "tests/<path>/test_x.py::test_name (with ::)"
        )
    if ".." in Path(match["file"]).parts:
        raise ManifestError(f"{entry_id}: '{test_id}' must not contain '..'")


def _tests_tuple(eid: str, value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list) and value and all(isinstance(t, str) for t in value):
        return tuple(value)
    raise ManifestError(f"{eid}: 'test' must be a node id or a non-empty list of node ids")


def _deferred(eid: str, value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip().startswith("TECH-DEBT"):
        raise ManifestError(f"{eid}: 'deferred' must start with TECH-DEBT and give the reason")
    return value.strip()


def _parse_one(index: int, raw: Mapping[str, Any]) -> Entry:
    eid = raw.get("id")
    if not isinstance(eid, str) or not eid.strip():
        raise ManifestError(f"entry #{index + 1}: 'id' must be a non-empty string, got {eid!r}")
    unknown = set(raw) - _ALLOWED_KEYS
    if unknown:
        raise ManifestError(f"{eid}: unknown keys {sorted(unknown)}")
    missing = _REQUIRED_KEYS - set(raw)
    if missing:
        raise ManifestError(f"{eid}: missing keys {sorted(missing)}")
    tests = _tests_tuple(eid, raw["test"])
    for test_id in tests:
        _validate_node_id(eid, test_id)
    return Entry(
        id=eid,
        failure=str(raw["failure"]),
        invariant=str(raw["invariant"]),
        tests=tests,
        deferred=_deferred(eid, raw.get("deferred")),
    )


def parse_manifest(raw: Iterable[Mapping[str, Any]]) -> tuple[Entry, ...]:
    entries = tuple(_parse_one(i, item) for i, item in enumerate(raw))
    if not entries:
        raise ManifestError("pre-mortem manifest is empty")
    seen: set[str] = set()
    for entry in entries:
        if entry.id in seen:
            raise ManifestError(f"duplicate pre-mortem id {entry.id}")
        seen.add(entry.id)
    return entries


def _binds(node: ast.stmt, name: str) -> bool:
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        return node.name == name
    if isinstance(node, ast.Assign):
        return any(isinstance(t, ast.Name) and t.id == name for t in node.targets)
    if isinstance(node, ast.AnnAssign | ast.AugAssign):
        return isinstance(node.target, ast.Name) and node.target.id == name
    return False


def _final_binding(body: Sequence[ast.stmt], name: str) -> ast.stmt | None:
    """The statement that binds ``name`` last in a scope -- what pytest will see."""
    bound = [node for node in body if _binds(node, name)]
    return bound[-1] if bound else None


def _defines(tree: ast.Module, scope: Sequence[str]) -> bool:
    *classes, fn = scope
    body: Sequence[ast.stmt] = tree.body
    for cls in classes:
        node = _final_binding(body, cls)
        if not (isinstance(node, ast.ClassDef) and cls.startswith("Test")):
            return False
        body = node.body
    node = _final_binding(body, fn)
    return isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and fn.startswith("test")


def _test_exists(root: Path, test_id: str, cache: dict[Path, ast.Module | None]) -> bool:
    match = _NODE_ID.match(test_id)
    if match is None:
        return False
    if not _COLLECTABLE_FILE.match(Path(match["file"]).name):
        return False
    path = root / match["file"]
    if path not in cache:
        try:
            cache[path] = ast.parse(path.read_text(), filename=str(path))
        except (OSError, SyntaxError):
            cache[path] = None
    tree = cache[path]
    return tree is not None and _defines(tree, match["scope"].split("::"))


def check_manifest(entries: Sequence[Entry], root: Path) -> tuple[Result, ...]:
    """One ``Result`` per (entry, test id); ``found`` is False when the test is absent."""
    cache: dict[Path, ast.Module | None] = {}
    return tuple(
        Result(
            entry_id=entry.id,
            test_id=test_id,
            found=_test_exists(root, test_id, cache),
            deferred=entry.deferred is not None,
        )
        for entry in entries
        for test_id in entry.tests
    )


def _report(results: Sequence[Result]) -> tuple[str, bool]:
    missing = [r for r in results if not r.found and not r.deferred]
    deferred = [r for r in results if r.deferred]
    lines = [
        f"pre-mortem: {len(results)} test ids, {len(missing)} missing, {len(deferred)} deferred"
    ]
    lines.extend(f"  MISSING  {r.entry_id}: {r.test_id}" for r in missing)
    lines.extend(f"  DEFERRED {r.entry_id}: {r.test_id}" for r in deferred)
    return "\n".join(lines), not missing


def _owned_by(plan_text: str, done: Sequence[str]) -> frozenset[str]:
    tasks = {t.id: t for t in parse_tasks(extract_yaml_block(plan_text, TASKS_BLOCK))}
    unknown = [tid for tid in done if tid not in tasks]
    if unknown:
        raise PlanError(f"--done names unknown task(s) {unknown}")
    return frozenset(path for tid in done for path in tasks[tid].owns)


def _in_files(result: Result, files: frozenset[str]) -> bool:
    return result.test_id.split("::", 1)[0] in files


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check pre-mortem tests exist")
    parser.add_argument("plan", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repository root")
    parser.add_argument(
        "--done", nargs="+", metavar="TASK", help="only check tests owned by these finished tasks"
    )
    args = parser.parse_args(argv)
    if not args.plan.is_file():
        print(f"error: {args.plan} not found", file=sys.stderr)
        return 2
    text = args.plan.read_text()
    try:
        entries = parse_manifest(extract_yaml_block(text, BLOCK_NAME))
        files = _owned_by(text, args.done) if args.done else None
    except (ManifestError, PhaseDocError, PlanError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    results = check_manifest(entries, args.root)
    if files is not None:
        results = tuple(r for r in results if _in_files(r, files))
    report, ok = _report(results)
    print(report)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

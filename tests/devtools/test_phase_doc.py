"""Fenced-block extraction from phase PLAN.md files (phase-plan / phase-split skills)."""

from __future__ import annotations

import pytest

from ai_hedge_fund.devtools.phase_doc import PhaseDocError, extract_yaml_block

DOC = """# Phase 99 -- Plan

Some prose.

```yaml phase-tasks
- id: T1
  title: first
```

```python
print("not yaml")
```

```yaml phase-premortem
- id: PM1
```
"""


def test_extracts_named_block() -> None:
    assert extract_yaml_block(DOC, "phase-tasks") == [{"id": "T1", "title": "first"}]


def test_blocks_are_independent() -> None:
    assert extract_yaml_block(DOC, "phase-premortem") == [{"id": "PM1"}]


def test_missing_block_raises_naming_it() -> None:
    with pytest.raises(PhaseDocError, match="phase-decisions"):
        extract_yaml_block(DOC, "phase-decisions")


def test_duplicate_block_raises() -> None:
    doubled = DOC + "\n```yaml phase-tasks\n- id: T2\n```\n"
    with pytest.raises(PhaseDocError, match="more than one"):
        extract_yaml_block(doubled, "phase-tasks")


def test_non_list_block_raises() -> None:
    doc = "```yaml phase-tasks\nid: T1\n```\n"
    with pytest.raises(PhaseDocError, match="list"):
        extract_yaml_block(doc, "phase-tasks")


def test_invalid_yaml_raises_phase_doc_error() -> None:
    doc = "```yaml phase-tasks\n- id: [unclosed\n```\n"
    with pytest.raises(PhaseDocError, match="YAML"):
        extract_yaml_block(doc, "phase-tasks")


def test_unterminated_fence_raises() -> None:
    doc = "```yaml phase-tasks\n- id: T1\n"
    with pytest.raises(PhaseDocError, match="phase-tasks"):
        extract_yaml_block(doc, "phase-tasks")

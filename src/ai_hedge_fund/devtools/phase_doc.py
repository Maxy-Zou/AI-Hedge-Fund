"""Extract machine-readable YAML blocks from a phase PLAN.md.

A phase plan is prose for humans plus fenced blocks for tools, e.g.::

    ```yaml phase-tasks
    - id: T1
      ...
    ```

The info string after ``yaml`` names the block. Each name may appear once.
"""

from __future__ import annotations

import re
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

_FENCE_CLOSE = re.compile(r"^\s*```\s*$")


class PhaseDocError(ValueError):
    """The phase document is missing a block or the block is malformed."""


def _open_fence(name: str) -> re.Pattern[str]:
    return re.compile(rf"^\s*```yaml\s+{re.escape(name)}\s*$")


def _block_bodies(text: str, name: str) -> list[str]:
    opener = _open_fence(name)
    bodies: list[str] = []
    current: list[str] | None = None
    for line in text.splitlines():
        if current is None:
            if opener.match(line):
                current = []
        elif _FENCE_CLOSE.match(line):
            bodies.append("\n".join(current))
            current = None
        else:
            current.append(line)
    if current is not None:
        raise PhaseDocError(f"block '{name}' has no closing ``` fence")
    return bodies


def extract_yaml_block(text: str, name: str) -> list[dict[str, Any]]:
    """Return the parsed list from the single ```yaml <name>``` block in ``text``."""
    bodies = _block_bodies(text, name)
    if not bodies:
        raise PhaseDocError(f"no ```yaml {name}``` block found")
    if len(bodies) > 1:
        raise PhaseDocError(f"more than one ```yaml {name}``` block found")
    try:
        data = YAML(typ="safe").load(bodies[0])
    except YAMLError as exc:
        raise PhaseDocError(f"block '{name}' is not valid YAML: {exc}") from exc
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise PhaseDocError(f"block '{name}' must be a list of mappings")
    return data

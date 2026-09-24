"""Phase 10 criterion 10.1 -- the execution package computes, it never asks an LLM.

Tool-first (CLAUDE.md): sizing, decisions, and submission are pure Python. This
scans the shipped ``execution`` package for any LLM surface and fails if one
appears -- a test, not a review note (09-PREMORTEM #20).
"""

from __future__ import annotations

import pathlib

import ai_hedge_fund.execution as execution_pkg

PKG_DIR = pathlib.Path(execution_pkg.__file__).parent
FORBIDDEN = ("pydantic_ai", "ai_hedge_fund.agents", "agent.run", "create_agent", "langchain")


def test_execution_package_has_no_llm_surface() -> None:
    offenders: list[str] = []
    for path in PKG_DIR.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for needle in FORBIDDEN:
            if needle in text:
                offenders.append(f"{path.name}: {needle}")
    assert offenders == [], f"LLM surface found in execution package: {offenders}"

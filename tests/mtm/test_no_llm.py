"""Phase 11 criterion 11.1 -- no LLM anywhere in the P&L path (11-PREMORTEM #34, #35).

Two checks, because each misses what the other catches: a source scan of the
``mtm`` package and its CLIs (no LLM import can be added), and an import-closure
check in a clean interpreter (no LLM or graph module is pulled in transitively).
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

import ai_hedge_fund.mtm as mtm_pkg

SRC = pathlib.Path(mtm_pkg.__file__).parent
CLIS = [SRC.parent / "scripts" / "mark_to_market.py", SRC.parent / "scripts" / "ingest_fills.py"]
FORBIDDEN_TEXT = (
    "pydantic_ai",
    "anthropic",
    "langchain",
    "langgraph",
    "ai_hedge_fund.agents",
    "ai_hedge_fund.graph",
    "agent.run",
)
FORBIDDEN_MODULES = (
    "pydantic_ai",
    "anthropic",
    "langchain",
    "langchain_core",
    "langchain_anthropic",
    "langgraph",
    "ai_hedge_fund.agents",
    "ai_hedge_fund.graph",
)


def test_mtm_source_has_no_llm_surface() -> None:
    offenders = [
        f"{path.name}: {needle}"
        for path in [*SRC.rglob("*.py"), *CLIS]
        for needle in FORBIDDEN_TEXT
        if needle in path.read_text(encoding="utf-8")
    ]
    assert offenders == [], f"LLM/graph surface in the P&L path: {offenders}"


def test_mtm_does_not_import_graph() -> None:
    """11-PREMORTEM #35: graph imports mtm (stances at store time), never the reverse."""
    code = (
        "import sys\n"
        "import ai_hedge_fund.mtm.job, ai_hedge_fund.mtm.rollup, ai_hedge_fund.mtm.ingest\n"
        "import ai_hedge_fund.scripts.mark_to_market, ai_hedge_fund.scripts.ingest_fills\n"
        f"bad = sorted(m for m in sys.modules if m.startswith({FORBIDDEN_MODULES!r}))\n"
        "print(','.join(bad))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=120, check=False
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "", f"P&L path imports: {proc.stdout.strip()}"

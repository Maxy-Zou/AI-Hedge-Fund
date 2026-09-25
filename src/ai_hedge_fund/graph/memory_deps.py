"""Runtime dependencies for the Phase-7 memory nodes.

:class:`MemoryDeps` bundles the objects the memory nodes need: the
SQLAlchemy :class:`Session` used by episodic queries/writes, the
filesystem path to the belief documents directory, and a hit-limit
bound for recall queries (Pitfall 8). The deps container is frozen
(immutable) and is bound to the node at ``build_debate_pipeline``
time via a closure.

Mirrors :class:`ai_hedge_fund.graph.risk_deps.RiskDeps` verbatim in
shape (frozen ``@dataclass`` with a typing-only :class:`Session`
forward-reference; no SQLAlchemy import at runtime).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from ai_hedge_fund.mtm.policy import MtmPolicy, load_mtm_policy

if TYPE_CHECKING:  # pragma: no cover - typing-only
    from sqlalchemy.orm import Session


@dataclass(frozen=True)
class MemoryDeps:
    """Immutable dependency bundle for memory_recall_node + episodic_store_node.

    Attributes:
        db_session: Open SQLAlchemy session used by episodic queries
            (:func:`ai_hedge_fund.memory.recall.query_episodic`) and by
            the :class:`EpisodicMemory` append written by
            :func:`ai_hedge_fund.graph.nodes.episodic_store_node`.
        beliefs_path: Root directory containing belief YAML files.
            Expects ``tickers/`` and (optionally) ``sectors/`` subtrees.
            Looked up via
            :func:`ai_hedge_fund.memory.beliefs.belief_path_for_ticker`.
        recall_limit: Max episodic_memory rows to load per recall
            (default 10; Pitfall 8 -- bound the return set so the
            analyst prompts stay in budget).
        mtm_policy: Phase 11 attribution rules; ``episodic_store_node``
            freezes analyst stances with it at write time (11-SPEC A2).
            Defaults to ``config/mtm_policy.yaml``.
    """

    db_session: Session
    beliefs_path: Path
    recall_limit: int = 10
    mtm_policy: MtmPolicy = field(default_factory=load_mtm_policy)

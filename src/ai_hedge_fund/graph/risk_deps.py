"""Runtime dependencies for the Phase-6 risk manager node.

:class:`RiskDeps` bundles the objects the node needs to evaluate a
candidate: the SQLAlchemy :class:`Session` used by ``load_portfolio``, the
pandas DataFrame of daily log returns used by the correlation and
drawdown checks, and either a pre-built :class:`RiskPolicy` instance or a
path to a YAML file that ``load_policy`` can read.

The deps container is frozen (immutable) and is bound to the node at
``build_debate_pipeline`` time (Phase-6 wiring uses a closure; see
``pipeline.py``). Tests construct a ``RiskDeps`` directly and call the
node / pipeline synchronously via ``TestModel`` stubs.

Mirrors the ``ResearchDeps`` pattern from
``src/ai_hedge_fund/agents/research.py`` -- frozen ``@dataclass`` with
arbitrary-type fields and no hidden side effects.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing-only
    import pandas as pd
    from sqlalchemy.orm import Session

    from ai_hedge_fund.risk.policy import RiskPolicy


@dataclass(frozen=True)
class RiskDeps:
    """Immutable dependency bundle for ``risk_manager_node``.

    Attributes:
        db_session: Open SQLAlchemy session used to load the portfolio
            snapshot via :func:`ai_hedge_fund.risk.portfolio.load_portfolio`.
        returns: Wide pandas DataFrame of daily log returns (one column
            per ticker, date index). Consumed by the correlation and
            drawdown checks.
        policy: Pre-built :class:`RiskPolicy` instance. If set, overrides
            ``policy_path`` -- tests use this to avoid writing temp YAML.
        policy_path: Path to the YAML policy file. Consumed by
            :func:`ai_hedge_fund.risk.policy.load_policy` when ``policy``
            is ``None``. Defaults to ``None`` which causes ``load_policy``
            to use ``DEFAULT_POLICY_PATH`` (``config/risk_policy.yaml``).
    """

    db_session: Session
    returns: pd.DataFrame
    policy: RiskPolicy | None = None
    policy_path: Path | None = None

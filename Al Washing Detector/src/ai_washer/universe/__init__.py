"""Universe builder package for discovering target companies.

Note: UniverseBuilder and build_universe are imported lazily to avoid
circular imports (builder -> ingestion -> universe.types -> universe.__init__).
Import directly from ai_washer.universe.builder when needed.
"""

from ai_washer.universe.filters import deduplicate_by_cik, filter_by_market_cap
from ai_washer.universe.types import EFTSHit, EFTSResponse, MarketCapRange


def __getattr__(name: str):
    """Lazy import for builder module to avoid circular imports."""
    if name in ("UniverseBuilder", "UniverseBuildResult", "build_universe"):
        from ai_washer.universe.builder import (
            UniverseBuildResult,
            UniverseBuilder,
            build_universe,
        )

        if name == "UniverseBuilder":
            return UniverseBuilder
        if name == "UniverseBuildResult":
            return UniverseBuildResult
        return build_universe
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "EFTSHit",
    "EFTSResponse",
    "MarketCapRange",
    "UniverseBuildResult",
    "UniverseBuilder",
    "build_universe",
    "deduplicate_by_cik",
    "filter_by_market_cap",
]

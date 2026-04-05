# Stub — will be implemented in Task 2
from pydantic import BaseModel


class MarketSnapshot(BaseModel):
    """Stub — full implementation in Task 2."""
    pass


def build_snapshot(market: dict, candle: dict, *, suppress_result: bool = False) -> MarketSnapshot:
    """Stub — full implementation in Task 2."""
    raise NotImplementedError("MarketSnapshot not yet implemented")

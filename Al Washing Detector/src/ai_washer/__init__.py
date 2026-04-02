"""AI Washing Detector - quantifies the gap between AI claims and investment."""

from ai_washer.api import get_latest_scores, get_score, get_score_history

__version__ = "0.1.0"

__all__ = [
    "get_latest_scores",
    "get_score",
    "get_score_history",
]

"""Data source client wrappers.

Each client encapsulates a single external data source (SEC EDGAR, XBRL, etc.)
with retry logic and structured logging.
"""

from __future__ import annotations

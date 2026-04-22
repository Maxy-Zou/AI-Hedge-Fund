"""Belief memory I/O -- ruamel.yaml round-trip + human-edit guard.

This module is the SOLE mutation entry point for belief YAML files
(MEM-03 contract). All machine writers -- Plan 07-04 self-critique,
any future agent-authored belief update -- MUST call :func:`write_belief`.
Nothing else in the system is permitted to touch a belief file.

Threat mitigations:
    T-07-10 (YAML RCE): :func:`ruamel.yaml.YAML` is safe by default
            (does NOT instantiate arbitrary Python classes). The unsafe
            PyYAML full-loader call is forbidden; this module imports
            ruamel only. ASVS V10.
    T-07-11 (Path traversal): :func:`belief_path_for_ticker` and
            :func:`belief_path_for_sector` enforce regex guards
            (``[A-Z0-9.\\-]{1,10}`` for tickers;
            ``[A-Za-z][A-Za-z0-9 \\-_]{0,49}`` for sectors) BEFORE
            joining user-supplied strings into a filesystem path.
            ASVS V5.
    T-07-12 (Silent human-edit overwrite): :func:`write_belief` is the
            single writer; skip-if-human-edited + per-field locks +
            override-meta blacklist audit every patched field. Every
            skip is recorded with a structured reason code and logged
            via structlog.
    T-07-13 (Partial-write corruption): atomic tmp+rename
            (:meth:`pathlib.Path.replace` is atomic on POSIX) means a
            mid-write crash leaves the original file intact. ASVS V8.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import structlog
from ruamel.yaml import YAML

from ai_hedge_fund.schemas.memory import Belief

logger = structlog.get_logger(__name__)

# Ticker regex: uppercase alphanumerics plus dot and dash (for class-A/B
# shares like BRK.B or RDS-A). Max 10 chars. ``fullmatch`` pins both ends.
_TICKER_RE = re.compile(r"^[A-Z0-9.\-]{1,10}$")

# Sector regex: GICS-like sector names. Must start with a letter, may contain
# letters, digits, spaces, hyphens, and underscores. Max 50 chars (matches the
# ``episodic_memory.sector`` column width). ``fullmatch`` pins both ends.
_SECTOR_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 \-_]{0,49}$")

# These fields are human-authoritative; the writer NEVER touches them.
# A patch targeting any of them is refused with a structured reason code.
_OVERRIDE_META_FIELDS = frozenset({"human_edited", "edited_at", "field_locks"})

# Fields covered by the global ``human_edited=true`` guard. Field-level
# locks in ``field_locks`` apply to all other fields as well.
_HUMAN_GUARDED_FIELDS = frozenset({"thesis", "confidence"})

# Skip-reason codes (keep in sync with the test file).
_REASON_OVERRIDE_META = "writer_never_touches_override_meta"
_REASON_FIELD_LOCKED = "field_locked_by_human"
_REASON_HUMAN_EDITED = "human_edited_global_flag_set"


def _yaml() -> YAML:
    """Return a :class:`YAML` instance configured for round-trip safety.

    Round-trip mode (the default) preserves comments, key order, and
    quoting style. ``preserve_quotes = True`` keeps string quoting
    identical across a read/write cycle (matters for thesis strings
    that operators may quote for readability).
    """
    y = YAML()
    y.preserve_quotes = True
    return y


def belief_path_for_ticker(beliefs_dir: Path, ticker: str) -> Path:
    """Return ``beliefs_dir/tickers/<ticker>.yaml`` with a regex guard.

    Pitfall 9 (T-07-11): rejects path-traversal attempts (``"../foo"``),
    lowercase tickers, empty strings, and anything longer than 10 chars
    or containing non-ticker characters. Same regex the SEC ticker
    fields use elsewhere in the project.

    Args:
        beliefs_dir: Root directory containing the ``tickers/`` subtree.
        ticker: Uppercase ticker symbol (e.g., ``"AAPL"`` or ``"BRK.B"``).

    Returns:
        ``beliefs_dir / "tickers" / f"{ticker}.yaml"``.

    Raises:
        ValueError: ``ticker`` does not match ``[A-Z0-9.\\-]{1,10}``.
    """
    if not _TICKER_RE.fullmatch(ticker):
        raise ValueError(f"Invalid ticker {ticker!r} (expected [A-Z0-9.\\-]{{1,10}})")
    return beliefs_dir / "tickers" / f"{ticker}.yaml"


def belief_path_for_sector(beliefs_dir: Path, sector: str) -> Path:
    """Return ``beliefs_dir/sectors/<sector>.yaml`` with a regex guard.

    Defense-in-depth sibling of :func:`belief_path_for_ticker` (T-07-11
    analogue for the sector subtree). Rejects path-traversal attempts
    (``"../tickers/AAPL"``), empty strings, and anything longer than 50
    chars or containing non-sector characters. The regex tolerates spaces
    and hyphens to match GICS-like names (e.g., ``"Consumer Discretionary"``
    or ``"Health-Care"``).

    Args:
        beliefs_dir: Root directory containing the ``sectors/`` subtree.
        sector: Sector name (e.g., ``"Technology"`` or
            ``"Consumer Discretionary"``).

    Returns:
        ``beliefs_dir / "sectors" / f"{sector}.yaml"``.

    Raises:
        ValueError: ``sector`` does not match
            ``[A-Za-z][A-Za-z0-9 \\-_]{0,49}``.
    """
    if not _SECTOR_RE.fullmatch(sector):
        raise ValueError(
            f"Invalid sector {sector!r} (expected [A-Za-z][A-Za-z0-9 \\-_]{{0,49}})"
        )
    return beliefs_dir / "sectors" / f"{sector}.yaml"


def load_belief(path: Path) -> tuple[Belief, Any]:
    """Load and validate a belief YAML file.

    Uses :class:`ruamel.yaml.YAML` (safe by default) exclusively -- see
    T-07-10 in the module docstring. Returns BOTH a validated
    :class:`Belief` AND the round-trip raw object so that subsequent
    calls to :func:`write_belief` can preserve comments and key order.

    Args:
        path: Path to the belief YAML file.

    Returns:
        ``(belief, raw)`` tuple. ``raw`` is a ruamel ``CommentedMap``
        suitable for :func:`write_belief`; write operations MUST be
        applied to this object (not to ``Belief.model_dump()``) so
        comments survive.

    Raises:
        FileNotFoundError: File does not exist.
        ValueError: File is empty.
        pydantic.ValidationError: YAML is not a valid :class:`Belief`.
    """
    parser = _yaml()
    raw = parser.load(path)
    if raw is None:
        raise ValueError(f"Belief file {path} is empty")
    belief = Belief.model_validate(dict(raw))
    return belief, raw


def write_belief(
    path: Path,
    raw: Any,
    patches: dict[str, Any],
    *,
    skip_if_human_edited: bool = True,
) -> dict[str, Any]:
    """Apply ``patches`` to ``raw`` and atomically rewrite ``path``.

    Override-meta fields (``human_edited``, ``edited_at``,
    ``field_locks``) are NEVER written by this function -- patches
    targeting them are refused with reason
    ``writer_never_touches_override_meta``. Per-field locks in
    ``raw['field_locks']`` veto the corresponding patch. When
    ``raw['human_edited']`` is true and ``skip_if_human_edited`` is
    true (the default), the global guard vetoes ``thesis`` and
    ``confidence`` patches regardless of ``field_locks``.

    The file is rewritten via tmp+rename so a crash mid-write does not
    corrupt the original (T-07-13). If :meth:`YAML.dump` raises, the
    ``.tmp`` file is cleaned up and the exception propagates with the
    target file unchanged.

    Version increments by 1 iff at least one patch was applied; a
    fully-skipped write does NOT bump the version.

    Args:
        path: Target YAML file (same file :func:`load_belief` read).
        raw: Round-trip object from :func:`load_belief`.
        patches: ``{field: new_value}`` map of proposed writes.
        skip_if_human_edited: When true (default), block thesis and
            confidence patches when the YAML has ``human_edited: true``.
            Set false only in offline repair scripts where an operator
            has explicitly asked to override.

    Returns:
        Audit dict ``{"applied": list[str], "skipped": dict[str, str]}``.
        Reason codes are one of ``writer_never_touches_override_meta``,
        ``field_locked_by_human``, ``human_edited_global_flag_set``.
    """
    applied: list[str] = []
    skipped: dict[str, str] = {}
    locks = raw.get("field_locks", {}) or {}
    human_edited = bool(raw.get("human_edited"))

    for field, value in patches.items():
        if field in _OVERRIDE_META_FIELDS:
            skipped[field] = _REASON_OVERRIDE_META
            continue
        if locks.get(field) is True:
            skipped[field] = _REASON_FIELD_LOCKED
            continue
        if human_edited and skip_if_human_edited and field in _HUMAN_GUARDED_FIELDS:
            skipped[field] = _REASON_HUMAN_EDITED
            continue
        raw[field] = value
        applied.append(field)

    if applied:
        raw["version"] = int(raw.get("version", 0)) + 1

    parser = _yaml()
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with tmp.open("w") as fh:
            parser.dump(raw, fh)
        tmp.replace(path)  # atomic on POSIX
    except Exception:
        # Clean up the tmp if the rename didn't happen. ``missing_ok``
        # protects against the case where the tmp was never created.
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise

    logger.info(
        "belief_write",
        path=str(path),
        applied=applied,
        skipped=skipped,
        new_version=raw.get("version"),
    )
    return {"applied": applied, "skipped": skipped}

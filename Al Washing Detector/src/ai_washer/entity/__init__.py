"""Entity resolution package for mapping companies across data sources."""

from ai_washer.entity.normalizer import LEGAL_SUFFIXES, normalize_company_name
from ai_washer.entity.resolver import EntityResolver, resolve_entity
from ai_washer.entity.types import (
    AliasesSchema,
    EntityResolutionResult,
    ResolutionMetadata,
    ResolutionMethod,
)

__all__ = [
    "AliasesSchema",
    "EntityResolutionResult",
    "EntityResolver",
    "LEGAL_SUFFIXES",
    "ResolutionMetadata",
    "ResolutionMethod",
    "normalize_company_name",
    "resolve_entity",
]

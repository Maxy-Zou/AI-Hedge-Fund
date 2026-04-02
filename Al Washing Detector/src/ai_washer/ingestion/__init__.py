"""Data ingestion package for SEC, patents, GitHub, and other data sources."""

from ai_washer.ingestion.edgar_client import (
    EdgarFactsClient,
    get_cik_ticker_mapping,
    get_entity_public_float,
    pad_cik,
    strip_cik,
)
from ai_washer.ingestion.efts_client import EFTSClient, search_filings
from ai_washer.ingestion.filing_client import FilingClient
from ai_washer.ingestion.filing_collector import FilingCollector
from ai_washer.ingestion.patent_client import PatentClientError, PatentSearchClient
from ai_washer.ingestion.patent_collector import PatentCollector
from ai_washer.ingestion.patent_types import (
    CPC_AI_PREFIXES,
    PATENT_SIGNAL_VERSION,
    PatentCollectionResult,
    PatentForScoring,
    PatentRecord,
)
from ai_washer.ingestion.github_client import GitHubClient, GitHubClientError
from ai_washer.ingestion.github_collector import GitHubCollector
from ai_washer.ingestion.github_types import (
    GITHUB_SIGNAL_VERSION,
    GitHubCollectionResult,
    GitHubOrgSnapshot,
    GitHubRepoRecord,
    ML_FRAMEWORK_PATTERNS,
    ML_LANGUAGES,
)
from ai_washer.ingestion.types import (
    CollectionResult,
    FilingData,
    FilingSections,
    XBRLFactRecord,
    XBRL_TAG_GROUPS,
)
from ai_washer.ingestion.xbrl_extractor import (
    XBRLExtractor,
    deduplicate_by_period,
    extract_all_facts,
    extract_facts_for_concept,
)

__all__ = [
    "CPC_AI_PREFIXES",
    "CollectionResult",
    "EFTSClient",
    "EdgarFactsClient",
    "FilingClient",
    "FilingCollector",
    "FilingData",
    "FilingSections",
    "GITHUB_SIGNAL_VERSION",
    "GitHubClient",
    "GitHubClientError",
    "GitHubCollectionResult",
    "GitHubCollector",
    "GitHubOrgSnapshot",
    "GitHubRepoRecord",
    "ML_FRAMEWORK_PATTERNS",
    "ML_LANGUAGES",
    "PATENT_SIGNAL_VERSION",
    "PatentClientError",
    "PatentCollectionResult",
    "PatentCollector",
    "PatentForScoring",
    "PatentRecord",
    "PatentSearchClient",
    "XBRLExtractor",
    "XBRLFactRecord",
    "XBRL_TAG_GROUPS",
    "deduplicate_by_period",
    "extract_all_facts",
    "extract_facts_for_concept",
    "get_cik_ticker_mapping",
    "get_entity_public_float",
    "pad_cik",
    "search_filings",
    "strip_cik",
]

"""Unit tests for company name normalization.

Tests normalize_company_name which strips legal suffixes, normalizes
case/whitespace/punctuation for entity resolution matching.
"""

from __future__ import annotations

import pytest

from ai_washer.entity.normalizer import LEGAL_SUFFIXES, normalize_company_name


class TestNormalizeCompanyName:
    """Parametrized tests for standard company name normalization."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("ALPHABET INC", "ALPHABET"),
            ("Meta Platforms, Inc.", "META PLATFORMS"),
            ("AMAZON COM INC", "AMAZON COM"),
            ("  Apple   Inc.  ", "APPLE"),
            ("NVIDIA CORPORATION", "NVIDIA"),
            ("INTERNATIONAL BUSINESS MACHINES CORP.", "INTERNATIONAL BUSINESS MACHINES"),
            ("BERKSHIRE HATHAWAY INC", "BERKSHIRE HATHAWAY"),
            ("ACME CO", "ACME"),
            ("ACME LIMITED", "ACME"),
            ("ACME LP", "ACME"),
            ("Acme inc", "ACME"),
            ("Acme, Corp.", "ACME"),
            # Additional suffix variants
            ("TESLA INC.", "TESLA"),
            ("MICROSOFT CORP", "MICROSOFT"),
            ("FORD MOTOR COMPANY", "FORD MOTOR"),
            ("GENERAL ELECTRIC CO.", "GENERAL ELECTRIC"),
            ("BROADCOM LTD", "BROADCOM"),
            ("BROADCOM LTD.", "BROADCOM"),
            ("SHELL PLC", "SHELL"),
            ("UNILEVER N.V.", "UNILEVER"),
            ("AIRBUS S.A.", "AIRBUS"),
            ("SIEMENS AG", "SIEMENS"),
            ("ACME L.P.", "ACME"),
            ("ACME P.L.C.", "ACME"),
            ("SOME COMPANY LLC", "SOME COMPANY"),
            ("ACME INCORPORATED", "ACME"),
        ],
        ids=[
            "alphabet_inc",
            "meta_platforms_comma_inc_dot",
            "amazon_com_inc",
            "apple_extra_whitespace",
            "nvidia_corporation",
            "ibm_corp_dot",
            "berkshire_hathaway_inc",
            "acme_co",
            "acme_limited",
            "acme_lp",
            "acme_lowercase_inc",
            "acme_comma_corp_dot",
            "tesla_inc_dot",
            "microsoft_corp",
            "ford_motor_company",
            "ge_co_dot",
            "broadcom_ltd",
            "broadcom_ltd_dot",
            "shell_plc",
            "unilever_nv",
            "airbus_sa",
            "siemens_ag",
            "acme_lp_with_dots",
            "acme_plc_with_dots",
            "some_company_llc",
            "acme_incorporated",
        ],
    )
    def test_normalize(self, raw: str, expected: str) -> None:
        assert normalize_company_name(raw) == expected


class TestEdgeCases:
    """Tests for edge cases in company name normalization."""

    def test_empty_string(self) -> None:
        assert normalize_company_name("") == ""

    def test_single_character(self) -> None:
        assert normalize_company_name("A") == "A"

    def test_name_equals_suffix(self) -> None:
        """When the entire name is a suffix word, it should be preserved."""
        assert normalize_company_name("INC") == "INC"

    def test_whitespace_only(self) -> None:
        assert normalize_company_name("   ") == ""

    def test_already_clean(self) -> None:
        assert normalize_company_name("ALPHABET") == "ALPHABET"

    def test_preserves_internal_structure(self) -> None:
        """Hyphens and other non-comma/period punctuation are preserved."""
        assert normalize_company_name("HEWLETT-PACKARD INC") == "HEWLETT-PACKARD"

    def test_multiple_suffix_words_only_strips_trailing(self) -> None:
        """Only the trailing suffix should be stripped, not internal matches."""
        assert normalize_company_name("INC SYSTEMS INC") == "INC SYSTEMS"


class TestLegalSuffixes:
    """Tests for the LEGAL_SUFFIXES constant."""

    def test_suffixes_is_tuple(self) -> None:
        assert isinstance(LEGAL_SUFFIXES, tuple)

    def test_suffixes_not_empty(self) -> None:
        assert len(LEGAL_SUFFIXES) > 0

    def test_longer_suffixes_first(self) -> None:
        """Longer suffixes must come before shorter ones to prevent partial matches.
        E.g., INCORPORATED before INC."""
        incorporated_idx = None
        inc_idx = None
        for i, suffix in enumerate(LEGAL_SUFFIXES):
            if suffix == " INCORPORATED":
                incorporated_idx = i
            if suffix == " INC":
                inc_idx = i
        assert incorporated_idx is not None, "INCORPORATED not in LEGAL_SUFFIXES"
        assert inc_idx is not None, "INC not in LEGAL_SUFFIXES"
        assert incorporated_idx < inc_idx, "INCORPORATED must come before INC"

    def test_corporation_before_corp(self) -> None:
        corporation_idx = None
        corp_idx = None
        for i, suffix in enumerate(LEGAL_SUFFIXES):
            if suffix == " CORPORATION":
                corporation_idx = i
            if suffix == " CORP":
                corp_idx = i
        assert corporation_idx is not None
        assert corp_idx is not None
        assert corporation_idx < corp_idx, "CORPORATION must come before CORP"

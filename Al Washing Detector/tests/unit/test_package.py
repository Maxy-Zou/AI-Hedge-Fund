"""Tests for package installation and imports."""

import re


def test_import_ai_washer():
    import ai_washer

    assert hasattr(ai_washer, "__version__")


def test_version_is_semver():
    from ai_washer import __version__

    assert re.match(r"^\d+\.\d+\.\d+", __version__)


def test_cli_app_exists():
    from ai_washer.cli import app

    assert app is not None

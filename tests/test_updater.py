
import pytest
import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from updater import (
    parse_semver,
    format_version,
    is_newer_version,
    _is_sha256,
    validate_manifest,
    UpdateError,
    UpdateInfo,
    check_for_update,
    APP_VERSION
)

def test_parse_semver():
    assert parse_semver("1.0.0") == (1, 0, 0)
    assert parse_semver("v1.2.3") == (1, 2, 3)
    assert parse_semver("2.0") is None
    assert parse_semver("") is None

def test_format_version():
    assert format_version((1, 2, 3)) == "1.2.3"

def test_is_newer_version():
    assert is_newer_version((1, 0, 0), (1, 0, 1)) is True
    assert is_newer_version((1, 0, 0), (2, 0, 0)) is True
    assert is_newer_version((1, 1, 0), (1, 0, 1)) is False
    assert is_newer_version((1, 0, 0), (1, 0, 0)) is False

def test_is_sha256():
    valid_sha = "a" * 64
    assert _is_sha256(valid_sha) is True
    assert _is_sha256("short") is False
    assert _is_sha256("z" * 64) is False # Not hex

def test_validate_manifest_success():
    release = {"tag_name": "v1.0.0"}
    manifest = {
        "version": "1.0.0",
        "asset_filename": "app.zip",
        "download_url": "http://example.com/app.zip",
        "sha256": "a" * 64,
        "published_at": "2023-01-01"
    }
    validated = validate_manifest(manifest, release)
    assert validated == manifest

def test_validate_manifest_missing_fields():
    release = {"tag_name": "v1.0.0"}
    manifest = {
        "version": "1.0.0"
    }
    with pytest.raises(UpdateError):
        validate_manifest(manifest, release)

def test_validate_manifest_version_mismatch():
    release = {"tag_name": "v1.0.1"}
    manifest = {
        "version": "1.0.0",
        "asset_filename": "app.zip",
        "download_url": "http://example.com/app.zip",
        "sha256": "a" * 64,
        "published_at": "2023-01-01"
    }
    with pytest.raises(UpdateError):
        validate_manifest(manifest, release)

@patch('updater.fetch_latest_release')
@patch('updater.download_manifest')
def test_check_for_update_available(mock_download, mock_fetch):
    mock_fetch.return_value = {"tag_name": "v99.99.99"} # Definitely newer
    mock_download.return_value = {
        "version": "99.99.99",
        "asset_filename": "app.zip",
        "download_url": "http://example.com/app.zip",
        "sha256": "a" * 64,
        "published_at": "2023-01-01"
    }
    
    # We rely on APP_VERSION being importable and smaller than 99.99.99
    update_info = check_for_update()
    assert update_info is not None
    assert update_info.latest_version == "99.99.99"

@patch('updater.fetch_latest_release')
def test_check_for_update_none(mock_fetch):
    mock_fetch.return_value = {"tag_name": "v0.0.0"} # Very old
    update_info = check_for_update()
    assert update_info is None

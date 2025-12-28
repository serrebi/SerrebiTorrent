import base64
import binascii

import pytest
from hypothesis import given, strategies as st

import torrent_parsing


def test_parse_magnet_infohash_hex():
    info_hash = "0123456789abcdef0123456789abcdef01234567"
    url = f"magnet:?xt=urn:btih:{info_hash}"
    assert torrent_parsing.parse_magnet_infohash(url) == info_hash


def test_parse_magnet_infohash_base32():
    raw = b"\x01" * 20
    b32 = base64.b32encode(raw).decode("ascii")
    url = f"magnet:?xt=urn:btih:{b32}"
    expected = binascii.hexlify(raw).decode("ascii")
    assert torrent_parsing.parse_magnet_infohash(url) == expected


def test_parse_magnet_infohash_invalid():
    assert torrent_parsing.parse_magnet_infohash("magnet:?xt=urn:btih:ZZZ") is None


@given(st.text(min_size=0, max_size=200))
def test_parse_magnet_infohash_never_crashes(text):
    result = torrent_parsing.parse_magnet_infohash(text)
    if result is not None:
        assert len(result) in (40, 64)
        assert all(c in "0123456789abcdef" for c in result)


@pytest.mark.skipif(torrent_parsing.lt is None, reason="libtorrent not installed")
def test_safe_torrent_info_hash_invalid_bytes():
    assert torrent_parsing.safe_torrent_info_hash(b"not a torrent") is None

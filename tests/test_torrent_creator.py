import os
import tempfile

import pytest

import torrent_creator
import torrent_parsing


@pytest.mark.skipif(torrent_creator.lt is None, reason="libtorrent not installed")
def test_create_torrent_bytes_roundtrip():
    with tempfile.TemporaryDirectory() as tmp_dir:
        src = os.path.join(tmp_dir, "file.txt")
        with open(src, "wb") as f:
            f.write(b"hello world")

        torrent_bytes, magnet, info_hash = torrent_creator.create_torrent_bytes(
            src,
            trackers=[],
        )

        assert torrent_bytes
        assert info_hash
        assert magnet.startswith("magnet:?xt=urn:btih:")
        assert torrent_parsing.safe_torrent_info_hash(torrent_bytes) == info_hash


@pytest.mark.skipif(torrent_creator.lt is None, reason="libtorrent not installed")
def test_create_torrent_bytes_missing_path():
    with pytest.raises(FileNotFoundError):
        torrent_creator.create_torrent_bytes("does_not_exist", trackers=[])

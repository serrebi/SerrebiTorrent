import binascii
import tempfile
import unittest
from unittest import mock

import clients


class FakeQbittorrentApiClient:
    def __init__(self, host=None, username=None, password=None):
        self.calls = []

    def auth_log_in(self):
        return None

    def torrents_delete(self, torrent_hashes=None, delete_files=False):
        self.calls.append((torrent_hashes, delete_files))


class FakeTransmissionApiClient:
    def __init__(self, host=None, port=None, username=None, password=None, protocol=None):
        self.calls = []

    def remove_torrent(self, torrent_id, delete_data=False):
        self.calls.append((torrent_id, delete_data))


class FakeSession:
    def __init__(self):
        self.calls = []

    def remove_torrent(self, info_hash, delete_files=False):
        self.calls.append((info_hash, delete_files))


class RemoveTorrentsTests(unittest.TestCase):
    def test_qbittorrent_remove_torrents_normalizes_bytes_and_delete_flag(self):
        hash_bytes = b"0123456789abcdef0123456789abcdef01234567"
        with mock.patch.object(clients.qbittorrentapi, "Client", FakeQbittorrentApiClient):
            client = clients.QBittorrentClient("localhost", "user", "pass")
            client.remove_torrents([hash_bytes], df="false")

            self.assertEqual(len(client.c.calls), 1)
            torrent_hashes, delete_files = client.c.calls[0]
            self.assertEqual(torrent_hashes, [hash_bytes.decode("ascii")])
            self.assertFalse(delete_files)

    def test_qbittorrent_remove_multiple_torrents_efficiently(self):
        h1 = "0000000000000000000000000000000000000001"
        h2 = "0000000000000000000000000000000000000002"
        with mock.patch.object(clients.qbittorrentapi, "Client", FakeQbittorrentApiClient):
            client = clients.QBittorrentClient("localhost", "user", "pass")
            client.remove_torrents([h1, h2], df=True)

            # Should be a single call with a list of hashes
            self.assertEqual(len(client.c.calls), 1)
            hashes, delete_files = client.c.calls[0]
            self.assertEqual(hashes, [h1, h2])
            self.assertTrue(delete_files)

    def test_transmission_remove_torrents_parses_delete_flag(self):
        with mock.patch.object(clients, "TransClient", FakeTransmissionApiClient):
            client = clients.TransmissionClient("http://localhost:9091", "user", "pass")
            client.remove_torrents(["abc123"], df="false")

            self.assertEqual(client.c.calls, [("abc123", False)])

    def test_local_remove_torrents_normalizes_raw_hash_and_delete_flag(self):
        raw_hash = b"\x01" * 20
        expected_hash = binascii.hexlify(raw_hash).decode("ascii")
        fake_session = FakeSession()

        class FakeSessionManager:
            @classmethod
            def get_instance(cls):
                return fake_session

        with mock.patch.object(clients, "SessionManager", FakeSessionManager), \
            mock.patch.object(clients, "lt", object()):
            with tempfile.TemporaryDirectory() as temp_dir:
                client = clients.LocalClient(temp_dir)
                client.remove_torrents([raw_hash], df="false")

        self.assertEqual(fake_session.calls, [(expected_hash, False)])


if __name__ == "__main__":
    unittest.main()

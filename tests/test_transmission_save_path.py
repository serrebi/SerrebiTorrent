from unittest import mock

import clients


class FakeTorrent:
    def __init__(self, download_dir=None, downloadDir=None):
        self.download_dir = download_dir
        self.downloadDir = downloadDir


class FakeTransClient:
    def __init__(self, host=None, port=None, username=None, password=None, protocol=None):
        pass

    def get_torrent(self, torrent_id):
        return FakeTorrent(download_dir="C:\\Downloads")


class FakeTransClientFallback:
    def __init__(self, host=None, port=None, username=None, password=None, protocol=None):
        pass

    def get_torrent(self, torrent_id):
        return FakeTorrent(download_dir=None, downloadDir="C:\\Legacy")


def test_transmission_save_path_prefers_download_dir():
    with mock.patch.object(clients, "TransClient", FakeTransClient):
        client = clients.TransmissionClient("http://localhost:9091", "user", "pass")
        assert client.get_torrent_save_path("abc") == "C:\\Downloads"


def test_transmission_save_path_falls_back_downloadDir():
    with mock.patch.object(clients, "TransClient", FakeTransClientFallback):
        client = clients.TransmissionClient("http://localhost:9091", "user", "pass")
        assert client.get_torrent_save_path("abc") == "C:\\Legacy"


import pytest
import sys
import os

# Add parent directory to path to import list_torrents
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from list_torrents import format_size, format_time, get_status

class MockTorrent:
    def __init__(self, state):
        self.state = state

def test_format_size():
    assert format_size(100) == "100.00 B"
    assert format_size(1024) == "1.00 KB"
    assert format_size(1024 * 1024) == "1.00 MB"
    assert format_size(1024 * 1024 * 1024) == "1.00 GB"
    assert format_size(1024 * 1024 * 1024 * 1024) == "1.00 TB"

def test_format_time():
    assert format_time(-1) == "∞"
    assert format_time(8640000) == "∞"
    assert format_time(30) == "30s"
    assert format_time(90) == "1m 30s"
    assert format_time(3600) == "1h 0m 0s"
    assert format_time(3665) == "1h 1m 5s"
    assert format_time(86400) == "1d 0h 0m"
    assert format_time(90065) == "1d 1h 1m"

def test_get_status():
    assert get_status(MockTorrent('downloading')) == "Downloading"
    assert get_status(MockTorrent('uploading')) == "Seeding"
    assert get_status(MockTorrent('metaDL')) == "Downloading"
    assert get_status(MockTorrent('pausedDL')) == "Paused"
    assert get_status(MockTorrent('checkingUP')) == "Checking"
    assert get_status(MockTorrent('stalledDL')) == "Stalled"
    assert get_status(MockTorrent('queuedDL')) == "Queued DL"
    assert get_status(MockTorrent('queuedUP')) == "Queued UP"
    assert get_status(MockTorrent('unknown')) == "Unknown"

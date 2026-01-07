
import pytest
import sys
import os
from unittest.mock import MagicMock, patch

# Robust mocking of libtorrent
if 'session_manager' in sys.modules:
    del sys.modules['session_manager']
if 'libtorrent' in sys.modules:
    del sys.modules['libtorrent']

mock_lt = MagicMock()
sys.modules['libtorrent'] = mock_lt

mock_lt.proxy_type_t = MagicMock()
mock_lt.proxy_type_t.none = 0
mock_lt.proxy_type_t.socks4 = 1
mock_lt.proxy_type_t.socks5 = 2
mock_lt.proxy_type_t.socks5_pw = 3
mock_lt.proxy_type_t.http = 4
mock_lt.proxy_type_t.http_pw = 5

mock_lt.alert = MagicMock()
mock_lt.alert.category_t = MagicMock()
mock_lt.alert.category_t.status_notification = 1
mock_lt.alert.category_t.storage_notification = 2
mock_lt.alert.category_t.error_notification = 4

mock_lt.resume_data_flags_t = MagicMock()
mock_lt.resume_data_flags_t.flush_disk_cache = 1

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from session_manager import SessionManager

@pytest.fixture
def session_manager():
    # Reset singleton
    SessionManager._instance = None
    
    # Reset mock_lt session
    mock_lt.session.return_value.reset_mock()
    
    with patch('session_manager.get_state_dir', return_value='.'):
        with patch('os.path.exists', return_value=False):
            with patch('session_manager.ConfigManager') as MockCM:
                MockCM.return_value.get_preferences.return_value = {}
                with patch('os.listdir', return_value=[]):
                    sm = SessionManager.get_instance()
                    # Reset mock calls that happened during init so we can test clean
                    sm.ses.reset_mock()
                    return sm

def test_singleton(session_manager):
    sm2 = SessionManager.get_instance()
    assert session_manager is sm2

def test_apply_preferences(session_manager):
    prefs = {
        'dl_limit': 1000,
        'ul_limit': 2000,
        'max_connections': 50
    }
    session_manager.apply_preferences(prefs)
    
    # Check if ses.apply_settings was called
    session_manager.ses.apply_settings.assert_called_once()
    call_args = session_manager.ses.apply_settings.call_args[0][0]
    
    assert call_args['download_rate_limit'] == 1000
    assert call_args['upload_rate_limit'] == 2000
    assert call_args['connections_limit'] == 50

def test_add_magnet(session_manager):
    magnet = "magnet:?xt=urn:btih:abcdef"
    save_path = "/tmp"
    
    mock_params = MagicMock()
    mock_params.info_hashes.v1 = "abcdef"
    mock_params.info_hashes.has_v1.return_value = True
    
    mock_lt.parse_magnet_uri.return_value = mock_params
    
    with patch.object(session_manager, '_find_handle', return_value=None):
         session_manager.add_magnet(magnet, save_path)
    
    session_manager.ses.add_torrent.assert_called()
    assert "abcdef" in session_manager.torrents_db
    assert session_manager.torrents_db["abcdef"]['save_path'] == save_path

def test_remove_torrent(session_manager):
    info_hash = "abcdef"
    session_manager.torrents_db[info_hash] = {'save_path': '/tmp'}
    
    mock_handle = MagicMock()
    with patch.object(session_manager, '_find_handle', return_value=mock_handle):
         mock_lt.remove_flags_t = MagicMock()
         mock_lt.remove_flags_t.delete_files = 1
         
         session_manager.remove_torrent(info_hash)
         
         session_manager.ses.remove_torrent.assert_called()
         assert info_hash not in session_manager.torrents_db

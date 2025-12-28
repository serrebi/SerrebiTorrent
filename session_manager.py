import os
import threading
import time

from libtorrent_env import prepare_libtorrent_dlls

prepare_libtorrent_dlls()

try:
    import libtorrent as lt
except ImportError:
    lt = None

from app_paths import get_state_dir
from config_manager import ConfigManager

class SessionManager:
    _instance = None
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = SessionManager()
        return cls._instance

    def __init__(self):
        if not lt:
            raise RuntimeError("libtorrent not available")
            
        self.state_dir = get_state_dir()

        # Create Session
        self.ses = lt.session()
        
        # Load preferences
        cm = ConfigManager()
        prefs = cm.get_preferences()
        self.apply_preferences(prefs)
        
        self.alerts_queue = []
        self.running = True
        self.pending_saves = set()  # Track info_hashes for pending resume data
        self.alert_thread = threading.Thread(target=self._alert_loop, daemon=True)
        self.alert_thread.start()
        
        self.load_state()

    def _info_hash_key(self, info_hashes):
        if info_hashes is None:
            return ""
        try:
            if hasattr(info_hashes, "has_v1") and info_hashes.has_v1():
                return str(info_hashes.v1)
            if hasattr(info_hashes, "has_v2") and info_hashes.has_v2():
                return str(info_hashes.v2)
        except Exception:
            pass
        try:
            return str(info_hashes)
        except Exception:
            return ""

    def _handle_hash_key(self, handle):
        try:
            if hasattr(handle, "info_hashes"):
                return self._info_hash_key(handle.info_hashes())
        except Exception:
            pass
        try:
            return self._info_hash_key(handle.info_hash())
        except Exception:
            return ""

    def apply_preferences(self, prefs):
        # Proxy Mapping
        # 0=None, 1=SOCKS4, 2=SOCKS5, 3=HTTP
        p_type = prefs.get('proxy_type', 0)
        lt_proxy_type = lt.proxy_type_t.none
        
        if p_type == 1:
            lt_proxy_type = lt.proxy_type_t.socks4
        elif p_type == 2:
            lt_proxy_type = lt.proxy_type_t.socks5
            if prefs.get('proxy_user'):
                lt_proxy_type = lt.proxy_type_t.socks5_pw
        elif p_type == 3:
            lt_proxy_type = lt.proxy_type_t.http
            if prefs.get('proxy_user'):
                lt_proxy_type = lt.proxy_type_t.http_pw

        settings = {
            'user_agent': 'qBittorrent/4.6.3',
            'peer_fingerprint': b'-qB4630-',
            'enable_dht': prefs.get('enable_dht', True),
            'enable_lsd': prefs.get('enable_lsd', True),
            'enable_upnp': prefs.get('enable_upnp', True),
            'enable_natpmp': prefs.get('enable_natpmp', True),
            'alert_mask': lt.alert.category_t.status_notification | lt.alert.category_t.storage_notification | lt.alert.category_t.error_notification,
            
            # Limits
            'connections_limit': prefs.get('max_connections', -1),
            'active_downloads': -1, # Unlimited active
            'active_seeds': -1,
            'active_limit': -1, # Total active torrents
            # 'upload_slots_limit': prefs.get('max_uploads', -1), # Removed as it causes error in newer libtorrent
            'download_rate_limit': prefs.get('dl_limit', 0),
            'upload_rate_limit': prefs.get('ul_limit', 0),

            # Proxy
            'proxy_type': lt_proxy_type,
            'proxy_hostname': prefs.get('proxy_host', ''),
            'proxy_port': prefs.get('proxy_port', 8080),
            'proxy_username': prefs.get('proxy_user', ''),
            'proxy_password': prefs.get('proxy_password', '')
        }
        
        # Listen Port
        port = prefs.get('listen_port', 6881)
        self.ses.listen_on(port, port + 10)
        
        self.ses.apply_settings(settings)

    def _alert_loop(self):
        while self.running:
            try:
                if not self.ses:
                    time.sleep(0.5)
                    continue
                if self.ses.wait_for_alert(1000):
                    alerts = self.ses.pop_alerts()
                    for alert in alerts:
                        if isinstance(alert, lt.save_resume_data_alert):
                            self._handle_save_resume(alert)
                        elif isinstance(alert, lt.save_resume_data_failed_alert):
                            ih = self._info_hash_key(alert.params.info_hashes)
                            if ih:
                                self.pending_saves.discard(ih)
                        elif isinstance(alert, lt.metadata_received_alert):
                            # ... handle metadata ...
                            pass
            except Exception as e:
                # Suppress session-level RTTI/Access violations
                time.sleep(1)
                continue

    def _handle_save_resume(self, alert):
        # alert.params is add_torrent_params
        # alert.resume_data is list of bytes (if bencoded) usually?
        # In lt 2.0, params has the resume data inside it?
        # Actually alert.params is an add_torrent_params object.
        # We can pickle it or bencode it.
        
        # Save to disk
        try:
            ih = self._info_hash_key(alert.params.info_hashes)
            if not ih:
                return
            self.pending_saves.discard(ih)
            
            path = os.path.join(self.state_dir, ih + '.resume')
            
            # Serialize add_torrent_params
            # lt.write_resume_data(add_torrent_params) -> bencoded bytes
            data = lt.write_resume_data(alert.params)
            with open(path, 'wb') as f:
                f.write(data)
        except Exception as e:
            print(f"Error writing resume data: {e}")

    def add_torrent_file(self, file_content, save_path, file_priorities=None):
        info = lt.torrent_info(file_content)
        ih = ""
        try:
            if hasattr(info, "info_hashes"):
                ih = self._info_hash_key(info.info_hashes())
        except Exception:
            ih = ""
        if not ih:
            ih = self._info_hash_key(info.info_hash())
        
        # Check if already exists
        if self._find_handle(ih):
            raise ValueError(f"Torrent with hash {ih} already exists.")

        # Save .torrent file for restoration
        tpath = os.path.join(self.state_dir, ih + '.torrent')
        with open(tpath, 'wb') as f:
            f.write(file_content)
            
        params = {'ti': info, 'save_path': save_path}
        if file_priorities:
            params['file_priorities'] = file_priorities
            
        self.ses.add_torrent(params)

    def add_magnet(self, url, save_path):
        params = lt.parse_magnet_uri(url)
        params.save_path = save_path
        
        # Check if already exists from magnet's hash
        ih = self._info_hash_key(params.info_hashes)
        if ih and self._find_handle(ih):
            raise ValueError(f"Magnet with hash {ih} already exists.")
        
        # We should also save the magnet URI itself for robust restoration if metadata is not fetched quickly
        # Or let resume data handle it.
        # For now, just adding it directly to session.
        self.ses.add_torrent(params)

    def load_state(self):
        print("Loading session state...")
        loaded_hashes = set()
        default_save_path = os.path.expanduser('~') # Fallback if save_path can't be determined
        
        # 1. Scan for .resume files and try to add them
        if os.path.exists(self.state_dir):
            for f in os.listdir(self.state_dir):
                if f.endswith('.resume'):
                    try:
                        with open(os.path.join(self.state_dir, f), 'rb') as fp:
                            data = fp.read()
                        params = lt.read_resume_data(data)
                        
                        # Add torrent params might not have save_path if it's a magnet with no metadata yet.
                        # For robustness, ensure save_path is set from profile or some default.
                        # If a profile existed and specified save_path for local, it would be in params.
                        # For now, default if not present.
                        if not params.save_path:
                             params.save_path = default_save_path

                        self.ses.add_torrent(params)
                        ih = self._info_hash_key(params.info_hashes)
                        if ih:
                            loaded_hashes.add(ih)
                    except Exception as e:
                        print(f"Error loading resume data for {f}: {e}")
                        # If resume data fails, try to load .torrent directly if it exists.
                        ih_from_resume = f.replace('.resume', '')
                        torrent_file_path = os.path.join(self.state_dir, ih_from_resume + '.torrent')
                        if os.path.exists(torrent_file_path):
                            try:
                                with open(torrent_file_path, 'rb') as tfp:
                                    torrent_content = tfp.read()
                                    info = lt.torrent_info(torrent_content)
                                    # Need original save_path here. If not in resume, fallback.
                                    # For simplicity, if resume data failed, we re-add as new, so save_path from profile.
                                    params = {'ti': info, 'save_path': default_save_path} 
                                    self.ses.add_torrent(params)
                                    ih = ""
                                    try:
                                        if hasattr(info, "info_hashes"):
                                            ih = self._info_hash_key(info.info_hashes())
                                    except Exception:
                                        ih = ""
                                    if not ih:
                                        ih = self._info_hash_key(info.info_hash())
                                    if ih:
                                        loaded_hashes.add(ih)
                                    print(f"Successfully loaded {ih_from_resume}.torrent after resume data failure using default path.")
                            except Exception as tf_e:
                                print(f"Failed to load .torrent file {torrent_file_path} as fallback: {tf_e}")

        # 2. Scan for .torrent files that were added but never had resume data saved (e.g., app crashed immediately)
        if os.path.exists(self.state_dir):
            for f in os.listdir(self.state_dir):
                if f.endswith('.torrent'):
                    ih = f.replace('.torrent', '')
                    if ih not in loaded_hashes:
                        try:
                            with open(os.path.join(self.state_dir, f), 'rb') as tfp:
                                torrent_content = tfp.read()
                                info = lt.torrent_info(torrent_content)
                                params = {'ti': info, 'save_path': default_save_path}
                                self.ses.add_torrent(params)
                                loaded_hashes.add(ih)
                                print(f"Loaded {ih}.torrent from file (no resume data).")
                        except Exception as e:
                            print(f"Error loading torrent file {f}: {e}")

    def save_state(self):
        print("Saving session state...")
        # Trigger save_resume_data for all torrents
        handles = self.ses.get_torrents()
        self.pending_saves.clear()
        
        count = 0
        for h in handles:
            if h.is_valid():
                ih = self._handle_hash_key(h)
                if ih:
                    self.pending_saves.add(ih)
                h.save_resume_data(lt.resume_data_flags_t.flush_disk_cache)
                count += 1
        
        if count == 0:
            return

        # Wait for saves to complete with a timeout (e.g., 10 seconds)
        start_time = time.time()
        while self.pending_saves and time.time() - start_time < 10:
            time.sleep(0.1)
            
        if self.pending_saves:
            print(f"Timed out waiting for {len(self.pending_saves)} resume data saves.")
        else:
            print("All resume data saved successfully.")

    def _find_handle(self, info_hash_str):
        for h in self.ses.get_torrents():
             if self._handle_hash_key(h) == info_hash_str:
                 return h
        return None

    def remove_torrent(self, info_hash, delete_files=False):
        h = self._find_handle(info_hash)
        if h:
            # Remove from session
            # Remove from session.
            flags = 0
            if delete_files:
                flags = 1
                try:
                    if hasattr(lt, 'remove_flags_t') and hasattr(lt.remove_flags_t, 'delete_files'):
                        flags = int(lt.remove_flags_t.delete_files)
                    elif hasattr(lt, 'options_t') and hasattr(lt.options_t, 'delete_files'):
                        flags = int(lt.options_t.delete_files)
                except Exception:
                    flags = 1
            self.ses.remove_torrent(h, flags)
            
            # Clean up state files to prevent resurrection
            try:
                t_path = os.path.join(self.state_dir, info_hash + '.torrent')
                if os.path.exists(t_path):
                    os.remove(t_path)
                    
                r_path = os.path.join(self.state_dir, info_hash + '.resume')
                if os.path.exists(r_path):
                    os.remove(r_path)
            except Exception as e:
                print(f"Error cleaning up state files for {info_hash}: {e}")

    def get_torrents(self):
        return self.ses.get_torrents()

    def get_status(self):
        return self.ses.status()

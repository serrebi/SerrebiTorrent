import abc
import time
from urllib.parse import urlparse
import requests

from libtorrent_env import prepare_libtorrent_dlls

class BaseClient(abc.ABC):
    @abc.abstractmethod
    def test_connection(self):
        pass

    @abc.abstractmethod
    def get_torrents_full(self):
        """
        Returns list of dicts:
        {
            "hash": str,
            "name": str,
            "size": int,
            "done": int,
            "up_total": int,
            "ratio": float (e.g. 1.5),
            "state": int (1=started, 0=stopped),
            "active": int (1=active/open, 0=inactive/closed),
            "hashing": int (1/0),
            "message": str,
            "down_rate": int (bytes/s),
            "up_rate": int (bytes/s),
            "tracker_domain": str
        }
        """
        pass
    
    @abc.abstractmethod
    def start_torrent(self, info_hash):
        pass

    @abc.abstractmethod
    def stop_torrent(self, info_hash):
        pass

    @abc.abstractmethod
    def remove_torrent(self, info_hash):
        pass

    @abc.abstractmethod
    def remove_torrent_with_data(self, info_hash):
        pass

    @abc.abstractmethod
    def add_torrent_url(self, url, save_path=None):
        pass

    @abc.abstractmethod
    def add_torrent_file(self, file_content, save_path=None, file_priorities=None):
        pass

    @abc.abstractmethod
    def get_global_stats(self):
        """Returns (down_rate, up_rate) in bytes/s"""
        pass

# --- rTorrent Client (Existing + Adapted) ---
import xmlrpc.client
import ssl
import socket
import io

class CookieTransport(xmlrpc.client.SafeTransport):
    def __init__(self, context=None, cookies=None):
        super().__init__(context=context)
        self.cookies = cookies or {}

    def send_user_agent(self, connection):
        if self.cookies:
            cookie_str = "; ".join([f"{k}={v}" for k, v in self.cookies.items()])
            connection.putheader("Cookie", cookie_str)
        super().send_user_agent(connection)

class SCGITransport(xmlrpc.client.Transport):
    def __init__(self, host, port):
        super().__init__()
        self.scgi_host = host
        self.scgi_port = port
        self.verbose = False 

    def request(self, host, handler, request_body, verbose=False):
        self.verbose = verbose
        headers = {
            "CONTENT_LENGTH": str(len(request_body)),
            "SCGI": "1",
            "REQUEST_METHOD": "POST",
            "REQUEST_URI": handler if handler else "/"
        }
        content = b""
        for k, v in headers.items():
            content += k.encode('ascii') + b'\0' + v.encode('ascii') + b'\0'
        header_payload = str(len(content)).encode('ascii') + b':' + content + b','
        full_payload = header_payload + request_body
        
        try:
            # Standard connection (allows IPv6/IPv4)
            with socket.create_connection((self.scgi_host, self.scgi_port), timeout=10) as sock:
                sock.sendall(full_payload)
                response_data = b""
                while True:
                    chunk = sock.recv(4096)
                    if not chunk: break
                    response_data += chunk
        except OSError as e:
            with open(r"C:\\Users\\admin\\coding\\debug\\gui_debug.log", "a") as f: f.write(f"SCGI Socket Error to {self.scgi_host}: {e}\n")
            raise xmlrpc.client.ProtocolError(host + handler, 500, str(e), {})

        response_str = response_data.decode('utf-8', errors='replace')
        if "\r\n\r\n" in response_str:
            _, body = response_str.split("\r\n\r\n", 1)
        elif "\n\n" in response_str:
            _, body = response_str.split("\n\n", 1)
        elif response_str.strip().startswith("<?xml"):
            body = response_str
        else:
            body = response_str
        return self.parse_response(io.BytesIO(body.encode('utf-8')))

    def parse_response(self, response_file):
        p, u = self.getparser()
        while True:
            data = response_file.read(1024)
            if not data: break
            p.feed(data)
        response_file.close()
        p.close()
        return u.close()

class RTorrentClient(BaseClient):
    def __init__(self, url, username=None, password=None):
        self.url = url
        self.username = username
        self.password = password
        self.cookies = {}
        self.context = ssl._create_unverified_context()
        self.server = None
        self.tracker_cache = {} 
        self._setup_connection()

    def _setup_connection(self):
        parsed = urlparse(self.url)
        if parsed.scheme == "scgi":
            self.server = xmlrpc.client.ServerProxy("http://dummy", transport=SCGITransport(parsed.hostname, parsed.port))
        else:
            self._authenticate_http()

    def _authenticate_http(self):
        # Simplified robust auth from previous steps
        try:
            r = requests.get(self.url, verify=False, allow_redirects=False)
            if r.status_code == 302 and "yunohost/sso" in r.headers.get("Location", ""):
                 pass # Assume session handling or manual
            elif r.status_code == 401 and self.username and "@" not in self.url:
                parsed = urlparse(self.url)
                new_netloc = f"{self.username}:{self.password}@{parsed.netloc}"
                self.url = parsed._replace(netloc=new_netloc).geturl()
        except: pass
        
        transport = CookieTransport(context=self.context, cookies=self.cookies)
        self.server = xmlrpc.client.ServerProxy(self.url, transport=transport, context=self.context)

    def test_connection(self):
        return self.server.system.client_version()

    def _safe_int(self, val):
        if isinstance(val, (list, tuple)):
            if len(val) > 0:
                return self._safe_int(val[0])
            return 0
        try:
            return int(val)
        except:
            return 0

    def _safe_str(self, val):
        if isinstance(val, (list, tuple)):
            if len(val) > 0:
                return self._safe_str(val[0])
            return ""
        return str(val)

    def get_torrents_full(self):
        try:
            # 1. Fetch DYNAMIC data + Basic STATIC data (Name, Size)
            # We fetch name/size every time now. It's fast and simplifies the logic massively.
            # d.multicall2 signature: view, params...
            # Fields: hash, bytes_done, up_total, ratio, state, is_active, is_hash_checking, message, down_rate, up_rate, name, size
            dynamic_raw = self.server.d.multicall2(
                "", "main",
                "d.hash=", "d.bytes_done=", "d.up.total=", "d.ratio=", 
                "d.state=", "d.is_active=", "d.is_hash_checking=", 
                "d.message=", "d.down.rate=", "d.up.rate=",
                "d.name=", "d.size_bytes="
            )
            
            if not dynamic_raw: return []

            # 2. Identify hashes missing Tracker info
            new_hashes = []
            for t in dynamic_raw:
                h = t[0]
                if h not in self.tracker_cache:
                    new_hashes.append(h)

            # 3. Fetch Trackers (Limited Batch)
            # Only fetch a small batch per update to keep UI responsive on first load
            BATCH_SIZE = 50
            if new_hashes:
                batch = new_hashes[:BATCH_SIZE]
                
                calls = []
                for h in batch:
                    calls.append({"methodName": "t.multicall", "params": [h, "", "t.url="]})
                
                try:
                    tracker_results = self.server.system.multicall(calls)
                    
                    for i, h in enumerate(batch):
                        trackers = tracker_results[i]
                        tracker_domain = ""
                        if isinstance(trackers, list) and trackers:
                            try:
                                first_t = trackers[0]
                                if isinstance(first_t, list) and len(first_t) > 0:
                                    url = first_t[0]
                                else:
                                    url = str(first_t)
                                tracker_domain = urlparse(url).hostname or ""
                            except: pass
                        
                        self.tracker_cache[h] = tracker_domain
                except Exception as e:
                    print(f"Tracker fetch warning: {e}")

            # 4. Merge
            results = []
            for t in dynamic_raw:
                h = t[0]
                tracker_domain = self.tracker_cache.get(h, "")
                
                # Indices shifted because we added name/size to main call
                # 0=hash, 1=done, 2=up, 3=ratio, 4=state, 5=active, 6=check, 7=msg, 8=down, 9=up, 10=name, 11=size
                
                results.append({
                    "hash": h,
                    "name": self._safe_str(t[10]),
                    "size": self._safe_int(t[11]),
                    "done": self._safe_int(t[1]),
                    "up_total": self._safe_int(t[2]),
                    "ratio": self._safe_int(t[3]),
                    "state": self._safe_int(t[4]), 
                    "active": self._safe_int(t[5]),
                    "hashing": self._safe_int(t[6]),
                    "message": self._safe_str(t[7]),
                    "down_rate": self._safe_int(t[8]),
                    "up_rate": self._safe_int(t[9]),
                    "tracker_domain": tracker_domain
                })
            return results
        except Exception as e:
            print(f"rTorrent fetch error: {e}")
            return []

    def start_torrent(self, info_hash):
        self.server.d.open(info_hash)
        self.server.d.start(info_hash)

    def stop_torrent(self, info_hash):
        self.server.d.stop(info_hash)
        self.server.d.close(info_hash)

    def remove_torrent(self, info_hash):
        self.server.d.erase(info_hash)

    def remove_torrent_with_data(self, info_hash):
        self.server.d.erase(info_hash)

    def add_torrent_url(self, url, save_path=None):
        # Note: rTorrent load.start supports target path via command modification, but simplified here.
        self.server.load.start("", url)

    def add_torrent_file(self, file_content, save_path=None, file_priorities=None):
        self.server.load.raw_start("", xmlrpc.client.Binary(file_content))

    def get_global_stats(self):
        try:
            return self.server.throttle.global_down.rate(), self.server.throttle.global_up.rate()
        except: return 0, 0


# --- qBittorrent Client ---
import qbittorrentapi

class QBittorrentClient(BaseClient):
    def __init__(self, url, username, password):
        self.client = qbittorrentapi.Client(host=url, username=username, password=password)
        # qBittorrent requires explicit login
        self.client.auth_log_in()

    def test_connection(self):
        return self.client.app_version()

    def get_torrents_full(self):
        try:
            torrents = self.client.torrents_info()
            results = []
            for t in torrents:
                # Map qBit fields
                state_val = 0
                active_val = 0
                hashing_val = 0
                # qBit states: error, missingFiles, uploading, pausedUP, queuedUP, stalledUP, checkingUP, forcedUP, allocating, downloading, metaDL, pausedDL, queuedDL, stalledDL, checkingDL, forcedDL, checkingResumeData, moving, unknown
                
                s = t.state
                if s in ['downloading', 'uploading', 'stalledDL', 'stalledUP', 'stallingDL', 'stallingUP', 'metaDL', 'forcedDL', 'forcedUP', 'queuedDL', 'queuedUP']:
                    state_val = 1 # Started
                    active_val = 1 # Active
                elif s in ['pausedDL', 'pausedUP']:
                    state_val = 0
                elif 'checking' in s:
                    hashing_val = 1
                    state_val = 1

                tracker = ""
                # Basic logic to get tracker from tracker property or list
                # qBit returns 'tracker' field usually
                if t.tracker:
                    tracker = urlparse(t.tracker).hostname or ""

                results.append({
                    "hash": t.hash,
                    "name": t.name,
                    "size": t.total_size,
                    "done": t.completed, # or total_done
                    "up_total": t.uploaded,
                    "ratio": t.ratio * 1000, # rTorrent uses int ratio * 1000 usually? Wait, rTorrent returns ratio as integer per mille (1000 = 1.0). My UI divides by 1000. qBit returns float. So multiply by 1000.
                    "state": state_val,
                    "active": active_val,
                    "hashing": hashing_val,
                    "message": "", # qBit doesn't have generic message field easily mapped here
                    "down_rate": t.dlspeed,
                    "up_rate": t.upspeed,
                    "tracker_domain": tracker
                })
            return results
        except Exception as e:
            print(f"qBit error: {e}")
            return []

    def start_torrent(self, info_hash):
        self.client.torrents_resume(torrent_hashes=info_hash)

    def stop_torrent(self, info_hash):
        self.client.torrents_pause(torrent_hashes=info_hash)

    def remove_torrent(self, info_hash):
        self.client.torrents_delete(torrent_hashes=info_hash, delete_files=False)

    def remove_torrent_with_data(self, info_hash):
        self.client.torrents_delete(torrent_hashes=info_hash, delete_files=True)

    def add_torrent_url(self, url, save_path=None):
        kwargs = {}
        if save_path: kwargs['save_path'] = save_path
        self.client.torrents_add(urls=url, **kwargs)

    def add_torrent_file(self, file_content, save_path=None, file_priorities=None):
        kwargs = {}
        if save_path: kwargs['save_path'] = save_path
        self.client.torrents_add(torrent_files=file_content, **kwargs)

    def get_global_stats(self):
        info = self.client.transfer_info()
        return info.dl_info_speed, info.up_info_speed


# --- Transmission Client ---
from transmission_rpc import Client as TransClient

class TransmissionClient(BaseClient):
    def __init__(self, url, username, password):
        # Transmission-rpc expects host, port separately or full url?
        # It supports parsing from URL usually
        p = urlparse(url)
        self.client = TransClient(host=p.hostname, port=p.port, username=username, password=password, protocol=p.scheme)

    def test_connection(self):
        return self.client.server_version

    def get_torrents_full(self):
        try:
            torrents = self.client.get_torrents()
            results = []
            for t in torrents:
                # Map Transmission fields
                # status: 'check pending', 'checking', 'downloading', 'download pending', 'seeding', 'seed pending', 'stopped'
                
                state_val = 0
                active_val = 0
                hashing_val = 0
                
                s = t.status
                if s == 'stopped':
                    state_val = 0
                elif s == 'checking' or s == 'check pending':
                    hashing_val = 1
                    state_val = 1
                else:
                    state_val = 1
                    active_val = 1 # downloading/seeding
                
                tracker = ""
                if t.trackers:
                    # t.trackers is list of objects
                    try:
                        tracker = urlparse(t.trackers[0].announce).hostname or ""
                    except: pass

                results.append({
                    "hash": t.hashString,
                    "name": t.name,
                    "size": t.total_size,
                    "done": t.downloaded_ever + t.corrupt_ever, # approx? or t.size * t.percentDone
                    "up_total": t.uploaded_ever,
                    "ratio": t.ratio * 1000, # Trans uses float
                    "state": state_val,
                    "active": active_val,
                    "hashing": hashing_val,
                    "message": t.error_string,
                    "down_rate": t.rate_download,
                    "up_rate": t.rate_upload,
                    "tracker_domain": tracker
                })
            return results
        except Exception as e:
            print(f"Transmission error: {e}")
            return []

    def start_torrent(self, info_hash):
        self.client.start_torrent(info_hash)

    def stop_torrent(self, info_hash):
        self.client.stop_torrent(info_hash)

    def remove_torrent(self, info_hash):
        self.client.remove_torrent(info_hash, delete_data=False)

    def remove_torrent_with_data(self, info_hash):
        self.client.remove_torrent(info_hash, delete_data=True)

    def add_torrent_url(self, url, save_path=None):
        kwargs = {}
        if save_path: kwargs['download_dir'] = save_path
        self.client.add_torrent(url, **kwargs)

    def add_torrent_file(self, file_content, save_path=None, file_priorities=None):
        # Transmission-rpc expects base64 encoded binary string for 'metainfo' usually,
        # but library handles bytes if passed to add_torrent(filename=...) ?
        # Actually library expects file path or url. For raw data, we might need base64.
        import base64
        b64 = base64.b64encode(file_content).decode('utf-8')
        kwargs = {}
        if save_path: kwargs['download_dir'] = save_path
        self.client.add_torrent(b64, **kwargs)

    def get_global_stats(self):
        s = self.client.session_stats()
        return s.download_speed, s.upload_speed

# --- Local Client (libtorrent) ---
prepare_libtorrent_dlls()
try:
    import libtorrent as lt
except ImportError:
    lt = None

import os
from session_manager import SessionManager

class LocalClient(BaseClient):
    def __init__(self, download_path, username=None, password=None):
        # Username/Password ignored for local
        if not lt:
            raise RuntimeError("libtorrent module not found or DLL failed to load.")
        
        self.manager = SessionManager.get_instance()
        self.download_path = download_path if download_path and os.path.isdir(download_path) else os.getcwd()
        
        # Session is managed globally now.

    def _get_effective_download_path(self):
        from config_manager import ConfigManager
        cm = ConfigManager()
        prefs = cm.get_preferences()
        path = prefs.get('download_path')
        if path and os.path.isdir(path):
            return path
        return self.download_path

    def test_connection(self):
        return f"libtorrent {lt.version}"

    def get_torrents_full(self):
        # Delegate to global session
        handles = self.manager.get_torrents()
        results = []
        
        for h in handles:
            s = h.status()
            
            # Map State
            state_val = 0 # Stopped
            active_val = 0 # Inactive
            hashing_val = 0
            
            if s.paused and not s.auto_managed:
                state_val = 0 # Stopped
            else:
                state_val = 1 # Started
                if s.state != lt.torrent_status.seeding and s.state != lt.torrent_status.finished:
                     active_val = 1 # Downloading or checking
                if s.state == lt.torrent_status.seeding:
                     active_val = 1 # Uploading?

            if s.state in [lt.torrent_status.checking_files, lt.torrent_status.queued_for_checking]:
                hashing_val = 1

            # Tracker
            tracker = urlparse(s.current_tracker).hostname or ""
            
            # Info
            name = s.name
            if not name: name = str(h.info_hash()) # fallback
            
            # Ratio
            ratio = 0
            if s.all_time_download > 0:
                ratio = (s.all_time_upload / s.all_time_download) * 1000
            
            results.append({
                "hash": str(h.info_hash()),
                "name": name,
                "size": s.total_wanted,
                "done": s.total_wanted_done,
                "up_total": s.all_time_upload,
                "ratio": int(ratio),
                "state": state_val,
                "active": active_val,
                "hashing": hashing_val,
                "message": s.errc.message() if s.errc else "",
                "down_rate": s.download_payload_rate,
                "up_rate": s.upload_payload_rate,
                "tracker_domain": tracker
            })
        return results

    def start_torrent(self, info_hash):
        h = self._get_handle(info_hash)
        if h: h.resume()

    def stop_torrent(self, info_hash):
        h = self._get_handle(info_hash)
        if h: h.pause()

    def remove_torrent(self, info_hash):
        self.manager.remove_torrent(info_hash, delete_files=False)

    def remove_torrent_with_data(self, info_hash):
        self.manager.remove_torrent(info_hash, delete_files=True)

    def add_torrent_url(self, url, save_path=None):
        # Use passed save_path or default
        final_path = save_path if save_path else self._get_effective_download_path()
        
        if url.startswith("magnet:"):
            self.manager.add_magnet(url, final_path)
        elif url.startswith(("http://", "https://")):
            # Download .torrent file
            try:
                r = requests.get(url, timeout=30)
                r.raise_for_status()
                content = r.content
                self.manager.add_torrent_file(content, final_path)
            except Exception as e:
                raise Exception(f"Failed to download torrent from URL: {e}")
        else:
            raise ValueError(f"Unsupported URL scheme: {url}")

    def add_torrent_file(self, file_content, save_path=None, file_priorities=None):
        # Use passed save_path or default
        final_path = save_path if save_path else self._get_effective_download_path()
        self.manager.add_torrent_file(file_content, final_path, file_priorities)

    def get_global_stats(self):
        st = self.manager.get_status()
        return st.payload_download_rate, st.payload_upload_rate

    def _get_handle(self, info_hash_str):
        for h in self.manager.get_torrents():
             if str(h.info_hash()) == info_hash_str:
                 return h
        return None

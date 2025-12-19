import abc
import time
from urllib.parse import urlparse
import requests

from app_paths import get_log_path

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
            "tracker_domain": str,
            "save_path": str | None,
            "availability": float | None
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

    def remove_torrents(self, info_hashes, delete_files=False):
        """Remove multiple torrents.

        Default implementation loops over :meth:`remove_torrent` or
        :meth:`remove_torrent_with_data`.
        """
        if not info_hashes:
            return
        # Accept a single hash as a string/bytes.
        if isinstance(info_hashes, (str, bytes)):
            info_hashes = [info_hashes.decode("utf-8", "ignore") if isinstance(info_hashes, bytes) else info_hashes]

        for h in info_hashes:
            if not h:
                continue
            h = str(h).strip()
            if not h:
                continue
            if delete_files:
                self.remove_torrent_with_data(h)
            else:
                self.remove_torrent(h)

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

    def get_app_preferences(self):
        """Retrieve app preferences from the client (if supported)."""
        return None

    def set_app_preferences(self, prefs):
        """Apply app preferences through the client (if supported)."""
        raise NotImplementedError
    def get_default_save_path(self):
        """Optional override for client-specific default download directory."""
        return None


    def recheck_torrent(self, info_hash):
        """Request a hash check / verification (if supported)."""
        raise NotImplementedError

    def reannounce_torrent(self, info_hash):
        """Request an immediate tracker announce (if supported)."""
        raise NotImplementedError

    @abc.abstractmethod
    def get_torrent_save_path(self, info_hash):
        """Return the torrent's save path if available (local client only)."""
        return None

    @abc.abstractmethod
    def get_files(self, info_hash):
        """
        Returns list of dicts:
        {
            "index": int,
            "name": str,
            "size": int,
            "progress": float (0.0 - 1.0),
            "priority": int (0=Skip, 1=Normal, 2=High)
        }
        """
        pass

    @abc.abstractmethod
    def set_file_priority(self, info_hash, file_index, priority):
        """
        Set priority: 0=Skip, 1=Normal, 2=High
        """
        pass

    @abc.abstractmethod
    def get_peers(self, info_hash):
        """
        Returns list of dicts:
        {
            "address": str,
            "client": str,
            "progress": float (0.0 - 1.0),
            "down_rate": int (bytes/s),
            "up_rate": int (bytes/s)
        }
        """
        pass

    @abc.abstractmethod
    def get_trackers(self, info_hash):
        """
        Returns list of dicts:
        {
            "url": str,
            "status": str,
            "peers": int,
            "message": str
        }
        """
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
            # Never hard-code user paths. Log into the app data logs directory.
            try:
                with open(get_log_path("gui_debug.log"), "a", encoding="utf-8") as f:
                    f.write(f"SCGI Socket Error to {self.scgi_host}: {e}\n")
            except Exception:
                pass
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
        except Exception as e:
            try:
                with open(get_log_path("gui_debug.log"), "a", encoding="utf-8") as f:
                    f.write(f"HTTP Auth Probe Error: {e}\n")
            except Exception:
                pass
        
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

    def get_files(self, info_hash):
        try:
            # f.multicall: hash, match_pattern, commands...
            # f.get_path, f.get_size_bytes, f.get_priority, f.get_completed_chunks, f.get_size_chunks
            res = self.server.f.multicall(
                info_hash, "",
                "f.get_path=", "f.get_size_bytes=", "f.get_priority=",
                "f.get_completed_chunks=", "f.get_size_chunks="
            )
            files = []
            for i, r in enumerate(res):
                # r is [path, size, prio, complete_chunks, total_chunks]
                path = r[0]
                size = r[1]
                prio = r[2]
                done_chunks = r[3]
                total_chunks = r[4]
                
                progress = 0.0
                if total_chunks > 0:
                    progress = done_chunks / total_chunks
                elif size == 0:
                    progress = 1.0 # Empty file
                
                # rTorrent priorities: 0=off, 1=normal, 2=high. Fits our standard.
                files.append({
                    "index": i,
                    "name": path,
                    "size": size,
                    "progress": progress,
                    "priority": prio
                })
            return files
        except Exception as e:
            print(f"rTorrent get_files error: {e}")
            return []

    def set_file_priority(self, info_hash, file_index, priority):
        try:
            self.server.f.priority.set(info_hash, file_index, priority)
            self.server.d.update_priorities(info_hash)
        except Exception as e:
            print(f"rTorrent set_file_priority error: {e}")

    def get_peers(self, info_hash):
        try:
            # p.multicall: hash, view, commands...
            res = self.server.p.multicall(
                info_hash, "",
                "p.address=", "p.client_version=", "p.completed_percent=",
                "p.down_rate=", "p.up_rate="
            )
            peers = []
            for r in res:
                peers.append({
                    "address": str(r[0]),
                    "client": str(r[1]),
                    "progress": float(r[2]) / 100.0,
                    "down_rate": int(r[3]),
                    "up_rate": int(r[4])
                })
            return peers
        except Exception as e:
            print(f"rTorrent get_peers error: {e}")
            return []

    def get_trackers(self, info_hash):
        try:
            # t.multicall: hash, view, commands...
            res = self.server.t.multicall(
                info_hash, "",
                "t.url=", "t.is_enabled=", "t.scrape_complete="
            )
            trackers = []
            for r in res:
                trackers.append({
                    "url": str(r[0]),
                    "status": "Enabled" if r[1] else "Disabled",
                    "peers": int(r[2]) if r[2] else 0,
                    "message": ""
                })
            return trackers
        except Exception as e:
            print(f"rTorrent get_trackers error: {e}")
            return []

    def get_torrent_save_path(self, info_hash):
        try:
            return self.server.d.directory(info_hash)
        except Exception:
            return None

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
                "d.name=", "d.size_bytes=",
                "d.left_bytes=", "d.connection_seed=", "d.connection_leech=",
                "d.peers_complete=", "d.peers_accounted=", "d.directory="
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
                
                # 0=hash, 1=done, 2=up, 3=ratio, 4=state, 5=active, 6=check, 7=msg,
                # 8=down, 9=up, 10=name, 11=size, 12=left_bytes, 13=conn_seed, 14=conn_leech,
                # 15=peers_complete, 16=peers_accounted

                down_rate = self._safe_int(t[8])
                left_bytes = self._safe_int(t[12])
                eta = -1
                if down_rate > 0 and left_bytes > 0:
                    try:
                        eta = int(left_bytes / down_rate)
                    except Exception:
                        eta = -1
                
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
                    "down_rate": down_rate,
                    "up_rate": self._safe_int(t[9]),
                    "tracker_domain": tracker_domain,
                    "save_path": self._safe_str(t[17]) if len(t) > 17 else None,
                    "eta": eta,
                    "seeds_connected": self._safe_int(t[13]),
                    "seeds_total": self._safe_int(t[15]),
                    "leechers_connected": self._safe_int(t[14]),
                    "leechers_total": self._safe_int(t[16])
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

    def get_app_preferences(self):
        try:
            # We use a multicall to fetch common settings
            m = xmlrpc.client.MultiCall(self.server)
            m.throttle.global_down.max_rate()
            m.throttle.global_up.max_rate()
            m.directory.default()
            m.throttle.max_peers.normal()
            m.throttle.min_peers.normal()
            m.throttle.max_uploads()
            m.network.port_range()
            m.pieces.hash.on_completion()
            m.dht.mode()
            m.protocol.pex()
            m.trackers.use_udp()
            m.protocol.encryption.items()
            m.network.http.proxy_address()

            res = m()
            
            # Helper to extract value or default if fault
            def val(idx, default):
                if idx < len(res):
                    v = res[idx]
                    if isinstance(v, dict) and 'faultCode' in v:
                        return default
                    return v
                return default

            return {
                "dl_limit": val(0, 0),
                "ul_limit": val(1, 0),
                "directory_default": val(2, ""),
                "max_peers": val(3, 0),
                "min_peers": val(4, 0),
                "max_uploads": val(5, 0),
                "port_range": val(6, ""),
                "check_hash": bool(val(7, 0)),
                "dht_mode": val(8, "off"),
                "pex_enabled": bool(val(9, 0)),
                "use_udp_trackers": bool(val(10, 0)),
                "encryption": ",".join(val(11, [])) if isinstance(val(11, []), list) else "",
                "proxy_address": val(12, "")
            }
        except Exception as e:
            print(f"rTorrent get prefs error: {e}")
            return None

    def set_app_preferences(self, prefs):
        try:
            m = xmlrpc.client.MultiCall(self.server)
            
            if "dl_limit" in prefs:
                m.throttle.global_down.max_rate.set("", int(prefs["dl_limit"]))
            if "ul_limit" in prefs:
                m.throttle.global_up.max_rate.set("", int(prefs["ul_limit"]))
            if "directory_default" in prefs:
                m.directory.default.set("", str(prefs["directory_default"]))
            if "max_peers" in prefs:
                m.throttle.max_peers.normal.set("", int(prefs["max_peers"]))
            if "min_peers" in prefs:
                m.throttle.min_peers.normal.set("", int(prefs["min_peers"]))
            if "max_uploads" in prefs:
                m.throttle.max_uploads.set("", int(prefs["max_uploads"]))
            if "port_range" in prefs:
                m.network.port_range.set("", str(prefs["port_range"]))
            if "check_hash" in prefs:
                m.pieces.hash.on_completion.set("", 1 if prefs["check_hash"] else 0)
            if "dht_mode" in prefs:
                m.dht.mode.set("", str(prefs["dht_mode"]))
            if "pex_enabled" in prefs:
                m.protocol.pex.set("", 1 if prefs["pex_enabled"] else 0)
            if "use_udp_trackers" in prefs:
                m.trackers.use_udp.set("", 1 if prefs["use_udp_trackers"] else 0)
            if "encryption" in prefs:
                # Expects list of strings? No, set takes args.
                # protocol.encryption.set = "arg1", "arg2" ...
                # Actually commonly passed as one string or multiple calls?
                # The command often takes variable arguments.
                # rTorrent docs say: protocol.encryption.set = option, ...
                # xmlrpc usually handles this by passing multiple params.
                # But our dialog provides one string.
                # We can try passing it as a single string if rTorrent supports it, or split.
                # Better safe: rTorrent config usually looks like: protocol.encryption.set = allow_incoming,try_outgoing
                # In XMLRPC, one usually passes them as separate string arguments.
                # But MultiCall method.set("", arg) implies one arg.
                # Let's try passing the whole comma-separated string as one arg, or loop.
                # Actually, `protocol.encryption.set` usually clears and sets.
                # If we can't easily set multiple args via this wrapper, we might skip or try simplified approach.
                # Let's try passing the string as-is.
                m.protocol.encryption.set("", str(prefs["encryption"]))
            if "proxy_address" in prefs:
                m.network.http.proxy_address.set("", str(prefs["proxy_address"]))

            m()
        except Exception as e:
            raise Exception(f"Failed to set rTorrent prefs: {e}")


# --- qBittorrent Client ---
import qbittorrentapi

class QBittorrentClient(BaseClient):
    def __init__(self, url, username, password):
        self.url = url
        self.username = username
        self.password = password
        
        # Ensure URL has a scheme for qbittorrentapi
        if not url.startswith(('http://', 'https://')):
            url = 'http://' + url
            
        self.client = qbittorrentapi.Client(
            host=url, 
            username=username, 
            password=password
        )
        
        try:
            self.client.auth_log_in()
        except Exception as e:
            # Fallback for localhost/127.0.0.1 mismatch
            if "localhost" in url:
                try:
                    new_url = url.replace("localhost", "127.0.0.1")
                    self.client = qbittorrentapi.Client(host=new_url, username=username, password=password)
                    self.client.auth_log_in()
                    self.url = new_url # Update to working URL
                except Exception:
                    raise e # Raise original error if fallback also fails
            else:
                raise

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
                    "tracker_domain": tracker,
                    "eta": int(getattr(t, "eta", -1) or -1),
                    "seeds_connected": int(getattr(t, "num_seeds", 0) or 0),
                    "seeds_total": int(getattr(t, "num_complete", 0) or 0),
                    "leechers_connected": int(getattr(t, "num_leechs", 0) or 0),
                    "leechers_total": int(getattr(t, "num_incomplete", 0) or 0),
                    "availability": (float(getattr(t, "availability", 0) or 0) if getattr(t, "availability", None) is not None else None),
                    "save_path": getattr(t, "download_dir", None) or getattr(t, "downloadDir", None)
                })
            return results
        except Exception as e:
            print(f"qBit error: {e}")
            return []

    def start_torrent(self, info_hash):
        try:
            self.client.torrents_set_auto_management(False, torrent_hashes=info_hash)
        except Exception:
            pass

        try:
            self.client.torrents_set_force_start(True, torrent_hashes=info_hash)
        except Exception:
            pass

        try:
            self.client.torrents_resume(torrent_hashes=info_hash)
        except Exception:
            pass

    def stop_torrent(self, info_hash):
        self.client.torrents_pause(torrent_hashes=info_hash)

    def _normalize_hashes(self, info_hashes):
        if not info_hashes:
            return []
        if isinstance(info_hashes, (str, bytes)):
            info_hashes = [info_hashes.decode('utf-8', 'ignore') if isinstance(info_hashes, bytes) else info_hashes]
        cleaned = []
        for h in info_hashes:
            if not h:
                continue
            h = str(h).strip()
            if not h:
                continue
            cleaned.append(h.lower())
        seen = set()
        out = []
        for h in cleaned:
            if h in seen:
                continue
            seen.add(h)
            out.append(h)
        return out

    def remove_torrents(self, info_hashes, delete_files=False):
        hashes = self._normalize_hashes(info_hashes)
        if not hashes:
            return
        joined = '|'.join(hashes)
        last_err = None
        for attempt in range(2):
            try:
                # Use joined string to avoid accidental per-character iteration in some library versions.
                try:
                    return self.client.torrents_delete(torrent_hashes=joined, delete_files=delete_files)
                except TypeError:
                    try:
                        return self.client.torrents_delete(torrent_hashes=hashes, delete_files=delete_files)
                    except TypeError:
                        try:
                            return self.client.torrents_delete(hashes=joined, delete_files=delete_files)
                        except TypeError:
                            return self.client.torrents_delete(hashes=hashes, delete_files=delete_files)
            except Exception as e:
                last_err = e
                if attempt == 0:
                    try:
                        self.client.auth_log_in()
                        continue
                    except Exception:
                        break
        if last_err:
            raise last_err

    def remove_torrent(self, info_hash):
        self.remove_torrents([info_hash], delete_files=False)

    def remove_torrent_with_data(self, info_hash):
        self.remove_torrents([info_hash], delete_files=True)


    def add_torrent_url(self, url, save_path=None):
        kwargs = {}
        if save_path: kwargs['save_path'] = save_path
        self.client.torrents_add(urls=url, **kwargs)

    def add_torrent_file(self, file_content, save_path=None, file_priorities=None):
        kwargs = {}
        if save_path: kwargs['save_path'] = save_path
        self.client.torrents_add(torrent_files=file_content, **kwargs)

    def recheck_torrent(self, info_hash):
        try:
            self.client.torrents_recheck(torrent_hashes=info_hash)
        except Exception as e:
            raise NotImplementedError(str(e))

    def reannounce_torrent(self, info_hash):
        try:
            self.client.torrents_reannounce(torrent_hashes=info_hash)
        except Exception as e:
            raise NotImplementedError(str(e))

    def get_files(self, info_hash):
        try:
            # Returns list of objects with name, size, progress, priority
            files = self.client.torrents_files(torrent_hash=info_hash)
            out = []
            for i, f in enumerate(files):
                # qBit priorities: 0=Ignored, 1=Normal, 6=High, 7=Max
                p = f.priority
                std_p = 1
                if p == 0: std_p = 0
                elif p >= 6: std_p = 2
                
                out.append({
                    "index": i,
                    "name": f.name,
                    "size": f.size,
                    "progress": f.progress,
                    "priority": std_p
                })
            return out
        except Exception as e:
            print(f"qBit get_files error: {e}")
            return []

    def set_file_priority(self, info_hash, file_index, priority):
        try:
            # Map std to qBit
            q_p = 1
            if priority == 0: q_p = 0
            elif priority == 2: q_p = 7
            
            self.client.torrents_file_priority(torrent_hash=info_hash, file_ids=file_index, priority=q_p)
        except Exception as e:
            print(f"qBit set_file_priority error: {e}")

    def get_peers(self, info_hash):
        try:
            # In qbittorrentapi, the method is sync_torrent_peers
            peers_data = self.client.sync_torrent_peers(torrent_hash=info_hash)
            peers = peers_data.get('peers', {})
            out = []
            for ip_port, p in peers.items():
                out.append({
                    "address": ip_port,
                    "client": p.get('client', 'Unknown'),
                    "progress": p.get('progress', 0.0),
                    "down_rate": p.get('dl_speed', 0),
                    "up_rate": p.get('up_speed', 0)
                })
            return out
        except Exception as e:
            # Suppress common noise if hash is missing/removed
            msg = str(e).lower()
            if "torrent hash" not in msg and "not found" not in msg:
                print(f"qBit get_peers error: {e}")
            return []

    def get_trackers(self, info_hash):
        try:
            trackers = self.client.torrents_trackers(torrent_hash=info_hash)
            out = []
            for t in trackers:
                out.append({
                    "url": t.get('url', ''),
                    "status": t.get('status_desc', str(t.get('status', 'Unknown'))),
                    "peers": t.get('num_peers', 0),
                    "message": t.get('msg', '')
                })
            return out
        except Exception as e:
            print(f"qBit get_trackers error: {e}")
            return []

    def get_torrent_save_path(self, info_hash):
        try:
            info = self.client.torrents_info(torrent_hashes=info_hash)
            if info:
                # qbittorrentapi usually returns dict-like object
                return info[0].get('save_path') or info[0].get('download_path')
        except Exception:
            pass
        return None

    def get_default_save_path(self):
        try:
            prefs = self.client.app_preferences()
            save_path = getattr(prefs, 'save_path', None)
            if not save_path and isinstance(prefs, dict):
                save_path = prefs.get('save_path')
            return save_path
        except Exception:
            return None

    def get_global_stats(self):
        info = self.client.transfer_info()
        return info.dl_info_speed, info.up_info_speed

    def get_app_preferences(self):
        try:
            prefs = self.client.app_preferences()
            if isinstance(prefs, dict):
                return dict(prefs)
            return prefs.as_dict()
        except Exception:
            return None

    def set_app_preferences(self, prefs):
        self.client.app_set_preferences(prefs)


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
                    except:
                        pass

                # Availability (distributed copies) if the RPC provides piece availability.
                availability_copies = None
                try:
                    al = getattr(t, "availability", None)
                    if isinstance(al, (list, tuple)) and al:
                        mn = min(al)
                        extra = 0
                        for v in al:
                            try:
                                if int(v) > int(mn):
                                    extra += 1
                            except Exception:
                                continue
                        availability_copies = float(mn) + (extra / float(len(al)))
                except Exception:
                    availability_copies = None

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
                    "tracker_domain": tracker,
                    "eta": int(getattr(t, "eta", -1) or -1),
                    "seeds_connected": int(getattr(t, "peersSendingToUs", 0) or 0),
                    "seeds_total": int(getattr(t, "seeders", 0) or 0),
                    "leechers_connected": int(getattr(t, "peersGettingFromUs", 0) or 0),
                    "leechers_total": int(getattr(t, "leechers", 0) or 0),
                    "availability": availability_copies,
                    "save_path": getattr(t, "download_dir", None) or getattr(t, "downloadDir", None)
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

    def recheck_torrent(self, info_hash):
        # transmission-rpc varies by version; try common method names.
        if hasattr(self.client, 'verify_torrent'):
            try:
                self.client.verify_torrent([info_hash])
                return
            except Exception:
                try:
                    self.client.verify_torrent(info_hash)
                    return
                except Exception as e:
                    raise NotImplementedError(str(e))
        raise NotImplementedError('Torrent verification not supported by transmission-rpc client')

    def reannounce_torrent(self, info_hash):
        if hasattr(self.client, 'reannounce_torrent'):
            try:
                self.client.reannounce_torrent([info_hash])
                return
            except Exception:
                try:
                    self.client.reannounce_torrent(info_hash)
                    return
                except Exception as e:
                    raise NotImplementedError(str(e))
        raise NotImplementedError('Reannounce not supported by transmission-rpc client')

    def get_files(self, info_hash):
        try:
            # Need 'files' and 'fileStats'
            # transmission-rpc library might wrap this.
            # .get_torrent(ids, arguments=...)
            t = self.client.get_torrent(info_hash, arguments=['files', 'fileStats'])
            
            out = []
            files = getattr(t, 'files', [])
            stats = getattr(t, 'fileStats', [])
            
            # files is list of objects/dicts with name, length, bytesCompleted
            # stats is list of objects/dicts with priority, wanted
            
            if not files or not stats or len(files) != len(stats):
                return []

            for i, f in enumerate(files):
                # transmission-rpc < 4 returns dicts, >= 4 might return objects
                # Safety access
                def get_val(obj, key):
                    if isinstance(obj, dict): return obj.get(key)
                    return getattr(obj, key, None)

                name = get_val(f, 'name')
                length = get_val(f, 'length')
                done = get_val(f, 'bytesCompleted')
                
                s = stats[i]
                wanted = get_val(s, 'wanted')
                prio = get_val(s, 'priority') # -1, 0, 1
                
                progress = 0.0
                if length > 0: progress = done / length
                
                std_p = 1
                if not wanted:
                    std_p = 0
                elif prio > 0:
                    std_p = 2
                # else normal (1)
                
                out.append({
                    "index": i,
                    "name": name,
                    "size": length,
                    "progress": progress,
                    "priority": std_p
                })
            return out
        except Exception as e:
            print(f"Transmission get_files error: {e}")
            return []

    def set_file_priority(self, info_hash, file_index, priority):
        try:
            # 0=Skip (unwanted), 1=Normal, 2=High
            args = {}
            # file_index can be single int
            
            if priority == 0:
                args['files_unwanted'] = [file_index]
            elif priority == 1:
                args['files_wanted'] = [file_index]
                args['priority_normal'] = [file_index]
            elif priority == 2:
                args['files_wanted'] = [file_index]
                args['priority_high'] = [file_index]
            
            self.client.change_torrent(info_hash, **args)
        except Exception as e:
            print(f"Transmission set_file_priority error: {e}")

    def get_peers(self, info_hash):
        try:
            t = self.client.get_torrent(info_hash, arguments=['peers'])
            out = []
            peers = getattr(t, 'peers', [])
            for p in peers:
                def get_val(obj, key):
                    if isinstance(obj, dict): return obj.get(key)
                    return getattr(obj, key, None)
                
                out.append({
                    "address": f"{get_val(p, 'address')}:{get_val(p, 'port')}",
                    "client": get_val(p, 'clientName') or 'Unknown',
                    "progress": get_val(p, 'progress') or 0.0,
                    "down_rate": get_val(p, 'rateToClient') or 0,
                    "up_rate": get_val(p, 'rateFromClient') or 0
                })
            return out
        except Exception as e:
            print(f"Transmission get_peers error: {e}")
            return []

    def get_trackers(self, info_hash):
        try:
            t = self.client.get_torrent(info_hash, arguments=['trackers', 'trackerStats'])
            out = []
            # Stats usually have better status info
            stats = getattr(t, 'trackerStats', [])
            for s in stats:
                def get_val(obj, key):
                    if isinstance(obj, dict): return obj.get(key)
                    return getattr(obj, key, None)
                
                out.append({
                    "url": get_val(s, 'announce'),
                    "status": "Active" if get_val(s, 'hasAnnounced') else "Unknown",
                    "peers": get_val(s, 'peerCount') or 0,
                    "message": get_val(s, 'lastAnnounceResult') or ''
                })
            return out
        except Exception as e:
            print(f"Transmission get_trackers error: {e}")
            return []

    def get_torrent_save_path(self, info_hash):
        try:
            t = self.client.get_torrent(info_hash)
            return getattr(t, 'downloadDir', None)
        except Exception:
            return None

    def get_default_save_path(self):
        try:
            session = self.client.get_session()
            return getattr(session, 'download_dir', None)
        except Exception:
            return None

    def get_global_stats(self):
        s = self.client.session_stats()
        return s.download_speed, s.upload_speed

    def get_app_preferences(self):
        try:
            s = self.client.get_session()
            # Extensive properties map
            keys = [
                # Speed
                'speed_limit_down', 'speed_limit_down_enabled',
                'speed_limit_up', 'speed_limit_up_enabled',
                # Alt Speed (Turtle Mode)
                'alt_speed_down', 'alt_speed_up', 'alt_speed_enabled',
                'alt_speed_time_begin', 'alt_speed_time_end',
                'alt_speed_time_day', 'alt_speed_time_enabled',
                # Files & Locations
                'download_dir', 'incomplete_dir', 'incomplete_dir_enabled',
                'rename_partial_files', 'trash_original_torrent_files',
                'start_added_torrents', 'script_torrent_done_enabled',
                'script_torrent_done_filename', 'cache_size_mb',
                # Limits & Queues
                'peer_limit_global', 'peer_limit_per_torrent',
                'download_queue_enabled', 'download_queue_size',
                'seed_queue_enabled', 'seed_queue_size',
                'idle_seeding_limit', 'idle_seeding_limit_enabled',
                'seedRatioLimit', 'seedRatioLimited',
                # Network & Peers
                'encryption', 'dht_enabled', 'pex_enabled', 'lpd_enabled',
                'utp_enabled', 'port_forwarding_enabled', 'peer_port',
                'peer_port_random_on_start',
                # Blocklist
                'blocklist_enabled', 'blocklist_url'
            ]
            data = {}
            for k in keys:
                # Library uses underscores for python attributes usually
                val = getattr(s, k, None)
                if val is not None:
                    data[k] = val
            return data
        except Exception as e:
            print(f"Transmission get prefs error: {e}")
            return None

    def set_app_preferences(self, prefs):
        try:
            # Filter out known keys that shouldn't be passed back if they weren't changed or are read-only?
            # transmission_rpc handles arguments matching session keys.
            # We assume prefs keys match the get_app_preferences keys (underscores)
            self.client.set_session(**prefs)
        except Exception as e:
            raise Exception(f"Failed to set Transmission prefs: {e}")

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
            
            save_path = getattr(s, 'save_path', None)
            if not save_path:
                try:
                    if hasattr(h, 'save_path'):
                        save_path = h.save_path()
                except Exception:
                    save_path = None
            if not save_path:
                save_path = self._get_effective_download_path()

            # Peers and ETA (best effort)
            seeds_connected = getattr(s, 'num_seeds', 0)
            peers_connected = getattr(s, 'num_peers', None)
            if peers_connected is None:
                peers_connected = getattr(s, 'num_connections', 0)
            leechers_connected = 0
            try:
                leechers_connected = max(0, int(peers_connected) - int(seeds_connected))
            except Exception:
                leechers_connected = 0
            seeds_total = getattr(s, 'num_complete', 0)
            leechers_total = getattr(s, 'num_incomplete', 0)

            eta = -1
            try:
                remaining = max(0, int(s.total_wanted) - int(s.total_wanted_done))
                rate = int(getattr(s, 'download_payload_rate', 0) or 0)
                if rate > 0 and remaining > 0:
                    eta = int(remaining / rate)
            except Exception:
                eta = -1

            # Availability (distributed copies) from libtorrent when available.
            availability_copies = None
            try:
                if hasattr(s, "distributed_copies"):
                    availability_copies = float(getattr(s, "distributed_copies"))
                elif hasattr(s, "distributed_full_copies"):
                    full = float(getattr(s, "distributed_full_copies"))
                    frac = getattr(s, "distributed_fraction", None)
                    if frac is not None:
                        try:
                            availability_copies = full + (float(frac) / 1000.0)
                        except Exception:
                            availability_copies = full
                    else:
                        availability_copies = full
            except Exception:
                availability_copies = None

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
                "tracker_domain": tracker,
                "save_path": save_path,
                "eta": eta,
                "seeds_connected": int(seeds_connected) if seeds_connected is not None else 0,
                "seeds_total": int(seeds_total) if seeds_total is not None else 0,
                "leechers_connected": int(leechers_connected) if leechers_connected is not None else 0,
                "leechers_total": int(leechers_total) if leechers_total is not None else 0,
                "availability": availability_copies
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

    def recheck_torrent(self, info_hash):
        h = self._get_handle(info_hash)
        if not h:
            return
        try:
            h.force_recheck()
        except Exception as e:
            raise NotImplementedError(str(e))

    def reannounce_torrent(self, info_hash):
        h = self._get_handle(info_hash)
        if not h:
            return
        try:
            h.force_reannounce()
        except Exception as e:
            raise NotImplementedError(str(e))

    def get_files(self, info_hash):
        h = self._get_handle(info_hash)
        if not h: return []
        try:
            if not h.has_metadata(): return [] 
            ti = h.get_torrent_info()
            files = ti.files()
            progress = h.file_progress()
            priorities = h.file_priorities()
            
            out = []
            for i in range(ti.num_files()):
                size = files.file_size(i)
                p = 0.0
                if size > 0: p = progress[i] / size
                
                # libtorrent priorities: 0=dont_download, 1=low... 4=default, 7=top
                prio = priorities[i]
                std_p = 1
                if prio == 0: std_p = 0
                elif prio > 4: std_p = 2
                
                out.append({
                    "index": i,
                    "name": files.file_path(i),
                    "size": size,
                    "progress": p,
                    "priority": std_p
                })
            return out
        except Exception as e:
            print(f"LocalClient get_files error: {e}")
            return []

    def set_file_priority(self, info_hash, file_index, priority):
        h = self._get_handle(info_hash)
        if not h: return
        try:
            # Map 0->0, 1->4 (default), 2->7 (top)
            p = 4
            if priority == 0: p = 0
            elif priority == 2: p = 7
            h.file_priority(file_index, p)
        except Exception as e:
            print(f"LocalClient set_file_priority error: {e}")

    def get_peers(self, info_hash):
        h = self._get_handle(info_hash)
        if not h: return []
        try:
            pi = h.get_peer_info()
            out = []
            for p in pi:
                out.append({
                    "address": str(p.ip),
                    "client": str(p.client),
                    "progress": float(p.progress),
                    "down_rate": int(p.down_speed),
                    "up_rate": int(p.up_speed)
                })
            return out
        except Exception as e:
            print(f"LocalClient get_peers error: {e}")
            return []

    def get_trackers(self, info_hash):
        h = self._get_handle(info_hash)
        if not h: return []
        try:
            trackers = h.trackers()
            out = []
            for t in trackers:
                out.append({
                    "url": str(t['url']),
                    "status": "Working" if t['verified'] else "Unknown",
                    "peers": 0, # libtorrent tracker list doesn't show peer count directly per entry in this call
                    "message": str(t.get('message', ''))
                })
            return out
        except Exception as e:
            print(f"LocalClient get_trackers error: {e}")
            return []

    def get_torrent_save_path(self, info_hash):
        h = self._get_handle(info_hash)
        if not h:
            return None
        try:
            return getattr(h.status(), 'save_path', None)
        except Exception:
            return None


    def get_default_save_path(self):
        return self._get_effective_download_path()

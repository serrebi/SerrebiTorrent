"""Config management for SerrebiTorrent.

Goals:
- Store config in the app data directory (portable SerrebiTorrent_Data when writable).
- Migrate legacy config.json that lived next to main.py / the EXE.
- Keep a stable, minimal API used by the GUI.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict

from app_paths import get_config_path, get_portable_base_dir


def _read_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


CONFIG_FILE = get_config_path()
LEGACY_CONFIG_FILE = os.path.join(get_portable_base_dir(), "config.json")


DEFAULT_PREFERENCES: Dict[str, Any] = {
    "download_path": os.path.join(os.path.expanduser("~"), "Downloads"),
    "dl_limit": 0,  # 0 = unlimited (bytes/s)
    "ul_limit": 0,  # 0 = unlimited (bytes/s)
    "max_connections": -1,  # -1 = unlimited
    "max_uploads": -1,  # -1 = unlimited
    "listen_port": 6881,
    "enable_upnp": True,
    "enable_natpmp": True,
    "enable_dht": True,
    "enable_lsd": True,
    "auto_start": True,
    "min_to_tray": True,
    "close_to_tray": True,
    "enable_trackers": True,
    "tracker_url": "https://raw.githubusercontent.com/scriptzteam/BitTorrent-Tracker-List/refs/heads/main/trackers_best.txt",
    # 0=None, 1=SOCKS4, 2=SOCKS5, 3=HTTP
    "proxy_type": 0,
    "proxy_host": "",
    "proxy_port": 8080,
    "proxy_user": "",
    "proxy_password": "",
}

DEFAULT_CONFIG: Dict[str, Any] = {
    "default_profile": "",
    "profiles": {},  # uuid -> profile_dict
    "preferences": DEFAULT_PREFERENCES,
}


class ConfigManager:
    def __init__(self) -> None:
        self.config: Dict[str, Any] = self.load_config()

    def _normalize(self, cfg: Dict[str, Any]) -> Dict[str, Any]:
        # Ensure preferences exist and contain all required keys.
        prefs = cfg.get("preferences")
        if not isinstance(prefs, dict):
            prefs = {}
        for k, v in DEFAULT_PREFERENCES.items():
            prefs.setdefault(k, v)
        cfg["preferences"] = prefs

        profiles = cfg.get("profiles")
        if not isinstance(profiles, dict):
            cfg["profiles"] = {}

        cfg.setdefault("default_profile", "")
        return cfg

    def load_config(self) -> Dict[str, Any]:
        # Prefer the new path.
        if os.path.exists(CONFIG_FILE):
            try:
                return self._normalize(_read_json(CONFIG_FILE))
            except Exception:
                return DEFAULT_CONFIG.copy()

        # Migrate legacy config.json if present.
        if os.path.exists(LEGACY_CONFIG_FILE):
            try:
                cfg = self._normalize(_read_json(LEGACY_CONFIG_FILE))
                # Save to the new location. Keep the legacy file untouched.
                try:
                    _write_json(CONFIG_FILE, cfg)
                except Exception:
                    pass
                return cfg
            except Exception:
                return DEFAULT_CONFIG.copy()

        # First run: create a default config.
        cfg = DEFAULT_CONFIG.copy()
        try:
            _write_json(CONFIG_FILE, cfg)
        except Exception:
            pass
        return cfg

    def save_config(self) -> None:
        _write_json(CONFIG_FILE, self.config)

    def get_preferences(self) -> Dict[str, Any]:
        return dict(self.config.get("preferences", DEFAULT_PREFERENCES.copy()))

    def set_preferences(self, prefs: Dict[str, Any]) -> None:
        self.config["preferences"] = dict(prefs)
        self.save_config()

    def get_profiles(self) -> Dict[str, Any]:
        profiles = self.config.get("profiles", {})
        return profiles if isinstance(profiles, dict) else {}

    def add_profile(self, name: str, client_type: str, url: str, user: str, password: str) -> str:
        import uuid

        pid = str(uuid.uuid4())
        self.config.setdefault("profiles", {})[pid] = {
            "name": name,
            "type": client_type,
            "url": url,
            "user": user,
            "password": password,
        }
        self.save_config()
        return pid

    def update_profile(self, pid: str, name: str, client_type: str, url: str, user: str, password: str) -> None:
        if pid in self.get_profiles():
            self.config["profiles"][pid].update(
                {
                    "name": name,
                    "type": client_type,
                    "url": url,
                    "user": user,
                    "password": password,
                }
            )
            self.save_config()

    def delete_profile(self, pid: str) -> None:
        if pid in self.get_profiles():
            del self.config["profiles"][pid]
            if self.config.get("default_profile") == pid:
                self.config["default_profile"] = ""
            self.save_config()

    def get_default_profile_id(self) -> str:
        return str(self.config.get("default_profile", ""))

    def set_default_profile_id(self, pid: str) -> None:
        self.config["default_profile"] = pid
        self.save_config()

    def get_profile(self, pid: str):
        return self.get_profiles().get(pid)

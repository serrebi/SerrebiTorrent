import json
import os
import sys

def get_app_path():
    if getattr(sys, 'frozen', False):
        # If the application is run as a bundle, the PyInstaller bootloader
        # extends the sys module by a flag frozen=True and sets the app 
        # path into variable _MEIPASS'.
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(get_app_path(), "config.json")

DEFAULT_PREFERENCES = {
    "download_path": os.path.join(os.path.expanduser("~"), "Downloads"),
    "dl_limit": 0,       # 0 = unlimited (bytes/s)
    "ul_limit": 0,       # 0 = unlimited (bytes/s)
    "max_connections": -1, # -1 = unlimited
    "max_uploads": -1,     # -1 = unlimited
    "listen_port": 6881,
    "enable_upnp": True,
    "enable_natpmp": True,
    "auto_start": True,
    "min_to_tray": True,
    "close_to_tray": True,
    "enable_trackers": True,
    "tracker_url": "https://raw.githubusercontent.com/scriptzteam/BitTorrent-Tracker-List/refs/heads/main/trackers_best.txt"
}

DEFAULT_CONFIG = {
    "default_profile": "",
    "profiles": {}, # uuid -> profile_dict
    "preferences": DEFAULT_PREFERENCES
}

class ConfigManager:
    def __init__(self):
        self.config = self.load_config()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    cfg = json.load(f)
                    # Ensure preferences exist
                    if "preferences" not in cfg:
                        cfg["preferences"] = DEFAULT_PREFERENCES.copy()
                    else:
                        # Ensure all keys exist in preferences
                        for k, v in DEFAULT_PREFERENCES.items():
                            if k not in cfg["preferences"]:
                                cfg["preferences"][k] = v
                    return cfg
            except:
                return DEFAULT_CONFIG.copy()
        return DEFAULT_CONFIG.copy()

    def save_config(self):
        with open(CONFIG_FILE, 'w') as f:
            json.dump(self.config, f, indent=4)

    def get_preferences(self):
        return self.config.get("preferences", DEFAULT_PREFERENCES.copy())

    def set_preferences(self, prefs):
        self.config["preferences"] = prefs
        self.save_config()

    def get_profiles(self):
        return self.config.get("profiles", {})

    def add_profile(self, name, client_type, url, user, password):
        import uuid
        pid = str(uuid.uuid4())
        self.config.setdefault("profiles", {})[pid] = {
            "name": name,
            "type": client_type,
            "url": url,
            "user": user,
            "password": password
        }
        self.save_config()
        return pid

    def update_profile(self, pid, name, client_type, url, user, password):
        if pid in self.config.get("profiles", {}):
            self.config["profiles"][pid].update({
                "name": name,
                "type": client_type,
                "url": url,
                "user": user,
                "password": password
            })
            self.save_config()

    def delete_profile(self, pid):
        if pid in self.config.get("profiles", {}):
            del self.config["profiles"][pid]
            if self.config.get("default_profile") == pid:
                self.config["default_profile"] = ""
            self.save_config()

    def get_default_profile_id(self):
        return self.config.get("default_profile", "")

    def set_default_profile_id(self, pid):
        self.config["default_profile"] = pid
        self.save_config()

    def get_profile(self, pid):
        return self.config.get("profiles", {}).get(pid)

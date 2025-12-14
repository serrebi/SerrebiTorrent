"""Application path helpers.

Design goals:
- Portable mode: store data in a folder next to the executable/script (SerrebiTorrent_Data)
  when that location is writable.
- Installed mode: fall back to a per-user data directory (AppData on Windows).

Centralizing this logic avoids scattering user-specific hard-coded paths.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

APP_DIR_NAME = "SerrebiTorrent"
PORTABLE_DATA_DIR_NAME = "SerrebiTorrent_Data"

_CACHED_DATA_DIR: Optional[str] = None


def _is_writable_dir(path: str) -> bool:
    try:
        p = Path(path)
        p.mkdir(parents=True, exist_ok=True)
        test_path = p / ".write_test"
        test_path.write_text("ok", encoding="utf-8")
        try:
            test_path.unlink()
        except Exception:
            pass
        return True
    except Exception:
        return False


def get_portable_base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_user_data_base_dir() -> str:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
        if base:
            return base

    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return xdg

    return os.path.join(os.path.expanduser("~"), ".local", "share")


def get_data_dir() -> str:
    """Return the directory where SerrebiTorrent should store config/state/logs."""
    global _CACHED_DATA_DIR
    if _CACHED_DATA_DIR:
        return _CACHED_DATA_DIR

    portable_dir = os.path.join(get_portable_base_dir(), PORTABLE_DATA_DIR_NAME)
    if _is_writable_dir(portable_dir):
        _CACHED_DATA_DIR = portable_dir
        return _CACHED_DATA_DIR

    user_dir = os.path.join(get_user_data_base_dir(), APP_DIR_NAME)
    Path(user_dir).mkdir(parents=True, exist_ok=True)
    _CACHED_DATA_DIR = user_dir
    return _CACHED_DATA_DIR


def ensure_dir(path: str) -> str:
    Path(path).mkdir(parents=True, exist_ok=True)
    return path


def get_config_path() -> str:
    return os.path.join(get_data_dir(), "config.json")


def get_state_dir() -> str:
    return ensure_dir(os.path.join(get_data_dir(), "state"))


def get_logs_dir() -> str:
    return ensure_dir(os.path.join(get_data_dir(), "logs"))


def get_log_path(filename: str = "app.log") -> str:
    return os.path.join(get_logs_dir(), filename)

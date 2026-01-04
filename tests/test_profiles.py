from __future__ import annotations

from config_manager import ConfigManager
import config_manager


def _configure_paths(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    legacy_path = tmp_path / "legacy_config.json"
    monkeypatch.setattr(config_manager, "CONFIG_FILE", str(config_path))
    monkeypatch.setattr(config_manager, "LEGACY_CONFIG_FILE", str(legacy_path))
    return config_path, legacy_path


def test_profiles_creates_default_profile(tmp_path, monkeypatch):
    _configure_paths(tmp_path, monkeypatch)

    cm = ConfigManager()
    profiles = cm.get_profiles()
    assert isinstance(profiles, dict)
    assert profiles, "Default profile should be created automatically"

    default_id = cm.get_default_profile_id()
    assert default_id in profiles

    profile = profiles[default_id]
    assert profile.get("name") == "Local"
    assert profile.get("type") == "local"
    assert "url" in profile

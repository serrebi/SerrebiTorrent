from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import subprocess
import zipfile
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import requests

from app_version import APP_VERSION

GITHUB_OWNER = "serrebi"
GITHUB_REPO = "SerrebiTorrent"
UPDATE_MANIFEST_ASSET = "SerrebiTorrent-update.json"
APP_EXE_NAME = "SerrebiTorrent.exe"

API_TIMEOUT = 15
DOWNLOAD_TIMEOUT = 60

_SEMVER_RE = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")


class UpdateError(Exception):
    pass


class RateLimitError(UpdateError):
    pass


@dataclass
class UpdateInfo:
    current_version: str
    latest_version: str
    manifest: Dict[str, Any]
    release: Dict[str, Any]


def parse_semver(text: str) -> Optional[Tuple[int, int, int]]:
    if not text:
        return None
    match = _SEMVER_RE.search(text.strip())
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def format_version(value: Tuple[int, int, int]) -> str:
    return f"{value[0]}.{value[1]}.{value[2]}"


def is_newer_version(current: Tuple[int, int, int], latest: Tuple[int, int, int]) -> bool:
    return latest > current


def _is_sha256(value: str) -> bool:
    return bool(value) and re.fullmatch(r"[0-9a-fA-F]{64}", value) is not None


def _rate_limit_message(headers: Dict[str, str]) -> str:
    reset = headers.get("X-RateLimit-Reset")
    if reset and reset.isdigit():
        reset_dt = datetime.datetime.utcfromtimestamp(int(reset))
        return f"GitHub API rate limit reached. Try again after {reset_dt:%Y-%m-%d %H:%M:%SZ}."
    return "GitHub API rate limit reached. Try again later."


def fetch_latest_release() -> Dict[str, Any]:
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "SerrebiTorrent-Updater",
    }
    try:
        response = requests.get(url, headers=headers, timeout=API_TIMEOUT)
    except requests.RequestException as exc:
        raise UpdateError(f"Network error while contacting GitHub: {exc}") from exc
    if response.status_code == 403 and response.headers.get("X-RateLimit-Remaining") == "0":
        raise RateLimitError(_rate_limit_message(response.headers))
    if response.status_code != 200:
        raise UpdateError(f"GitHub API error: {response.status_code} {response.reason}")
    try:
        return response.json()
    except json.JSONDecodeError as exc:
        raise UpdateError(f"Failed to parse GitHub API response: {exc}") from exc


def _find_asset(release: Dict[str, Any], name: str) -> Optional[Dict[str, Any]]:
    for asset in release.get("assets", []) or []:
        if asset.get("name") == name:
            return asset
    return None


def download_manifest(release: Dict[str, Any]) -> Dict[str, Any]:
    asset = _find_asset(release, UPDATE_MANIFEST_ASSET)
    if not asset:
        raise UpdateError("Update manifest not found in the latest release.")
    url = asset.get("browser_download_url")
    if not url:
        raise UpdateError("Update manifest asset is missing a download URL.")
    try:
        response = requests.get(url, timeout=API_TIMEOUT)
    except requests.RequestException as exc:
        raise UpdateError(f"Network error while downloading manifest: {exc}") from exc
    if response.status_code != 200:
        raise UpdateError(f"Failed to download update manifest: {response.status_code}")
    try:
        return response.json()
    except json.JSONDecodeError as exc:
        raise UpdateError(f"Update manifest is not valid JSON: {exc}") from exc


def validate_manifest(manifest: Dict[str, Any], release: Dict[str, Any]) -> Dict[str, Any]:
    missing = [k for k in ("version", "asset_filename", "download_url", "sha256", "published_at") if k not in manifest]
    if missing:
        raise UpdateError(f"Update manifest missing required fields: {', '.join(missing)}")

    if not _is_sha256(str(manifest.get("sha256", ""))):
        raise UpdateError("Update manifest has an invalid sha256 checksum.")

    release_tag = release.get("tag_name", "")
    manifest_version = parse_semver(str(manifest.get("version", "")))
    release_version = parse_semver(release_tag)
    if manifest_version and release_version and manifest_version != release_version:
        raise UpdateError("Update manifest version does not match the latest release tag.")

    if not manifest.get("download_url"):
        asset = _find_asset(release, str(manifest.get("asset_filename", "")))
        if asset and asset.get("browser_download_url"):
            manifest["download_url"] = asset["browser_download_url"]

    if not manifest.get("download_url"):
        raise UpdateError("Update manifest does not include a download URL.")

    return manifest


def check_for_update() -> Optional[UpdateInfo]:
    release = fetch_latest_release()
    tag = str(release.get("tag_name", ""))
    latest_tuple = parse_semver(tag)
    current_tuple = parse_semver(APP_VERSION)
    if not latest_tuple:
        raise UpdateError("Latest release tag is not a semver version.")
    if not current_tuple:
        raise UpdateError("Current app version is not a semver version.")
    if not is_newer_version(current_tuple, latest_tuple):
        return None

    manifest = validate_manifest(download_manifest(release), release)
    latest_version = format_version(latest_tuple)
    return UpdateInfo(
        current_version=APP_VERSION,
        latest_version=latest_version,
        manifest=manifest,
        release=release,
    )


def download_file(url: str, dest_path: str) -> None:
    try:
        response = requests.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT)
    except requests.RequestException as exc:
        raise UpdateError(f"Network error while downloading update: {exc}") from exc
    if response.status_code != 200:
        raise UpdateError(f"Download failed: {response.status_code} {response.reason}")
    with open(dest_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                f.write(chunk)


def compute_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_zip(zip_path: str, dest_dir: str) -> None:
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest_dir)


def find_app_dir(staging_dir: str, exe_name: str = APP_EXE_NAME) -> Optional[str]:
    candidate = os.path.join(staging_dir, "SerrebiTorrent", exe_name)
    if os.path.isfile(candidate):
        return os.path.dirname(candidate)
    for root, _dirs, files in os.walk(staging_dir):
        if exe_name in files:
            return root
    return None


def verify_authenticode(exe_path: str) -> None:
    module_paths = []
    for candidate in (
        r"C:\Program Files\WindowsPowerShell\Modules",
        r"C:\Windows\System32\WindowsPowerShell\v1.0\Modules",
    ):
        if os.path.isdir(candidate):
            module_paths.append(candidate)
    module_path = ";".join(module_paths)
    cmd = [
        "powershell",
        "-NoProfile",
        "-Command",
        (
            f"$env:PSModulePath='{module_path}'; "
            "Get-AuthenticodeSignature -FilePath "
            f"'{exe_path}' | Select-Object -Property Status,StatusMessage | ConvertTo-Json"
        ),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise UpdateError(f"Signature verification failed: {result.stderr.strip()}")
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise UpdateError("Signature verification did not return valid JSON.") from exc
    status = str(data.get("Status", ""))
    if status.lower() != "valid":
        msg = data.get("StatusMessage", "Unknown signature status.")
        raise UpdateError(f"Authenticode signature is not valid: {msg}")


def build_update_prompt(info: UpdateInfo) -> str:
    notes = str(info.manifest.get("notes_summary") or "").strip()
    if len(notes) > 1200:
        notes = notes[:1200].rstrip() + "..."
    details = f"Current version: v{info.current_version}\nLatest version: v{info.latest_version}"
    if notes:
        return f"{details}\n\nRelease summary:\n{notes}\n\nDownload and install now?"
    return f"{details}\n\nDownload and install now?"

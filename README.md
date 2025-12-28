# SerrebiTorrent

SerrebiTorrent is a Windows desktop app that lets you keep tabs on your torrents--whether they live on this PC or on a remote seedbox--without giving up accessibility or keyboard control. 

## What you get
- Connect to local libtorrent, rTorrent (SCGI/XML-RPC), qBittorrent, or Transmission from a single interface.
- Live download/upload speeds, progress, ratio, tracker host, and status messages for each torrent.
- **New:** create your own torrents!.
- **Performance:** Background processing for all remote client interactions (updates, deletions, start/stop) ensures the UI remains responsive and lag-free.
- Quick filters (All, Downloading, Complete, Active) plus a tracker tree in the sidebar.
- Thoughtful keyboard workflow and tray support that play nicely with NVDA and other screen readers.

## Quick start on Windows
Grab the latest release from the releases section:
https://github.com/serrebi/SerrebiTorrent/releases

SerrebiTorrent is a portable app. Download the ZIP file, extract the entire `SerrebiTorrent` folder to a location of your choice, and run `SerrebiTorrent.exe`. **Note:** Do not move the `.exe` out of its folder, as it requires the accompanying files to run.

## How to build
I will not be going through installing python, and such. I assume you know how to do that, or can do it with Codex or Gemini.

git clone https://github.com/serrebi/SerrebiTorrent

Pip3 install -r ./requirements.txt
build_exe.bat build

The `.spec` is configured for a directory distribution (`onedir`) to ensure maximum compatibility. It automatically packages the `web_static` folder (web UI) and the OpenSSL 1.1 DLLs. Keep those files in the repo root before building.

The build output will be a folder named `SerrebiTorrent` inside the `dist` directory. To distribute the app, ZIP this entire folder.

## Release pipeline (automated)
Prereqs:
- Python 3.12 + dependencies from `requirements.txt`
- Git + GitHub CLI (`gh auth login` completed)
- Code signing cert installed
- SignTool available (default path used, or set `SIGNTOOL_PATH`)

Commands:
- `build_exe.bat build` builds, signs, and zips locally.
- `build_exe.bat release` auto-bumps version, builds, signs, zips, tags, pushes, creates the GitHub release, and uploads the update manifest.
- `build_exe.bat dry-run` shows what it would do without modifying anything.

Versioning uses the latest `vMAJOR.MINOR.PATCH` tag as the base. If none exists, it starts at `v1.0.0`. Commits with `BREAKING CHANGE` or `!:` bump major; commits starting with `feat` (or containing `feature`) bump minor; otherwise it bumps patch.

## Auto-updater (Windows)
The app checks GitHub Releases for updates. By default it auto-checks on startup (toggle in Preferences). You can also use Tools -> Check for Updates.

Update flow:
- Downloads the release ZIP from GitHub using the update manifest asset (`SerrebiTorrent-update.json`).
- Verifies the ZIP SHA-256 from the manifest.
- Verifies Authenticode signature on the new `SerrebiTorrent.exe`.
- Uses a helper script to swap folders safely, keep a backup, and restart the app.

## Accessibility & shortcuts
Everything stays reachable by keyboard:
- Ctrl+Shift+C: Connection Manager
- Ctrl+O / Ctrl+U: Add torrent file / Add URL or magnet
- Ctrl+S / Ctrl+P: Start / Stop selected torrents
- Delete / Shift+Delete: Remove / Remove with data
- Ctrl+A: Select all
- Tab: Toggle focus between the sidebar and torrent list; double-clicking the tray icon restores the window.
- Control N will allow you to create a torrent.

Need to troubleshoot? Logs live under `SerrebiTorrent_Data\logs` next to the EXE/script in portable mode (or per-user app data in installed mode). Open `agents.md` if you need technical or build details.

## Test plan (manual)
- Build a release with `build_exe.bat release` and extract the ZIP to a folder like `C:\Temp\SerrebiTorrent-old`.
- Create a newer release (make a small commit, then run `build_exe.bat release` again).
- Launch the older app, run Tools -> Check for Updates, accept the prompt, and confirm:
  - The app closes and restarts on the new version.
  - A backup folder `SerrebiTorrent_Backup_YYYYMMDD_HHMMSS` exists next to the install directory.
  - The status bar reports update status or errors clearly.




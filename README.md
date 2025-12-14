# SerrebiTorrent

SerrebiTorrent is a portable Windows client that keeps you in control of torrents on your PC or a remote seedbox—fast, keyboard-friendly, and screen-reader aware.

## Highlights
- One interface for local libtorrent, rTorrent (SCGI/XML-RPC), qBittorrent, and Transmission.
- Live stats (speeds, progress, ratio, tracker host, status) plus quick filters (All, Downloading, Complete, Active) and a tracker tree.
- Create torrents, manage remote clients in the background, and keep the UI responsive even when rTorrent or Transmission live elsewhere.
- Designed for keyboard workflows, tray control, and NVDA-friendly navigation.

## Download & run
1. Grab the latest ZIP from the [Releases page](https://github.com/serrebi/SerrebiTorrent/releases).
2. Extract it to an empty folder.
3. Launch `SerrebiTorrent.exe` (portable mode doesn’t touch your registry or user profile).

## Build (Python + PyInstaller)
1. Clone the repo: `git clone https://github.com/serrebi/SerrebiTorrent`
2. Install dependencies: `pip3 install -r requirements.txt`
3. Build: `pyinstaller --noconfirm --clean SerrebiTorrent.spec`
4. Grab the `.exe` from `dist\SerrebiTorrent\`.

## Accessibility & shortcuts
Everything is keyboard-accessible:
- `Ctrl+Shift+C`: Connection manager
- `Ctrl+O` / `Ctrl+U`: Add torrent file / Add URL or magnet
- `Ctrl+S` / `Ctrl+P`: Start / Stop selections
- `Ctrl+A`: Select all
- `Delete` / `Shift+Delete`: Remove / Remove + data
- `Tab`: Toggle focus between sidebar and list
- `Ctrl+N`: Create new torrent
- Double-click tray icon to restore the window.

Logs live under `SerrebiTorrent_Data\logs` beside the EXE (portable) or under per-user app data (installed). Refer to `agents.md` for deep dives on agents and builds.





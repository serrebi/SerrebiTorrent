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
Grab the latest release from the releases section, 
https://github.com/serrebi/SerrebiTorrent/releases
and place it in an empty folder. Unless I release setup files one day, It is a portable app.

## How to build
I will not be going through installing python, and such. I asume you know how to do that, or can do it with Codex or Gemini.

git clone https://github.com/serrebi/SerrebiTorrent

Pip3 install -r ./requirements.txt
PyInstaller --noconfirm --clean SerrebiTorrent.spec
The spec already packages the `web_static` folder (web UI) and the OpenSSL 1.1 DLLs; keep those files in the repo root before building.
The .exe will be in the dist folder.
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





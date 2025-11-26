# SerrebiTorrent

SerrebiTorrent is a Windows desktop app that lets you keep tabs on your torrents--whether they live on this PC or on a remote seedbox--without giving up accessibility or keyboard control. Launch it, pick (or create) a profile, and you can start or stop torrents, add new ones from files or magnet/HTTP links, and watch real-time stats for every tracker.

## What you get
- Connect to local libtorrent, rTorrent (SCGI/XML-RPC), qBittorrent, or Transmission from a single interface.
- Live download/upload speeds, progress, ratio, tracker host, and status messages for each torrent.
- Quick filters (All, Downloading, Complete, Active) plus a tracker tree in the sidebar.
- Thoughtful keyboard workflow and tray support that play nicely with NVDA and other screen readers.

## Quick start on Windows
1. Download or clone the SerrebiTorrent folder.
2. Want the packaged build? Open `dist\SerrebiTorrent.exe`. Prefer source mode? Install Python 3.13 (64-bit), run `pip install -r requirements.txt`, then `python main.py`.
3. The Connection Manager opens on first launch--add a profile that matches where your torrents run (local path, rTorrent URL, etc.).
4. Click Connect and the main window refreshes every couple of seconds.

## Connecting to your client
- **Local**: point the profile at your download directory. SerrebiTorrent owns a hidden libtorrent session so magnets just work.
- **rTorrent**: use `scgi://host:port` for SCGI or `https://domain/RPC2` for XML-RPC. Basic auth and common SSO front ends are handled.
- **qBittorrent / Transmission**: enter the WebUI URL plus your credentials. The app speaks the native APIs.

## Everyday tips
- Add torrents through File -> Add Torrent File or File -> Add URL/Magnet. Magnets inherit any tracker list you define under Preferences -> Trackers.
- The status bar shows global download/upload rates whenever you are connected.
- Use the Torrent menu (or right-click) to start, stop, or remove selections, with Shift+Delete removing data too.
- Preferences let you set default paths, global limits, and whether close/minimize sends the window to the tray.

## Accessibility & shortcuts
Everything stays reachable by keyboard:
- Ctrl+Shift+C: Connection Manager
- Ctrl+O / Ctrl+U: Add torrent file / Add URL or magnet
- Ctrl+S / Ctrl+P: Start / Stop selected torrents
- Delete / Shift+Delete: Remove / Remove with data
- Ctrl+A: Select all
- Tab: Toggle focus between the sidebar and torrent list; double-clicking the tray icon restores the window.

Need to troubleshoot? Logs and helper scripts now live in `C:\Users\admin\coding\debug`, so the main folder stays clean. Open `agents.md` if you need technical or build details. Otherwise, enjoy managing your torrents without fuss.







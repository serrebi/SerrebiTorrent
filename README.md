# SerrebiTorrent

SerrebiTorrent is a Windows desktop app that lets you keep tabs on your torrents--whether they live on this PC or on a remote seedbox--without giving up accessibility or keyboard control. Launch it, pick (or create) a profile, and you can start or stop torrents, add new ones from files or magnet/HTTP links, and watch real-time stats for every tracker.

## What you get
- Connect to local libtorrent, rTorrent (SCGI/XML-RPC), qBittorrent, or Transmission from a single interface.
- Live download/upload speeds, progress, ratio, tracker host, and status messages for each torrent.

- **Performance:** Background processing for all remote client interactions (updates, deletions, start/stop) ensures the UI remains responsive and lag-free.
- Quick filters (All, Downloading, Complete, Seeding, Active, etc) plus a tracker tree in the sidebar.
- Thoughtful keyboard workflow and tray support that play nicely with NVDA and other screen readers.

## Quick start on Windows
1. Download or clone the SerrebiTorrent folder.
2. Want the packaged build? Open the releases page and download the latest release!
3.  Prefer source mode? Install Python 3.13 (64-bit), run `pip install -r requirements.txt`, then `python main.py`.
4. The Connection Manager opens on first launch--add a profile that matches where your torrents run (local path, rTorrent URL, etc.).
5. Click Connect and the main window refreshes every couple of seconds.


## Everyday tips
- Add torrents through File -> Add Torrent File or File -> Add URL/Magnet. Magnets inherit any tracker list you define under Preferences -> Trackers.
- The status bar shows global download/upload rates whenever you are connected.
- Use the Torrent menu (or right-click) to start, stop, or remove selections, with Shift+Delete removing data too.
- Preferences let you set default paths, global limits, and whether close/minimize sends the window to the tray.

## Keyboard shortcuts
- Ctrl+Shift+C: Connection Manager
- Ctrl+O / Ctrl+U: Add torrent file / Add URL or magnet
- Ctrl+S / Ctrl+P: Start / Stop selected torrents
- Delete / Shift+Delete: Remove / Remove with data
- Ctrl+A: Select all
- Tab: Toggle focus between the sidebar and torrent list; double-clicking the tray icon restores the window.

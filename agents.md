# SerrebiTorrent – agent notes

## Repo facts
- Location: Assume Windows 11, 64‑bit.
- Entry point: `main.py`. GUI built with wxPython.
- Background libtorrent session lives in `session_manager.py`. Do not duplicate sessions.


## Runtime requirements
- Python 3.13 (64‑bit Store build). Path: `C:\Users\admin\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\python.exe`.
- Core packages: see `requirements.txt`. Libs already installed in the user site-packages.
- Libtorrent DLL resolution happens in `libtorrent_env.py`. Always call `prepare_libtorrent_dlls()` before importing `libtorrent`.
- OpenSSL 1.1 DLLs (`libcrypto-1_1*.dll`, `libssl-1_1*.dll`) sit in the repo root and must ship with the EXE.

## Threading Model
- **Blocking I/O:** All network operations (fetching torrents, sending commands like start/stop/remove) MUST be offloaded to a background thread to prevent freezing the GUI.
- **Implementation:** `MainFrame` uses a `concurrent.futures.ThreadPoolExecutor`.
- **Pattern:**
    1. UI event triggers a method (e.g., `on_remove`).
    2. Method submits a worker function (e.g., `_remove_background`) to `self.thread_pool`.
    3. Worker function performs blocking calls.
    4. Worker uses `wx.CallAfter` to invoke a UI-thread method (e.g., `_on_action_complete`) to update the display/statusbar.
    5. **Never** call `self.client` methods directly from the main GUI thread.

## Build commands
- Install deps (only if new environment): `python -m pip install -r requirements.txt` (Store Python, 64‑bit).
- Build EXE: `pyinstaller SerrebiTorrent.spec`. Output lands in `dist\\SerrebiTorrent.exe`.
- **Important:** The `.spec` file explicitly includes OpenSSL binaries (`libssl-1_1*.dll`, `libcrypto-1_1*.dll`). Ensure these are present in the root directory before building.
- Legacy spec filename `rtorrentGUI.spec` still exists for backwards compatibility; it points to the same settings and emits SerrebiTorrent.exe.

## Packaging
- Ship the entire `dist` folder: EXE + `config.json` + bundled libraries. No extra installers are provided.
- If you rebrand the EXE, update both `.spec` files and any doc references. Remember to refresh the tray icon (`icon.ico`) if you change branding.

## Ops notes
- Local mode needs the OpenSSL DLLs in `PATH`; `libtorrent_env.py` already injects both the repo root and Python’s `DLLs` directory. Don’t delete that helper.
- Connection profiles, preferences, and session state write to `SerrebiTorrent_Data` under the repo (portable mode). Keep that directory next to the EXE if you expect resume data to persist.
- Accessibility shortcuts are hard-coded in `MainFrame.__init__`. Update README if you touch them.
- If you must run tests, there are no automated suites. Launch `python main.py` and exercise the UI manually.

Keep edits lean, comment only when code is not self-explanatory, and leave user-facing docs in README.md. Everything technical goes here.


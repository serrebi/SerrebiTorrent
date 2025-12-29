# SerrebiTorrent – agent notes

## Repo facts
- Location: Assume Windows 11, 64‑bit.
- Entry point: `main.py`. GUI built with wxPython.
- Background libtorrent session lives in `session_manager.py`. Do not duplicate sessions.


## Runtime requirements
- Python 3.12 (64‑bit).
- Core packages: see `requirements.txt`. Libs already installed in the user site-packages.
- Libtorrent DLL resolution happens in `libtorrent_env.py`. Always call `prepare_libtorrent_dlls()` before importing `libtorrent`.
- OpenSSL 1.1 DLLs (`libcrypto-1_1*.dll`, `libssl-1_1*.dll`) sit in the repo root and are bundled into the EXE.

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
- Install deps (only if new environment): `python -m pip install -r requirements.txt`.
- Build EXE: `pyinstaller SerrebiTorrent.spec`. Output lands in `dist\\SerrebiTorrent\\`.
- The `.spec` file is configured for a directory-based distribution (`onedir`) to improve stability and startup performance. It includes all submodules for major dependencies (`flask`, `requests`, `qbittorrentapi`, `transmission_rpc`, `bs4`, `yaml`, etc.) using `collect_submodules`.
- It also bundles the web UI (`web_static`), OpenSSL DLLs, and other resources into the distribution folder.
- Hidden imports explicitly include local modules (`clients`, `rss_manager`, `web_server`, etc.) and core dependency sub-components (`werkzeug`, `jinja2`, `urllib3`) to ensure compatibility across different environments.
- `icon.ico` is conditionally included in the build only if it exists in the root directory.
- All OpenSSL 1.1 variants are explicitly added (`libssl-1_1*.dll`, `libcrypto-1_1*.dll`); keep these four DLLs in the repo root before building.

## Packaging
- Ship the entire `SerrebiTorrent` folder from the `dist` directory. The main executable is `SerrebiTorrent.exe` inside that folder.
- User data (profiles, preferences, resume data, logs) lives under `SerrebiTorrent_Data` next to the EXE (or the distribution folder) in portable mode.
- To preconfigure profiles for distribution, ship a `SerrebiTorrent_Data\config.json` (use `config.example.json` as a starting point).
- If you rebrand the EXE, update the `.spec` file and any doc references. Remember to refresh the tray icon (`icon.ico`) if you change branding.

## Ops notes
- Local mode needs the OpenSSL DLLs in `PATH`; `libtorrent_env.py` already injects both the repo root and Python's `DLLs` directory. Don't delete that helper.
- Connection profiles, preferences, session state, and logs write to `SerrebiTorrent_Data` (portable mode) or per-user app data (installed mode).
- Accessibility shortcuts are hard-coded in `MainFrame.__init__`. Update README if you touch them.
- If you must run tests, there are no automated suites. Launch `python main.py` and exercise the UI manually.

## Update notes
- The updater accepts a `signing_thumbprint` value in the release manifest so self-signed Authenticode signatures can be trusted when Windows reports UnknownError.

Keep edits lean, comment only when code is not self-explanatory, and leave user-facing docs in README.md. Everything technical goes here.

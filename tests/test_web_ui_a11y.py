import threading

import pytest
from werkzeug.serving import make_server

import web_server

pytest.importorskip("pytest_playwright")
pytest.importorskip("axe_playwright_python")

from axe_playwright_python.sync_playwright import Axe

pytestmark = pytest.mark.e2e


class DummyConfigManager:
    def __init__(self, profiles):
        self._profiles = profiles

    def get_profiles(self):
        return self._profiles


class DummyApp:
    def __init__(self, torrents, profiles, current_profile_id):
        self.all_torrents = torrents
        self.config_manager = DummyConfigManager(profiles)
        self.current_profile_id = current_profile_id

    def _open_path(self, path):
        return None


class DummyClient:
    def __init__(self, torrents):
        self._torrents = torrents

    def get_torrents_full(self):
        return list(self._torrents)

    def get_files(self, h):
        return []


@pytest.fixture(scope="session")
def web_ui_server():
    torrents = [
        {
            "hash": "a" * 40,
            "name": "Alpha",
            "size": 1000,
            "done": 250,
            "state": 1,
            "message": "",
            "tracker_domain": "tracker.one",
            "down_rate": 0,
            "up_rate": 0,
            "save_path": "C:\\Downloads",
        },
        {
            "hash": "b" * 40,
            "name": "Beta",
            "size": 1000,
            "done": 1000,
            "state": 1,
            "message": "",
            "tracker_domain": "tracker.two",
            "down_rate": 0,
            "up_rate": 0,
            "save_path": "C:\\Downloads",
        },
    ]
    profiles = {
        "local": {
            "name": "Local",
            "type": "local",
            "url": "C:\\Downloads",
            "user": "",
            "password": "",
        }
    }
    app_ref = DummyApp(torrents, profiles, "local")
    client = DummyClient(torrents)

    original_config = web_server.WEB_CONFIG.copy()
    web_server.WEB_CONFIG.update(
        {
            "app": app_ref,
            "client": client,
            "username": "admin",
            "password": "password",
        }
    )

    server = make_server("127.0.0.1", 0, web_server.app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"

    try:
        yield url
    finally:
        server.shutdown()
        thread.join()
        web_server.WEB_CONFIG.update(original_config)


def _block_cdn(route):
    route.fulfill(status=200, body="")


def _login(page, base_url):
    page.route("https://cdn.jsdelivr.net/**", _block_cdn)
    page.goto(f"{base_url}/login.html")
    page.fill("#username", "admin")
    page.fill("#password", "password")
    page.click("button[type=submit]")
    page.wait_for_url(f"{base_url}/")
    page.wait_for_selector("#torrentTable")
    page.wait_for_selector("tr[data-hash]")


def test_web_ui_axe(page, web_ui_server):
    _login(page, web_ui_server)
    axe = Axe()
    results = axe.run(page)
    assert results.violations_count == 0, results.generate_report()


def test_web_ui_keyboard_navigation(page, web_ui_server):
    _login(page, web_ui_server)
    page.wait_for_function("document.querySelectorAll('tr[data-hash]').length >= 2")
    page.wait_for_function("document.activeElement && document.activeElement.matches('tr[data-hash]')")
    first_hash = page.evaluate("document.activeElement.getAttribute('data-hash')")
    page.keyboard.press("ArrowDown")
    page.wait_for_function(
        "(prev) => document.activeElement && document.activeElement.getAttribute('data-hash') !== prev",
        arg=first_hash,
    )
    active_hash = page.evaluate("document.activeElement.getAttribute('data-hash')")
    assert active_hash and active_hash != first_hash


def test_web_ui_landmarks(page, web_ui_server):
    _login(page, web_ui_server)
    assert page.locator("header[role='banner']").count() == 1
    assert page.locator("main[role='main']").count() == 1
    assert page.locator("nav[aria-label='Navigation']").count() == 1

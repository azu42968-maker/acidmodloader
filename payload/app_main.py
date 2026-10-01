import urllib.parse
from pathlib import Path

import webview

import adblock
from api import Api

ACID_URL = "https://acidorg.com/#mods"
GAMEBANANA_URL = "https://gamebanana.com/mods/games/5704"

ACID_SCRIPT = (Path(__file__).parent / "modloader_inject.js").read_text(encoding="utf-8")
GAMEBANANA_SCRIPT = (Path(__file__).parent / "gamebanana_inject.js").read_text(encoding="utf-8")
MANAGER_SCRIPT = (Path(__file__).parent / "modmanager_inject.js").read_text(encoding="utf-8")
UPDATE_SCRIPT = (Path(__file__).parent / "update_inject.js").read_text(encoding="utf-8")


def main() -> None:
    api = Api()
    window = webview.create_window(
        "Acid Mod Loader",
        ACID_URL,
        js_api=api,
        width=1320,
        height=860,
        min_size=(1024, 700),
        background_color="#08090a",
        maximized=True,
    )

    def inject():
        try:
            current_url = window.get_current_url() or ""
        except Exception:
            current_url = ""
        host = urllib.parse.urlparse(current_url).hostname or ""
        if host.endswith("gamebanana.com"):
            window.evaluate_js(GAMEBANANA_SCRIPT)
        else:
            window.evaluate_js(ACID_SCRIPT)
        window.evaluate_js(MANAGER_SCRIPT)
        window.evaluate_js(UPDATE_SCRIPT)
        adblock.install(window, api.get_adblock())  # solo actua la primera vez
        adblock.on_loaded(window, host)

    window.events.loaded += inject

    webview.start(debug=False, gui="edgechromium")


if __name__ == "__main__":
    main()

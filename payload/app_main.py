import importlib.util
import json
import sys
import threading
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


# Aviso de Azu Modification: autocontenido (no depende de los .js inyectados) y sin innerHTML.
AZUMOD_BANNER_JS = """
(function (info) {
  if (document.getElementById('acid-azumod-banner') || !window.pywebview || !window.pywebview.api) return;
  var api = window.pywebview.api;
  var box = document.createElement('div');
  box.id = 'acid-azumod-banner';
  box.style.cssText = 'position:fixed;left:16px;bottom:16px;z-index:2147483647;max-width:380px;' +
    'padding:12px 14px;border-radius:10px;background:#1f2937;color:#fff;font:13px/1.4 system-ui,sans-serif;' +
    'box-shadow:0 6px 24px rgba(0,0,0,.35);display:flex;gap:10px;align-items:flex-start';
  var text = document.createElement('div'); text.style.flex = '1';
  text.textContent = info.installed
    ? 'Azu Modification ' + info.latest + ' is available (you have ' + info.installed + ').'
    : 'Azu Modification ' + info.latest + ' is available to install.';
  var act = document.createElement('button');
  act.textContent = info.installed ? 'Update' : 'Install';
  var btnCss = 'background:#3b82f6;border:0;color:#fff;border-radius:6px;padding:4px 10px;cursor:pointer;font:inherit';
  act.style.cssText = btnCss;
  var close = document.createElement('button');
  close.textContent = '\\u00d7';
  close.style.cssText = 'background:none;border:0;color:#fff;font-size:18px;cursor:pointer;line-height:1';
  close.onclick = function () { box.remove(); try { api.azumod_dismiss(info.latest); } catch (e) {} };
  act.onclick = async function () {
    act.disabled = true; act.textContent = 'Downloading...';
    var r;
    try { r = await api.azumod_install(); } catch (e) { r = {ok: false, error: String(e)}; }
    if (r && r.ok) {
      text.textContent = 'Azu Modification ' + (r.version || info.latest) + ' is ready.';
      act.disabled = false; act.textContent = 'Open';
      act.onclick = function () { api.azumod_launch(); box.remove(); };
    } else {
      text.textContent = (r && r.error) || 'Could not install Azu Modification.';
      act.disabled = false; act.textContent = 'Retry';
    }
  };
  box.appendChild(text); box.appendChild(act); box.appendChild(close);
  document.body.appendChild(box);
})(__INFO__);
"""

_azumod = {"info": None, "started": False}


def _show_azumod_banner(window, api) -> None:
    info = _azumod["info"]
    if not info or api.cfg.get("azumod_dismissed_tag") == info.get("latest"):
        return
    try:
        window.evaluate_js(AZUMOD_BANNER_JS.replace("__INFO__", json.dumps(
            {"installed": info.get("installed"), "latest": info.get("latest")})))
    except Exception:
        pass


def _azumod_check_bg(window, api) -> None:
    """Consulta GitHub sin bloquear; sin internet o con error no hace nada."""
    try:
        info = api.azumod_check()
        if info.get("available") and not info.get("dismissed"):
            _azumod["info"] = info
            _show_azumod_banner(window, api)
    except Exception:
        pass


def _pick_gui():
    """Windows: WebView2. Linux: Qt si esta instalado (mas fiable en KDE/Bazzite); si no, que
    pywebview elija. macOS: el motor nativo."""
    if sys.platform == "win32":
        return "edgechromium"
    if sys.platform.startswith("linux") and importlib.util.find_spec("qtpy") is not None:
        return "qt"
    return None


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
        _show_azumod_banner(window, api)          # se reinyecta tras cada navegacion
        if not _azumod["started"]:
            _azumod["started"] = True
            threading.Thread(target=_azumod_check_bg, args=(window, api), daemon=True).start()

    window.events.loaded += inject

    webview.start(debug=False, gui=_pick_gui())


if __name__ == "__main__":
    main()

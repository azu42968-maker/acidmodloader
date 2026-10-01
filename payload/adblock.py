"""
Bloqueador de anuncios para GameBanana (solo dentro de la ventana de la app).

Tres capas, cada una funciona aunque las otras fallen:
  1. Red:   WebView2 (WebResourceRequested) corta las peticiones a dominios de
            anuncios antes de que se descarguen.
  2. CSS:   oculta los contenedores de anuncios (script al crear el documento).
  3. Aviso: oculta el cartel "Ads keep us online / unblock us".

Reglas en adblock_rules.json (se actualizan con el payload). Cada usuario puede
agregar las suyas en %LOCALAPPDATA%\\AcidModLoader\\adblock_user.json.
"""
from __future__ import annotations

import json
import threading
import urllib.parse
from collections import Counter
from pathlib import Path

from appdirs import get_appdata_dir

_DIR = Path(__file__).parent
_lock = threading.Lock()
_blocked: Counter = Counter()
_keep: list = []  # referencias para que el GC no mate los handlers .NET
_rules: dict = {}
_js: str = ""
_state = {"enabled": True, "installed": False, "network": False, "script": False, "error": ""}


def _load_rules() -> dict:
    rules = json.loads((_DIR / "adblock_rules.json").read_text(encoding="utf-8"))
    user_file = get_appdata_dir() / "adblock_user.json"
    if user_file.is_file():
        try:
            extra = json.loads(user_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            extra = {}
        for key in ("domains", "selectors", "allow", "notice"):
            rules[key] = list(rules.get(key, [])) + [x for x in extra.get(key, []) if isinstance(x, str)]
    return rules


def _host_in(host: str, domains: set[str]) -> bool:
    parts = host.lower().rstrip(".").split(".")
    return any(".".join(parts[i:]) in domains for i in range(len(parts) - 1))


def _build_js(rules: dict) -> str:
    payload = {"selectors": rules.get("selectors", []), "notice": rules.get("notice", [])}
    template = (_DIR / "adblock_inject.js").read_text(encoding="utf-8")
    return template.replace("__RULES__", json.dumps(payload))


def _find_control(window):
    native = getattr(window, "native", None)
    if native is None:
        raise RuntimeError("window.native no disponible")
    for chain in (("browser", "webview"), ("webview",), ("browser", "web_view")):
        obj = native
        for attr in chain:
            obj = getattr(obj, attr, None)
            if obj is None:
                break
        if obj is not None:
            return native, obj
    raise RuntimeError("no encontre el control WebView2")


def _install_native(window) -> None:
    from System import Action  # pythonnet (ya viene con pywebview)

    native, control = _find_control(window)
    domains = {d.lower() for d in _rules.get("domains", [])}
    allow = {d.lower() for d in _rules.get("allow", [])}
    problems: list[str] = []

    def work() -> None:  # corre en el hilo de UI de WinForms
        try:
            core = control.CoreWebView2
            if core is None:
                raise RuntimeError("CoreWebView2 todavia no esta listo")
            from Microsoft.Web.WebView2.Core import CoreWebView2WebResourceContext

            def on_request(sender, args) -> None:
                try:
                    if not _state["enabled"]:
                        return
                    host = urllib.parse.urlparse(str(args.Request.Uri)).hostname or ""
                    if not host or _host_in(host, allow) or not _host_in(host, domains):
                        return
                    args.Response = core.Environment.CreateWebResourceResponse(None, 204, "Blocked", "")
                    with _lock:
                        _blocked[host] += 1
                except Exception:
                    pass  # nunca romper la carga de la pagina

            core.WebResourceRequested += on_request
            core.AddWebResourceRequestedFilter("*", CoreWebView2WebResourceContext.All)
            _keep.append(on_request)
            _state["network"] = True

            try:
                core.AddScriptToExecuteOnDocumentCreatedAsync(_js)
                _state["script"] = True
            except Exception as e:  # el CSS igual se inyecta en 'loaded'
                problems.append(f"script: {e}")
        except Exception as e:
            problems.append(f"{type(e).__name__}: {e}")

    native.Invoke(Action(work))
    if problems:
        raise RuntimeError("; ".join(problems))


def install(window, enabled: bool = True) -> None:
    """Llamar una vez (en el primer 'loaded'). Nunca lanza excepciones."""
    global _rules, _js
    if _state["installed"]:
        return
    _state["installed"] = True
    _state["enabled"] = bool(enabled)
    try:
        _rules = _load_rules()
        _js = _build_js(_rules)
        _install_native(window)
    except Exception as e:
        _state["error"] = str(e)  # queda solo la capa CSS (via on_loaded)


def on_loaded(window, host: str) -> None:
    """En cada carga: refuerza el CSS en GameBanana y aplica el estado on/off."""
    if not _js or not host.endswith("gamebanana.com"):
        return
    try:
        window.evaluate_js(_js)
        window.evaluate_js(f"window.__acidAdblock && window.__acidAdblock.{'on' if _state['enabled'] else 'off'}()")
    except Exception:
        pass


def set_enabled(window, enabled: bool) -> None:
    _state["enabled"] = bool(enabled)
    try:
        window.evaluate_js(f"window.__acidAdblock && window.__acidAdblock.{'on' if enabled else 'off'}()")
    except Exception:
        pass


def stats() -> dict:
    with _lock:
        top = _blocked.most_common(8)
        total = sum(_blocked.values())
    return {**_state, "blocked": total, "top": top}

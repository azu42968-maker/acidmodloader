"""
Entrypoint del .exe. Cambia casi nunca; todo lo demás vive en payload/.

Orden al arrancar:
  1. Si hay una actualización descargada (app.pending), se activa ANTES de
     importar nada (así no hay archivos bloqueados en Windows).
  2. Se elige el payload con la versión más alta entre:
       - %LOCALAPPDATA%/AcidModLoader/app   (descargado de GitHub)
       - <exe>/payload                      (copia empaquetada, respaldo)
  3. Si el payload descargado revienta al arrancar, se pone en cuarentena
     (app.bad) y se arranca el empaquetado.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

# Súbelo solo si un payload nuevo necesita algo que el .exe actual no trae
# (una librería nueva, otra versión de pywebview, etc.). El updater se niega
# a instalar payloads que pidan un launcher_api mayor.
LAUNCHER_API = 1
os.environ["ACID_LAUNCHER_API"] = str(LAUNCHER_API)

APP_NAME = "AcidModLoader"
FAST_FAIL_SECONDS = 20  # si crashea antes de esto, asumimos que el payload está roto


def _appdata_dir() -> Path:
    # Misma lógica que appdirs.get_appdata_dir (duplicada a propósito: appdirs.py
    # vive en el payload y todavía no se puede importar).
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Local"
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        base = os.environ.get("XDG_DATA_HOME")
        root = Path(base) if base else Path.home() / ".local" / "share"
    d = root / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _bundled_payload() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / "payload"


def _version_tuple(d: Path) -> tuple[int, ...] | None:
    try:
        data = json.loads((d / "version.json").read_text(encoding="utf-8"))
        if not (d / "app_main.py").is_file():
            return None
        return tuple(int(x) for x in re.findall(r"\d+", str(data["version"])))
    except Exception:
        return None


def _activate_pending(root: Path) -> None:
    pending, live, old = root / "app.pending", root / "app", root / "app.old"
    if not pending.is_dir():
        return
    try:
        shutil.rmtree(old, ignore_errors=True)
        if live.exists():
            live.rename(old)
        pending.rename(live)
    except OSError:
        # Se reintenta en el próximo arranque.
        pass


def _pick_payload(root: Path) -> tuple[Path, bool]:
    bundled = _bundled_payload()
    live = root / "app"
    vb, vl = _version_tuple(bundled), _version_tuple(live)
    if vl is not None and (vb is None or vl > vb):
        return live, True
    return bundled, False


def _run(payload: Path) -> None:
    sys.path.insert(0, str(payload))
    import app_main  # noqa: E402  (vive en payload/)

    app_main.main()


def _drop_payload(payload: Path) -> None:
    for p in payload.glob("*.py"):
        sys.modules.pop(p.stem, None)
    try:
        sys.path.remove(str(payload))
    except ValueError:
        pass


def main() -> None:
    root = _appdata_dir()
    _activate_pending(root)
    payload, is_live = _pick_payload(root)

    started = time.time()
    try:
        _run(payload)
    except Exception:
        if not is_live or time.time() - started > FAST_FAIL_SECONDS:
            raise
        # El payload descargado está roto: cuarentena y volver al empaquetado.
        _drop_payload(payload)
        bad = root / "app.bad"
        shutil.rmtree(bad, ignore_errors=True)
        try:
            payload.rename(bad)
        except OSError:
            pass
        _run(_bundled_payload())


if __name__ == "__main__":
    main()

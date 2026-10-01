"""
Actualizador del payload (código liviano + JS) desde GitHub Releases.

Cada release del repo debe tener 2 assets:
  - manifest.json  {"version": "1.2.0", "sha256": "...", "payload": "payload.zip",
                    "launcher_api": 1, "notes": "..."}
  - payload.zip    contenido de payload/ (lo genera build_payload.py)

No usa la API de GitHub (sin rate limit): /releases/latest/download/<asset>
redirige siempre al release más reciente.

apply() NO toca el código en uso: extrae a app.pending y el launcher lo activa
en el siguiente arranque (por eso restart() es parte del flujo).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from appdirs import get_appdata_dir

REPO = "azu42968-maker/acidmodloader"
BASE = f"https://github.com/{REPO}/releases/latest/download"
ALLOWED_HOSTS = ("github.com", "githubusercontent.com")
UA = {"User-Agent": "AcidModLoader-updater"}

LAUNCHER_API = int(os.environ.get("ACID_LAUNCHER_API", "1"))
_last_manifest: dict | None = None


def _vt(s: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", str(s)))


def current_version() -> str:
    try:
        data = json.loads((Path(__file__).parent / "version.json").read_text(encoding="utf-8"))
        return str(data["version"])
    except Exception:
        return "0.0.0"


def _open(url: str, timeout: int = 20):
    resp = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout)
    host = urllib.parse.urlparse(resp.geturl()).hostname or ""
    if not host.endswith(ALLOWED_HOSTS):
        resp.close()
        raise ValueError(f"Redirección a host no permitido: {host}")
    return resp


def check() -> dict:
    """Consulta el manifest del último release."""
    global _last_manifest
    cur = current_version()
    try:
        with _open(f"{BASE}/manifest.json") as r:
            m = json.loads(r.read().decode("utf-8"))
        _last_manifest = m
        return {
            "current": cur,
            "latest": m["version"],
            "available": _vt(m["version"]) > _vt(cur),
            "notes": m.get("notes", ""),
            "needs_new_exe": int(m.get("launcher_api", 1)) > LAUNCHER_API,
        }
    except Exception as e:
        return {"current": cur, "error": f"No se pudo consultar actualizaciones: {e}"}


def _safe_extract(zpath: Path, dest: Path) -> None:
    base = dest.resolve()
    with zipfile.ZipFile(zpath) as zf:
        for info in zf.infolist():
            if not (dest / info.filename).resolve().is_relative_to(base):
                raise ValueError(f"Ruta sospechosa en el zip: {info.filename}")
        zf.extractall(dest)


def apply() -> dict:
    """Descarga, verifica y deja el payload listo para el próximo arranque."""
    info = check()
    if "error" in info:
        return {"ok": False, "error": info["error"]}
    if info["needs_new_exe"]:
        return {"ok": False, "error": "Esta versión necesita un .exe nuevo. Descárgalo desde la página del proyecto."}
    if not info["available"]:
        return {"ok": True, "uptodate": True, "version": info["current"]}

    m = _last_manifest or {}
    tmp = Path(tempfile.mkdtemp(prefix="acid_upd_"))
    pending = get_appdata_dir() / "app.pending"
    try:
        zpath = tmp / "payload.zip"
        sha = hashlib.sha256()
        with _open(f"{BASE}/{m.get('payload', 'payload.zip')}", timeout=60) as r, open(zpath, "wb") as f:
            while chunk := r.read(1 << 16):
                sha.update(chunk)
                f.write(chunk)
        if sha.hexdigest().lower() != str(m.get("sha256", "")).lower():
            return {"ok": False, "error": "El archivo descargado no coincide con el hash esperado."}

        shutil.rmtree(pending, ignore_errors=True)
        pending.mkdir(parents=True)
        _safe_extract(zpath, pending)
        if not (pending / "app_main.py").is_file() or not (pending / "version.json").is_file():
            shutil.rmtree(pending, ignore_errors=True)
            return {"ok": False, "error": "El paquete descargado está incompleto."}
        return {"ok": True, "version": m["version"]}
    except Exception as e:
        shutil.rmtree(pending, ignore_errors=True)
        return {"ok": False, "error": f"Falló la actualización: {e}"}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def restart() -> None:
    """Relanza la app (el launcher activa app.pending al arrancar) y cierra esta instancia."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("_PYI") and k != "_MEIPASS2"}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"  # necesario al relanzar un onefile
    if getattr(sys, "frozen", False):
        cmd = [sys.executable]
    else:
        cmd = [sys.executable, str(Path(sys.argv[0]).resolve())]
    subprocess.Popen(cmd, env=env, close_fds=True)
    os._exit(0)

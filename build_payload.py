"""
Uso:  python build_payload.py 1.1.0 "Notas del cambio"

Genera en release/:
  payload.zip    contenido de payload/ (sin __pycache__)
  manifest.json  versión + sha256 + notas

También escribe payload/version.json, así que el .exe que empaquetes después
con build_exe.py lleva la misma versión que este release.

Luego súbelos a un release de GitHub (ver comando gh en el README de la guía).
"""
from __future__ import annotations

import hashlib
import json
import py_compile
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PAYLOAD = ROOT / "payload"
OUT = ROOT / "release"
LAUNCHER_API = 1  # súbelo solo si este payload requiere un .exe nuevo


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit('Uso: python build_payload.py <version> ["notas"]')
    version = sys.argv[1].lstrip("v")
    notes = sys.argv[2] if len(sys.argv) > 2 else ""

    if not (PAYLOAD / "app_main.py").is_file():
        sys.exit("Falta payload/app_main.py (renombra main.py -> payload/app_main.py)")

    # No publicar un payload con errores de sintaxis (rompería a todos los usuarios).
    with tempfile.TemporaryDirectory() as td:
        for py in sorted(PAYLOAD.glob("*.py")):
            try:
                py_compile.compile(str(py), cfile=str(Path(td) / (py.name + "c")), doraise=True)
            except py_compile.PyCompileError as e:
                sys.exit(f"[X] Error de sintaxis en {py.name}:\n{e.msg}")

    (PAYLOAD / "version.json").write_text(json.dumps({"version": version}), encoding="utf-8")

    OUT.mkdir(exist_ok=True)
    zpath = OUT / "payload.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(PAYLOAD.rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts and f.suffix != ".pyc":
                zf.write(f, f.relative_to(PAYLOAD).as_posix())

    sha = hashlib.sha256(zpath.read_bytes()).hexdigest()
    manifest = {
        "version": version,
        "payload": "payload.zip",
        "sha256": sha,
        "launcher_api": LAUNCHER_API,
        "notes": notes,
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"OK  v{version}  {zpath.stat().st_size/1024:.0f} KB  sha256={sha[:12]}…")
    print(f'Siguiente: gh release create v{version} release/payload.zip release/manifest.json --title "v{version}" --notes "{notes}"')


if __name__ == "__main__":
    main()

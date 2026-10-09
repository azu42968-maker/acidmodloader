"""
Vigila tu carpeta de Descargas y convierte a .zip, automaticamente, todo archivo
comprimido (rar, 7z, tar, gz, bz2, xz, cab, iso...) que baje de GameBanana.

Uso:
  python auto_zip.py                    vigila Descargas, solo lo que viene de GameBanana
  python auto_zip.py "D:\\Mis descargas" vigila otra carpeta
  python auto_zip.py --todo             convierte cualquier archivo comprimido nuevo
  python auto_zip.py --borrar           borra el original despues de convertir
                                        (por defecto lo mueve a la subcarpeta _originales)
  python auto_zip.py --existentes       tambien convierte lo que ya estaba en la carpeta

Deja la ventana abierta mientras descargas. Ctrl+C para salir.
"""
from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

import archive_utils as au

PARTIAL_SUFFIXES = {".crdownload", ".part", ".tmp", ".download", ".partial", ".opdownload"}
POLL_SECONDS = 2.0


def _from_gamebanana(path: Path) -> bool | None:
    """True/False segun la marca de origen de Windows (Zone.Identifier);
    None si no hay forma de saberlo (otro sistema o archivo sin marca)."""
    try:
        text = Path(str(path) + ":Zone.Identifier").read_text(errors="ignore")
    except OSError:
        return None
    if not text.strip():
        return None
    return "gamebanana" in text.lower()


def _wanted(path: Path, only_gb: bool) -> bool:
    ext = path.suffix.lower()
    if ext in PARTIAL_SUFFIXES or ext == ".zip" or ext not in au.ARCHIVE_EXTS:
        return False
    if not only_gb:
        return True
    origin = _from_gamebanana(path)
    return True if origin is None else origin


def _convert(path: Path, delete_original: bool) -> None:
    data = path.read_bytes()
    zip_bytes = au.to_zip_bytes(data, path.name)
    out = path.with_suffix(".zip")
    n = 2
    while out.exists():
        out = path.with_name(f"{path.stem}_{n}.zip")
        n += 1
    out.write_bytes(zip_bytes)
    if delete_original:
        path.unlink()
    else:
        keep = path.parent / "_originales"
        keep.mkdir(exist_ok=True)
        target = keep / path.name
        k = 2
        while target.exists():
            target = keep / f"{path.stem}_{k}{path.suffix}"
            k += 1
        shutil.move(str(path), str(target))
    print(f"[OK] {path.name}  ->  {out.name}")


def _stable(path: Path, last_sizes: dict[Path, int]) -> bool:
    """El archivo ya termino de bajarse: mismo tamano en dos revisiones seguidas."""
    try:
        size = path.stat().st_size
    except OSError:
        return False
    previous = last_sizes.get(path)
    last_sizes[path] = size
    return size > 0 and previous == size


def main() -> None:
    args = sys.argv[1:]
    flags = {a for a in args if a.startswith("--")}
    folders = [a for a in args if not a.startswith("--")]
    folder = Path(folders[0]) if folders else Path.home() / "Downloads"
    only_gb = "--todo" not in flags
    delete_original = "--borrar" in flags

    if not folder.is_dir():
        print(f"No existe la carpeta: {folder}")
        input("Presiona Enter para cerrar...")
        return

    seen: set[Path] = set()
    if "--existentes" not in flags:
        seen = {p for p in folder.iterdir() if p.is_file()}

    print(f"Vigilando: {folder}")
    print("Solo archivos de GameBanana." if only_gb else "Cualquier archivo comprimido nuevo.")
    print("Ctrl+C para salir.\n")

    sizes: dict[Path, int] = {}
    try:
        while True:
            for p in sorted(folder.iterdir()):
                if p in seen or not p.is_file() or not _wanted(p, only_gb):
                    continue
                if not _stable(p, sizes):
                    continue
                seen.add(p)
                try:
                    _convert(p, delete_original)
                except au.ArchiveError as e:
                    print(f"[X] {p.name}: {e}")
                except OSError as e:
                    print(f"[X] {p.name}: {e}")
            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        print("\nListo, hasta luego.")


if __name__ == "__main__":
    main()

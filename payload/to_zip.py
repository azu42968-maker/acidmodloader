"""
Convierte archivos comprimidos (rar, 7z, tar, gz, bz2, xz, cab, iso...) a .zip.

Uso:
  - Arrastra uno o varios archivos encima de to_zip.py (o de to_zip.bat), o
  - python to_zip.py mod.rar otro.7z carpeta_con_archivos
  - Sin argumentos: abre una ventana para elegir los archivos.

El .zip se crea junto al original (mod.rar -> mod.zip). Usa archive_utils.py y la
carpeta 7zip/ que ya vienen con la app, asi que no hay que instalar nada.
"""
from __future__ import annotations

import sys
from pathlib import Path

import archive_utils as au


def convert(path: Path) -> bool:
    try:
        data = path.read_bytes()
        kind = au.detect_kind(data, path.name)
        if kind is None:
            print(f"[-] {path.name}: no es un archivo comprimido conocido, se omite.")
            return False
        if kind == "zip":
            print(f"[=] {path.name}: ya es un .zip, se omite.")
            return True
        zip_bytes = au.to_zip_bytes(data, path.name, log=lambda m: None)
        out = path.with_suffix(".zip")
        n = 2
        while out.exists():
            out = path.with_name(f"{path.stem}_{n}.zip")
            n += 1
        out.write_bytes(zip_bytes)
        print(f"[OK] {path.name}  ->  {out.name}")
        return True
    except au.ArchiveError as e:
        print(f"[X] {path.name}: {e}")
    except OSError as e:
        print(f"[X] {path.name}: {e}")
    return False


def collect(args: list[str]) -> list[Path]:
    files: list[Path] = []
    for a in args:
        p = Path(a)
        if p.is_dir():
            files += sorted(f for f in p.rglob("*") if f.is_file() and f.suffix.lower() in au.ARCHIVE_EXTS)
        elif p.is_file():
            files.append(p)
        else:
            print(f"[-] No existe: {a}")
    return files


def pick_files() -> list[str]:
    try:
        import tkinter
        from tkinter import filedialog
        root = tkinter.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        return list(filedialog.askopenfilenames(title="Elige los archivos a convertir a .zip"))
    except Exception:
        return [s.strip('" ') for s in input("Ruta del archivo (o carpeta): ").split('" "') if s.strip()]


def main() -> None:
    args = sys.argv[1:] or pick_files()
    files = collect(args)
    if not files:
        print("No hay nada que convertir.")
    ok = sum(convert(f) for f in files)
    if files:
        print(f"\nListo: {ok}/{len(files)} convertidos.")
    if len(sys.argv) <= 1 or sys.platform.startswith("win"):
        input("Presiona Enter para cerrar...")


if __name__ == "__main__":
    main()

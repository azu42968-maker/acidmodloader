"""
Soporte para cualquier archivo comprimido (zip, rar, 7z, tar, tar.gz, gz, bz2, xz, cab, iso...).

Todo se normaliza a un .zip en memoria con rutas seguras, y asi el instalador
(installer.install_zip_mod) no necesita saber de que formato venia el mod.

Motores de extraccion, en este orden:
  - zip / tar / gz / bz2 / xz : biblioteca estandar de Python (siempre disponible)
  - 7z                        : py7zr (si esta instalado), luego 7-Zip
  - rar / cab / iso / otros   : 7-Zip (7z.exe) y, para rar, tambien rarfile (si hay unrar)

7-Zip se busca en: 7zip/ (junto a este archivo, ya incluido en el payload), vendor/, PATH
y C:\\Program Files\\7-Zip. El usuario no necesita instalar nada.
"""
from __future__ import annotations

import gzip
import bz2
import io
import lzma
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

# La app lo asigna al arrancar (api.py) para encontrar 7z.exe dentro de vendor/.
VENDOR_DIR: Path | None = None

# Limite de seguridad contra "zip bombs": 3 GB descomprimidos / 50.000 archivos.
MAX_TOTAL_BYTES = 3 * 1024 ** 3
MAX_FILES = 50_000

ARCHIVE_EXTS = {
    ".zip", ".rar", ".7z",
    ".tar", ".tgz", ".gz", ".tbz", ".tbz2", ".bz2", ".txz", ".xz", ".lzma",
    ".cab", ".iso", ".zipx", ".cbz", ".cbr", ".cb7",
}

_EXT_TO_KIND = {
    ".zip": "zip", ".zipx": "zip", ".cbz": "zip",
    ".rar": "rar", ".cbr": "rar",
    ".7z": "7z", ".cb7": "7z",
    ".tar": "tar", ".tgz": "gz", ".gz": "gz",
    ".tbz": "bz2", ".tbz2": "bz2", ".bz2": "bz2",
    ".txz": "xz", ".xz": "xz", ".lzma": "xz",
    ".cab": "cab", ".iso": "iso",
}


class ArchiveError(Exception):
    pass


# ---------------------------------------------------------------- deteccion

def detect_kind(data: bytes, filename: str = "") -> str | None:
    """Devuelve el formato ('zip','rar','7z','tar','gz','bz2','xz','cab','iso') o None.
    Primero mira los bytes magicos (no se fia de la extension); si no reconoce
    nada, usa la extension como pista."""
    head = data[:8]
    if head[:4] in (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"):
        return "zip"
    if head[:7] == b"Rar!\x1a\x07\x00" or head[:8] == b"Rar!\x1a\x07\x01\x00":
        return "rar"
    if head[:6] == b"7z\xbc\xaf\x27\x1c":
        return "7z"
    if head[:2] == b"\x1f\x8b":
        return "gz"
    if head[:3] == b"BZh":
        return "bz2"
    if head[:6] == b"\xfd7zXZ\x00" or head[:4] == b"\x5d\x00\x00\x80":
        return "xz"
    if head[:4] == b"MSCF":
        return "cab"
    if data[257:262] == b"ustar":
        return "tar"
    if len(data) > 0x8006 and data[0x8001:0x8006] == b"CD001":
        return "iso"
    return _EXT_TO_KIND.get(Path(filename).suffix.lower())


def is_archive(data: bytes, filename: str = "") -> bool:
    return detect_kind(data, filename) is not None


# ---------------------------------------------------------------- 7-Zip

def _find_7z() -> str | None:
    if sys.platform.startswith("win"):
        names = ["7z.exe", "7zz.exe", "7za.exe"]
    else:
        names = ["7zz", "7z", "7za"]
    # 1) 7zip/ junto al codigo (viaja dentro del payload y se actualiza con el); 2) vendor/
    dirs: list[Path] = [Path(__file__).resolve().parent / "7zip"]
    if VENDOR_DIR:
        dirs += [VENDOR_DIR, VENDOR_DIR / "7zip", VENDOR_DIR / "7-Zip"]
    for d in dirs:
        for n in names:
            if (d / n).is_file():
                return str(d / n)
    for n in names:
        found = shutil.which(n)
        if found:
            return found
    for env in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
        base = os.environ.get(env)
        if base and (Path(base) / "7-Zip" / "7z.exe").is_file():
            return str(Path(base) / "7-Zip" / "7z.exe")
    return None


def _extract_with_7z(archive: Path, out: Path) -> None:
    exe = _find_7z()
    if not exe:
        raise ArchiveError("7-Zip not found")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform.startswith("win") else 0
    try:
        res = subprocess.run(
            [exe, "x", "-y", "-bd", "-bso0", "-bsp0", f"-o{out}", str(archive)],
            stdin=subprocess.DEVNULL, capture_output=True, text=True,
            timeout=600, creationflags=flags,
        )
    except (OSError, subprocess.SubprocessError) as e:
        raise ArchiveError(f"7-Zip failed to run: {e}") from e
    if res.returncode not in (0, 1):  # 1 = solo avisos
        msg = (res.stderr or res.stdout or "").strip().splitlines()
        raise ArchiveError("7-Zip: " + (msg[-1] if msg else f"exit code {res.returncode}"))


# ---------------------------------------------------------------- motores

def _safe_member(root: Path, name: str) -> Path:
    clean = name.replace("\\", "/").lstrip("/")
    dest = (root / clean).resolve()
    if not dest.is_relative_to(root.resolve()):
        raise ArchiveError(f"Unsafe path inside archive: {name}")
    return dest


def _extract_tar(data: bytes, out: Path) -> None:
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as tf:
            total = 0
            members = []
            for m in tf.getmembers():
                if not (m.isfile() or m.isdir()):
                    continue  # sin enlaces simbolicos, dispositivos, etc.
                _safe_member(out, m.name)
                total += max(m.size, 0)
                members.append(m)
            if total > MAX_TOTAL_BYTES or len(members) > MAX_FILES:
                raise ArchiveError("Archive is too large to extract safely.")
            for m in members:
                dest = _safe_member(out, m.name)
                if m.isdir():
                    dest.mkdir(parents=True, exist_ok=True)
                else:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    src = tf.extractfile(m)
                    if src is not None:
                        with src, open(dest, "wb") as f:
                            shutil.copyfileobj(src, f)
    except tarfile.TarError as e:
        raise ArchiveError(f"Corrupted tar archive: {e}") from e


def _extract_single_stream(data: bytes, kind: str, filename: str, out: Path) -> None:
    """.gz / .bz2 / .xz: o es un tar comprimido, o es un unico archivo comprimido."""
    try:
        if kind == "gz":
            raw = gzip.decompress(data)
        elif kind == "bz2":
            raw = bz2.decompress(data)
        else:
            raw = lzma.decompress(data)
    except (OSError, EOFError, lzma.LZMAError, ValueError) as e:
        raise ArchiveError(f"Corrupted {kind} file: {e}") from e
    if len(raw) > MAX_TOTAL_BYTES:
        raise ArchiveError("Archive is too large to extract safely.")
    if len(raw) > 262 and raw[257:262] == b"ustar":
        _extract_tar(raw, out)
        return
    stem = Path(filename).name
    inner = Path(stem).stem if Path(stem).suffix.lower() in ARCHIVE_EXTS else stem
    if stem.lower().endswith(".tgz") or stem.lower().endswith(".tbz2"):
        inner = Path(stem).stem
    (out / (inner or "file")).write_bytes(raw)


def _extract_7z_py(archive: Path, out: Path) -> bool:
    try:
        import py7zr  # type: ignore
    except ImportError:
        return False
    try:
        with py7zr.SevenZipFile(archive, "r") as z:
            for name in z.getnames():
                _safe_member(out, name)
            z.extractall(path=out)
        return True
    except ArchiveError:
        raise
    except Exception as e:
        # py7zr no soporta algunos metodos (p. ej. BCJ2 o cifrado); probamos con 7-Zip.
        if _find_7z():
            return False
        raise ArchiveError(f"Could not read the .7z file: {e}") from e


def _extract_rar_py(archive: Path, out: Path) -> bool:
    try:
        import rarfile  # type: ignore
    except ImportError:
        return False
    try:
        with rarfile.RarFile(str(archive)) as rf:
            for name in rf.namelist():
                _safe_member(out, name)
            rf.extractall(str(out))
        return True
    except ArchiveError:
        raise
    except Exception:
        return False


_NO_ENGINE_HELP = {
    "rar": "7-Zip is missing from the app folder (7zip/7z.exe and 7z.dll). Update the app, "
           "or install 7-Zip (https://www.7-zip.org) on this PC, then try again.",
    "7z": "To install .7z mods, install the 'py7zr' Python package, or put 7z.exe and 7z.dll "
          "(from 7-Zip) in the app's vendor folder, or install 7-Zip on this PC.",
}


def _extract_with_tools(data: bytes, kind: str, filename: str, out: Path) -> None:
    suffix = Path(filename).suffix or f".{kind}"
    with tempfile.TemporaryDirectory(prefix="acid_arc_") as td:
        archive = Path(td) / f"archive{suffix}"
        archive.write_bytes(data)

        if kind == "7z" and _extract_7z_py(archive, out):
            return
        if kind == "rar":
            if _find_7z():
                try:
                    _extract_with_7z(archive, out)
                    return
                except ArchiveError as e:
                    if not _extract_rar_py(archive, out):
                        raise e
                    return
            if _extract_rar_py(archive, out):
                return
            raise ArchiveError(_NO_ENGINE_HELP["rar"])
        try:
            _extract_with_7z(archive, out)
        except ArchiveError as e:
            if str(e) == "7-Zip not found":
                raise ArchiveError(
                    _NO_ENGINE_HELP.get(kind) or
                    f"Can't open .{kind} files without 7-Zip. Put 7z.exe and 7z.dll in the app's "
                    "vendor folder, or install 7-Zip, then try again."
                ) from e
            raise


# ---------------------------------------------------------------- conversion

def _dir_to_zip_bytes(root: Path) -> bytes:
    buf = io.BytesIO()
    total = 0
    count = 0
    root_resolved = root.resolve()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        for p in sorted(root.rglob("*")):
            if p.is_symlink() or not p.is_file():
                continue
            if not p.resolve().is_relative_to(root_resolved):
                continue
            count += 1
            total += p.stat().st_size
            if count > MAX_FILES or total > MAX_TOTAL_BYTES:
                raise ArchiveError("Archive is too large to extract safely.")
            zf.write(p, p.relative_to(root).as_posix())
    if count == 0:
        raise ArchiveError("The archive is empty (or couldn't be read).")
    return buf.getvalue()


def to_zip_bytes(data: bytes, filename: str = "", log=None) -> bytes:
    """Convierte cualquier archivo comprimido soportado a bytes de .zip.
    Si ya es zip, lo devuelve tal cual. Lanza ArchiveError si no se puede."""
    kind = detect_kind(data, filename)
    if kind is None:
        raise ArchiveError(f"Unsupported archive type: {Path(filename).suffix or '(unknown)'}")
    if kind == "zip":
        return data

    if log:
        log(f"[i] Extracting .{kind} archive: {Path(filename).name or '(unnamed)'}")

    with tempfile.TemporaryDirectory(prefix="acid_ext_") as td:
        out = Path(td) / "out"
        out.mkdir()
        if kind == "tar":
            _extract_tar(data, out)
        elif kind in ("gz", "bz2", "xz"):
            _extract_single_stream(data, kind, filename, out)
        else:
            _extract_with_tools(data, kind, filename, out)
        return _dir_to_zip_bytes(out)

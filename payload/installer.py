import io
import re
import tempfile
import zipfile
from pathlib import Path

import archive_utils
import mod_registry
from bmod_reader import parse_bmod, BmodError
from swf_sprite_merge import merge_bmod_swfs, MergeError

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
AUDIO_BANK_EXTS = {".bnk", ".wem"}
MAPART_SUBFOLDER = "mapart"
JUNK_NAMES = {".ds_store", "thumbs.db", "desktop.ini"}
# Carpetas de primer nivel que son rutas reales del juego (no agrupaciones de mapas).
# Ademas se acepta cualquier carpeta que ya exista en la carpeta del juego.
DIRECT_ROOTS = {"sprites"}


class InstallError(Exception):
    pass


# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------

def _ci_path(base: Path, rel) -> Path:
    """Resuelve `rel` dentro de `base` ignorando mayusculas/minusculas.
    Windows no distingue Gfx.swf de gfx.swf, Linux/macOS si: sin esto, un mod hecho en Windows
    no encuentra el archivo del juego o crea un duplicado con otra capitalizacion.
    Tambien descarta '..' y rutas absolutas para que nada salga de `base`."""
    rel = Path(rel)
    parts = rel.parts[1:] if rel.anchor else rel.parts
    parts = [p for p in parts if p not in ("", ".", "..")]
    cur = base
    for i, part in enumerate(parts):
        nxt = cur / part
        if not nxt.exists():
            try:
                found = next((c for c in cur.iterdir() if c.name.lower() == part.lower()), None)
            except OSError:
                found = None
            if found is None:
                return cur.joinpath(*parts[i:])
            nxt = found
        cur = nxt
    return cur


def find_ci(parent, name):
    """Busca una subcarpeta ignorando mayusculas (Linux distingue mapArt de mapart)."""
    try:
        for child in parent.iterdir():
            if child.name.lower() == name.lower():
                return child
    except OSError:
        pass
    return parent / name


def _entry_name(zip_path: str) -> str:
    return Path(zip_path.replace("\\", "/")).name


def _is_junk(raw_path: str) -> bool:
    """Basura que meten macOS/Windows en los zips (__MACOSX/._foo.png, .DS_Store, Thumbs.db...).
    Sin filtrarla, esos archivos parecen imagenes y ensucian el resultado como "missing"."""
    parts = [p for p in raw_path.replace("\\", "/").split("/") if p]
    if not parts or "__MACOSX" in parts:
        return True
    last = parts[-1]
    return last.startswith("._") or last.lower() in JUNK_NAMES


def _zip_rel_parts(raw_path: str):
    """Partes de la ruta de una entrada del zip, o None si intenta escapar de la carpeta
    (ruta absoluta, letra de unidad o '..'). Evita sobrescribir archivos fuera del juego."""
    norm = raw_path.replace("\\", "/")
    if norm.startswith("/") or re.match(r"^[A-Za-z]:", norm):
        return None
    parts = [p for p in norm.split("/") if p not in ("", ".")]
    if ".." in parts:
        return None
    return parts


def _is_packaged_root(brawlhalla_folder: Path, first: str) -> bool:
    """True si la primera carpeta del zip es una ruta real del juego (sprites/, bones/...)
    y no un simple agrupador de mapas (p. ej. "Tekken/"). mapart/ se sigue resolviendo por nombre."""
    low = first.lower()
    if low == MAPART_SUBFOLDER:
        return False
    return low in DIRECT_ROOTS or find_ci(brawlhalla_folder, first).is_dir()


def build_filename_index(root_folder: Path) -> dict:
    index: dict[str, list[Path]] = {}
    for p in root_folder.rglob("*"):
        if p.is_file():
            index.setdefault(p.name.lower(), []).append(p)
    return index


def _safe_write(dest: Path, data: bytes, log, write_errors: list | None) -> bool:
    """Escribe y, si falla (juego abierto, sin permisos, disco lleno), lo registra y sigue
    con el resto en vez de abortar la instalacion a medias."""
    try:
        mod_registry.write_bytes(dest, data)
        return True
    except OSError as e:
        msg = f"{dest}: {e}"
        if write_errors is not None:
            write_errors.append(msg)
        log(f"   [X] Could not write {msg}")
        return False


# ---------------------------------------------------------------------------
# Imagenes
# ---------------------------------------------------------------------------

def _image_entries(infos):
    out = []
    for info in infos:
        if info.is_dir() or _is_junk(info.filename):
            continue
        name = _entry_name(info.filename)
        if name and Path(name).suffix.lower() in IMAGE_EXTS:
            out.append((name, info))
    return out


def get_target_folder_by_intersection(infos, name_index: dict, bg_entry_name: str | None):
    folder_sets = []
    for name, _info in _image_entries(infos):
        if bg_entry_name and name == bg_entry_name:
            continue
        matches = name_index.get(name.lower())
        if not matches:
            continue
        folder_sets.append({p.parent for p in matches})

    if not folder_sets:
        return None

    common = folder_sets[0]
    for s in folder_sets[1:]:
        common = common & s
        if not common:
            break
    if len(common) == 1:
        return next(iter(common))

    # Intersection failed (e.g. one file of the mod doesn't exist in this game
    # version): pick the folder that holds the most of the mod's files.
    votes: dict[Path, int] = {}
    for s in folder_sets:
        for folder in s:
            votes[folder] = votes.get(folder, 0) + 1
    best = max(votes.values())
    winners = [f for f, n in votes.items() if n == best]
    if len(winners) == 1 and len(folder_sets) > 1 and best >= 2:
        return winners[0]
    return None


def _find_bg_entry_name(infos) -> str | None:
    names = [n for n, _ in _image_entries(infos)]
    # If every image is a background, there is no "odd one out" to exclude.
    if names and all(n.lower().startswith("bg") for n in names):
        return None
    for name in names:
        if name.lower().startswith("bg"):
            return name
    return None


def _process_image_group(
    zf: zipfile.ZipFile,
    infos,
    name_index: dict,
    source_name: str,
    replaced_images: list,
    missing_images: list,
    skipped_multi: list,
    log=lambda _m: None,
    write_errors: list | None = None,
) -> None:
    entries = _image_entries(infos)
    bg_entry_name = _find_bg_entry_name(infos)
    target_folder = get_target_folder_by_intersection(infos, name_index, bg_entry_name)

    if not target_folder and bg_entry_name:
        bg_matches = name_index.get(bg_entry_name.lower(), [])
        if len(bg_matches) == 1:
            candidate = bg_matches[0].parent
            others_here = any(
                p.parent == candidate
                for name, _info in entries
                if name != bg_entry_name
                for p in name_index.get(name.lower(), [])
            )
            if others_here:
                target_folder = candidate

    for img_name, img_info in entries:
        matches = name_index.get(img_name.lower())
        if not matches:
            missing_images.append((source_name, img_name))
            continue

        if target_folder:
            filtered = [p for p in matches if p.parent == target_folder]
            if filtered:
                matches = filtered
            elif len(matches) > 1:
                skipped_multi.append((img_name, matches))
                continue
        elif len(matches) > 1:
            skipped_multi.append((img_name, matches))
            continue

        img_bytes = zf.read(img_info)
        for dest_path in matches:
            if _safe_write(dest_path, img_bytes, log, write_errors):
                replaced_images.append((img_name, dest_path))


# ---------------------------------------------------------------------------
# Zip
# ---------------------------------------------------------------------------

def install_zip_mod(
    zip_bytes: bytes,
    brawlhalla_folder: Path,
    log,
    ffdec_jar_path: str | None = None,
    java_home: str | None = None,
) -> dict:
    mapart_folder = find_ci(brawlhalla_folder, MAPART_SUBFOLDER)
    if not mapart_folder.is_dir():
        raise InstallError(
            f"Could not find the '{MAPART_SUBFOLDER}' folder inside: {brawlhalla_folder}"
        )

    log(f"[i] Indexing existing files in: {mapart_folder}")
    name_index = build_filename_index(mapart_folder)
    log(f"[i] {sum(len(v) for v in name_index.values())} files indexed.")
    log("")

    copied_swf: list[str] = []
    replaced_swf: list[tuple[str, Path]] = []
    missing_swf_targets: list[str] = []
    copied_direct: list[tuple[str, Path]] = []
    replaced_images: list[tuple[str, Path]] = []
    missing_images: list[tuple[str, str]] = []
    skipped_multi: list[tuple[str, list[Path]]] = []
    bmod_results: list[tuple[str, dict]] = []
    bmod_errors: list[tuple[str, str]] = []
    write_errors: list[str] = []
    unsafe_entries: list[str] = []

    try:
        mods_zip_cm = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile as e:
        raise InstallError(f"The file is not a valid zip: {e}")

    with mods_zip_cm as mods_zip:
        top_level_image_infos = []
        folder_image_infos: dict[str, list] = {}

        for info in mods_zip.infolist():
            if info.is_dir() or _is_junk(info.filename):
                continue
            raw_path = info.filename.replace("\\", "/")
            rel_parts = _zip_rel_parts(raw_path)
            if rel_parts is None:
                unsafe_entries.append(info.filename)
                log(f"   [!] Skipped unsafe path inside the zip: {info.filename}")
                continue
            name = rel_parts[-1] if rel_parts else ""
            if not name:
                continue
            ext = Path(name).suffix.lower()

            if ext == ".swf":
                if len(rel_parts) > 1:
                    rel_path = Path(*rel_parts)
                    dest = _ci_path(brawlhalla_folder, rel_path)
                    if dest.is_file():
                        if _safe_write(dest, mods_zip.read(info), log, write_errors):
                            replaced_swf.append((str(rel_path), dest))
                    else:
                        missing_swf_targets.append(str(rel_path))
                    continue

                if name.lower().startswith("bones"):
                    dest = _ci_path(brawlhalla_folder, Path("bones") / name)
                    label = f"{name}  (-> bones/)"
                else:
                    dest = _ci_path(brawlhalla_folder, name)
                    label = name
                if _safe_write(dest, mods_zip.read(info), log, write_errors):
                    copied_swf.append(label)
                continue

            if ext == ".bmod":
                bmod_bytes = mods_zip.read(info)
                with tempfile.NamedTemporaryFile(suffix=".bmod", delete=False) as tmp:
                    tmp.write(bmod_bytes)
                    tmp_bmod_path = Path(tmp.name)
                log(f"[i] Found .bmod inside the zip: {name}")
                try:
                    result = install_bmod(
                        bmod_bytes, tmp_bmod_path, brawlhalla_folder, log,
                        ffdec_jar_path=ffdec_jar_path,
                        java_home=java_home,
                    )
                    bmod_results.append((name, result))
                except InstallError as e:
                    bmod_errors.append((name, str(e)))
                    log(f"   [X] {name}: {e}")
                finally:
                    tmp_bmod_path.unlink(missing_ok=True)
                log("")
                continue

            if ext in archive_utils.ARCHIVE_EXTS:
                nested_bytes = mods_zip.read(info)
                try:
                    nested_bytes = archive_utils.to_zip_bytes(nested_bytes, name, log)
                    nested_zip_file = zipfile.ZipFile(io.BytesIO(nested_bytes))
                except (archive_utils.ArchiveError, zipfile.BadZipFile) as e:
                    log(f"   [X] Couldn't open the archive {name}: {e}")
                    continue
                with nested_zip_file as nested_zip:
                    _process_image_group(
                        nested_zip, nested_zip.infolist(), name_index, name,
                        replaced_images, missing_images, skipped_multi, log, write_errors,
                    )
                continue

            if ext in IMAGE_EXTS:
                if len(rel_parts) > 1:
                    dest = _ci_path(brawlhalla_folder, Path(*rel_parts))
                    existed = dest.is_file()
                    if existed or _is_packaged_root(brawlhalla_folder, rel_parts[0]):
                        # The zip already uses the real packaged path (the file may be new,
                        # e.g. sprites/handmade/live/<skin>/...): write it, creating folders.
                        try:
                            dest.parent.mkdir(parents=True, exist_ok=True)
                        except OSError as e:
                            write_errors.append(f"{dest.parent}: {e}")
                            log(f"   [X] Could not create folder {dest.parent}: {e}")
                            continue
                        if _safe_write(dest, mods_zip.read(info), log, write_errors):
                            label = str(Path(*rel_parts)) + ("" if existed else "  (new file)")
                            copied_direct.append((label, dest))
                    else:
                        # Folder inside the zip is only a grouping (e.g. "Tekken/"):
                        # resolve the real files inside mapart/ by name.
                        folder_image_infos.setdefault(rel_parts[0], []).append(info)
                    continue

                top_level_image_infos.append(info)
                continue

        for folder_name, folder_infos in folder_image_infos.items():
            _process_image_group(
                mods_zip, folder_infos, name_index, folder_name,
                replaced_images, missing_images, skipped_multi, log, write_errors,
            )

        if top_level_image_infos:
            _process_image_group(
                mods_zip, top_level_image_infos, name_index, "(root)",
                replaced_images, missing_images, skipped_multi, log, write_errors,
            )

    problems = (
        len(missing_swf_targets) + len(missing_images) + len(skipped_multi)
        + len(bmod_errors) + len(write_errors) + len(unsafe_entries)
    )

    log("=" * 60)
    log(f"SWF files copied directly to the game folder ({len(copied_swf)}):")
    for f in copied_swf:
        log(f"   OK {f}")
    log("")
    log(f"Game SWF files replaced in place ({len(replaced_swf)}):")
    for rel, p in replaced_swf:
        log(f"   OK {rel}  ->  {p}")
    if missing_swf_targets:
        log("")
        log(f"[X] SWF replacement targets not found ({len(missing_swf_targets)}) - nothing written for these, check the path matches your install:")
        for rel in missing_swf_targets:
            log(f"   MISSING {rel}")
    log("")
    log(f"Files copied directly to their packaged path ({len(copied_direct)}):")
    for rel, p in copied_direct:
        log(f"   OK {rel}  ->  {p}")
    log("")
    log(f"Images replaced ({len(replaced_images)}):")
    for n, p in replaced_images:
        log(f"   OK {n}  ->  {p}")
    if skipped_multi:
        log("")
        log("[!] SKIPPED - ambiguous names with more than one match, nothing overwritten:")
        for n, paths in skipped_multi:
            log(f"   - {n}:")
            for p in paths:
                log(f"       {p}")
    if missing_images:
        log("")
        log(f"[X] Images with no match in the Brawlhalla folder ({len(missing_images)}):")
        for zip_name, img in missing_images:
            log(f"   MISSING {img}  (inside {zip_name})")
    if bmod_results or bmod_errors:
        log("")
        log(f".bmod files installed from inside this zip ({len(bmod_results)}):")
        for n, _result in bmod_results:
            log(f"   OK {n}")
        if bmod_errors:
            log("")
            log(f"[X] .bmod files that failed to install ({len(bmod_errors)}):")
            for n, err in bmod_errors:
                log(f"   {n}: {err}")
    if write_errors:
        log("")
        log(f"[X] Files that could not be written ({len(write_errors)}) - is the game running or the folder read-only?")
        for e in write_errors:
            log(f"   {e}")
    if unsafe_entries:
        log("")
        log(f"[!] Entries skipped for unsafe paths ({len(unsafe_entries)}):")
        for e in unsafe_entries:
            log(f"   {e}")
    log("=" * 60)
    log("Done." if not problems else f"Done, with {problems} problem(s) - see the messages above.")

    return {
        "copied_swf": copied_swf,
        "replaced_swf": [(rel, str(p)) for rel, p in replaced_swf],
        "missing_swf_targets": missing_swf_targets,
        "copied_direct": [(rel, str(p)) for rel, p in copied_direct],
        "replaced_images": [(n, str(p)) for n, p in replaced_images],
        "skipped_multi": [(n, [str(p) for p in paths]) for n, paths in skipped_multi],
        "missing_images": missing_images,
        "bmod_results": bmod_results,
        "bmod_errors": bmod_errors,
        "write_errors": write_errors,
        "unsafe_entries": unsafe_entries,
        "problems": problems,
    }


def install_loose_swf(swf_bytes: bytes, filename: str, brawlhalla_folder: Path, log) -> dict:
    filename = _entry_name(filename)
    if not filename:
        raise InstallError("Invalid SWF file name.")
    if filename.lower().startswith("bones"):
        dest = _ci_path(brawlhalla_folder, Path("bones") / filename)
    else:
        dest = _ci_path(brawlhalla_folder, filename)

    try:
        mod_registry.write_bytes(dest, swf_bytes)
    except OSError as e:
        raise InstallError(f"Could not write {dest}: {e}")
    log(f"OK {filename}  ->  {dest}")
    log("Done.")
    return {"copied_swf": [filename], "dest": str(dest)}


# ---------------------------------------------------------------------------
# .bmod
# ---------------------------------------------------------------------------

def install_bmod(bmod_bytes: bytes, bmod_path: Path, brawlhalla_folder: Path, log,
                  ffdec_jar_path: str | None = None, java_home: str | None = None) -> dict:
    try:
        bmod = parse_bmod(bmod_bytes)
    except BmodError as e:
        raise InstallError(str(e))

    meta = bmod.metadata
    files_map = {int(k): v for k, v in (meta.get("files") or {}).items()}
    swfs_map = meta.get("swfs") or {}

    log(f"[i] Mod: {meta.get('name', '(unnamed)')}  "
        f"(author: {meta.get('author', '?')}, game version: {meta.get('gameVersion', '?')})")
    log("")

    swf_merge_result = None
    if swfs_map:
        if ffdec_jar_path:
            log("[i] This mod also merges sprites/sounds/scripts into game SWFs:")
            for swf_name in swfs_map:
                log(f"      - {swf_name}")
            log("")
            try:
                swf_merge_result = merge_bmod_swfs(
                    meta, str(bmod_path), brawlhalla_folder, ffdec_jar_path, log,
                    java_home=java_home,
                )
            except MergeError as e:
                log(f"[X] SWF merge failed: {e}")
            log("")
        else:
            log("[!] This mod also merges sprites/sounds/scripts directly into:")
            for swf_name in swfs_map:
                log(f"      - {swf_name}")
            log("    No FFDec jar configured, so that part was skipped - only the")
            log("    plain files below (if any) were installed.")
            log("")

    needs_full_loader = bool(swfs_map) and swf_merge_result is None

    if not files_map:
        log("This mod has no plain embedded files to install.")
        log("Done.")
        return {
            "installed": [], "skipped": [], "missing": [], "failed": [],
            "needs_full_loader": needs_full_loader,
            "swf_merge": swf_merge_result,
        }

    # Indexar toda la carpeta del juego es lento: solo se hace si algun archivo
    # no se encuentra directamente por su ruta.
    index_cache: dict[str, dict] = {}

    def get_index() -> dict:
        if "idx" not in index_cache:
            index_cache["idx"] = build_filename_index(brawlhalla_folder)
        return index_cache["idx"]

    installed: list[str] = []
    skipped: list[str] = []
    missing: list[str] = []
    failed: list[str] = []

    def write(dest: Path, data: bytes, shown: str) -> None:
        errs: list[str] = []
        if _safe_write(dest, data, log, errs):
            installed.append(str(dest))
            log(f"   OK {shown}")
        else:
            failed.extend(errs)

    for char_id, dest_name in files_map.items():
        data = bmod.files_by_id.get(char_id)
        if data is None:
            missing.append(dest_name)
            log(f"   [X] {dest_name}: not embedded in the .bmod (no matching tag)")
            continue

        dest_name = dest_name.replace("\\", "/")
        base_name = Path(dest_name).name
        base_ext = Path(base_name).suffix.lower()

        if base_ext in AUDIO_BANK_EXTS:
            skipped.append(dest_name)
            log(f"   [!] {dest_name}: audio-bank file, needs BNK patching — skipped")
            continue

        if ("language." in base_name.lower() and base_ext == ".bin") or base_name.lower().endswith("_language.txt"):
            skipped.append(dest_name)
            log(f"   [!] {dest_name}: language file, needs text patching — skipped")
            continue

        direct = _ci_path(brawlhalla_folder, dest_name)
        if direct.is_file():
            write(direct, data, dest_name)
            continue

        candidates = get_index().get(base_name.lower())
        if not candidates:
            missing.append(dest_name)
            log(f"   [X] {dest_name}: no matching file found in your Brawlhalla folder")
        elif len(candidates) == 1:
            write(candidates[0], data, f"{base_name}  ->  {candidates[0]}")
        else:
            skipped.append(dest_name)
            log(f"   [!] {base_name}: matches {len(candidates)} files in your folder, ambiguous — skipped")

    log("")
    log(f"Installed: {len(installed)}   Skipped: {len(skipped)}   Missing: {len(missing)}   Failed: {len(failed)}")
    log("Done.")

    return {
        "installed": installed,
        "skipped": skipped,
        "missing": missing,
        "failed": failed,
        "needs_full_loader": needs_full_loader,
        "swf_merge": swf_merge_result,
    }

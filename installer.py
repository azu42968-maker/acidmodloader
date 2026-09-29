import tempfile
import zipfile
import io
from pathlib import Path

import mod_registry
from bmod_reader import parse_bmod, BmodError
from swf_sprite_merge import merge_bmod_swfs, MergeError

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
AUDIO_BANK_EXTS = {".bnk", ".wem"}
MAPART_SUBFOLDER = "mapart"


class InstallError(Exception):
    pass


def _entry_name(zip_path: str) -> str:
    return Path(zip_path.replace("\\", "/")).name


def build_filename_index(root_folder: Path) -> dict:
    index: dict[str, list[Path]] = {}
    for p in root_folder.rglob("*"):
        if p.is_file():
            index.setdefault(p.name.lower(), []).append(p)
    return index


def _image_entries(infos):
    out = []
    for info in infos:
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
    return None


def _find_bg_entry_name(infos) -> str | None:
    for name, _info in _image_entries(infos):
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
) -> None:
    bg_entry_name = _find_bg_entry_name(infos)
    target_folder = get_target_folder_by_intersection(infos, name_index, bg_entry_name)

    if not target_folder and bg_entry_name:
        bg_matches = name_index.get(bg_entry_name.lower(), [])
        if len(bg_matches) == 1:
            candidate = bg_matches[0].parent
            others_here = False
            for name, _info in _image_entries(infos):
                if not name or name == bg_entry_name:
                    continue
                for p in name_index.get(name.lower(), []):
                    if p.parent == candidate:
                        others_here = True
                        break
                if others_here:
                    break
            if others_here:
                target_folder = candidate

    for img_name, img_info in _image_entries(infos):
        key = img_name.lower()
        matches = name_index.get(key)
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
            mod_registry.write_bytes(dest_path, img_bytes)
            replaced_images.append((img_name, dest_path))


def install_zip_mod(
    zip_bytes: bytes,
    brawlhalla_folder: Path,
    log,
    ffdec_jar_path: str | None = None,
    java_home: str | None = None,
) -> dict:
    mapart_folder = brawlhalla_folder / MAPART_SUBFOLDER
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

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as mods_zip:
        top_level_image_infos = []

        for info in mods_zip.infolist():
            raw_path = info.filename.replace("\\", "/")
            name = _entry_name(info.filename)
            if not name:
                continue
            ext = Path(name).suffix.lower()

            if ext == ".swf":
                rel_parts = [p for p in Path(raw_path).parts if p not in ("", ".")]
                if len(rel_parts) > 1:
                    rel_path = Path(*rel_parts)
                    dest = brawlhalla_folder / rel_path
                    if dest.is_file():
                        with mods_zip.open(info) as src:
                            mod_registry.write_bytes(dest, src.read())
                        replaced_swf.append((str(rel_path), dest))
                    else:
                        missing_swf_targets.append(str(rel_path))
                    continue

                if name.lower().startswith("bones"):
                    dest = brawlhalla_folder / "bones" / name
                    copied_swf.append(f"{name}  (-> bones/)")
                else:
                    dest = brawlhalla_folder / name
                    copied_swf.append(name)
                with mods_zip.open(info) as src:
                    mod_registry.write_bytes(dest, src.read())
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

            if ext == ".zip":
                nested_bytes = mods_zip.read(info)
                with zipfile.ZipFile(io.BytesIO(nested_bytes)) as nested_zip:
                    _process_image_group(
                        nested_zip,
                        nested_zip.infolist(),
                        name_index,
                        name,
                        replaced_images,
                        missing_images,
                        skipped_multi,
                    )
                continue

            if ext in IMAGE_EXTS:
                rel_parts = [p for p in Path(raw_path).parts if p not in ("", ".")]
                if len(rel_parts) > 1:
                    rel_path = Path(*rel_parts)
                    dest = brawlhalla_folder / rel_path
                    with mods_zip.open(info) as src:
                        mod_registry.write_bytes(dest, src.read())
                    copied_direct.append((str(rel_path), dest))
                    continue

                top_level_image_infos.append(info)
                continue

        if top_level_image_infos:
            _process_image_group(
                mods_zip,
                top_level_image_infos,
                name_index,
                "(root)",
                replaced_images,
                missing_images,
                skipped_multi,
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
        log(f".bmod files installed from inside this zip ({len(bmod_results)}):")
        for n, _result in bmod_results:
            log(f"   OK {n}")
        if bmod_errors:
            log("")
            log(f"[X] .bmod files that failed to install ({len(bmod_errors)}):")
            for n, err in bmod_errors:
                log(f"   {n}: {err}")
        log("")
    log("=" * 60)
    log("Done.")

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
    }


def install_loose_swf(swf_bytes: bytes, filename: str, brawlhalla_folder: Path, log) -> dict:
    if filename.lower().startswith("bones"):
        dest = brawlhalla_folder / "bones" / filename
    else:
        dest = brawlhalla_folder / filename

    mod_registry.write_bytes(dest, swf_bytes)
    log(f"OK {filename}  ->  {dest}")
    log("Done.")
    return {"copied_swf": [filename], "dest": str(dest)}


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

    if not files_map:
        log("This mod has no plain embedded files to install.")
        log("Done.")
        return {
            "installed": [], "skipped": [], "missing": [],
            "needs_full_loader": bool(swfs_map) and swf_merge_result is None,
            "swf_merge": swf_merge_result,
        }

    name_index: dict[str, list[Path]] = {}
    for p in brawlhalla_folder.rglob("*"):
        if p.is_file():
            name_index.setdefault(p.name.lower(), []).append(p)

    installed: list[str] = []
    skipped: list[str] = []
    missing: list[str] = []

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

        direct = brawlhalla_folder / dest_name
        if direct.is_file():
            mod_registry.write_bytes(direct, data)
            installed.append(str(direct))
            log(f"   OK {dest_name}")
            continue

        candidates = name_index.get(base_name.lower())
        if not candidates:
            missing.append(dest_name)
            log(f"   [X] {dest_name}: no matching file found in your Brawlhalla folder")
        elif len(candidates) == 1:
            mod_registry.write_bytes(candidates[0], data)
            installed.append(str(candidates[0]))
            log(f"   OK {base_name}  ->  {candidates[0]}")
        else:
            skipped.append(dest_name)
            log(f"   [!] {base_name}: matches {len(candidates)} files in your folder, ambiguous — skipped")

    log("")
    log(f"Installed: {len(installed)}   Skipped: {len(skipped)}   Missing: {len(missing)}")
    log("Done.")

    return {
        "installed": installed,
        "skipped": skipped,
        "missing": missing,
        "needs_full_loader": bool(swfs_map) and swf_merge_result is None,
        "swf_merge": swf_merge_result,
    }

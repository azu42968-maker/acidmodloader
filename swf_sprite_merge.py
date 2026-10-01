from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

import jpype

import mod_registry

_ffdec_ready = False

MIN_JAVA_MAJOR = 9


def _find_jvm_path(java_home: str | None = None) -> str:
    if java_home:
        home = Path(java_home)
        if sys.platform.startswith("win"):
            candidates = [
                home / "bin" / "server" / "jvm.dll",
                home / "bin" / "client" / "jvm.dll",
                home / "jre" / "bin" / "server" / "jvm.dll",
            ]
        elif sys.platform == "darwin":
            candidates = [home / "lib" / "server" / "libjvm.dylib"]
        else:
            candidates = [home / "lib" / "server" / "libjvm.so"]
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
        raise MergeError(
            f"Couldn't find a jvm library under the configured java_home: {java_home}"
        )

    if sys.platform.startswith("win"):
        return jpype._jvmfinder.getDefaultJVMPath()
    if sys.platform == "darwin":
        candidate = "/Library/Internet Plug-Ins/JavaAppletPlugin.plugin/Contents/Home/lib/jli/libjli.dylib"
        if os.path.exists(candidate):
            return candidate
        return jpype._jvmfinder.getDefaultJVMPath()
    return jpype._jvmfinder.getDefaultJVMPath()


def _java_executable_near(jvm_path: str) -> str | None:
    exe_name = "java.exe" if sys.platform.startswith("win") else "java"
    for parent in Path(jvm_path).parents:
        candidate = parent / "bin" / exe_name
        if candidate.is_file():
            return str(candidate)
    return None


def _detect_java_major_version(java_exe: str) -> int | None:
    try:
        result = subprocess.run(
            [java_exe, "-version"], capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    output = (result.stderr or "") + (result.stdout or "")
    match = re.search(r'version "(\d+)(?:\.(\d+))?', output)
    if not match:
        return None
    major = int(match.group(1))
    if major == 1:
        major = int(match.group(2) or 0)
    return major


def _ffdec_classpath(ffdec_jar_path: str) -> list[str]:
    jar_path = Path(ffdec_jar_path)
    classpath = {str(jar_path)}
    for jar in jar_path.parent.rglob("*.jar"):
        classpath.add(str(jar))
    return sorted(classpath)


def ensure_ffdec(ffdec_jar_path: str, java_home: str | None = None) -> None:
    global _ffdec_ready
    if _ffdec_ready:
        return

    if not os.path.exists(ffdec_jar_path):
        raise FileNotFoundError(f"ffdec_lib.jar not found at: {ffdec_jar_path}")

    if not jpype.isJVMStarted():
        jvm_path = _find_jvm_path(java_home)

        java_exe = _java_executable_near(jvm_path)
        major = _detect_java_major_version(java_exe) if java_exe else None
        if major is not None and major < MIN_JAVA_MAJOR:
            raise MergeError(
                f"Found Java {major} at {jvm_path}, but FFDec needs Java "
                f"{MIN_JAVA_MAJOR} or later.\n"
                "    Install a current JDK (e.g. https://adoptium.net/temurin/releases/), "
                "then either set \"java_home\" in config.json to that JDK's install "
                "folder, or make it your system default (JAVA_HOME/PATH)."
            )

        jpype.startJVM(jvm_path, "-Xmx512m", "-Xms32m", classpath=_ffdec_classpath(ffdec_jar_path))

    global JClass
    from jpype import JClass

    _load_classes()
    _ffdec_ready = True


SWF = SymbolClassTag = DefineSpriteTag = DefineSoundTag = ImageTagClass = None
DefineShapeTags = ()
PlaceObjectTags = ()
HashSet = FileInputStream = FileOutputStream = BufferedInputStream = None


def _load_classes() -> None:
    from jpype import JClass

    global SWF, SymbolClassTag, DefineSpriteTag, DefineSoundTag, ImageTagClass
    global DefineShapeTags, PlaceObjectTags
    global HashSet, FileInputStream, FileOutputStream, BufferedInputStream

    HashSet = JClass("java.util.HashSet")
    FileInputStream = JClass("java.io.FileInputStream")
    FileOutputStream = JClass("java.io.FileOutputStream")
    BufferedInputStream = JClass("java.io.BufferedInputStream")

    SWF = JClass("com.jpexs.decompiler.flash.SWF")
    SymbolClassTag = JClass("com.jpexs.decompiler.flash.tags.SymbolClassTag")
    DefineSpriteTag = JClass("com.jpexs.decompiler.flash.tags.DefineSpriteTag")
    DefineSoundTag = JClass("com.jpexs.decompiler.flash.tags.DefineSoundTag")
    # DefineBits / DefineBitsLossless(2) / DefineBitsJPEG2-4: the textures used by shapes.
    ImageTagClass = JClass("com.jpexs.decompiler.flash.tags.base.ImageTag")

    DefineShapeTag = JClass("com.jpexs.decompiler.flash.tags.DefineShapeTag")
    DefineShape2Tag = JClass("com.jpexs.decompiler.flash.tags.DefineShape2Tag")
    DefineShape3Tag = JClass("com.jpexs.decompiler.flash.tags.DefineShape3Tag")
    DefineShape4Tag = JClass("com.jpexs.decompiler.flash.tags.DefineShape4Tag")
    DefineShapeTags = (DefineShapeTag, DefineShape2Tag, DefineShape3Tag, DefineShape4Tag)

    PlaceObject2Tag = JClass("com.jpexs.decompiler.flash.tags.PlaceObject2Tag")
    PlaceObject3Tag = JClass("com.jpexs.decompiler.flash.tags.PlaceObject3Tag")
    PlaceObjectTags = (PlaceObject2Tag, PlaceObject3Tag)


class MergeError(Exception):
    pass


def _is_image(element) -> bool:
    return bool(ImageTagClass.class_.isInstance(element))


def _get_element_id(element) -> int | None:
    t = type(element)
    if t in DefineShapeTags:
        eid = int(element.shapeId)
    elif t is DefineSpriteTag:
        eid = int(element.spriteId)
    elif t is DefineSoundTag:
        eid = int(element.soundId)
    elif t in PlaceObjectTags:
        eid = int(element.characterId)
    elif _is_image(element):
        eid = int(element.getCharacterId())
    else:
        return None
    return eid if eid > 0 else None


def _set_element_id(element, elid: int) -> None:
    t = type(element)
    if t in DefineShapeTags:
        element.shapeId = elid
    elif t is DefineSpriteTag:
        element.spriteId = elid
    elif t is DefineSoundTag:
        element.soundId = elid
    elif t in PlaceObjectTags:
        element.characterId = elid
    elif _is_image(element):
        element.setCharacterId(elid)
    element.setModified(True)


def _get_shape_bitmap_id(shape):
    if type(shape) in DefineShapeTags:
        shape.getShapes()
        fills = getattr(shape.shapes, "fillStyles", None)
        if fills is not None and len(fills.fillStyles) == 1 and fills.fillStyles[0].fillStyleType == 64:
            return int(fills.fillStyles[0].bitmapId)
    return None


def _set_shape_bitmap_id(shape, bitmap_id: int) -> None:
    shape.shapes.fillStyles.fillStyles[0].bitmapId = bitmap_id
    shape.setModified(True)


def _needed_character_ids(element) -> list[int]:
    from jpype import JClass

    ids = HashSet()

    hashset_class = JClass("java.util.HashSet").class_
    method = None
    for candidate in element.getClass().getMethods():
        if str(candidate.getName()) != "getNeededCharactersDeep":
            continue
        params = candidate.getParameterTypes()
        if len(params) in (1, 2) and all(p.isAssignableFrom(hashset_class) for p in params):
            method = candidate
            break

    if method is None:
        raise MergeError(
            "Couldn't find a getNeededCharactersDeep(...) method accepting a HashSet "
            f"via reflection on {element.getClass().getName()} - FFDec's API may have "
            "changed in this version."
        )

    args = [ids] if len(method.getParameterTypes()) == 1 else [ids, HashSet()]
    method.invoke(element, *args)
    return sorted(int(i) for i in ids)


class SwfHandle:
    def __init__(self, path: str):
        self.path = path
        self._swf = None
        self.symbol_class = None
        self._symbol_class_tag = None
        self.elements_by_id: dict[int, object] = {}

    def open(self):
        stream = BufferedInputStream(FileInputStream(self.path))
        self._swf = SWF(stream, True)

        self.symbol_class = {}
        self._symbol_class_tag = None
        self.elements_by_id = {}

        for tag in self._swf.getTags():
            if type(tag) is SymbolClassTag:
                self._symbol_class_tag = tag
                for n, char_id in enumerate(tag.tags):
                    self.symbol_class[str(tag.names[n])] = int(char_id)
            else:
                eid = _get_element_id(tag)
                if eid is not None:
                    self.elements_by_id[eid] = tag
        return self

    def id_for_anchor(self, anchor: str) -> int | None:
        return self.symbol_class.get(anchor)

    def get(self, elid: int):
        return self.elements_by_id.get(elid)

    def next_character_id(self) -> int:
        return int(self._swf.getNextCharacterId())

    def clone_and_add(self, element, new_id: int):
        clone = element.cloneTag()
        self._swf.addTag(clone)
        _set_element_id(clone, new_id)
        self.elements_by_id[new_id] = clone
        return clone

    def replace(self, old_element, new_element):
        self._swf.replaceTag(old_element, new_element)

    def remove(self, element):
        self._swf.removeTag(element)
        eid = _get_element_id(element)
        if eid in self.elements_by_id and self.elements_by_id[eid] is element:
            del self.elements_by_id[eid]

    def set_symbol_class(self, anchor: str, char_id: int):
        self.symbol_class[anchor] = char_id
        self._symbol_class_tag.tags.clear()
        self._symbol_class_tag.names.clear()
        from jpype import JInt, JString
        for name, cid in self.symbol_class.items():
            self._symbol_class_tag.tags.add(JInt(cid))
            self._symbol_class_tag.names.add(JString(name))
        self._symbol_class_tag.setModified(True)

    def save(self):
        out = FileOutputStream(self.path)
        self._swf.saveTo(out)
        out.close()

    def close(self):
        if self._swf is not None:
            self._swf.clearTagSwfs()
            try:
                self._swf.clearAllCache()
            except Exception:
                pass
            self._swf = None


def import_sprite(game: SwfHandle, mod: SwfHandle, anchor: str, elements_map: dict) -> bool:
    orig_id = game.id_for_anchor(anchor)
    if orig_id is None:
        return False
    orig_sprite = game.get(orig_id)
    if orig_sprite is None:
        return False

    mod_sprite_id = mod.id_for_anchor(anchor)
    if mod_sprite_id is None:
        return False
    mod_sprite = mod.get(mod_sprite_id)
    if mod_sprite is None:
        return False

    preserved_id = game.next_character_id()
    game.clone_and_add(orig_sprite, preserved_id)

    clone_sprites = []
    clone_shapes = []

    needed_ids = [*_needed_character_ids(mod_sprite), mod_sprite_id]
    for needed_id in needed_ids:
        if needed_id in elements_map:
            continue

        mod_element = mod.get(needed_id)
        if mod_element is None:
            continue

        if needed_id == mod_sprite_id:
            new_id = orig_id
            clone_el = mod_element.cloneTag()
            game._swf.addTag(clone_el)
            game.replace(orig_sprite, clone_el)
            _set_element_id(clone_el, orig_id)
            game.elements_by_id[orig_id] = clone_el
        else:
            new_id = game.next_character_id()
            clone_el = game.clone_and_add(mod_element, new_id)

        elements_map[needed_id] = new_id

        if type(clone_el) in DefineShapeTags and _get_shape_bitmap_id(clone_el) is not None:
            clone_shapes.append(clone_el)
        elif type(clone_el) is DefineSpriteTag:
            clone_sprites.append(clone_el)

    for sprite in clone_sprites:
        for inner in sprite.getTags():
            if type(inner) in PlaceObjectTags and int(inner.characterId) > 0:
                old_ref = int(inner.characterId)
                if old_ref in elements_map:
                    _set_element_id(inner, elements_map[old_ref])

    for shape in clone_shapes:
        old_bitmap_id = _get_shape_bitmap_id(shape)
        if old_bitmap_id in elements_map:
            _set_shape_bitmap_id(shape, elements_map[old_bitmap_id])

    return True


def import_sound(game: SwfHandle, mod: SwfHandle, anchor: str) -> bool:
    orig_id = game.id_for_anchor(anchor)
    if orig_id is None:
        return False
    orig_sound = game.get(orig_id)

    mod_sound_id = mod.id_for_anchor(anchor)
    mod_sound = mod.get(mod_sound_id) if mod_sound_id is not None else None
    if mod_sound is None:
        return False

    preserved_id = game.next_character_id()
    game.clone_and_add(orig_sound, preserved_id)

    clone = mod_sound.cloneTag()
    game._swf.addTag(clone)
    game.replace(orig_sound, clone)
    _set_element_id(clone, orig_id)
    game.elements_by_id[orig_id] = clone
    return True


def _create_as3_script_replacer(As3ScriptReplacerFactory):
    try:
        return As3ScriptReplacerFactory.createByConfig()
    except TypeError:
        return As3ScriptReplacerFactory.createByConfig(False)


def _replace_script_pack(pack, replacer, content: str) -> None:
    try:
        pack.abc.replaceScriptPack(replacer, pack, content)
    except TypeError:
        from jpype import JClass
        ArrayList = JClass("java.util.ArrayList")
        pack.abc.replaceScriptPack(replacer, pack, content, ArrayList())


def import_script(game: SwfHandle, content: str, anchor: str) -> bool:
    for pack in game._swf.getAS3Packs():
        if str(pack) != anchor:
            continue
        from jpype import JClass
        As3ScriptReplacerFactory = JClass("com.jpexs.decompiler.flash.importers.As3ScriptReplacerFactory")
        replacer = _create_as3_script_replacer(As3ScriptReplacerFactory)
        _replace_script_pack(pack, replacer, content)
        return True
    return False


def merge_bmod_swfs(
    bmod_metadata: dict,
    bmod_swf_path: str,
    brawlhalla_folder: Path,
    ffdec_jar_path: str,
    log: Callable[[str], None],
    java_home: str | None = None,
) -> dict:
    swfs_map = bmod_metadata.get("swfs") or {}
    if not swfs_map:
        return {"merged": [], "missing_game_swf": [], "missing_anchor": []}

    ensure_ffdec(ffdec_jar_path, java_home)

    name_index: dict[str, Path] = {}
    for p in brawlhalla_folder.rglob("*.swf"):
        name_index.setdefault(p.name, p)

    merged: list[str] = []
    missing_game_swf: list[str] = []
    missing_anchor: list[str] = []

    mod = SwfHandle(bmod_swf_path).open()
    try:
        for swf_name, categories in swfs_map.items():
            game_path = name_index.get(swf_name)
            if game_path is None:
                missing_game_swf.append(swf_name)
                log(f"   [X] {swf_name}: not found in your Brawlhalla folder")
                continue

            log(f"[i] Merging into {swf_name} ...")
            game = SwfHandle(str(game_path)).open()
            try:
                for scriptAnchor, content in (categories.get("scripts") or {}).items():
                    if import_script(game, content, scriptAnchor):
                        log(f"   OK script {scriptAnchor}")
                        merged.append(f"{swf_name}:{scriptAnchor}")
                    else:
                        missing_anchor.append(f"{swf_name}:{scriptAnchor}")
                        log(f"   [X] script anchor not found: {scriptAnchor}")

                for soundAnchor in categories.get("sounds") or []:
                    if import_sound(game, mod, soundAnchor):
                        log(f"   OK sound {soundAnchor}")
                        merged.append(f"{swf_name}:{soundAnchor}")
                    else:
                        missing_anchor.append(f"{swf_name}:{soundAnchor}")
                        log(f"   [X] sound anchor not found: {soundAnchor}")

                elements_map: dict = {}
                for spriteAnchor in categories.get("sprites") or []:
                    if import_sprite(game, mod, spriteAnchor, elements_map):
                        log(f"   OK sprite {spriteAnchor}")
                        merged.append(f"{swf_name}:{spriteAnchor}")
                    else:
                        missing_anchor.append(f"{swf_name}:{spriteAnchor}")
                        log(f"   [X] sprite anchor not found: {spriteAnchor}")

                mod_registry.before_overwrite(game_path)
                game.save()
            finally:
                game.close()
    finally:
        mod.close()

    return {"merged": merged, "missing_game_swf": missing_game_swf, "missing_anchor": missing_anchor}

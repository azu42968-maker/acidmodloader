"""
Update Color Mod.

Despues de un parche de Brawlhalla, el juego renombra los identificadores
internos que usan los color mods (clase / vector / array de ColorSwap y las
propiedades de los team colors). Un UI_MainMenu.swf con colores ya inyectados
deja de funcionar porque apunta a los nombres viejos.

Este modulo:
  1. decompila BrawlhallaAir.swf (ya actualizado) con FFDec y detecta los
     identificadores nuevos,
  2. exporta el pcode del metodo inyectado en UI_MainMenu.swf,
  3. reemplaza los identificadores viejos por los nuevos y
  4. reinyecta el metodo.

Los colores ya instalados no se tocan, solo los identificadores.
"""
from __future__ import annotations

import glob
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import mod_registry

AIR_SWF_NAME = "BrawlhallaAir.swf"
MAINMENU_SWF_NAME = "UI_MainMenu.swf"
CLASS_NAME = "a_BattlePassSplashArtButton"

REQUIRED_IMPORTS = [
    "import haxe.IMap;",
    "import haxe.ds.EnumValueMap;",
    "import haxe.ds.IntMap;",
    "import haxe.ds.StringMap;",
]

FIELD_PATTERN = re.compile(
    r"public\s+(?P<static>static\s+)?var\s+(?P<name>[^\s:]+)\s*:\s*(?P<type>[^;=]+?)\s*[;=]"
)
CLASS_PATTERN = re.compile(r"class\s+(?P<name>[^\s{]+)")

TEAM_SLOT_ORDER = [
    "TeamRed1", "TeamRed2", "TeamRed3", "TeamRed4",
    "TeamBlue1", "TeamBlue2", "TeamBlue3", "TeamBlue4",
    "TeamYellow1", "TeamYellow2", "TeamYellow3", "TeamYellow4",
    "TeamPurple1", "TeamPurple2", "TeamPurple3", "TeamPurple4",
]

_TEAM_FIELD_RE_TEMPLATE = (
    r"§[^§]+§\.§(?P<field>[^§]+)§\s*=\s*"
    r'"{name}"\s+in\s+StringMap\.reserved'
)

_FINGERPRINT_MARKERS = ('"hasDefinition"', '"getDefinition"')
_METHOD_BLOCK_RE = re.compile(r"method\b.*?end\s*;\s*method", re.DOTALL)

_TEAM_BLOCK_RE = re.compile(
    r'getlocal 5\s*\n'
    r'\s*getproperty QName\(PackageNamespace\("","4"\),"(?P<prop>[^"]*)"\)\s*\n'
    r'\s*coerce QName\(PackageNamespace\("","4"\),"(?P<cls>[^"]*)"\)\s*\n'
    r'\s*setlocal 13'
)


class ColorModError(Exception):
    pass


# --------------------------------------------------------------------------
# FFDec (linea de comandos, con el JRE que ya trae la app)
# --------------------------------------------------------------------------

class FFDec:

    def __init__(self, java_exe: str, jar_path: str, log):
        self.java_exe = java_exe
        self.jar_path = jar_path
        self.log = log

    def run(self, args: list[str], timeout: int = 1800) -> subprocess.CompletedProcess:
        cmd = [self.java_exe, "-jar", self.jar_path, *args]
        kwargs = {}
        if sys.platform.startswith("win"):
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        try:
            return subprocess.run(
                cmd, capture_output=True, text=True, errors="replace",
                timeout=timeout, **kwargs,
            )
        except subprocess.TimeoutExpired:
            raise ColorModError("FFDec took too long and was stopped.")
        except OSError as e:
            raise ColorModError(f"Couldn't start FFDec: {e}")


def make_ffdec(vendor_dir: Path, java_home: str | None, log) -> FFDec:
    exe_name = "java.exe" if sys.platform.startswith("win") else "java"

    java_exe = None
    if java_home:
        candidate = Path(java_home) / "bin" / exe_name
        if candidate.is_file():
            java_exe = str(candidate)
    if java_exe is None:
        java_exe = shutil.which("java")
    if java_exe is None:
        raise ColorModError("Couldn't find Java (the bundled JRE is missing and there is no system Java).")

    jar = None
    for name in ("ffdec-cli.jar", "ffdec.jar"):
        candidate = Path(vendor_dir) / "ffdec" / name
        if candidate.is_file():
            jar = str(candidate)
            break
    if jar is None:
        raise ColorModError(f"Couldn't find the FFDec command-line jar under {Path(vendor_dir) / 'ffdec'}.")

    return FFDec(java_exe, jar, log)


# --------------------------------------------------------------------------
# Paso 1: identificadores nuevos desde BrawlhallaAir.swf
# --------------------------------------------------------------------------

def _strip_marker(name: str) -> str:
    return name.replace("§", "")


def _extract_class_body(text: str, start_idx: int):
    m = CLASS_PATTERN.match(text, start_idx)
    if not m:
        return None, None
    name = m.group("name")
    brace_start = text.find("{", m.end())
    if brace_start == -1:
        return name, None
    depth = 0
    i = brace_start
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return name, text[brace_start + 1: i]
        i += 1
    return name, None


def _find_all_classes(text: str):
    classes = []
    for m in re.finditer(r"\bclass\s+[^\s{]+", text):
        name, body = _extract_class_body(text, m.start())
        if body is not None:
            classes.append((name, body))
    return classes


def _extract_fields(class_body: str):
    return [
        {
            "name": m.group("name"),
            "type": m.group("type").strip(),
            "is_static": bool(m.group("static")),
        }
        for m in FIELD_PATTERN.finditer(class_body)
    ]


def find_values(dump_text: str):
    target = None
    for name, body in _find_all_classes(dump_text):
        if "NO_COLOR_SCHEME" in body:
            target = (name, body)
            break
    if not target:
        return None

    class_name, body = target
    fields = _extract_fields(body)
    vector_fields = [f for f in fields if f["is_static"] and f["type"].startswith("Vector.<")]
    array_fields = [f for f in fields if not f["is_static"] and f["type"] == "Array"]
    vector_name = vector_fields[-1]["name"] if vector_fields else None
    array_name = array_fields[-1]["name"] if array_fields else None
    if not vector_name or not array_name:
        return None

    return {
        "class_name": _strip_marker(class_name),
        "vector_name": _strip_marker(vector_name),
        "array_name": _strip_marker(array_name),
    }


def find_team_values(dump_text: str):
    result = {}
    for name in TEAM_SLOT_ORDER:
        pattern = re.compile(_TEAM_FIELD_RE_TEMPLATE.format(name=re.escape(name)))
        m = pattern.search(dump_text)
        if not m:
            return None
        result[name] = _strip_marker(m.group("field"))
    return result


def _find_target_as_file(export_dir: str, log):
    matches = []
    for path in glob.glob(str(Path(export_dir) / "**" / "*.as"), recursive=True):
        try:
            text = Path(path).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        import_lines = [ln.strip() for ln in text.splitlines() if ln.strip().startswith("import ")]
        if len(import_lines) != 4:
            continue
        if all(imp in import_lines for imp in REQUIRED_IMPORTS):
            matches.append(path)

    if not matches:
        return None
    if len(matches) > 1:
        log(f"[!] Found {len(matches)} candidate classes (there used to be only 1); using the smallest.")
        matches.sort(key=lambda p: Path(p).stat().st_size)
    return matches[0]


def find_new_identifiers(ffdec: FFDec, air_swf: Path, log):
    if not air_swf.is_file():
        raise ColorModError(f"Couldn't find {AIR_SWF_NAME} at: {air_swf}")

    with tempfile.TemporaryDirectory() as workdir:
        export_dir = str(Path(workdir) / "decompiled")
        Path(export_dir).mkdir(parents=True, exist_ok=True)

        log(f"[i] Decompiling {air_swf.name} (this can take 1-3 minutes)...")
        result = ffdec.run([
            "-onerror", "ignore",
            "-exportFileTimeout", "15",
            "-exportTimeout", "1100",
            "-export", "script", export_dir, str(air_swf),
        ])
        if result.returncode != 0:
            tail = "\n".join([ln for ln in (result.stdout + "\n" + result.stderr).splitlines() if ln.strip()][-6:])
            raise ColorModError("FFDec failed to decompile the game." + (f" Output: {tail}" if tail else ""))

        best = _find_target_as_file(export_dir, log)
        if best is None:
            raise ColorModError(
                "Couldn't find the color class in the game (no class with the expected imports). "
                "The game may have changed its internal structure."
            )

        dump_text = Path(best).read_text(encoding="utf-8", errors="ignore")
        values = find_values(dump_text)
        if not values:
            raise ColorModError(f'Couldn\'t find the class with "NO_COLOR_SCHEME" (or its fields) in {Path(best).name}.')

        team_values = find_team_values(dump_text)
        if not team_values:
            raise ColorModError(
                "Couldn't find the 16 team color identifiers "
                "(the game may have changed that structure)."
            )

        return values["class_name"], values["vector_name"], values["array_name"], team_values


# --------------------------------------------------------------------------
# Pasos 2-3: pcode del metodo inyectado y relink de identificadores
# --------------------------------------------------------------------------

def export_class_pcode(ffdec: FFDec, swf_path: Path, class_name: str, out_dir: str) -> str:
    ffdec.run([
        "-format", "script:pcode",
        "-selectclass", class_name,
        "-export", "script", str(out_dir), str(swf_path),
    ])

    candidates = list(Path(out_dir).rglob(f"{class_name}.*"))
    if not candidates:
        candidates = [f for f in Path(out_dir).rglob("*") if f.is_file() and f.stem == class_name]
    if not candidates:
        raise ColorModError(f"FFDec didn't export anything for class {class_name}.")

    return candidates[0].read_text(encoding="utf-8", errors="replace")


def find_injected_method_block(class_pcode_text: str) -> str:
    for match in _METHOD_BLOCK_RE.finditer(class_pcode_text):
        block = match.group(0)
        if all(marker in block for marker in _FINGERPRINT_MARKERS):
            return block
    raise ColorModError(
        f"{MAINMENU_SWF_NAME} has no color mod injected yet (nothing to update), "
        "or the game changed the structure of the constructor."
    )


def relink_identifiers(method_block, new_cls, new_vec, new_arr, new_team, team_slot_order, log):
    text = method_block
    total = 0

    text, n = re.subn(
        r'(pushstring\s+")([^"]*)(")',
        lambda m: m.group(1) + new_cls + m.group(3),
        text, count=1,
    )
    if n == 0:
        raise ColorModError("Couldn't find the ColorSwapClass header in the injected method (unexpected pattern).")
    log(f"   - ColorSwapClass (header): {n}")
    total += n

    text, n = re.subn(
        r'(getlocal 5\s*\n\s*getproperty QName\(PackageNamespace\("","4"\),")([^"]*)("\)\s*\n\s*setlocal 7)',
        lambda m: m.group(1) + new_vec + m.group(3),
        text, count=1,
    )
    if n:
        log(f"   - ColorSwapVector (header): {n}")
        total += n

    text, n = re.subn(
        r'(getproperty MultinameL\(\[PackageNamespace\("","3"\)\]\)\s*\n\s*'
        r'coerce QName\(PackageNamespace\("","4"\),")([^"]*)("\)\s*\n\s*setlocal 13)',
        lambda m: m.group(1) + new_cls + m.group(3),
        text,
    )
    if n:
        log(f"   - ColorSwapClass (color blocks): {n}")
        total += n

    text, n = re.subn(
        r'(coerce QName\(PackageNamespace\("","4"\),"Array"\)\s*\n\s*'
        r'initproperty QName\(PackageNamespace\("","4"\),")([^"]*)("\))',
        lambda m: m.group(1) + new_arr + m.group(3),
        text,
    )
    if n:
        log(f"   - ColorSwapArray (color blocks): {n}")
        total += n

    matches = list(_TEAM_BLOCK_RE.finditer(text))
    if matches:
        if not team_slot_order and len(matches) == len(TEAM_SLOT_ORDER):
            team_slot_order = list(TEAM_SLOT_ORDER)
        if not team_slot_order or len(matches) != len(team_slot_order):
            raise ColorModError(
                f"The injected method has {len(matches)} team color block(s) but I can't tell "
                "which slot each one belongs to, so I won't touch them (I could write the wrong "
                "color into a slot). Nothing was changed."
            )
        for i in range(len(matches) - 1, -1, -1):
            m = matches[i]
            slot = team_slot_order[i]
            if slot not in new_team:
                raise ColorModError(f'No new identifier for the installed team color "{slot}".')
            new_prop = new_team[slot]
            old_prop = m.group("prop")
            block = m.group(0)
            block = block.replace(f'"{old_prop}"', f'"{new_prop}"', 1)
            block = block.replace(f'"{m.group("cls")}"', f'"{new_cls}"', 1)
            text = text[:m.start()] + block + text[m.end():]
            log(f'   - team color "{slot}": "{old_prop}" -> "{new_prop}"')
        total += len(matches)

    if total == 0:
        raise ColorModError("No color block found inside the injected method. The pattern may have changed.")

    return text, total


# --------------------------------------------------------------------------
# Paso 4: reinyectar el metodo
# --------------------------------------------------------------------------

def _find_as_file(tmp_dir: Path, class_name: str):
    for f in tmp_dir.rglob("*.as"):
        if f.stem == class_name:
            return f
    return None


def get_method_body_index(ffdec: FFDec, swf_path: Path, class_name: str) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        base = ["-config", "showMethodBodyId=true"]
        ffdec.run(base + ["-selectclass", class_name, "-export", "script", str(tmp_dir), str(swf_path)])
        as_file = _find_as_file(tmp_dir, class_name)

        if as_file is None:
            full_dir = tmp_dir / "full"
            full_dir.mkdir()
            ffdec.run(base + ["-onerror", "ignore", "-export", "script", str(full_dir), str(swf_path)])
            as_file = _find_as_file(full_dir, class_name)

        if as_file is None:
            raise ColorModError(
                f"Couldn't find class {class_name} in {swf_path.name}. "
                "The game may have renamed or removed it."
            )

        content = as_file.read_text(encoding="utf-8", errors="replace")
        signature = f"public function {class_name}("
        idx = content.find(signature)
        if idx == -1:
            raise ColorModError(f"Couldn't find the constructor '{signature}' in the exported script.")

        match = re.search(r"method body index:\s*(\d+)", content[idx: idx + 400])
        if not match:
            raise ColorModError("Couldn't find the 'method body index' comment near the constructor.")
        return int(match.group(1))


def update_color_mod(brawlhalla_folder: Path, vendor_dir: Path, java_home: str | None,
                     log, team_slot_order: list[str] | None = None) -> dict:
    """
    Corre los 4 pasos. El unico archivo del juego que se modifica es
    UI_MainMenu.swf, y se escribe con mod_registry.write_bytes para que quede un
    backup (el llamador debe haber hecho mod_registry.begin()).
    """
    brawlhalla_folder = Path(brawlhalla_folder)
    air_swf = brawlhalla_folder / AIR_SWF_NAME
    menu_swf = brawlhalla_folder / MAINMENU_SWF_NAME

    if not menu_swf.is_file():
        raise ColorModError(f"Couldn't find {MAINMENU_SWF_NAME} in your Brawlhalla folder.")

    ffdec = make_ffdec(vendor_dir, java_home, log)

    log("--- Step 1/4: new identifiers (from the updated BrawlhallaAir.swf) ---")
    new_cls, new_vec, new_arr, new_team = find_new_identifiers(ffdec, air_swf, log)
    log(f'[i] Class="{new_cls}"  Vector="{new_vec}"  Array="{new_arr}"')
    log(f"[i] {len(new_team)} team color identifiers found.")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        work_swf = tmp_dir / MAINMENU_SWF_NAME
        shutil.copy2(menu_swf, work_swf)

        log("")
        log(f"--- Step 2/4: reading the injected code from {MAINMENU_SWF_NAME} ---")
        pcode_dir = tmp_dir / "pcode"
        pcode_dir.mkdir()
        class_pcode = export_class_pcode(ffdec, work_swf, CLASS_NAME, str(pcode_dir))
        block = find_injected_method_block(class_pcode)

        log("")
        log("--- Step 3/4: replacing the old identifiers with the new ones ---")
        edited, total = relink_identifiers(
            block, new_cls, new_vec, new_arr, new_team, team_slot_order or [], log
        )
        edited_path = tmp_dir / "relinked_method.pcode"
        edited_path.write_text(edited, encoding="utf-8", newline="\r\n")

        log("")
        log(f"--- Step 4/4: re-injecting ({total} identifier(s) updated) ---")
        body_index = get_method_body_index(ffdec, work_swf, CLASS_NAME)
        patched_swf = tmp_dir / "patched.swf"
        result = ffdec.run([
            "-replace", str(work_swf), str(patched_swf),
            CLASS_NAME, str(edited_path), str(body_index),
        ])
        if result.returncode != 0 or not patched_swf.is_file():
            tail = "\n".join([ln for ln in (result.stdout + "\n" + result.stderr).splitlines() if ln.strip()][-6:])
            raise ColorModError("FFDec failed to re-inject the updated code." + (f" Output: {tail}" if tail else ""))

        try:
            mod_registry.write_bytes(menu_swf, patched_swf.read_bytes())
        except OSError as e:
            raise ColorModError(f"Couldn't write {MAINMENU_SWF_NAME} (is Brawlhalla running?): {e}")

    log("")
    log(f"[OK] {MAINMENU_SWF_NAME} updated ({total} identifier(s)). Your installed colors were not touched.")
    return {"updated": total}

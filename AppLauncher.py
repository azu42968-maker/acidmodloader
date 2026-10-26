import base64
import hashlib
import importlib.util
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import threading
import traceback
from pathlib import Path

import AppBox

if __name__ == "__main__":
    # Si hay un distrobox configurado (AZU_BOX / config.json / unico box), la app
    # se relanza ahi adentro, donde estan Java, FFDec y pywebview. AZU_NO_BOX=1 lo evita.
    AppBox.relaunch_in_box_if_needed()

import AppWebSync as WebSync

IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"
APP_NAME = "AzuModification"


def _data_root():
    """Carpeta de datos de la app.
    Linux:   $XDG_DATA_HOME/AzuModification  (por defecto ~/.local/share/AzuModification)
    Windows: %APPDATA%\\AzuModification
    macOS:   ~/Library/Application Support/AzuModification
    """
    if IS_WIN:
        base = os.getenv("APPDATA") or os.path.expanduser("~")
    elif IS_MAC:
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.getenv("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, APP_NAME)


def _base_dir_for_log():
    if hasattr(sys, "_MEIPASS"):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _show_fatal_error(title, message):
    log_path = None
    try:
        log_path = os.path.join(_base_dir_for_log(), "launcher_error.log")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write("\n" + "=" * 70 + "\n")
            f.write(message)
    except Exception:
        log_path = None

    full_message = message
    if log_path:
        full_message += f"\n\n(Guardado en: {log_path})"

    shown = False
    if IS_WIN:
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, full_message, title, 0x10)
            shown = True
        except Exception:
            pass
    else:
        # KDE (kdialog) / GNOME (zenity); si no hay ninguno, cae a tkinter o consola.
        for cmd in (
            ["kdialog", "--title", title, "--error", full_message],
            ["zenity", "--error", "--title", title, "--no-markup", "--text", full_message],
        ):
            if shutil.which(cmd[0]):
                try:
                    subprocess.run(cmd, check=False)
                    shown = True
                    break
                except Exception:
                    pass

    if not shown:
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(title, full_message)
            root.destroy()
            shown = True
        except Exception:
            pass

    if not shown:
        print(full_message)
        try:
            input("\nPresiona Enter para cerrar...")
        except Exception:
            pass


def _tee_log(msg):
    """print + update.log (en el exe print no deja rastro)."""
    print(msg)
    try:
        import AppUpdater as _upd
        _upd.log(str(msg))
    except Exception:
        pass


def _prereqs_dir():
    if hasattr(sys, "_MEIPASS"):
        path = os.path.join(_data_root(), "prerequisites")
    else:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prerequisites")
    os.makedirs(path, exist_ok=True)
    return path


def _download_and_extract(url, dest_dir, log):
    """Descarga un .zip o .tar.gz y lo extrae en dest_dir (detecta el formato solo)."""
    import tempfile
    import urllib.request
    import zipfile

    os.makedirs(dest_dir, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, "download.bin")
        log(f"[*] Descargando {url} ...")
        urllib.request.urlretrieve(url, archive)
        log("[*] Descarga completa, extrayendo...")
        if zipfile.is_zipfile(archive):
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(dest_dir)
        elif tarfile.is_tarfile(archive):
            with tarfile.open(archive) as tf:
                tf.extractall(dest_dir)
        else:
            raise RuntimeError("El archivo descargado no es .zip ni .tar.gz")
    log(f"[*] Listo en {dest_dir}")


def _find_file(root, filename):
    if not os.path.isdir(root):
        return None
    for dirpath, _dirnames, filenames in os.walk(root):
        if filename in filenames:
            return os.path.join(dirpath, filename)
    return None


def _make_executable(path):
    try:
        mode = os.stat(path).st_mode
        os.chmod(path, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except OSError:
        pass


def _prepend_to_path(folder):
    os.environ["PATH"] = folder + os.pathsep + os.environ.get("PATH", "")


def _adoptium_os_arch():
    os_name = "windows" if IS_WIN else ("mac" if IS_MAC else "linux")
    machine = platform.machine().lower()
    arch = "aarch64" if machine in ("aarch64", "arm64") else "x64"
    return os_name, arch


def _find_java_bin(root):
    """Busca <...>/bin/java dentro del JRE portable descargado."""
    names = ("java.exe",) if IS_WIN else ("java",)
    if not os.path.isdir(root):
        return None
    for dirpath, _dirnames, filenames in os.walk(root):
        if os.path.basename(dirpath) != "bin":
            continue
        for name in names:
            if name in filenames:
                return os.path.join(dirpath, name)
    return None


def ensure_java(log=print):
    if shutil.which("java"):
        return True

    jre_dir = os.path.join(_prereqs_dir(), "jre")
    java_bin = _find_java_bin(jre_dir)
    if java_bin:
        _make_executable(java_bin)
        _prepend_to_path(os.path.dirname(java_bin))
        return True

    log("[*] Java no encontrado, descargando un JRE portable (una sola vez, puede tardar)...")
    os_name, arch = _adoptium_os_arch()
    url = (
        f"https://api.adoptium.net/v3/binary/latest/17/ga/{os_name}/{arch}/jre/"
        "hotspot/normal/eclipse?project=jdk"
    )
    try:
        _download_and_extract(url, jre_dir, log)
    except Exception as e:
        log(f"[!] No se pudo instalar Java automaticamente: {e}. "
            "Instala un JDK/JRE a mano si el resto falla "
            "(en Bazzite: brew install openjdk, o dentro de distrobox).")
        return False

    java_bin = _find_java_bin(jre_dir)
    if not java_bin:
        log("[!] Se descargo el JRE pero no se encontro bin/java adentro.")
        return False

    # El zip/tar puede perder el bit de ejecucion: se lo devolvemos a todo bin/.
    bin_dir = os.path.dirname(java_bin)
    for f in os.listdir(bin_dir):
        _make_executable(os.path.join(bin_dir, f))

    _prepend_to_path(bin_dir)
    log(f"[*] Java portable listo: {java_bin}")
    return True


def _ffdec_launcher_name():
    return "ffdec.bat" if IS_WIN else "ffdec.sh"


def _setup_ffdec_launcher(launcher):
    """Deja ffdec listo para usarse: bit de ejecucion + alias 'ffdec' en Linux/macOS."""
    folder = os.path.dirname(launcher)
    if not IS_WIN:
        _make_executable(launcher)
        alias = os.path.join(folder, "ffdec")
        if not os.path.exists(alias):
            try:
                os.symlink(os.path.basename(launcher), alias)
            except OSError:
                try:
                    shutil.copy2(launcher, alias)
                    _make_executable(alias)
                except OSError:
                    pass
    _prepend_to_path(folder)


def ensure_ffdec(log=print):
    try:
        import AppCodeInstaller as inj
        inj.find_ffdec(None)
        return True
    except Exception:
        pass

    ffdec_dir = os.path.join(_prereqs_dir(), "ffdec")
    launcher_name = _ffdec_launcher_name()
    launcher = _find_file(ffdec_dir, launcher_name)
    if launcher:
        _setup_ffdec_launcher(launcher)
        return True

    log("[*] FFDec no encontrado, descargando (una sola vez)...")
    url = (
        "https://github.com/jindrapetrik/jpexs-decompiler/releases/download/"
        "version25.0.0/ffdec_25.0.0.zip"
    )
    try:
        _download_and_extract(url, ffdec_dir, log)
    except Exception as e:
        log(f"[!] No se pudo instalar FFDec automaticamente: {e}. "
            "Instalalo a mano (jindrapetrik/jpexs-decompiler en GitHub).")
        return False

    launcher = _find_file(ffdec_dir, launcher_name)
    if not launcher:
        log(f"[!] Se descargo FFDec pero no se encontro {launcher_name} adentro.")
        return False

    _setup_ffdec_launcher(launcher)
    log(f"[*] FFDec listo: {launcher}")
    return True


def ensure_prerequisites(log=print):
    try:
        ensure_java(log=log)
    except Exception as e:
        log(f"[!] Fallo verificando/instalando Java: {e}")
    try:
        ensure_ffdec(log=log)
    except Exception as e:
        log(f"[!] Fallo verificando/instalando FFDec: {e}")


try:
    import webview
except Exception:
    _show_fatal_error(
        "Azu Modification — Error al iniciar",
        "No se pudo cargar pywebview o su motor grafico.\n"
        "En Linux instala uno de estos en tu venv:\n"
        "  pip install \"pywebview[qt]\"     (recomendado en KDE/Bazzite)\n"
        "  pip install \"pywebview[gtk]\"    (necesita PyGObject + WebKit2GTK del sistema)\n\n"
        + traceback.format_exc(),
    )
    sys.exit(1)

def _persistent_module_dir():
    path = os.path.join(_data_root(), "engine")
    os.makedirs(path, exist_ok=True)
    return path


def _bundle_fingerprint():
    if not hasattr(sys, "_MEIPASS"):
        return None
    names = (
        "AppAllInOne.py", "AppPublic.py", "index.html", "app.js",
        "styles.css", "codemirror.bundle.js",
    )
    h = hashlib.sha256()
    for name in names:
        path = os.path.join(sys._MEIPASS, name)
        try:
            with open(path, "rb") as f:
                h.update(f.read())
        except OSError:
            pass
    return h.hexdigest()


def _reset_stale_cache_if_new_build():
    fingerprint = _bundle_fingerprint()
    if fingerprint is None:
        return

    root = _data_root()
    os.makedirs(root, exist_ok=True)
    marker_path = os.path.join(root, "build_fingerprint.txt")

    try:
        previous = Path(marker_path).read_text(encoding="utf-8").strip()
    except OSError:
        previous = None

    if previous == fingerprint:
        return

    for folder in ("engine", "webview_data", "updates"):
        shutil.rmtree(os.path.join(root, folder), ignore_errors=True)

    try:
        Path(marker_path).write_text(fingerprint, encoding="utf-8")
    except OSError:
        pass


def _exec_module_from(name, path):
    module_name = name[:-3]
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_allinone_module():
    _reset_stale_cache_if_new_build()

    if not hasattr(sys, "_MEIPASS"):
        try:
            import AppAllInOne as AllInOne
            return AllInOne
        except ImportError:
            import AppPublic as AllInOne
            return AllInOne

    persistent_dir = _persistent_module_dir()

    for name in ("AppAllInOne.py", "AppPublic.py"):
        dst = os.path.join(persistent_dir, name)
        if os.path.exists(dst):
            try:
                return _exec_module_from(name, dst)
            except Exception:
                # Copia sincronizada desde GitHub rota: se descarta y se usa la del .exe.
                traceback.print_exc()
                sys.modules.pop(name[:-3], None)
                try:
                    os.remove(dst)
                except OSError:
                    pass

    for name in ("AppAllInOne.py", "AppPublic.py"):
        src = os.path.join(sys._MEIPASS, name)
        if os.path.exists(src):
            dst = os.path.join(persistent_dir, name)
            shutil.copy2(src, dst)
            return _exec_module_from(name, dst)

    raise ImportError(
        "No se encontró AppAllInOne.py ni AppPublic.py dentro del .exe "
        "(revisa que el .bat de empaquetado los incluya con --add-data)."
    )


try:
    AllInOne = _load_allinone_module()
except Exception:
    _show_fatal_error(
        "Azu Modification — Error al iniciar",
        "No se encontró AppAllInOne.py ni AppPublic.py (o falló al "
        "cargarlos).\n\n" + traceback.format_exc(),
    )
    sys.exit(1)

ensure_prerequisites(log=_tee_log)

TEAM_COLORS_SUPPORTED = hasattr(AllInOne, "get_team_slot_options")


def resource_path(relative_path):
    # La web (html/js/css) se carga desde la carpeta de datos (ver _data_root()), que se
    # mantiene al dia desde GitHub (AppWebSync.py). El .exe es solo el respaldo.
    synced = WebSync.web_path(relative_path)
    if synced:
        return synced
    if hasattr(sys, "_MEIPASS"):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


def get_storage_path():
    path = os.path.join(_data_root(), "webview_data")
    os.makedirs(path, exist_ok=True)
    return path


def get_data_dir():
    path = _data_root()
    os.makedirs(path, exist_ok=True)
    return path


def get_dump_path():
    if hasattr(sys, "_MEIPASS"):
        base_path = os.path.dirname(os.path.abspath(sys.executable))
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, "dumb.txt")


def get_gamebanana_dir():
    path = os.path.join(_data_root(), "GameBananaBuild")
    os.makedirs(path, exist_ok=True)
    return path


def get_gamebanana_swf_path():
    return os.path.join(get_gamebanana_dir(), "UI_MainMenu.swf")


def _ensure_gamebanana_swf(swf_path_override=None):
    target = get_gamebanana_swf_path()
    if os.path.exists(target):
        return target

    import AppCodeInstaller as inj

    if swf_path_override:
        real_swf = Path(swf_path_override)
    else:
        real_swf = inj.find_brawlhalla_swf()
        if real_swf is None:
            raise FileNotFoundError(
                "No pude encontrar UI_MainMenu.swf automaticamente para "
                "crear el build de GameBanana. Indica la ruta a mano."
            )

    backup = real_swf.with_suffix(real_swf.suffix + ".bak")
    source = backup if backup.exists() else real_swf
    shutil.copy2(source, target)
    return target


def _resolve_profile(profile, swf_path=None):
    if profile == "gamebanana":
        resolved_swf = _ensure_gamebanana_swf(swf_path)
        return get_gamebanana_dir(), str(resolved_swf)
    return get_data_dir(), swf_path


def _real_base_dir():
    if hasattr(sys, "_MEIPASS"):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def get_sprite_types_dir():
    path = os.path.join(get_data_dir(), "SpriteTypes")
    os.makedirs(path, exist_ok=True)
    return path


def get_prerenders_dir():
    path = os.path.join(get_data_dir(), "PreRenders")
    os.makedirs(path, exist_ok=True)
    return path


def _prerenders_type_dir(sprite_type):
    safe = re.sub(r'[\\/:*?"<>|]+', "_", (sprite_type or "color").strip())
    safe = safe or "color"
    path = os.path.join(get_prerenders_dir(), safe)
    os.makedirs(path, exist_ok=True)
    return path


_PRERENDER_MIME_BY_EXT = {
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


def _seed_bundled_prerenders():
    bundled = resource_path("PreRenders")
    if not os.path.isdir(bundled):
        return
    dest_base = get_prerenders_dir()
    try:
        type_keys = os.listdir(bundled)
    except Exception:
        return
    for type_key in type_keys:
        src_folder = os.path.join(bundled, type_key)
        if not os.path.isdir(src_folder):
            continue
        dest_folder = os.path.join(dest_base, type_key)
        os.makedirs(dest_folder, exist_ok=True)
        try:
            filenames = os.listdir(src_folder)
        except Exception:
            continue
        for filename in filenames:
            src_file = os.path.join(src_folder, filename)
            if not os.path.isfile(src_file):
                continue
            dest_file = os.path.join(dest_folder, filename)
            if not os.path.exists(dest_file):
                try:
                    shutil.copy2(src_file, dest_file)
                except Exception:
                    pass


def _seed_bundled_sprite_types():
    bundled = resource_path("SpriteTypes")
    if not os.path.isdir(bundled):
        return
    dest = get_sprite_types_dir()
    try:
        filenames = os.listdir(bundled)
    except Exception:
        return
    for filename in filenames:
        if not filename.lower().endswith(".xml"):
            continue
        src_file = os.path.join(bundled, filename)
        if not os.path.isfile(src_file):
            continue
        dest_file = os.path.join(dest, filename)
        if not os.path.exists(dest_file):
            try:
                shutil.copy2(src_file, dest_file)
            except Exception:
                pass


def _background_sync(window):
    """Corre en un hilo aparte una vez que la ventana ya cargo (webview.start(func=...)).
    Baja PreRenders/SpriteTypes nuevos desde GitHub (ver AppSync.py). Nunca bloquea
    ni rompe la app: sin internet o con cualquier error, simplemente no hace nada."""
    try:
        import AppSync
        res = AppSync.ContentSync(
            prerenders_dir=get_prerenders_dir(),
            sprite_types_dir=get_sprite_types_dir(),
            state_dir=os.path.join(get_data_dir(), "sync"),
        ).sync()
        print("[sync]", res)
        if res.get("updated") or res.get("removed"):
            payload = json.dumps({"updated": res.get("updated", 0), "removed": res.get("removed", 0)})
            try:
                window.events.loaded.wait(60)   # si la pagina aun no cargo, el evento se perderia
            except Exception:
                pass
            window.evaluate_js(
                "window.dispatchEvent(new CustomEvent('azu-content-updated', {detail: %s}));" % payload
            )
    except Exception:
        traceback.print_exc()


_UPDATE_BANNER_JS = """
(function (msg) {
  if (document.getElementById('azu-update-banner')) return;
  var box = document.createElement('div');
  box.id = 'azu-update-banner';
  box.style.cssText = 'position:fixed;right:16px;bottom:16px;z-index:99999;max-width:360px;' +
    'padding:12px 14px;border-radius:10px;background:#1f2937;color:#fff;' +
    'font:13px/1.4 system-ui,sans-serif;box-shadow:0 6px 24px rgba(0,0,0,.35);' +
    'display:flex;gap:10px;align-items:flex-start';
  var text = document.createElement('div');
  text.style.flex = '1';
  text.textContent = msg;
  var close = document.createElement('button');
  close.textContent = '\\u00d7';
  close.style.cssText = 'background:none;border:0;color:#fff;font-size:18px;cursor:pointer;line-height:1';
  close.onclick = function () { box.remove(); };
  box.appendChild(text);
  box.appendChild(close);
  document.body.appendChild(box);
})(__MSG__);
"""


def _notify_update(window, res):
    status = res.get("status")
    version = res.get("version", "")
    if status != "staged":
        return
    msg = f"Update {version} downloaded. Close and reopen the app to apply it."
    try:
        window.events.loaded.wait(30)
    except Exception:
        pass
    try:
        window.evaluate_js(_UPDATE_BANNER_JS.replace("__MSG__", json.dumps(msg)))
    except Exception:
        traceback.print_exc()


def _background_update(window):
    """Nunca bloquea ni rompe la app: sin internet o con cualquier error, no hace nada."""
    try:
        web = WebSync.sync(log=print)
        print("[web-update]", web)
        _notify_update(window, web)
    except Exception:
        traceback.print_exc()


def _background_tasks(window):
    threading.Thread(target=_background_update, args=(window,), daemon=True).start()
    _background_sync(window)


class Api:

    def get_app_version(self):
        return {
            "web_version": WebSync.current_version(),
            "updater_enabled": WebSync.enabled(),
        }

    def check_for_updates(self):
        return WebSync.sync(log=print)

    def list_prerenders(self, sprite_type=None):
        results = []
        base = get_prerenders_dir()
        if sprite_type:
            type_keys = [sprite_type]
        else:
            try:
                type_keys = sorted(os.listdir(base))
            except Exception:
                type_keys = []
        for type_key in type_keys:
            safe = re.sub(r'[\\/:*?"<>|]+', "_", (type_key or "color").strip()) or "color"
            folder = os.path.join(base, safe)
            if not os.path.isdir(folder):
                continue
            try:
                filenames = sorted(os.listdir(folder))
            except Exception:
                continue
            for filename in filenames:
                fpath = os.path.join(folder, filename)
                if not os.path.isfile(fpath):
                    continue
                mime = _PRERENDER_MIME_BY_EXT.get(os.path.splitext(filename)[1].lower())
                if not mime:
                    continue
                try:
                    with open(fpath, "rb") as f:
                        raw = f.read()
                except Exception:
                    continue
                b64 = base64.b64encode(raw).decode("ascii")
                results.append({
                    "filename": filename,
                    "spriteType": type_key,
                    "dataUrl": f"data:{mime};base64,{b64}",
                })
        return results

    def save_prerender(self, data_url, filename, sprite_type):
        m = re.match(r'^data:([^;]+);base64,(.*)$', data_url or "", re.S)
        if not m:
            raise ValueError("data_url invalida")
        raw = base64.b64decode(m.group(2))
        safe_name = re.sub(r'[\\/:*?"<>|]+', "", (filename or "sprite").strip())
        safe_name = safe_name.rstrip(". ") or "sprite"
        folder = _prerenders_type_dir(sprite_type)
        stem, ext = os.path.splitext(safe_name)
        candidate = safe_name
        i = 1
        while os.path.exists(os.path.join(folder, candidate)):
            candidate = f"{stem} ({i}){ext}"
            i += 1
        with open(os.path.join(folder, candidate), "wb") as f:
            f.write(raw)
        return {"filename": candidate, "spriteType": sprite_type}

    def delete_prerender(self, sprite_type, filename):
        folder = _prerenders_type_dir(sprite_type)
        safe_name = os.path.basename(filename or "")
        fpath = os.path.join(folder, safe_name)
        try:
            if os.path.isfile(fpath):
                os.remove(fpath)
                return True
        except Exception:
            pass
        return False

    def list_custom_sprite_types(self):
        results = []
        folder = get_sprite_types_dir()
        try:
            filenames = sorted(f for f in os.listdir(folder) if f.lower().endswith(".xml"))
        except Exception as e:
            return results
        for filename in filenames:
            entry = {"filename": filename, "name": os.path.splitext(filename)[0]}
            try:
                with open(os.path.join(folder, filename), "r", encoding="utf-8", errors="replace") as f:
                    entry["xml"] = f.read()
            except Exception as e:
                entry["error"] = str(e)
            results.append(entry)
        return results

    def save_sprite_type_xml(self, xml_text, name):
        safe = re.sub(r'[\\/:*?"<>|]+', "", (name or "").strip())
        safe = safe.rstrip(". ")
        if not safe:
            safe = "SpriteType"
        filename = safe if safe.lower().endswith(".xml") else safe + ".xml"
        folder = get_sprite_types_dir()
        path = os.path.join(folder, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(xml_text)
        return {"filename": filename, "path": path}

    def open_sprite_types_folder(self):
        path = get_sprite_types_dir()
        try:
            if IS_WIN:
                os.startfile(path)
            elif IS_MAC:
                subprocess.run(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception:
            pass
        return path

    def get_brawlhalla_status(self):
        import AppConfig
        import AppCodeInstaller as inj

        saved = AppConfig.get_saved_brawlhalla_path()
        if saved is not None:
            return {"path": str(saved), "source": "saved"}

        auto = inj.find_brawlhalla_dir()
        if auto is not None:
            return {"path": str(auto), "source": "auto"}

        return {"path": None, "source": "none"}

    def _validate_and_save_brawlhalla_path(self, raw_path):
        import AppConfig

        if not raw_path:
            return {"success": False, "message": "No indicaste ninguna carpeta."}
        path = Path(raw_path)
        if not path.is_dir():
            return {"success": False, "message": f"'{raw_path}' no es una carpeta valida."}
        swf = path / "UI_MainMenu.swf"
        if not swf.exists():
            return {
                "success": False,
                "message": (
                    f"No encontre UI_MainMenu.swf dentro de '{raw_path}'. "
                    "Elegi la carpeta donde esta instalado Brawlhalla "
                    "(la que tiene BrawlhallaAir.exe adentro)."
                ),
            }
        AppConfig.set_brawlhalla_path(path)
        return {"success": True, "message": "Carpeta de Brawlhalla guardada.", "path": str(path)}

    def browse_brawlhalla_folder(self):
        try:
            result = webview.windows[0].create_file_dialog(webview.FOLDER_DIALOG)
        except Exception as e:
            return {"success": False, "message": f"No pude abrir el selector de carpetas: {e}"}
        if not result:
            return {"success": False, "message": "cancelled"}
        return self._validate_and_save_brawlhalla_path(result[0])

    def set_brawlhalla_folder(self, raw_path):
        return self._validate_and_save_brawlhalla_path(raw_path)

    def clear_brawlhalla_folder(self):
        import AppConfig
        AppConfig.clear_brawlhalla_path()
        return self.get_brawlhalla_status()

    def install_scheme(self, xml_text, scheme_name, pushbyte_num,
                        do_inject=True, ffdec_path=None, swf_path=None,
                        profile=None):
        dump_path = get_dump_path()
        base_dir, resolved_swf = _resolve_profile(profile, swf_path)
        return AllInOne.install_scheme_and_inject(
            xml_text=xml_text,
            scheme_name=scheme_name,
            pushbyte_num=pushbyte_num,
            base_dir=base_dir,
            dump_path=dump_path if os.path.exists(dump_path) else None,
            log=print,
            do_inject=do_inject,
            ffdec_path=ffdec_path,
            swf_path=resolved_swf,
        )

    def get_old_color_names(self):
        return AllInOne.OLD_COLOR_NAMES

    def get_pushbyte_options(self):
        return AllInOne.get_pushbyte_options()

    def get_dev_mode_status(self):
        try:
            return AllInOne.is_dev_mode_unlocked()
        except AttributeError:
            return True

    def unlock_dev_mode(self, code):
        try:
            return AllInOne.unlock_dev_mode(code)
        except AttributeError:
            return {"success": True, "message": "Esta build ya tiene todos los colores disponibles."}

    def get_team_slot_options(self):
        if not TEAM_COLORS_SUPPORTED:
            return []
        return AllInOne.get_team_slot_options()

    def install_team_scheme(self, xml_text, scheme_name, team_slot,
                             do_inject=True, ffdec_path=None, swf_path=None,
                             profile=None):
        if not TEAM_COLORS_SUPPORTED:
            return {
                "success": False,
                "message": "Team colors no está disponible en esta build.",
                "output_path": None,
                "injected": False,
            }
        base_dir, resolved_swf = _resolve_profile(profile, swf_path)
        return AllInOne.install_team_scheme_and_inject(
            xml_text=xml_text,
            scheme_name=scheme_name,
            team_slot=team_slot,
            base_dir=base_dir,
            log=print,
            do_inject=do_inject,
            ffdec_path=ffdec_path,
            swf_path=resolved_swf,
        )

    def list_installed_schemes(self, profile=None):
        base_dir, _ = _resolve_profile(profile)
        return AllInOne.list_installed_schemes(base_dir)

    def list_installed_team_schemes(self, profile=None):
        if not TEAM_COLORS_SUPPORTED:
            return []
        base_dir, _ = _resolve_profile(profile)
        return AllInOne.list_installed_team_schemes(base_dir)

    def uninstall_scheme(self, scheme_name, do_inject=True, ffdec_path=None,
                          swf_path=None, profile=None):
        dump_path = get_dump_path()
        base_dir, resolved_swf = _resolve_profile(profile, swf_path)
        return AllInOne.uninstall_scheme(
            scheme_name=scheme_name,
            base_dir=base_dir,
            dump_path=dump_path if os.path.exists(dump_path) else None,
            log=print,
            do_inject=do_inject,
            ffdec_path=ffdec_path,
            swf_path=resolved_swf,
        )

    def uninstall_team_scheme(self, team_slot, do_inject=True, ffdec_path=None,
                               swf_path=None, profile=None):
        if not TEAM_COLORS_SUPPORTED:
            return {
                "success": False,
                "message": "Team colors no está disponible en esta build.",
            }
        base_dir, resolved_swf = _resolve_profile(profile, swf_path)
        return AllInOne.uninstall_team_scheme(
            team_slot=team_slot,
            base_dir=base_dir,
            log=print,
            do_inject=do_inject,
            ffdec_path=ffdec_path,
            swf_path=resolved_swf,
        )

    def reset_all_schemes(self, ffdec_path=None, swf_path=None, profile=None):
        if profile == "gamebanana":
            gb_dir = get_gamebanana_dir()
            gb_swf = get_gamebanana_swf_path()
            store_path = os.path.join(gb_dir, "installed_schemes.json")
            team_store_path = os.path.join(gb_dir, "installed_team_schemes.json")
            try:
                if os.path.exists(gb_swf):
                    os.remove(gb_swf)
                if os.path.exists(store_path):
                    os.remove(store_path)
                if os.path.exists(team_store_path):
                    os.remove(team_store_path)
                pcode_path = os.path.join(gb_dir, "export", "MultiColorSwap.pcode")
                if os.path.exists(pcode_path):
                    os.remove(pcode_path)
                team_pcode_path = os.path.join(gb_dir, "export", "TeamColorSwap.pcode")
                if os.path.exists(team_pcode_path):
                    os.remove(team_pcode_path)
                return {
                    "success": True,
                    "message": "Build de GameBanana reseteado. La proxima vez que instales un color se crea de nuevo, limpio.",
                }
            except Exception as e:
                return {"success": False, "message": f"Fallo el reseteo del build de GameBanana: {e}"}

        return AllInOne.reset_all_schemes(
            base_dir=get_data_dir(),
            ffdec_path=ffdec_path,
            swf_path=swf_path,
            log=print,
        )

    def update_color_values(self, brawlhalla_air_swf_path=None, ffdec_path=None,
                             swf_path=None, profile=None):
        if profile == "gamebanana":
            return self._update_color_values_gamebanana(
                brawlhalla_air_swf_path=brawlhalla_air_swf_path,
                ffdec_path=ffdec_path,
                swf_path=swf_path,
            )

        import AppRelinker as relinker
        base_dir, resolved_swf = _resolve_profile(profile, swf_path)
        return relinker.update_color_values(
            brawlhalla_air_swf_path=brawlhalla_air_swf_path,
            mainmenu_swf_path=resolved_swf,
            allinone_path=AllInOne.__file__,
            ffdec_path=ffdec_path,
            base_dir=base_dir,
            log=_tee_log,
        )

    def _update_color_values_gamebanana(self, brawlhalla_air_swf_path=None,
                                         ffdec_path=None, swf_path=None):
        import AppRelinker as relinker
        upd = relinker.upd

        def log(msg):
            print(msg)
            upd.log(msg)

        try:
            log("--- GameBanana: identificadores nuevos (BrawlhallaAir.swf) ---")
            air_path = brawlhalla_air_swf_path or relinker.upd._default_swf_path()
            new_cls, new_vec, new_arr, new_team = relinker.find_new_identifiers(air_path)
            log(f'Nuevos identificadores -> Class="{new_cls}" Vector="{new_vec}" Array="{new_arr}"')
            log(f'Nuevos identificadores de team colors -> {new_team}')
            relinker.upd.write_identifiers_to_allinone(
                new_cls, new_vec, new_arr, AllInOne.__file__, log=log
            )
            relinker.upd.write_team_identifiers_to_allinone(
                new_team, AllInOne.__file__, log=log
            )
        except SystemExit as e:
            upd.log(f"SystemExit code={e.code}")
            return {
                "success": False,
                "message": (
                    "No se pudieron extraer los identificadores nuevos desde "
                    f"BrawlhallaAir.swf. Revisa el log en: {upd.LOGFILE}"
                ),
            }
        except Exception as e:
            upd.log_exc("Fallo actualizando identificadores")
            return {"success": False, "message": f"Fallo actualizando identificadores: {e}. Log: {upd.LOGFILE}"}

        log("--- GameBanana: regenerando el swf aislado desde el juego real ---")
        gb_swf = get_gamebanana_swf_path()
        try:
            if os.path.exists(gb_swf):
                os.remove(gb_swf)
            gb_backup = gb_swf + ".bak"
            if os.path.exists(gb_backup):
                os.remove(gb_backup)
            fresh_swf = _ensure_gamebanana_swf(swf_path)
        except Exception as e:
            return {
                "success": False,
                "message": (
                    "Identificadores actualizados, pero no pude regenerar el "
                    f"swf de GameBanana: {e}"
                ),
            }

        log("--- GameBanana: reinyectando los colores ya guardados ---")
        try:
            result = AllInOne.reinject_installed(
                base_dir=get_gamebanana_dir(),
                log=log,
                ffdec_path=ffdec_path,
                swf_path=str(fresh_swf),
            )
        except Exception as e:
            return {
                "success": False,
                "message": (
                    "Identificadores actualizados y swf de GameBanana regenerado, "
                    f"pero fallo la reinyeccion de los colores guardados: {e}"
                ),
            }
        prefix = "Identificadores actualizados y build de GameBanana regenerado desde cero. "
        if result.get("success"):
            result["message"] = prefix + result["message"]
        return result

    def open_gamebanana_build_folder(self):
        path = get_gamebanana_dir()
        try:
            if IS_WIN:
                os.startfile(path)
            elif IS_MAC:
                subprocess.run(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception:
            pass
        return path

    def bulk_export_shapes_to_swf(self, shapes, ffdec_path=None):
        import tempfile
        import AppCodeInstaller as inj

        MAX_CMDLINE_CHARS = 7500 if IS_WIN else 100000

        if not shapes:
            return {"success": False, "message": "No hay shapes seleccionadas para exportar."}

        try:
            result = webview.windows[0].create_file_dialog(
                webview.OPEN_DIALOG,
                file_types=("Archivos SWF (*.swf)", "Todos los archivos (*.*)"),
            )
        except Exception as e:
            return {"success": False, "message": f"No pude abrir el selector de archivos: {e}"}
        if not result:
            return {"success": False, "message": "cancelled"}

        target_swf = Path(result[0])
        if not target_swf.is_file():
            return {"success": False, "message": f"'{target_swf}' no es un archivo valido."}

        try:
            resolved_ffdec = inj.find_ffdec(ffdec_path)
        except inj.InjectError as e:
            return {"success": False, "message": str(e)}

        total = len(shapes)

        def _report_progress(done):
            try:
                webview.windows[0].evaluate_js(
                    f"window.updateBulkExportProgress && window.updateBulkExportProgress({done}, {total})"
                )
            except Exception:
                pass

        try:
            with tempfile.TemporaryDirectory() as tmp:
                tmp_dir = Path(tmp)

                pairs = []
                skipped = 0
                for i, shape in enumerate(shapes):
                    char_id = shape.get("characterId")
                    svg_text = shape.get("svg")
                    if char_id is None or not svg_text:
                        skipped += 1
                        continue
                    svg_path = tmp_dir / f"shape_{i}.svg"
                    svg_path.write_text(svg_text, encoding="utf-8")
                    pairs.append((str(char_id), str(svg_path)))

                valid_count = len(pairs)
                if valid_count == 0:
                    return {"success": False, "message": "No hay shapes validas para exportar."}

                final_tmp = tmp_dir / "final_result.swf"
                base_len = len(resolved_ffdec) + len("-replace") + len(str(target_swf)) + len(str(final_tmp)) + 40
                chunks = []
                current = []
                current_len = base_len
                for char_id, svg_path in pairs:
                    pair_len = len(char_id) + len(svg_path) + 2
                    if current and current_len + pair_len > MAX_CMDLINE_CHARS:
                        chunks.append(current)
                        current = []
                        current_len = base_len
                    current.append((char_id, svg_path))
                    current_len += pair_len
                if current:
                    chunks.append(current)

                current_in = target_swf
                done = 0
                for idx, chunk in enumerate(chunks):
                    is_last = idx == len(chunks) - 1
                    step_out = final_tmp if is_last else tmp_dir / f"step_{idx}.swf"

                    args = ["-replace", str(current_in), str(step_out)]
                    for char_id, svg_path in chunk:
                        args += [char_id, svg_path]

                    step_result = inj.run_ffdec(resolved_ffdec, args)
                    if step_result.returncode != 0 or not step_out.exists():
                        return {
                            "success": False,
                            "message": (
                                f"FFDec no pudo reemplazar la tanda {idx + 1}/{len(chunks)} "
                                "(revisa la consola para el detalle). El .swf original no fue tocado."
                            ),
                        }

                    current_in = step_out
                    done += len(chunk)
                    _report_progress(done)

                backup_path = target_swf.with_suffix(target_swf.suffix + ".bak")
                if not backup_path.exists():
                    shutil.copy2(target_swf, backup_path)

                shutil.move(str(final_tmp), str(target_swf))
        except Exception as e:
            return {"success": False, "message": f"Fallo el export a SWF: {e}"}

        message = f'{valid_count}/{total} shape(s) reemplazadas en "{target_swf.name}"'
        if len(chunks) > 1:
            message += f" ({len(chunks)} tandas de FFDec)"
        if skipped:
            message += f" ({skipped} omitidas por datos incompletos)"
        return {"success": True, "message": message, "path": str(target_swf)}


def main():
    try:
        import AppUpdater as _u
        _u.log(f"=== AppLauncher iniciado (frozen={getattr(sys, 'frozen', False)}) log={_u.LOGFILE} ===")
    except Exception as _e:
        print(f"[log] no pude inicializar update.log: {_e}")
    AllInOne.configure_paths(get_data_dir())
    try:
        WebSync.seed()
    except Exception:
        traceback.print_exc()
    _seed_bundled_prerenders()
    _seed_bundled_sprite_types()

    html_path = resource_path("index.html")

    if not os.path.exists(html_path):
        print(f"No se encontró el archivo: {html_path}")
        sys.exit(1)

    if not IS_WIN and not IS_MAC:
        # PyQt6 aborta el proceso entero si un slot/callback lanza una excepcion sin
        # manejar (cookies raras, permisos, etc.). Se registra el error y la app sigue viva.
        def _qt_safe_excepthook(exc_type, exc, tb):
            _tee_log("[!] Excepcion no manejada (ignorada):\n"
                     + "".join(traceback.format_exception(exc_type, exc, tb)))
        sys.excepthook = _qt_safe_excepthook
        if os.path.exists("/run/.containerenv"):
            # Dentro de distrobox Chromium no puede usar su sandbox ni la GPU.
            os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox --disable-gpu")

    webview.settings['ALLOW_DOWNLOADS'] = True

    api = Api()

    window = webview.create_window(
        title="Azu Modification — Brawlhalla Colour Scheme Editor",
        url=html_path,
        js_api=api,
        width=1280,
        height=800,
        resizable=True,
        min_size=(900, 600),
        maximized=True,
    )
    webview.start(
        func=_background_tasks,
        args=(window,),
        debug=False,
        private_mode=False,
        storage_path=get_storage_path(),
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        details = traceback.format_exc()
        _show_fatal_error(
            "Azu Modification — Error",
            "El programa encontró un error y tuvo que cerrarse.\n\n" + details,
        )
        sys.exit(1)

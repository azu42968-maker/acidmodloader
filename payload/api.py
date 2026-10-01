import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import webview

import adblock
import installer
import mod_registry
import updater
from appdirs import get_appdata_dir
from config import load_config, save_config

ALLOWED_HOSTS = {
    "acidorg.com", "www.acidorg.com",
    "gamebanana.com", "www.gamebanana.com",
}

NAV_ALLOWED_HOSTS = {
    "acidorg.com", "www.acidorg.com",
    "gamebanana.com", "www.gamebanana.com",
}

_FILENAME_FROM_CONTENT_DISPOSITION = re.compile(
    r"""filename\*?=(?:UTF-8'')?"?([^";]+)"?""", re.IGNORECASE
)


def _bundled_vendor_dir() -> Path:
    # Empaquetado: el .exe descomprime vendor/ en sys._MEIPASS.
    # Desde código fuente: payload/api.py -> vendor/ está un nivel arriba.
    base = getattr(sys, "_MEIPASS", None)
    root = Path(base) if base else Path(__file__).resolve().parent.parent
    return root / "vendor"


def _persistent_vendor_dir() -> Path:
    bundled = _bundled_vendor_dir()
    if not getattr(sys, "frozen", False):
        return bundled

    dest = get_appdata_dir() / "vendor"
    marker = dest / ".copied"
    if marker.is_file():
        return dest
    if bundled.is_dir():
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copytree(bundled, dest, dirs_exist_ok=True)
        marker.write_text("ok", encoding="utf-8")
    return dest


_VENDOR_DIR = _persistent_vendor_dir()

DEFAULT_FFDEC_JAR = _VENDOR_DIR / "ffdec_lib.jar"

DEFAULT_JAVA_HOME = _VENDOR_DIR / "jre"

STEAM_CANDIDATES = [
    r"C:\Program Files (x86)\Steam\steamapps\common\Brawlhalla",
    r"C:\Steam\steamapps\common\Brawlhalla",
    r"C:\SteamLibrary\steamapps\common\Brawlhalla",
    r"D:\Program Files (x86)\Steam\steamapps\common\Brawlhalla",
    r"D:\SteamLibrary\steamapps\common\Brawlhalla",
    r"E:\SteamLibrary\steamapps\common\Brawlhalla",
    r"F:\SteamLibrary\steamapps\common\Brawlhalla",
]


def autodetect_brawlhalla_folder() -> str | None:
    for candidate in STEAM_CANDIDATES:
        if Path(candidate).is_dir():
            return candidate
    return None


def _fetch(url: str, timeout: int = 25) -> tuple[bytes, str, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "AcidModLoader/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(), resp.geturl(), resp.headers.get("Content-Disposition", "")


def _resolve_filename(original_url: str, final_url: str, content_disposition: str) -> str:
    match = _FILENAME_FROM_CONTENT_DISPOSITION.search(content_disposition or "")
    if match:
        candidate = urllib.parse.unquote(match.group(1).strip())
        name = Path(candidate).name
        if name and Path(name).suffix:
            return name

    for candidate_url in (final_url, original_url):
        name = Path(urllib.parse.urlparse(candidate_url).path).name
        if name and Path(name).suffix:
            return name

    return Path(urllib.parse.urlparse(original_url).path).name or "download"


class Api:

    def __init__(self):
        self.cfg = load_config()
        if not self.cfg.get("brawlhalla_path"):
            detected = autodetect_brawlhalla_folder()
            if detected:
                self.cfg["brawlhalla_path"] = detected
                save_config(self.cfg)

    def get_brawlhalla_path(self) -> str:
        return self.cfg.get("brawlhalla_path") or ""

    def _resolve_ffdec_jar_path(self) -> str | None:
        configured = self.cfg.get("ffdec_jar_path")
        if configured and Path(configured).is_file():
            return configured
        if DEFAULT_FFDEC_JAR.is_file():
            return str(DEFAULT_FFDEC_JAR)
        return None

    def _resolve_java_home(self) -> str | None:
        configured = self.cfg.get("java_home")
        if configured and Path(configured).is_dir():
            return configured
        if DEFAULT_JAVA_HOME.is_dir():
            return str(DEFAULT_JAVA_HOME)
        return None

    def pick_brawlhalla_folder(self) -> str:
        result = webview.windows[0].create_file_dialog(webview.FOLDER_DIALOG)
        if result:
            path = result[0]
            self.cfg["brawlhalla_path"] = path
            save_config(self.cfg)
        return self.get_brawlhalla_path()

    def navigate(self, url: str) -> bool:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https") or parsed.hostname not in NAV_ALLOWED_HOSTS:
            return False
        webview.windows[0].load_url(url)
        return True

    def install_mod(self, url: str, title: str | None = None) -> dict:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return {"ok": False, "log": ["[X] Invalid mod URL."]}
        if parsed.hostname not in ALLOWED_HOSTS:
            return {"ok": False, "log": [f"[X] Refusing to fetch from an untrusted host: {parsed.hostname}"]}

        brawlhalla_path = self.cfg.get("brawlhalla_path")
        if not brawlhalla_path or not Path(brawlhalla_path).is_dir():
            return {
                "ok": False,
                "log": ["[X] No valid Brawlhalla folder is set. Use the folder button first."],
            }

        log_lines: list[str] = []

        def log(msg: str) -> None:
            log_lines.append(msg)

        log(f"[i] Downloading: {url}")
        try:
            data, final_url, content_disposition = _fetch(url)
        except urllib.error.HTTPError as e:
            log(f"[X] Server returned an error ({e.code}) for this mod.")
            return {"ok": False, "log": log_lines}
        except urllib.error.URLError:
            log(f"[X] Couldn't reach {parsed.hostname} — check your internet connection.")
            return {"ok": False, "log": log_lines}
        except TimeoutError:
            log("[X] Download timed out — check your internet connection and try again.")
            return {"ok": False, "log": log_lines}

        name = _resolve_filename(url, final_url, content_disposition)
        ext = Path(name).suffix.lower()

        previous = mod_registry.find_by_source(url)
        if previous:
            log("[i] This mod was already installed - replacing the previous install.")
            if not mod_registry.uninstall(previous["id"], log):
                log("[!] Couldn't fully undo the previous install; continuing anyway.")
            log("")

        display_name = " ".join((title or "").split())[:120] or Path(name).stem
        tracker = mod_registry.begin(Path(brawlhalla_path))
        failed = True
        try:
            try:
                if ext == ".zip":
                    installer.install_zip_mod(
                        data, Path(brawlhalla_path), log,
                        ffdec_jar_path=self._resolve_ffdec_jar_path(),
                        java_home=self._resolve_java_home(),
                    )
                elif ext == ".swf":
                    installer.install_loose_swf(data, name, Path(brawlhalla_path), log)
                elif ext == ".bmod":
                    with tempfile.NamedTemporaryFile(suffix=".bmod", delete=False) as tmp:
                        tmp.write(data)
                        tmp_bmod_path = Path(tmp.name)
                    try:
                        installer.install_bmod(
                            data, tmp_bmod_path, Path(brawlhalla_path), log,
                            ffdec_jar_path=self._resolve_ffdec_jar_path(),
                            java_home=self._resolve_java_home(),
                        )
                    finally:
                        tmp_bmod_path.unlink(missing_ok=True)
                else:
                    log(f"[X] Unsupported mod file type: {ext}")
                    return {"ok": False, "log": log_lines}
                failed = False
            except installer.InstallError as e:
                log(f"[X] {e}")
                return {"ok": False, "log": log_lines}
            except Exception as e:
                log(f"[X] Unexpected error: {e}")
                return {"ok": False, "log": log_lines}
        finally:
            mod_registry.end()
            try:
                mod_registry.commit(tracker, display_name, url, name, partial=failed)
            except Exception as e:
                log(f"[!] Couldn't save this install to the installed-mods list: {e}")

        return {"ok": True, "log": log_lines}

    def list_installed_mods(self) -> list[dict]:
        return mod_registry.list_mods()

    def uninstall_mod(self, mod_id: str) -> dict:
        log_lines: list[str] = []
        try:
            ok = mod_registry.uninstall(str(mod_id), log_lines.append)
        except Exception as e:
            log_lines.append(f"[X] Unexpected error: {e}")
            ok = False
        return {"ok": ok, "log": log_lines}

    def uninstall_all_mods(self) -> dict:
        log_lines: list[str] = []
        try:
            removed, failed = mod_registry.uninstall_all(log_lines.append)
        except Exception as e:
            log_lines.append(f"[X] Unexpected error: {e}")
            return {"ok": False, "log": log_lines}
        log_lines.append(f"Uninstalled: {removed}   Failed: {failed}")
        return {"ok": failed == 0, "log": log_lines}

    # ---- Actualizaciones del payload (ver updater.py) ----
    def get_app_version(self) -> str:
        return updater.current_version()

    def check_update(self) -> dict:
        return updater.check()

    def apply_update(self) -> dict:
        return updater.apply()

    def restart_app(self) -> None:
        updater.restart()

    # ---- Bloqueador de anuncios (ver adblock.py) ----
    def get_adblock(self) -> bool:
        return bool(self.cfg.get("adblock", True))

    def set_adblock(self, enabled: bool) -> bool:
        self.cfg["adblock"] = bool(enabled)
        save_config(self.cfg)
        adblock.set_enabled(webview.windows[0], bool(enabled))
        return self.get_adblock()

    def adblock_stats(self) -> dict:
        return adblock.stats()

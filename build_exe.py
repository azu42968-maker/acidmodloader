from __future__ import annotations

import io
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import traceback
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
VENDOR = ROOT / "vendor"
JRE_DIR = VENDOR / "jre"
FFDEC_JAR = VENDOR / "ffdec_lib.jar"
DIST_DIR = ROOT / "dist"
ICON_FILE = ROOT / "icon.ico"
PAYLOAD = ROOT / "payload"

TARGET_PYTHON = (3, 12)
BUILD_VENV = ROOT / ".build-venv"

LOCAL_PY312_DIR = ROOT / ".build-python312"
_PYTHON_312_VERSIONS_TO_TRY = ["3.12.10", "3.12.8", "3.12.6"]

_HEADERS = {"User-Agent": "AcidModLoaderBuildScript/1.0"}


def _get(url: str, timeout: int) -> bytes:
    with urlopen(Request(url, headers=_HEADERS), timeout=timeout) as resp:
        return resp.read()

ADOPTIUM_API = (
    "https://api.adoptium.net/v3/assets/latest/17/hotspot"
    "?image_type=jre&os={os}&architecture={arch}&vendor=eclipse"
)


def _adoptium_os_arch() -> tuple[str, str]:
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "windows":
        os_name = "windows"
    elif system == "darwin":
        os_name = "mac"
    elif system == "linux":
        os_name = "linux"
    else:
        raise SystemExit(f"[X] Unsupported OS for this build script: {system}")

    if machine in ("amd64", "x86_64"):
        arch = "x64"
    elif machine in ("arm64", "aarch64"):
        arch = "aarch64"
    else:
        raise SystemExit(f"[X] Unsupported architecture: {machine}")

    return os_name, arch


def _venv_python(venv_dir: Path) -> Path:
    return venv_dir / ("Scripts/python.exe" if platform.system() == "Windows" else "bin/python")


def _venv_has_target_python(venv_dir: Path) -> bool:
    python_exe = _venv_python(venv_dir)
    if not python_exe.is_file():
        return False
    try:
        result = subprocess.run(
            [str(python_exe), "-c", "import sys; print(tuple(sys.version_info[:2]))"],
            capture_output=True, text=True, timeout=15,
        )
        return result.returncode == 0 and result.stdout.strip() == str(TARGET_PYTHON)
    except (OSError, subprocess.SubprocessError):
        return False


def _download_and_install_python312() -> Path:
    python_exe = LOCAL_PY312_DIR / "python.exe"
    if python_exe.is_file():
        return python_exe

    last_error: Exception | None = None
    for version in _PYTHON_312_VERSIONS_TO_TRY:
        url = f"https://www.python.org/ftp/python/{version}/python-{version}-amd64.exe"
        print(f"[i] Python 3.12 wasn't found on this machine - downloading {version}...")
        try:
            installer_bytes = _get(url, timeout=180)
        except Exception as e:
            last_error = e
            print(f"[!] Couldn't fetch Python {version} ({e}) - trying another version...")
            continue

        with tempfile.TemporaryDirectory() as tmp:
            installer_path = Path(tmp) / f"python-{version}-amd64.exe"
            installer_path.write_bytes(installer_bytes)
            LOCAL_PY312_DIR.mkdir(parents=True, exist_ok=True)
            print(f"[i] Installing Python {version} into {LOCAL_PY312_DIR} (just for this build - per-user, no PATH changes)...")
            try:
                subprocess.run(
                    [
                        str(installer_path), "/quiet",
                        "InstallAllUsers=0", "PrependPath=0", "Include_launcher=0",
                        "Include_test=0", "Include_doc=0", "Include_tcltk=0",
                        f"TargetDir={LOCAL_PY312_DIR}",
                    ],
                    check=True,
                )
            except subprocess.CalledProcessError as e:
                last_error = e
                print(f"[!] Silent install of Python {version} failed ({e}) - trying another version...")
                continue

        if python_exe.is_file():
            print(f"[i] Python {version} installed at {LOCAL_PY312_DIR}")
            return python_exe
        last_error = RuntimeError(f"Installer for {version} ran but {python_exe} wasn't created.")

    raise SystemExit(
        f"[X] Couldn't automatically install Python {TARGET_PYTHON[0]}.{TARGET_PYTHON[1]}: "
        f"{last_error}\nYou can install it yourself from "
        f"https://www.python.org/downloads/release/python-{TARGET_PYTHON[0]}{TARGET_PYTHON[1]}0/ "
        "and re-run this script."
    )


def _find_target_python_interpreter() -> list[str]:
    version_str = f"{TARGET_PYTHON[0]}.{TARGET_PYTHON[1]}"

    if platform.system() == "Windows":
        py_launcher = shutil.which("py")
        if py_launcher:
            probe = subprocess.run(
                [py_launcher, f"-{version_str}", "-c", "print('ok')"],
                capture_output=True, text=True,
            )
            if probe.returncode == 0:
                return [py_launcher, f"-{version_str}"]

        local_python = LOCAL_PY312_DIR / "python.exe"
        if not local_python.is_file():
            local_python = _download_and_install_python312()
        return [str(local_python)]

    candidate = shutil.which(f"python{version_str}")
    if candidate:
        return [candidate]
    raise SystemExit(
        f"[X] Python {version_str} isn't installed, and this script can only "
        "auto-install it on Windows. Install Python 3.12 for your OS from "
        f"https://www.python.org/downloads/release/python-{TARGET_PYTHON[0]}{TARGET_PYTHON[1]}0/ "
        "and re-run this script."
    )


def _venv_is_usable(venv_dir: Path) -> bool:
    python_exe = _venv_python(venv_dir)
    if not python_exe.is_file():
        return False
    try:
        result = subprocess.run(
            [str(python_exe), "-c", "import PyInstaller, webview, jpype"],
            capture_output=True, timeout=60,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _ensure_target_python() -> None:
    # Ya estamos corriendo dentro del entorno de build.
    if os.environ.get("_ACID_BUILD_VENV_ACTIVE") == "1":
        return

    if not _venv_is_usable(BUILD_VENV):
        if "--py312" in sys.argv:
            # Opcional: forzar Python 3.12 (lo descarga si hace falta).
            interpreter_prefix = _find_target_python_interpreter()
        else:
            interpreter_prefix = [sys.executable]  # usa el Python con el que lo abriste

        print(
            f"[i] Creating a build environment at {BUILD_VENV} with "
            f"Python {sys.version_info.major}.{sys.version_info.minor} (first run only)..."
        )
        if BUILD_VENV.exists():
            shutil.rmtree(BUILD_VENV)
        subprocess.run([*interpreter_prefix, "-m", "venv", str(BUILD_VENV)], check=True)

        venv_python = str(_venv_python(BUILD_VENV))
        print("[i] Installing pyinstaller + requirements.txt into it...")
        subprocess.run([venv_python, "-m", "pip", "install", "--upgrade", "pip"], check=True)
        subprocess.run(
            [venv_python, "-m", "pip", "install", "pyinstaller", "-r", str(ROOT / "requirements.txt")],
            check=True,
        )

    print(f"[i] Re-launching this script under {BUILD_VENV} ...")
    env = os.environ.copy()
    env["_ACID_BUILD_VENV_ACTIVE"] = "1"
    result = subprocess.run(
        [str(_venv_python(BUILD_VENV)), str(Path(__file__).resolve()), *sys.argv[1:]],
        env=env,
    )
    raise SystemExit(result.returncode)


def _extracted_home(extracted: Path) -> Path:
    mac_home = extracted / "Contents" / "Home"
    return mac_home if mac_home.is_dir() else extracted


def _download_jre() -> None:
    if JRE_DIR.is_dir() and any(JRE_DIR.iterdir()):
        print(f"[i] {JRE_DIR} already exists, skipping download.")
        return

    os_name, arch = _adoptium_os_arch()
    print(f"[i] Looking up latest Temurin 17 JRE for {os_name}/{arch}...")

    with urlopen(Request(ADOPTIUM_API.format(os=os_name, arch=arch), headers=_HEADERS), timeout=30) as resp:
        assets = json.load(resp)
    if not assets:
        raise SystemExit("[X] Adoptium returned no matching JRE build.")

    package = assets[0]["binary"]["package"]
    download_url = package["link"]
    print(f"[i] Downloading {package['name']} ...")

    archive_bytes = _get(download_url, timeout=180)

    print("[i] Extracting...")
    VENDOR.mkdir(parents=True, exist_ok=True)
    if download_url.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as zf:
            top = zf.namelist()[0].split("/")[0]
            zf.extractall(VENDOR)
    else:
        with tarfile.open(fileobj=io.BytesIO(archive_bytes)) as tf:
            top = tf.getnames()[0].split("/")[0]
            tf.extractall(VENDOR)

    extracted = VENDOR / top
    home = _extracted_home(extracted)

    if JRE_DIR.exists():
        shutil.rmtree(JRE_DIR)
    shutil.move(str(home), str(JRE_DIR))
    shutil.rmtree(extracted, ignore_errors=True)
    print(f"[i] JRE ready at {JRE_DIR}")


def _check_ffdec_jar() -> None:
    if not FFDEC_JAR.is_file():
        raise SystemExit(
            f"[X] {FFDEC_JAR} is missing. Grab a FFDec release "
            "(github.com/jindrapetrik/jpexs-decompiler/releases) and copy ffdec_lib.jar "
            "PLUS its whole lib/dependencies folder into vendor/ - see README - then "
            "re-run this script."
        )
    print(f"[i] Found {FFDEC_JAR}")
    dep_jars = [p for p in FFDEC_JAR.parent.rglob("*.jar") if p != FFDEC_JAR]
    if not dep_jars:
        print(
            "[!] No other .jar files found next to ffdec_lib.jar - FFDec needs its "
            "dependency jars (tomlj, jsyntaxpane, commons-io, ...) too, or the "
            "packaged exe will fail with NoClassDefFoundError. See README."
        )


def _check_icon() -> None:
    if not ICON_FILE.is_file():
        print(
            f"[!] {ICON_FILE} not found - building without a custom icon "
            "(the exe will get PyInstaller's default icon). Drop an "
            "icon.ico next to build_exe.py to fix that."
        )


def _check_payload() -> None:
    if not (PAYLOAD / "app_main.py").is_file() or not (PAYLOAD / "version.json").is_file():
        raise SystemExit(
            "[X] Falta payload/app_main.py o payload/version.json. "
            "Corre primero: python build_payload.py <version>"
        )
    version = json.loads((PAYLOAD / "version.json").read_text(encoding="utf-8"))["version"]
    print(f"[i] Payload empaquetado: v{version}")


def _payload_imports() -> list[str]:
    """
    El launcher no importa nada del payload, asi que PyInstaller no lo veria.
    Escaneamos payload/*.py y pasamos cada import externo como --hidden-import
    (incluye stdlib: si no, modulos como zlib/zipfile podrian faltar en el .exe).
    """
    import ast

    local = {p.stem for p in PAYLOAD.glob("*.py")}
    found: set[str] = set()
    for py in PAYLOAD.glob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            else:
                continue
            for name in names:
                if name.split(".")[0] not in local | {"System", "Microsoft"}:  # .NET, no son modulos Python
                    found.add(name)
    return sorted(found)


def _clear_old_dist() -> None:
    targets = [DIST_DIR / "AcidModLoader.exe", DIST_DIR / "AcidModLoader"]
    for target in targets:
        if not target.exists():
            continue
        for attempt in range(3):
            try:
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
                break
            except PermissionError:
                if attempt == 2:
                    raise SystemExit(
                        f"[X] Couldn't remove {target} - it's still open. Close any "
                        "running AcidModLoader.exe (check Task Manager), close any "
                        "Explorer window on it, and re-run this script."
                    )
                time.sleep(1)


def _run_pyinstaller() -> None:
    try:
        import PyInstaller
    except ImportError:
        raise SystemExit("[X] PyInstaller isn't installed - run: pip install pyinstaller")

    _clear_old_dist()

    print("[i] Running PyInstaller in --onefile mode (this bundles the ~45+ MB JRE "
          "INTO the exe itself, give it a minute)...")
    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--windowed", "--onefile", "--name", "AcidModLoader",
        "--add-data", f"{VENDOR}{os.pathsep}vendor",
        "--add-data", f"{PAYLOAD}{os.pathsep}payload",
    ]
    for module in _payload_imports():
        args += ["--hidden-import", module]
    if ICON_FILE.is_file():
        args += ["--icon", str(ICON_FILE)]
    args.append(str(ROOT / "launcher.py"))
    subprocess.run(args, check=True)
    print(
        "[i] Done - a single dist/AcidModLoader.exe is all you need to hand out. "
        "No Java install needed on the target machine. First launch each time will "
        "be a bit slower than --onedir was, since the exe has to unpack the JRE to "
        "a temp folder every time it starts."
    )


_LAUNCHER_BAT_CONTENT = (
    "@echo off\r\n"
    "setlocal\r\n"
    "\r\n"
    "rem --- Microsoft Visual C++ Runtime - needed for python312.dll itself to load ---\r\n"
    "reg query \"HKLM\\SOFTWARE\\Microsoft\\VisualStudio\\14.0\\VC\\Runtimes\\X64\" /v Installed >nul 2>&1\r\n"
    "if %errorlevel% neq 0 (\r\n"
    "    echo Installing a required system component (1/2), please wait...\r\n"
    "    set \"VC_EXE=%TEMP%\\vc_redist.x64.exe\"\r\n"
    "    powershell -NoProfile -Command \"try { Invoke-WebRequest -Uri 'https://aka.ms/vs/17/release/vc_redist.x64.exe' -OutFile '%VC_EXE%' -UseBasicParsing } catch { exit 1 }\"\r\n"
    "    if exist \"%VC_EXE%\" (\r\n"
    "        \"%VC_EXE%\" /install /quiet /norestart\r\n"
    "        del \"%VC_EXE%\"\r\n"
    "    ) else (\r\n"
    "        echo Could not download the required component automatically.\r\n"
    "        echo Please install it manually from: https://aka.ms/vs/17/release/vc_redist.x64.exe\r\n"
    "        pause\r\n"
    "    )\r\n"
    ")\r\n"
    "\r\n"
    "rem --- Microsoft Edge WebView2 Runtime - needed for the app's window to open ---\r\n"
    "set \"WV2_KEY=HKLM\\SOFTWARE\\WOW6432Node\\Microsoft\\EdgeUpdate\\Clients\\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}\"\r\n"
    "reg query \"%WV2_KEY%\" /v pv >nul 2>&1\r\n"
    "if %errorlevel% neq 0 (\r\n"
    "    reg query \"HKCU\\SOFTWARE\\Microsoft\\EdgeUpdate\\Clients\\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}\" /v pv >nul 2>&1\r\n"
    ")\r\n"
    "if %errorlevel% neq 0 (\r\n"
    "    echo Installing a required system component (2/2), please wait...\r\n"
    "    set \"WV2_EXE=%TEMP%\\MicrosoftEdgeWebview2Setup.exe\"\r\n"
    "    powershell -NoProfile -Command \"try { Invoke-WebRequest -Uri 'https://go.microsoft.com/fwlink/p/?LinkId=2124703' -OutFile '%WV2_EXE%' -UseBasicParsing } catch { exit 1 }\"\r\n"
    "    if exist \"%WV2_EXE%\" (\r\n"
    "        \"%WV2_EXE%\" /silent /install\r\n"
    "        del \"%WV2_EXE%\"\r\n"
    "    ) else (\r\n"
    "        echo Could not download the required component automatically.\r\n"
    "        echo Please install it manually from: https://developer.microsoft.com/microsoft-edge/webview2/\r\n"
    "        pause\r\n"
    "    )\r\n"
    ")\r\n"
    "\r\n"
    "start \"\" \"%~dp0AcidModLoader.exe\"\r\n"
    "endlocal\r\n"
)
_LAUNCHER_BAT_NAME = "Run AcidModLoader.bat"


def _write_launcher_bat() -> None:
    launcher_path = DIST_DIR / _LAUNCHER_BAT_NAME
    launcher_path.write_text(_LAUNCHER_BAT_CONTENT, encoding="utf-8")
    print(
        f"[i] Wrote {launcher_path} next to AcidModLoader.exe. If you want the "
        "smoothest experience for someone who's never run anything Python/WebView2 "
        "before, zip BOTH files together and send that - the .bat silently installs "
        "the Microsoft Visual C++ Runtime and the Microsoft Edge WebView2 Runtime "
        "the first time either is needed (harmless if already present) before "
        "starting AcidModLoader.exe. That said, since this is now a single onefile "
        ".exe, sending just AcidModLoader.exe by itself also works fine for anyone "
        "who already has those two runtimes (most Windows 10/11 PCs do) - they'll "
        "just get one of the two DLL-loading errors from the README if they don't, "
        "instead of the automatic fix."
    )


def main() -> None:
    os.chdir(ROOT)
    _ensure_target_python()
    _download_jre()
    _check_ffdec_jar()
    _check_icon()
    _check_payload()
    _run_pyinstaller()
    _write_launcher_bat()


def _opened_by_double_click() -> bool:
    """True si Windows abrio una consola nueva solo para este script (doble clic)."""
    if platform.system() != "Windows" or "--no-pause" in sys.argv:
        return False
    if os.environ.get("_ACID_BUILD_VENV_ACTIVE") == "1":
        return False  # el proceso hijo nunca pausa; pausa el padre
    if any(k in os.environ for k in ("PROMPT", "WT_SESSION", "TERM_PROGRAM")):
        return False  # ya estaba en una terminal abierta
    try:
        import ctypes
        pids = (ctypes.c_uint * 4)()
        return ctypes.windll.kernel32.GetConsoleProcessList(pids, 4) <= 2
    except Exception:
        return True


if __name__ == "__main__":
    exit_code = 0
    try:
        main()
    except SystemExit as e:
        if isinstance(e.code, int):
            exit_code = e.code
        elif e.code:
            print(e.code, file=sys.stderr)
            exit_code = 1
    except BaseException:
        traceback.print_exc()
        exit_code = 1

    if _opened_by_double_click():
        print()
        print("[OK] Build terminado." if exit_code == 0 else f"[X] El build fallo (codigo {exit_code}). Revisa el mensaje de arriba.")
        input("Presiona Enter para cerrar...")
    sys.exit(exit_code)

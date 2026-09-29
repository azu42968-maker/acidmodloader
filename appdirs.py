from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "AcidModLoader"


def get_appdata_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Local"
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        base = os.environ.get("XDG_DATA_HOME")
        root = Path(base) if base else Path.home() / ".local" / "share"

    app_dir = root / APP_NAME
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir

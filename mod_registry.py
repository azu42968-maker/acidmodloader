from __future__ import annotations

import json
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from appdirs import get_appdata_dir

REGISTRY_PATH = get_appdata_dir() / "installed_mods.json"
BACKUPS_DIR = get_appdata_dir() / "backups"

_lock = threading.RLock()
_local = threading.local()


def _load() -> dict:
    if REGISTRY_PATH.exists():
        try:
            data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("mods"), list):
                return data
        except (OSError, json.JSONDecodeError):
            try:
                REGISTRY_PATH.replace(REGISTRY_PATH.with_suffix(".json.corrupt"))
            except OSError:
                pass
    return {"mods": []}


def _save(data: dict) -> None:
    tmp = REGISTRY_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(REGISTRY_PATH)


class Tracker:

    def __init__(self, root: Path):
        self.root = root
        self.mod_id = uuid.uuid4().hex[:12]
        self.files: dict[str, str | None] = {}
        self.created_dirs: list[str] = []

    def _rel(self, path: Path) -> str | None:
        try:
            return path.resolve().relative_to(self.root.resolve()).as_posix()
        except (ValueError, OSError):
            return None

    def before_write(self, dest: Path) -> None:
        rel = self._rel(dest)
        if rel is None or rel in self.files:
            return

        missing = []
        p = dest.parent
        while not p.exists() and p != p.parent:
            missing.append(p)
            p = p.parent
        for d in reversed(missing):
            d_rel = self._rel(d)
            if d_rel and d_rel not in self.created_dirs:
                self.created_dirs.append(d_rel)

        if dest.is_file():
            backup = BACKUPS_DIR / self.mod_id / rel
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dest, backup)
            self.files[rel] = f"{self.mod_id}/{rel}"
        else:
            self.files[rel] = None


def begin(root: Path) -> Tracker:
    tracker = Tracker(root)
    _local.tracker = tracker
    return tracker


def end() -> None:
    _local.tracker = None


def before_overwrite(dest: Path) -> None:
    tracker = getattr(_local, "tracker", None)
    if tracker is not None:
        tracker.before_write(dest)


def write_bytes(dest: Path, data: bytes) -> None:
    before_overwrite(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)


def commit(tracker: Tracker, name: str, source_url: str, filename: str, partial: bool = False) -> dict | None:
    if not tracker.files:
        shutil.rmtree(BACKUPS_DIR / tracker.mod_id, ignore_errors=True)
        return None
    record = {
        "id": tracker.mod_id,
        "name": name,
        "filename": filename,
        "source": source_url,
        "installed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "root": str(tracker.root),
        "partial": partial,
        "created_dirs": tracker.created_dirs,
        "files": [{"rel": rel, "backup": bk} for rel, bk in tracker.files.items()],
    }
    with _lock:
        data = _load()
        data["mods"].append(record)
        _save(data)
    return record


def list_mods() -> list[dict]:
    with _lock:
        mods = _load()["mods"]
    return [
        {
            "id": m["id"],
            "name": m.get("name") or m.get("filename") or "(unnamed)",
            "filename": m.get("filename", ""),
            "source": m.get("source", ""),
            "installed_at": m.get("installed_at", ""),
            "file_count": len(m.get("files", [])),
            "partial": bool(m.get("partial")),
        }
        for m in reversed(mods)
    ]


def find_by_source(url: str) -> dict | None:
    with _lock:
        for m in _load()["mods"]:
            if m.get("source") == url:
                return m
    return None


def _remove_empty_dirs(root: Path, rels: list[str]) -> None:
    for rel in sorted(rels, key=lambda r: r.count("/"), reverse=True):
        d = root / rel
        try:
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()
        except OSError:
            pass


def uninstall(mod_id: str, log) -> bool:
    with _lock:
        data = _load()
        mods = data["mods"]
        idx = next((i for i, m in enumerate(mods) if m["id"] == mod_id), None)
        if idx is None:
            log("[X] That mod isn't in the installed list.")
            return False

        mod = mods[idx]
        later = mods[idx + 1:]
        root = Path(mod["root"])
        log(f"[i] Uninstalling: {mod.get('name')}")

        if not root.is_dir():
            log(f"[X] The Brawlhalla folder this mod was installed into no longer exists: {root}")
            return False

        failed: list[dict] = []
        kept_backups: set[str] = set()

        for f in mod["files"]:
            rel, backup = f["rel"], f.get("backup")
            dest = root / rel

            successor = None
            for m in later:
                successor = next((sf for sf in m["files"] if sf["rel"] == rel), None)
                if successor:
                    break
            if successor is not None:
                old = successor.get("backup")
                if old:
                    (BACKUPS_DIR / old).unlink(missing_ok=True)
                successor["backup"] = backup
                if backup:
                    kept_backups.add(backup)
                log(f"   OK {rel}  (kept: a newer mod also changes it)")
                continue

            try:
                if backup:
                    src = BACKUPS_DIR / backup
                    if not src.is_file():
                        log(f"   [!] {rel}: backup is missing, can't restore it. "
                            "Use Steam > Verify integrity of game files to get the original back.")
                        continue
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dest)
                    log(f"   OK {rel}  (restored)")
                else:
                    dest.unlink(missing_ok=True)
                    log(f"   OK {rel}  (removed)")
            except OSError as e:
                log(f"   [X] {rel}: {e}")
                failed.append(f)

        keep = kept_backups | {f["backup"] for f in failed if f.get("backup")}
        for f in mod["files"]:
            b = f.get("backup")
            if b and b not in keep:
                (BACKUPS_DIR / b).unlink(missing_ok=True)

        if failed:
            mod["files"] = failed
            _save(data)
            log(f"[X] {len(failed)} file(s) couldn't be restored - close Brawlhalla and try again.")
            return False

        _remove_empty_dirs(root, mod.get("created_dirs", []))
        mods.pop(idx)
        _save(data)

        mod_dir = BACKUPS_DIR / mod_id
        if mod_dir.is_dir():
            for d in sorted((p for p in mod_dir.rglob("*") if p.is_dir()),
                            key=lambda p: len(p.parts), reverse=True):
                try:
                    d.rmdir()
                except OSError:
                    pass
            try:
                mod_dir.rmdir()
            except OSError:
                pass

        log("[i] Done.")
        return True


def uninstall_all(log) -> tuple[int, int]:
    ids = [m["id"] for m in list_mods()]
    removed = failed = 0
    for mod_id in ids:
        if uninstall(mod_id, log):
            removed += 1
        else:
            failed += 1
        log("")
    return removed, failed

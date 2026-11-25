"""PARKER's first skill: opening apps and folders by name.

Safety rules:
- PARKER only opens things the owner could already open with a click: Start
  Menu shortcuts, a few built-in Windows tools, the standard user folders,
  and entries the owner adds with /app add.
- "open ..." requests are recognised in code, never by the model, and nothing
  the model writes is ever run as a command.
- Opening goes through the operating system's normal "open" action
  (os.startfile on Windows), the same as double-clicking.
"""

from __future__ import annotations

import difflib
import os
import re
import sqlite3
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from backend.memory import DB_PATH

# Built into Windows; opened by name like the Run box does.
BUILT_IN = {
    "Notepad": "notepad.exe",
    "Calculator": "calc.exe",
    "Paint": "mspaint.exe",
    "File Explorer": "explorer.exe",
    "Task Manager": "taskmgr.exe",
    "Settings": "ms-settings:",
    "Snipping Tool": "ms-screenclip:",
}
# Spoken nicknames -> the name to look for.
NICKNAMES = {
    "vs code": "Visual Studio Code", "vscode": "Visual Studio Code", "code": "Visual Studio Code",
    "chrome": "Google Chrome", "edge": "Microsoft Edge", "word": "Word", "excel": "Excel",
    "powerpoint": "PowerPoint", "explorer": "File Explorer", "files": "File Explorer",
    "calc": "Calculator", "terminal": "Terminal", "whatsapp": "WhatsApp",
}
FOLDERS = ["Documents", "Downloads", "Desktop", "Pictures", "Music", "Videos"]
_SKIP = re.compile(
    r"uninstall|readme|release notes|\bhelp\b|\bdocs?\b|documentation|manual|license|website", re.I
)
_SHORTCUT_TYPES = {".lnk", ".url", ".appref-ms"}

# "open chrome", "please launch VS Code", "can you start Spotify for me"
_OPEN = re.compile(
    r"^(?:(?:hey|ok|okay)[\s,]+)?(?:parker[\s,]+)?(?:(?:can|could|would|will)\s+you\s+)?"
    r"(?:please\s+)?(?:open|launch|start|run|bring\s+up)\s+(?:up\s+)?(?P<name>.+?)"
    r"(?:\s+(?:for\s+me|please|now))*[\s.!?]*$",
    re.IGNORECASE,
)
_ARTICLES = re.compile(r"^(?:the|my|a|an)\s+", re.IGNORECASE)


class AppError(Exception):
    pass


@dataclass(frozen=True)
class AppEntry:
    name: str
    target: str
    source: str  # "start menu", "built-in", "folder" or "added"


def parse_open_request(message: str) -> str | None:
    """Return the thing to open in "open X" messages, else None."""
    m = _OPEN.match(message.strip())
    if not m:
        return None
    name = _ARTICLES.sub("", m.group("name").strip())
    name = re.sub(r"\s+(?:app|application|folder|program)$", "", name, flags=re.IGNORECASE)
    return name.strip(" .") or None


def start_menu_dirs() -> list[Path]:
    dirs = []
    for env in ("APPDATA", "PROGRAMDATA"):
        base = os.environ.get(env)
        if base:
            dirs.append(Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    return dirs


def scan_shortcuts(dirs: Iterable[Path]) -> list[AppEntry]:
    found: dict[str, AppEntry] = {}
    for folder in dirs:
        if not folder.is_dir():
            continue
        for path in folder.rglob("*"):
            if path.suffix.lower() in _SHORTCUT_TYPES and not _SKIP.search(path.stem):
                found.setdefault(path.stem.lower(), AppEntry(path.stem, str(path), "start menu"))
    return list(found.values())


def user_folders(home: Path | None = None) -> list[AppEntry]:
    home = home or Path.home()
    entries = []
    for name in FOLDERS:
        # Windows often moves these into OneDrive.
        for candidate in (home / name, home / "OneDrive" / name):
            if candidate.is_dir():
                entries.append(AppEntry(name, str(candidate), "folder"))
                break
    return entries


def default_launcher(target: str) -> None:
    if sys.platform != "win32":
        raise AppError("Opening apps is only set up for Windows so far.")
    os.startfile(target)  # noqa: S606 — the same as double-clicking it


class AppLauncher:
    """Finds apps by (spoken) name and opens them."""

    def __init__(
        self,
        db_path: Path | str = DB_PATH,
        *,
        shortcut_dirs: Iterable[Path] | None = None,
        home: Path | None = None,
        built_in: dict[str, str] | None = None,
        launch: Callable[[str], None] = default_launcher,
    ) -> None:
        if str(db_path) != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(db_path), check_same_thread=False)
        self._lock = threading.RLock()
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS apps (name TEXT PRIMARY KEY COLLATE NOCASE, target TEXT NOT NULL)"
        )
        self._db.commit()
        self._launch = launch
        self._shortcut_dirs = list(start_menu_dirs() if shortcut_dirs is None else shortcut_dirs)
        self._home = home
        self._built_in = BUILT_IN if built_in is None else built_in
        self.refresh()

    def refresh(self) -> None:
        """Re-read the Start Menu (e.g. after installing something)."""
        entries = [AppEntry(n, t, "built-in") for n, t in self._built_in.items()]
        entries += user_folders(self._home)
        entries += scan_shortcuts(self._shortcut_dirs)
        self._found = entries

    # ---- the owner's own entries ------------------------------------------
    def added(self) -> list[AppEntry]:
        with self._lock:
            rows = self._db.execute("SELECT name, target FROM apps ORDER BY name").fetchall()
        return [AppEntry(n, t, "added") for n, t in rows]

    def add(self, name: str, target: str) -> AppEntry:
        name, target = " ".join(name.split()), target.strip().strip('"')
        if not name or not target:
            raise AppError("Usage: /app add <name> = <path or web address>")
        is_link = re.match(r"^(https?://|ms-settings:|mailto:)", target, re.IGNORECASE)
        if not is_link and not Path(target).expanduser().exists():
            raise AppError(f"I can't find '{target}'. Check the path, or use a full web address.")
        if not is_link:
            target = str(Path(target).expanduser())
        with self._lock:
            self._db.execute(
                "INSERT INTO apps (name, target) VALUES (?, ?) "
                "ON CONFLICT(name) DO UPDATE SET target = excluded.target",
                (name, target),
            )
            self._db.commit()
        return AppEntry(name, target, "added")

    def remove(self, name: str) -> bool:
        with self._lock:
            cur = self._db.execute("DELETE FROM apps WHERE name = ?", (name.strip(),))
            self._db.commit()
        return cur.rowcount == 1

    # ---- finding and opening ----------------------------------------------
    def entries(self) -> list[AppEntry]:
        return self.added() + self._found  # the owner's entries win

    def find(self, spoken: str) -> AppEntry | None:
        spoken = spoken.lower().strip()
        entries = self.entries()
        by_name = {e.name.lower(): e for e in reversed(entries)}  # first entry wins
        if spoken in by_name:  # an exact name, including ones the owner added
            return by_name[spoken]
        wanted = NICKNAMES.get(spoken, spoken).lower()
        if wanted in by_name:
            return by_name[wanted]
        # "chrome" -> "Google Chrome": every spoken word appears in the name.
        words = wanted.split()
        contains = [e for e in entries if all(w in e.name.lower().split() for w in words)]
        if contains:
            return min(contains, key=lambda e: len(e.name))
        close = difflib.get_close_matches(wanted, list(by_name), n=1, cutoff=0.8)
        return by_name[close[0]] if close else None

    def open(self, spoken: str) -> AppEntry:
        entry = self.find(spoken)
        if entry is None:
            raise AppError(
                f"I couldn't find an app or folder called '{spoken}'. "
                f"You can add it with: /app add {spoken} = <path>"
            )
        try:
            self._launch(entry.target)
        except AppError:
            raise
        except OSError as err:
            raise AppError(f"Windows couldn't open {entry.name}: {err}") from err
        return entry

    def close(self) -> None:
        self._db.close()

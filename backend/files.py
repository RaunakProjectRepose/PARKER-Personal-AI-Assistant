"""Finding files by name: "find my AIML303 notes", "where is my resume?".

Privacy and safety:
- Only the owner's own folders are searched (Documents, Downloads, Desktop,
  Pictures, Music, Videos, including OneDrive ones, plus any folders listed in
  PARKER_SEARCH_FOLDERS). Hidden folders, program folders, .git, node_modules
  and virtual environments are skipped.
- Only file NAMES are matched; file contents are never read.
- Requests are recognised in code; the model never touches files.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

from backend.apps import FOLDERS, AppError, default_launcher

MAX_RESULTS = 8
TIME_BUDGET_S = 4.0  # never search for longer than this
MAX_ENTRIES = 300_000

_SKIP_DIRS = {
    "appdata", "node_modules", "__pycache__", "site-packages", ".venv", "venv", "env",
    "$recycle.bin", "system volume information", "windows", "program files",
    "program files (x86)", "programdata", "build", "dist", "target", ".git", ".idea",
    ".vscode", "library", "cache", "caches",
}
_STOP = {
    "my", "the", "a", "an", "file", "files", "called", "named", "for", "me", "of", "please",
    "some", "that", "this", "is", "are", "where", "did", "i", "save", "saved", "put", "about",
    "on", "in", "with", "latest", "recent", "newest", "last", "find", "all", "any",
    "from", "to", "and", "at", "by", "it", "them",
}
_TYPES = {
    ".pdf": {"pdf", "pdfs"},
    ".pptx .ppt .key .odp": {"slides", "slide", "presentation", "presentations", "ppt", "pptx", "deck"},
    ".xlsx .xls .csv .ods": {"spreadsheet", "spreadsheets", "excel", "xlsx", "csv", "sheet", "sheets"},
    ".docx .doc .odt .rtf": {"docx", "word"},
    ".png .jpg .jpeg .gif .webp .heic .bmp": {"photo", "photos", "picture", "pictures", "image", "images", "screenshot", "screenshots"},
    ".mp4 .mkv .mov .avi .webm": {"video", "videos", "recording", "recordings"},
    ".mp3 .wav .m4a .flac .ogg": {"song", "songs", "audio", "music"},
    ".py .ipynb .cpp .c .h .cs .java .js .ts": {"code", "script", "notebook", "notebooks"},
}

_FIND = re.compile(
    r"^(?:(?:hey|ok|okay)[\s,]+)?(?:parker[\s,]+)?(?:(?:can|could|would|will)\s+you\s+)?(?:please\s+)?"
    r"(?:"
    r"(?:find|locate|look\s+for|search\s+for|get)\s+(?P<a>(?:my|the)\s+.+)"
    r"|search\s+(?:my\s+)?(?:files|computer|laptop|pc|documents)\s+for\s+(?P<b>.+)"
    r"|find\s+(?P<c>.+?)\s+(?:on|in)\s+my\s+(?:files|computer|laptop|pc)"
    r"|find\s+(?:a\s+|the\s+)?files?\s+(?:called|named)\s+(?P<d>.+)"
    r"|where(?:'s|\s+is|\s+are)\s+(?P<e>my\s+.+)"
    r"|where\s+did\s+i\s+(?:save|put|keep)\s+(?P<f>.+)"
    r")$",
    re.IGNORECASE,
)
_ORDINALS = {"first": 0, "1st": 0, "second": 1, "2nd": 1, "third": 2, "3rd": 2, "fourth": 3,
             "4th": 3, "fifth": 4, "5th": 4, "sixth": 5, "seventh": 6, "eighth": 7, "last": -1}
_PICK = re.compile(
    r"^(?:(?:please|can\s+you|could\s+you)\s+)?(?P<verb>open|show(?:\s+me)?)\s+"
    r"(?:(?:the\s+)?(?P<ord>first|second|third|fourth|fifth|sixth|seventh|eighth|last|1st|2nd|3rd|4th|5th)"
    r"(?:\s+one|\s+file)?|(?:number|no\.?|#)?\s*(?P<num>[1-8])|(?P<it>it|that(?:\s+one)?|this(?:\s+one)?))"
    r"(?P<folder>\s+in\s+(?:the\s+)?(?:folder|explorer|file\s+explorer))?[\s.!?]*(?:please)?[\s.!?]*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class FoundFile:
    path: Path
    folder: str  # where it is, readable: "Documents/University"
    modified: datetime
    score: float

    @property
    def name(self) -> str:
        return self.path.name


def parse_find_request(message: str) -> str | None:
    """The thing to look for in "find my X" messages, else None."""
    m = _FIND.match(message.strip().rstrip("?.! "))
    if not m:
        return None
    query = next(g for g in m.groups() if g)
    return query.strip() or None


def parse_pick(message: str) -> tuple[int, bool] | None:
    """"open the second one" -> (1, False); "show it in the folder" -> (0, True)."""
    m = _PICK.match(message.strip())
    if not m:
        return None
    if m.group("ord"):
        index = _ORDINALS[m.group("ord").lower()]
    elif m.group("num"):
        index = int(m.group("num")) - 1
    else:
        index = 0
    reveal = bool(m.group("folder"))  # "show me the second one" just opens it
    return index, reveal


def _compact(text: str) -> str:
    return re.sub(r"[\W_]+", "", text.lower())


def plan_query(query: str) -> tuple[list[str], set[str], bool]:
    """Split a request into name words, wanted extensions and "newest first"."""
    words = re.findall(r"[\w.+#-]+", query.lower())
    newest = any(w in ("latest", "recent", "newest", "last") for w in words)
    extensions: set[str] = set()
    tokens = []
    for word in words:
        matched_type = False
        for exts, names in _TYPES.items():
            if word in names:
                extensions.update(exts.split())
                matched_type = word not in ("screenshot", "screenshots", "notebook", "notebooks", "recording", "recordings")
        if word in _STOP or (matched_type and word not in ("screenshot", "screenshots")):
            continue
        tokens.append(word.strip(".-"))
    return [t for t in tokens if t], extensions, newest


def search_roots(home: Path | None = None, extra: Iterable[str] | None = None) -> list[Path]:
    home = home or Path.home()
    roots = []
    for name in FOLDERS:
        for candidate in (home / name, home / "OneDrive" / name):
            if candidate.is_dir():
                roots.append(candidate)
    if extra is None:
        extra = [p for p in os.environ.get("PARKER_SEARCH_FOLDERS", "").split(os.pathsep) if p]
    roots += [Path(p).expanduser() for p in extra if Path(p).expanduser().is_dir()]
    # Drop roots inside other roots so nothing is searched twice.
    unique: list[Path] = []
    for root in sorted({r.resolve() for r in roots}, key=lambda p: len(p.parts)):
        if not any(root.is_relative_to(u) for u in unique):
            unique.append(root)
    return unique


def default_reveal(path: str) -> None:
    """Show a file selected in File Explorer."""
    if sys.platform != "win32":
        raise AppError("Showing files in a folder is only set up for Windows so far.")
    subprocess.run(["explorer", "/select,", path], check=False)  # fixed program, no shell


class FileFinder:
    def __init__(
        self,
        roots: Iterable[Path] | None = None,
        *,
        home: Path | None = None,
        launch: Callable[[str], None] = default_launcher,
        reveal: Callable[[str], None] = default_reveal,
        time_budget: float = TIME_BUDGET_S,
        max_entries: int = MAX_ENTRIES,
    ) -> None:
        self.home = home or Path.home()
        self.roots = list(search_roots(self.home) if roots is None else roots)
        self._launch = launch
        self._reveal = reveal
        self.time_budget = time_budget
        self.max_entries = max_entries
        self.last_search_complete = True

    def describe_roots(self) -> str:
        names = []
        for root in self.roots:
            try:
                names.append(str(root.relative_to(self.home)).replace("\\", "/"))
            except ValueError:
                names.append(str(root))
        return ", ".join(names) or "no folders"

    def _walk(self) -> Iterable[os.DirEntry]:
        started = time.monotonic()
        seen = 0
        self.last_search_complete = True
        stack = list(self.roots)
        while stack:
            folder = stack.pop()
            try:
                with os.scandir(folder) as entries:
                    for entry in entries:
                        seen += 1
                        if seen > self.max_entries or time.monotonic() - started > self.time_budget:
                            self.last_search_complete = False
                            return
                        name = entry.name
                        if name.startswith((".", "~$")):
                            continue
                        try:
                            if entry.is_dir(follow_symlinks=False):
                                if name.lower() not in _SKIP_DIRS:
                                    stack.append(entry.path)
                            elif entry.is_file(follow_symlinks=False):
                                yield entry
                        except OSError:
                            continue
            except (PermissionError, FileNotFoundError, NotADirectoryError, OSError):
                continue

    def _where(self, path: Path) -> str:
        try:
            rel = path.parent.relative_to(self.home)
        except ValueError:
            return str(path.parent)
        parts = [p for p in rel.parts if p.lower() != "onedrive"]
        return "/".join(parts) or "Home"

    def search(self, query: str, limit: int = MAX_RESULTS) -> list[FoundFile]:
        tokens, extensions, newest = plan_query(query)
        if not tokens and not extensions:
            return []
        variants = [(t, t[:-1] if len(t) > 3 and t.endswith("s") else t) for t in tokens]
        allowed_misses = 1 if len(tokens) >= 3 else 0
        found: list[FoundFile] = []
        now = time.time()
        for entry in self._walk():
            path = Path(entry.path)
            if extensions and path.suffix.lower() not in extensions:
                continue
            stem = path.stem.lower()
            stem_compact = _compact(stem)
            folders = " ".join(p.lower() for p in path.parent.parts[-3:])
            score = 0.0
            misses = 0
            for token, singular in variants:
                if re.search(rf"(?<![a-z0-9]){re.escape(token)}", stem) or _compact(token) in stem_compact:
                    score += 3
                elif singular != token and singular in stem:
                    score += 2.5
                elif token in folders or _compact(token) in _compact(folders):
                    score += 1.5
                else:
                    misses += 1
            if misses > allowed_misses:
                continue
            try:
                mtime = entry.stat().st_mtime
            except OSError:
                continue
            age_days = max(0.0, (now - mtime) / 86400)
            recency = 1.0 / (1.0 + age_days / 30)  # 1 today, 0.5 after a month
            score += recency * (4 if newest or not tokens else 1)
            found.append(FoundFile(path, self._where(path), datetime.fromtimestamp(mtime), score))
        found.sort(key=lambda f: (-f.score, -f.modified.timestamp(), f.name.lower()))
        return found[:limit]

    def open(self, found: FoundFile) -> None:
        try:
            self._launch(str(found.path))
        except AppError:
            raise
        except OSError as err:
            raise AppError(f"Windows couldn't open {found.name}: {err}") from err

    def reveal(self, found: FoundFile) -> None:
        self._reveal(str(found.path))


def summary(query: str, results: list[FoundFile], finder: FileFinder) -> str:
    """What PARKER says after a search."""
    if not results:
        note = "" if finder.last_search_complete else " (I stopped early: there are a lot of files)"
        return (f"I couldn't find any files matching \"{query}\" in your "
                f"{finder.describe_roots()}{note}.")
    best = results[0]
    if len(results) == 1:
        return f"I found {best.name} in {best.folder}. Say \"open it\" to open it."
    return (f"I found {len(results)} files. The best match is {best.name} in {best.folder}. "
            "Say \"open the first one\", or pick one from the list.")

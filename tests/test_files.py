"""Tests for finding files by name, with a fake home folder."""

import os
import time
from datetime import datetime

import pytest

from backend.assistant import Assistant
from backend.files import FileFinder, parse_find_request, parse_pick, plan_query, search_roots, summary
from backend.main import FileResults, handle_files, run

DAY = 86400


@pytest.fixture
def home(tmp_path):
    home = tmp_path / "home"
    files = {
        "Documents/University/AIML303/AIML303 Notes Week 3.pdf": 2,
        "Documents/University/AIML303/aiml_303_notes_week1.docx": 40,
        "Documents/University/AIML303/Generative AI slides.pptx": 5,
        "Documents/Resume - Raunak 2026.pdf": 10,
        "Documents/Old Resume.docx": 400,
        "Downloads/hackathon_brief.pdf": 1,
        "Downloads/Screenshot 2026-11-25 181455.png": 0.5,
        "Downloads/Screenshot 2026-11-20 101010.png": 6,
        "OneDrive/Desktop/Budget 2026.xlsx": 3,
        "Pictures/Goa trip/beach.jpg": 90,
        # Never searched:
        "Documents/project/node_modules/aiml303/notes.js": 1,
        "Documents/project/.git/aiml303 notes": 1,
        "Documents/.hidden/aiml303 notes.txt": 1,
        "AppData/Local/aiml303 notes.txt": 1,
        "Documents/~$AIML303 Notes.docx": 1,  # Office lock file
    }
    now = time.time()
    for rel, age_days in files.items():
        path = home / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x")
        os.utime(path, (now - age_days * DAY, now - age_days * DAY))
    for name in ("Music", "Videos"):
        (home / name).mkdir()
    return home


@pytest.fixture
def finder(home):
    opened, revealed = [], []
    f = FileFinder(home=home, launch=opened.append, reveal=revealed.append)
    f.opened, f.revealed = opened, revealed
    return f


# ---- understanding requests -------------------------------------------------

@pytest.mark.parametrize(
    "message, query",
    [
        ("Find my AIML303 notes", "my AIML303 notes"),
        ("where is my resume?", "my resume"),
        ("Search my files for hackathon", "hackathon"),
        ("Can you find the slides for Generative AI", "the slides for Generative AI"),
        ("Where did I save the project report", "the project report"),
        ("find hackathon on my laptop", "hackathon"),
        ("Find a file called budget", "budget"),
    ],
)
def test_find_requests(message, query):
    assert parse_find_request(message) == query


@pytest.mark.parametrize("message", ["where is Paris?", "find a good restaurant", "find out what time it is", "open chrome"])
def test_not_find_requests(message):
    assert parse_find_request(message) is None


@pytest.mark.parametrize(
    "message, pick",
    [
        ("open the first one", (0, False)),
        ("open number 2", (1, False)),
        ("open it", (0, False)),
        ("open the 3rd file", (2, False)),
        ("show it in the folder", (0, True)),
        ("open the last one", (-1, False)),
        ("show me the second one", (1, False)),
    ],
)
def test_picks(message, pick):
    assert parse_pick(message) == pick


def test_query_planning():
    assert plan_query("my PDFs about Python") == (["python"], {".pdf"}, False)
    tokens, exts, newest = plan_query("my latest screenshot")
    assert tokens == ["screenshot"] and ".png" in exts and newest


# ---- searching ----------------------------------------------------------------

def names(results):
    return [r.name for r in results]


def test_only_the_owners_folders_are_searched(finder, home):
    roots = {p.name for p in finder.roots}
    assert roots == {"Documents", "Downloads", "Desktop", "Pictures", "Music", "Videos"}
    # Only check below the home folder: on Windows pytest's own temporary
    # folders live under AppData, so the full path may contain it.
    home = home.resolve()
    assert all("AppData" not in p.relative_to(home).parts for p in finder.roots)


def test_aiml303_notes_matches_different_spellings_and_skips_junk(finder):
    found = names(finder.search("my AIML303 notes"))
    assert found[:2] == ["AIML303 Notes Week 3.pdf", "aiml_303_notes_week1.docx"]  # newest first among equals
    assert "notes.js" not in found and "aiml303 notes.txt" not in found
    assert "~$AIML303 Notes.docx" not in found


def test_resume_prefers_the_recent_one(finder):
    assert names(finder.search("my resume"))[:2] == ["Resume - Raunak 2026.pdf", "Old Resume.docx"]


def test_type_words_filter_results(finder):
    assert names(finder.search("the slides for Generative AI")) == ["Generative AI slides.pptx"]
    assert names(finder.search("my AIML303 notes pdf")) == ["AIML303 Notes Week 3.pdf"]


def test_latest_screenshot(finder):
    assert names(finder.search("my latest screenshot"))[0] == "Screenshot 2026-11-25 181455.png"


def test_folder_names_count_too(finder):
    assert names(finder.search("my Goa photos")) == ["beach.jpg"]


def test_onedrive_files_are_found_and_described_nicely(finder):
    result = finder.search("budget")[0]
    assert result.name == "Budget 2026.xlsx" and result.folder == "Desktop"


def test_nothing_found(finder):
    assert finder.search("quantum cookbook") == []
    text = summary("quantum cookbook", [], finder)
    assert text.startswith('I couldn\'t find any files matching "quantum cookbook" in your')


def test_search_stops_at_its_time_budget(home):
    slow = FileFinder(home=home, time_budget=0.0)
    assert slow.search("resume") == []
    assert not slow.last_search_complete
    assert "stopped early" in summary("resume", [], slow)


def test_extra_folders_from_settings(tmp_path, home):
    extra = tmp_path / "Projects"
    extra.mkdir()
    (extra / "parker roadmap.md").write_text("x")
    roots = search_roots(home, extra=[str(extra), str(home / "Documents" / "University")])
    assert extra.resolve() in roots
    assert (home / "Documents" / "University").resolve() not in roots  # already inside Documents


# ---- chat --------------------------------------------------------------------

def test_search_then_open_and_reveal(finder):
    said, printed = [], []
    state = FileResults()
    assert handle_files("Find my AIML303 notes", finder, state, said.append, printed.append)
    assert said[0].startswith("I found 2 files. The best match is AIML303 Notes Week 3.pdf in Documents/University/AIML303.")
    assert printed[0].startswith("  1. AIML303 Notes Week 3.pdf  (Documents/University/AIML303,")
    assert handle_files("open the second one", finder, state, said.append, printed.append)
    assert finder.opened[-1].endswith("aiml_303_notes_week1.docx")
    assert said[-1] == "Opening aiml_303_notes_week1.docx."
    assert handle_files("show it in the folder", finder, state, said.append, printed.append)
    assert finder.revealed[-1].endswith("AIML303 Notes Week 3.pdf")
    assert handle_files("open number 7", finder, state, said.append, printed.append)
    assert printed[-1] == "PARKER: There are only 2 results.\n"


def test_open_it_without_a_search_is_not_handled(finder):
    assert not handle_files("open it", finder, FileResults(), print, print)


def test_terminal_chat_finds_files(finder):
    out, sent = [], []
    inputs = iter(["where is my resume?", "open it", "where is Paris?", "/quit"])
    run(
        Assistant(generate=lambda m, h, **k: sent.append(m) or "In France."),
        input_fn=lambda _p: next(inputs),
        print_fn=lambda *a: out.append(" ".join(map(str, a))),
        finder=finder,
    )
    assert finder.opened[-1].endswith("Resume - Raunak 2026.pdf")
    assert sent == ["where is Paris?"]


def test_model_is_told_it_cannot_search_files():
    from backend import brain

    assert "you cannot see or search their files yourself" in brain.SYSTEM_PROMPT


# ---- desktop app --------------------------------------------------------------

def test_desktop_app_searches_off_thread_and_shows_clickable_results(finder, tmp_path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6.QtWidgets")
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    from frontend.app import MainWindow

    QApplication.instance() or QApplication([])
    sent = []
    window = MainWindow(
        Assistant(generate=lambda m, h, **k: sent.append(m) or "ok", now=lambda: datetime(2026, 11, 26, 10)),
        make_speaker=None, make_listener=None, threaded=False,
        now=lambda: datetime(2026, 11, 26, 10), tray_available=lambda: False, make_hotkey=None,
        settings=QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat),
        finder=finder,
    )
    window.process("Find my AIML303 notes")
    assert sent == []
    kinds = [kind for kind, _ in window.chat.messages]
    assert kinds[-2:] == ["parker", "files"]
    open_button, reveal_button = window.chat.file_buttons[1]
    open_button.click()
    assert finder.opened[-1].endswith("aiml_303_notes_week1.docx")
    reveal_button.click()
    assert finder.revealed[-1].endswith("aiml_303_notes_week1.docx")
    window.process("open the first one")
    assert finder.opened[-1].endswith("AIML303 Notes Week 3.pdf")

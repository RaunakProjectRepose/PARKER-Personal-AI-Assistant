"""Tests for opening apps and folders, with a fake Start Menu and launcher."""

import pytest

from backend.apps import AppError, AppLauncher, parse_open_request
from backend.assistant import Assistant
from backend.main import handle_apps, run


@pytest.fixture
def start_menu(tmp_path):
    menu = tmp_path / "Start Menu" / "Programs"
    for rel in [
        "Visual Studio Code/Visual Studio Code.lnk",
        "Google Chrome.lnk",
        "Microsoft Edge.lnk",
        "Spotify.lnk",
        "Steam/Hollow Knight.url",
        "Visual Studio Code/Uninstall Visual Studio Code.lnk",
        "Python 3.12/Python 3.12 Module Docs.lnk",
        "notes.txt",
    ]:
        path = menu / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x")
    return menu


@pytest.fixture
def home(tmp_path):
    home = tmp_path / "home"
    (home / "Downloads").mkdir(parents=True)
    (home / "OneDrive" / "Documents").mkdir(parents=True)  # moved by OneDrive
    return home


@pytest.fixture
def launcher(start_menu, home):
    opened = []
    apps = AppLauncher(":memory:", shortcut_dirs=[start_menu], home=home,
                       built_in={"Notepad": "notepad.exe", "Calculator": "calc.exe"},
                       launch=opened.append)
    apps.opened = opened
    yield apps
    apps.close()


# ---- understanding "open ..." -----------------------------------------------

@pytest.mark.parametrize(
    "message, name",
    [
        ("open chrome", "chrome"),
        ("Please launch VS Code", "VS Code"),
        ("can you start Spotify for me", "Spotify"),
        ("Open my Documents folder", "Documents"),
        ("Hey Parker, open the calculator app.", "calculator"),
        ("open up notepad please", "notepad"),
        ("Bring up Settings", "Settings"),
    ],
)
def test_open_requests_are_understood(message, name):
    assert parse_open_request(message) == name


@pytest.mark.parametrize("message", ["Open", "opening hours?", "I want to open a shop", "How do I open a PDF?"])
def test_other_messages_are_not_open_requests(message):
    assert parse_open_request(message) is None


# ---- finding apps -------------------------------------------------------------

@pytest.mark.parametrize(
    "spoken, expected",
    [
        ("VS Code", "Visual Studio Code"),
        ("vscode", "Visual Studio Code"),
        ("chrome", "Google Chrome"),
        ("Google Chrome", "Google Chrome"),
        ("spotify", "Spotify"),
        ("hollow knight", "Hollow Knight"),
        ("calculator", "Calculator"),
        ("calc", "Calculator"),
        ("Downloads", "Downloads"),
        ("documents", "Documents"),
        ("Spotfy", "Spotify"),  # small transcription slip
    ],
)
def test_find(launcher, spoken, expected):
    assert launcher.find(spoken).name == expected


def test_uninstallers_docs_and_other_files_are_never_offered(launcher):
    names = {e.name for e in launcher.entries()}
    assert "Uninstall Visual Studio Code" not in names
    assert "Python 3.12 Module Docs" not in names
    assert "notes" not in names


def test_unknown_apps_are_not_guessed(launcher):
    assert launcher.find("photoshop") is None
    assert launcher.find("timer for 5 minutes") is None


def test_open_uses_the_shortcut_path(launcher, start_menu):
    entry = launcher.open("vs code")
    assert launcher.opened == [str(start_menu / "Visual Studio Code" / "Visual Studio Code.lnk")]
    assert entry.source == "start menu"


def test_folders_resolve_to_onedrive_when_moved(launcher, home):
    launcher.open("documents")
    assert launcher.opened == [str(home / "OneDrive" / "Documents")]


def test_open_unknown_explains_how_to_add(launcher):
    with pytest.raises(AppError, match="/app add photoshop"):
        launcher.open("photoshop")


def test_launch_failures_are_explained(start_menu, home):
    def broken(target):
        raise OSError("access denied")

    apps = AppLauncher(":memory:", shortcut_dirs=[start_menu], home=home, built_in={}, launch=broken)
    with pytest.raises(AppError, match="Windows couldn't open Google Chrome: access denied"):
        apps.open("chrome")


# ---- the owner's own entries --------------------------------------------------

def test_added_apps_take_priority_and_persist(tmp_path, start_menu, home):
    db = tmp_path / "parker.db"
    tool = tmp_path / "MyTool.exe"
    tool.write_text("x")
    apps = AppLauncher(db, shortcut_dirs=[start_menu], home=home, built_in={}, launch=lambda t: None)
    apps.add("chrome", str(tool))  # override the Start Menu one
    apps.add("Timetable", "https://example.edu/timetable")
    apps.close()
    again = AppLauncher(db, shortcut_dirs=[start_menu], home=home, built_in={}, launch=lambda t: None)
    assert again.find("chrome").target == str(tool)
    assert again.find("timetable").target == "https://example.edu/timetable"
    assert again.remove("Timetable")
    assert again.find("timetable") is None
    again.close()


@pytest.mark.parametrize("target", ["C:/does/not/exist.exe", ""])
def test_bad_targets_are_rejected(launcher, target):
    with pytest.raises(AppError):
        launcher.add("Thing", target)


# ---- the chat handler -------------------------------------------------------

def run_handler(launcher, message):
    said, printed = [], []
    handled = handle_apps(message, launcher, said.append, printed.append)
    return handled, said, printed


def test_open_request_is_handled_without_the_model(launcher):
    handled, said, _ = run_handler(launcher, "Open VS Code please")
    assert handled and said == ["Opening Visual Studio Code."]


def test_unknown_open_request_goes_to_the_model(launcher):
    handled, said, printed = run_handler(launcher, "open the pod bay doors")
    assert not handled and said == [] and printed == []


def test_app_commands(launcher, tmp_path):
    tool = tmp_path / "tool.exe"
    tool.write_text("x")
    assert run_handler(launcher, f"/app add My Tool = {tool}")[1] == ['Got it. Say "open My Tool" whenever you need it.']
    _, _, printed = run_handler(launcher, "/apps tool")
    assert printed == ["PARKER: I can open: My Tool\n"]
    assert run_handler(launcher, "/app remove My Tool")[1] == ["Removed My Tool."]
    _, _, printed = run_handler(launcher, "/app add Broken")
    assert "Usage" in printed[0]


def test_without_a_launcher(launcher):
    assert handle_apps("open chrome", None, print, print) is False
    printed = []
    assert handle_apps("/apps", None, print, printed.append) is True
    assert "isn't available" in printed[0]


def test_terminal_chat_opens_apps(launcher):
    sent, out = [], []
    inputs = iter(["open chrome", "open the pod bay doors", "/quit"])
    run(
        Assistant(generate=lambda m, h, **k: sent.append(m) or "I can't do that."),
        input_fn=lambda _p: next(inputs),
        print_fn=lambda *a: out.append(" ".join(map(str, a))),
        apps=launcher,
    )
    assert launcher.opened[-1].endswith("Google Chrome.lnk")
    assert "PARKER: Opening Google Chrome.\n" in out
    assert sent == ["open the pod bay doors"]  # only the unknown one reached the model


def test_model_is_told_it_cannot_open_things_itself():
    from backend import brain

    assert "you never open anything yourself" in brain.SYSTEM_PROMPT

"""Tests for the phone companion: pairing, security and the API."""

import io
import json
import socket
import ssl
import time
import wave
from datetime import datetime

import numpy as np
import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from backend.agenda import Agenda  # noqa: E402
from backend.assistant import Assistant  # noqa: E402
from backend.brain import BrainError  # noqa: E402
from backend.companion import (  # noqa: E402
    Companion,
    fingerprint_of,
    load_or_create_identity,
    pairing_payload,
    qr_matrix,
    reset_pairing,
    wav_to_audio,
)
from backend.companion_server import CompanionServer, create_app  # noqa: E402
from backend.google_calendar import GoogleCalendar  # noqa: E402
from backend.memory import Memory  # noqa: E402
from backend.reminders import Reminders  # noqa: E402

NOW = datetime(2026, 11, 26, 14, 0)
TOKEN = "test-token-123"


def wav_bytes(seconds=1.0, rate=48000, channels=2):
    frames = np.zeros(int(rate * seconds) * channels, dtype=np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(frames.tobytes())
    return buf.getvalue()


class FakeService:
    def __init__(self):
        self.inserted = []

    def events(self):
        return self

    def list(self, **kw):
        return self

    def insert(self, calendarId, body):  # noqa: N803
        self.inserted.append(body)
        self._result = {**body}
        return self

    def execute(self):
        return getattr(self, "_result", {"items": []})


@pytest.fixture
def parts():
    service = FakeService()
    calendar = GoogleCalendar(service, clock=lambda: NOW)
    heard = []
    assistant = Assistant(
        generate=lambda m, h, **k: heard.append(m) or f"Reply to: {m}",
        memory=Memory(":memory:"), agenda=Agenda(":memory:"), calendar=calendar, now=lambda: NOW,
    )
    reminders = Reminders(":memory:")
    companion = Companion(
        assistant, reminders=reminders, calendar=calendar,
        transcribe=lambda audio: "What's on today?" if len(audio) else "",
        synthesize=lambda text: b"RIFF....WAVEfake:" + text.encode(),
        now=lambda: NOW,
    )
    client = TestClient(create_app(companion, TOKEN))
    client.headers["Authorization"] = f"Bearer {TOKEN}"
    return client, companion, service, heard, reminders


# ---- pairing and identity -------------------------------------------------------

def test_identity_is_created_once_and_kept(tmp_path):
    first = load_or_create_identity(tmp_path)
    second = load_or_create_identity(tmp_path)
    assert first == second
    assert len(first.token) >= 40 and len(first.fingerprint) == 64
    assert fingerprint_of(first.cert_path) == first.fingerprint


def test_reset_pairing_changes_the_token_but_keeps_the_certificate(tmp_path):
    first = load_or_create_identity(tmp_path)
    second = reset_pairing(tmp_path)
    assert second.token != first.token and second.fingerprint == first.fingerprint


def test_pairing_payload_and_qr(tmp_path):
    identity = load_or_create_identity(tmp_path)
    payload = json.loads(pairing_payload(identity, hosts=["192.168.1.20"]))
    assert payload == {"app": "parker", "v": 1, "hosts": ["192.168.1.20"], "port": 8765,
                       "token": identity.token, "fp": identity.fingerprint, "name": "Raunak"}
    matrix = qr_matrix(pairing_payload(identity, hosts=["192.168.1.20"]))
    assert len(matrix) > 20 and len(matrix) == len(matrix[0])


def test_companion_secrets_are_never_committed():
    import subprocess

    for path in ["memory/companion_token.txt", "memory/companion_key.pem", "memory/companion_cert.pem"]:
        assert subprocess.run(["git", "check-ignore", "-q", path]).returncode == 0


# ---- security -------------------------------------------------------------------

@pytest.mark.parametrize("header", [None, "Bearer wrong", "Bearer ", "Basic dGVzdA=="])
def test_requests_without_the_pairing_token_are_refused(parts, header):
    client = parts[0]
    headers = {} if header is None else {"Authorization": header}
    del client.headers["Authorization"]
    for method, url in [("get", "/api/status"), ("get", "/api/today"), ("post", "/api/message")]:
        r = getattr(client, method)(url, headers=headers, **({"json": {"text": "hi"}} if method == "post" else {}))
        assert r.status_code == 401


def test_no_api_docs_are_exposed(parts):
    client = parts[0]
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


# ---- the API --------------------------------------------------------------------

def test_status(parts):
    assert parts[0].get("/api/status").json() == {
        "app": "parker", "model": "qwen3.5:4b", "owner": "Raunak", "voice_in": True, "voice_out": True}


def test_chat_goes_to_the_same_brain(parts):
    client, _, _, heard, _ = parts
    r = client.post("/api/message", json={"text": "Hello from my phone"})
    assert r.json() == {"messages": [{"kind": "parker", "text": "Reply to: Hello from my phone"}]}
    assert heard == ["Hello from my phone"]


def test_memories_reminders_and_plans_work_from_the_phone(parts):
    client, companion, _, heard, reminders = parts
    r = client.post("/api/message", json={"text": "Remember that my exam is on Friday"}).json()
    assert r["messages"] == [{"kind": "parker", "text": "Noted. I'll remember that: my exam is on Friday"}]
    client.post("/api/message", json={"text": "remind me in 20 minutes to stretch"})
    client.post("/api/message", json={"text": "/plan finish the Android app"})
    today = client.get("/api/today").json()
    assert today["memories"] == ["my exam is on Friday"]
    assert today["reminders"] == [{"text": "stretch", "when": "at 14:20"}]
    assert today["plans"] == ["finish the Android app"]
    assert today["greeting"].startswith("Good afternoon, Raunak. Planned for this session: finish the Android app.")
    assert heard == []


def test_forget_all_is_laptop_only(parts):
    client, companion, *_ = parts
    client.post("/api/message", json={"text": "/remember one thing"})
    r = client.post("/api/message", json={"text": "/forget all"}).json()
    assert {"kind": "note", "text": "For safety, deleting all memories only works on the laptop."} in r["messages"]
    assert len(companion.assistant.memory.all()) == 1


@pytest.mark.parametrize("text", ["open chrome", "find my resume"])
def test_apps_and_files_stay_on_the_laptop(parts, text):
    client, _, _, heard, _ = parts
    r = client.post("/api/message", json={"text": text}).json()
    assert r["messages"][0]["text"] == "Opening apps and files only works on the laptop for now."
    assert heard == []


def test_calendar_events_need_confirmation_from_the_phone(parts):
    client, _, service, _, _ = parts
    r = client.post("/api/message", json={"text": "add gym to my calendar tomorrow at 7 am"}).json()
    assert r["confirm"]["question"] == 'Add "Gym", Fri 27 Nov 07:00–08:00 to your Google Calendar?'
    assert service.inserted == []
    no = client.post("/api/confirm", json={"id": r["confirm"]["id"], "yes": False}).json()
    assert no["messages"][0]["text"] == "Okay, I haven't added it."
    again = client.post("/api/confirm", json={"id": r["confirm"]["id"], "yes": True}).json()
    assert "expired" in again["messages"][0]["text"]  # each confirmation works once
    r = client.post("/api/message", json={"text": "add gym to my calendar tomorrow at 7 am"}).json()
    yes = client.post("/api/confirm", json={"id": r["confirm"]["id"], "yes": True}).json()
    assert yes["messages"][0]["text"] == 'Added to your calendar: "Gym", Fri 27 Nov 07:00–08:00.'
    assert service.inserted[0]["summary"] == "Gym"


def test_voice_from_the_phone(parts):
    client, _, _, heard, _ = parts
    r = client.post("/api/voice", content=wav_bytes()).json()
    assert r["heard"] == "What's on today?"
    assert r["messages"] == [{"kind": "parker", "text": "Reply to: What's on today?"}]
    assert client.post("/api/voice", content=b"not audio").status_code == 400
    assert client.post("/api/voice", content=b"").status_code == 400


def test_phone_audio_is_converted_for_whisper():
    audio = wav_to_audio(wav_bytes(seconds=1.0, rate=48000, channels=2))
    assert audio.dtype == np.float32 and abs(len(audio) - 16000) <= 1


def test_speak_returns_parkers_voice(parts):
    r = parts[0].post("/api/speak", json={"text": "Good evening"})
    assert r.headers["content-type"] == "audio/wav" and r.content.endswith(b"Good evening")


def test_model_errors_are_reported(parts):
    client, companion, *_ = parts

    def broken(m, h, **k):
        raise BrainError("Cannot reach Ollama")

    companion.assistant._generate = broken
    r = client.post("/api/message", json={"text": "Hi"}).json()
    assert r["messages"] == [{"kind": "error", "text": "Cannot reach Ollama"}]


def test_long_messages_are_refused(parts):
    assert parts[0].post("/api/message", json={"text": "x" * 2001}).status_code == 413


# ---- the real server over HTTPS ---------------------------------------------------

def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_real_https_server_with_a_pinned_certificate(parts, tmp_path):
    import httpx

    _, companion, *_ = parts
    identity = load_or_create_identity(tmp_path)
    port = free_port()
    server = CompanionServer(companion, identity, port=port, host="127.0.0.1")
    server.start()
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.05)
        # Trust exactly this laptop's certificate, as the phone does.
        context = ssl.create_default_context(cafile=str(identity.cert_path))
        context.check_hostname = False
        with httpx.Client(verify=context, base_url=f"https://127.0.0.1:{port}") as phone:
            ok = phone.get("/api/status", headers={"Authorization": f"Bearer {identity.token}"})
            assert ok.status_code == 200 and ok.json()["app"] == "parker"
            assert phone.get("/api/status").status_code == 401
        # A phone that trusts some other certificate refuses to talk to it.
        other = load_or_create_identity(tmp_path / "other")
        wrong = ssl.create_default_context(cafile=str(other.cert_path))
        wrong.check_hostname = False
        with httpx.Client(verify=wrong, base_url=f"https://127.0.0.1:{port}") as impostor:
            with pytest.raises(httpx.ConnectError):
                impostor.get("/api/status")
        # Plain unencrypted HTTP is not served at all.
        with pytest.raises(httpx.HTTPError):
            httpx.get(f"http://127.0.0.1:{port}/api/status", timeout=3)
    finally:
        server.stop()


# ---- desktop app switch and pairing window -----------------------------------------

def make_window(tmp_path, servers, enabled=None):
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6.QtWidgets")
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    from frontend.app import MainWindow

    QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    if enabled is not None:
        settings.setValue("companion", enabled)

    class FakeServer:
        def __init__(self, companion, identity):
            self.companion, self.identity, self.running = companion, identity, False
            servers.append(self)

        def start(self):
            self.running = True

        def stop(self):
            self.running = False

    return MainWindow(
        Assistant(generate=lambda m, h, **k: "ok", memory=Memory(":memory:"), now=lambda: NOW),
        make_speaker=None, make_listener=None, threaded=False, now=lambda: NOW,
        tray_available=lambda: False, make_hotkey=None, settings=settings,
        make_companion_server=FakeServer, companion_dir=tmp_path / "id",
    )


def test_companion_is_off_by_default(tmp_path):
    servers = []
    window = make_window(tmp_path, servers)
    assert not window.companion_action.isChecked() and not window.pair_action.isEnabled()
    assert servers == []


def test_switching_on_starts_the_server_and_is_remembered(tmp_path):
    servers = []
    window = make_window(tmp_path, servers)
    window.companion_action.setChecked(True)
    assert servers[-1].running and window.pair_action.isEnabled()
    assert window.settings.value("companion") == "true"
    # The phone talks to the same brain and memory as the window.
    assert servers[-1].companion.assistant is window.assistant
    window.companion_action.setChecked(False)
    assert not servers[-1].running
    again = make_window(tmp_path, [], enabled="true")
    assert again.companion_server is not None


def test_pairing_window_shows_a_qr_with_this_laptops_token(tmp_path):
    servers = []
    window = make_window(tmp_path, servers, enabled="true")
    dialog = window.show_pairing()
    token = servers[-1].identity.token
    assert len(dialog.qr.matrix) > 20
    old = token
    dialog.findChildren(__import__("PySide6.QtWidgets", fromlist=["QPushButton"]).QPushButton)[0].click()
    assert servers[-1].identity.token != old  # "Unpair all phones" made a new code
    assert servers[-2].running is False


# ---- finding the laptop's Wi-Fi address (bug from the first phone test) ----------

def test_home_wifi_address_comes_before_vpn_addresses(monkeypatch):
    import backend.companion as c

    # On the laptop a VPN-style 10.58.x.x address was put in the QR code instead of
    # the Wi-Fi's 192.168.1.48, so the phone (192.168.1.17) couldn't connect.
    monkeypatch.setattr(c.socket, "gethostbyname_ex",
                        lambda name: (name, [], ["10.58.18.182", "192.168.1.48", "169.254.3.4", "100.101.2.3"]))
    monkeypatch.setattr(c.socket, "getaddrinfo", lambda *a, **k: [])

    class VpnRoute:
        def __init__(self, *a):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def connect(self, addr):
            pass

        def getsockname(self):
            return ("10.58.18.182", 50000)

    monkeypatch.setattr(c.socket, "socket", VpnRoute)
    monkeypatch.setattr(c, "tailscale_addresses", lambda: [])
    assert c.local_addresses(env="") == ["192.168.1.48", "10.58.18.182", "100.101.2.3"]


def test_hosts_can_be_set_by_hand():
    from backend.companion import local_addresses

    assert local_addresses(env="192.168.1.48, 100.64.0.9") == ["192.168.1.48", "100.64.0.9"]


def test_server_reports_when_the_port_is_already_in_use(parts, tmp_path):
    """It used to fail silently, so the phone just timed out."""
    _, companion, *_ = parts
    identity = load_or_create_identity(tmp_path)
    port = free_port()
    first = CompanionServer(companion, identity, port=port, host="127.0.0.1")
    first.start()
    try:
        second = CompanionServer(companion, identity, port=port, host="127.0.0.1")
        with pytest.raises(RuntimeError, match=f"port {port} is probably already in use"):
            second.start(wait_seconds=5)
    finally:
        first.stop()


def test_window_reports_a_companion_that_could_not_start(tmp_path):
    servers = []
    window = make_window(tmp_path, servers)

    class Failing:
        def __init__(self, companion, identity):
            pass

        def start(self):
            raise RuntimeError("PARKER couldn't listen for the phone: port 8765 is probably already in use.")

    window._make_companion_server = Failing
    window.companion_action.setChecked(True)
    assert window.companion_server is None
    assert ("error", "Phone companion couldn't start: PARKER couldn't listen for the phone: "
                     "port 8765 is probably already in use.") in window.chat.messages



def test_tailscale_address_is_asked_from_tailscale_itself(monkeypatch):
    """On the laptop Python couldn't see the Tailscale address and `tailscale`
    wasn't on PATH, so it's also looked up in Tailscale's install folder."""
    import subprocess
    from types import SimpleNamespace

    import backend.companion as c

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd[0])
        if cmd[0] == "tailscale":
            raise FileNotFoundError("not on PATH")
        return SimpleNamespace(stdout="100.71.12.5\n")

    assert c.tailscale_addresses(run=fake_run) == ["100.71.12.5"]
    assert calls[:2] == ["tailscale", r"C:\Program Files\Tailscale\tailscale.exe"]
    assert c.tailscale_addresses(run=lambda *a, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired("t", 3))) == []

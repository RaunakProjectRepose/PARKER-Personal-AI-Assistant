"""PARKER companion: lets the Android app use the PARKER running on this laptop.

Security:
- Off by default; the owner switches it on.
- Pairing: a random 256-bit token, shared once by QR code. Every request must
  carry it; anything else gets 401.
- Encryption: HTTPS with a certificate made on this laptop. The phone pins its
  SHA-256 fingerprint (in the QR code), so nobody else on the network can read
  or impersonate PARKER.
- The token, certificate and key live in memory/ (ignored by Git).
- Some things stay laptop-only for safety: opening apps or files, and deleting
  all memories.
"""

from __future__ import annotations

import base64
import hashlib
import io
import ipaddress
import json
import os
import secrets
import socket
import threading
import uuid
import wave
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from backend.apps import parse_open_request
from backend.brain import MODEL, OWNER_NAME, BrainError
from backend.files import parse_find_request
from backend.google_calendar import CalendarError, EventRequest
from backend.greeting import build_greeting
from backend.main import (
    HELP_TEXT,
    RESET_COMMAND,
    events_today,
    handle_agenda,
    handle_memory,
    handle_reminders,
    is_calendar_request,
    parse_calendar_request,
)
from backend.memory import PROJECT_ROOT

PORT = 8765
IDENTITY_DIR = PROJECT_ROOT / "memory"
CONFIRM_SECONDS = 300
LAPTOP_ONLY = "Opening apps and files only works on the laptop for now."


# ---- identity: pairing token + HTTPS certificate -------------------------------

@dataclass(frozen=True)
class Identity:
    token: str
    cert_path: Path
    key_path: Path
    fingerprint: str  # SHA-256 of the certificate (DER), hex


def _make_certificate(cert_path: Path, key_path: Path) -> None:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "PARKER companion")])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.SubjectAlternativeName([
            x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
        ]), critical=False)
        .sign(key, hashes.SHA256())
    )
    key_path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def fingerprint_of(cert_path: Path) -> str:
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization

    cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    return hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()


def load_or_create_identity(folder: Path = IDENTITY_DIR) -> Identity:
    folder.mkdir(parents=True, exist_ok=True)
    cert_path, key_path = folder / "companion_cert.pem", folder / "companion_key.pem"
    token_path = folder / "companion_token.txt"
    if not token_path.exists():
        token_path.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    if not (cert_path.exists() and key_path.exists()):
        _make_certificate(cert_path, key_path)
    return Identity(token_path.read_text(encoding="utf-8").strip(), cert_path, key_path,
                    fingerprint_of(cert_path))


def reset_pairing(folder: Path = IDENTITY_DIR) -> Identity:
    """Forget the paired phone(s): a new token means old ones stop working."""
    (folder / "companion_token.txt").unlink(missing_ok=True)
    return load_or_create_identity(folder)


def _address_rank(addr: str) -> int:
    """Home Wi-Fi first: 192.168.x.x, then 172.16-31.x.x, then 10.x.x.x (often VPNs or
    virtual adapters), then Tailscale's 100.x.x.x for use away from home."""
    if addr.startswith("192.168."):
        return 0
    if addr.startswith("172."):
        return 1
    if addr.startswith("10."):
        return 2
    return 3


TAILSCALE_PATHS = [
    "tailscale",  # on PATH
    r"C:\Program Files\Tailscale\tailscale.exe",
    r"C:\Program Files (x86)\Tailscale\tailscale.exe",
]


def tailscale_addresses(run=None) -> list[str]:
    """Ask Tailscale itself for this laptop's 100.x address (it isn't always visible
    to Python, and the tailscale command isn't always on PATH)."""
    import subprocess

    run = run or subprocess.run
    for exe in TAILSCALE_PATHS:
        try:
            result = run([exe, "ip", "-4"], capture_output=True, text=True, timeout=3)
        except (OSError, subprocess.SubprocessError):
            continue
        found = [line.strip() for line in (result.stdout or "").splitlines() if line.strip().startswith("100.")]
        if found:
            return found
    return []


def local_addresses(env: str | None = None) -> list[str]:
    """This laptop's addresses the phone could reach, best first.

    Lists EVERY network connection (Wi-Fi, Ethernet, VPN, Tailscale), not just
    the one Windows uses for the internet: with a VPN on, that one is the VPN's.
    PARKER_COMPANION_HOSTS (comma-separated) overrides the list.
    """
    override = env if env is not None else os.environ.get("PARKER_COMPANION_HOSTS", "")
    if override.strip():
        return [h.strip() for h in override.split(",") if h.strip()]
    found: list[str] = []
    try:
        found += socket.gethostbyname_ex(socket.gethostname())[2]  # all IPv4 addresses
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.append(info[4][0])
    except OSError:
        pass
    try:  # the address used for outgoing traffic; nothing is actually sent
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))
            found.append(s.getsockname()[0])
    except OSError:
        pass
    found += tailscale_addresses()
    usable: list[str] = []
    for addr in found:
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if ip.is_loopback or ip.is_link_local or addr in usable:
            continue  # 127.x and 169.254.x (adapters with no network) can't be reached
        if ip.is_private or addr.startswith("100."):
            usable.append(addr)
    return sorted(usable, key=_address_rank)


def pairing_payload(identity: Identity, port: int = PORT, hosts: list[str] | None = None) -> str:
    """What the QR code contains: where PARKER is, the token, and the certificate to trust."""
    return json.dumps({
        "app": "parker", "v": 1, "hosts": hosts if hosts is not None else local_addresses(),
        "port": port, "token": identity.token, "fp": identity.fingerprint, "name": OWNER_NAME,
    }, separators=(",", ":"))


def qr_matrix(text: str) -> list[list[bool]]:
    import qrcode

    qr = qrcode.QRCode(border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(text)
    qr.make(fit=True)
    return qr.get_matrix()


# ---- the conversation, as used by the phone -------------------------------------

def wav_to_audio(wav_bytes: bytes):
    """16-bit PCM WAV from the phone -> 16 kHz mono float32 for Whisper."""
    import numpy as np

    with wave.open(io.BytesIO(wav_bytes)) as wav:
        channels, width, rate = wav.getnchannels(), wav.getsampwidth(), wav.getframerate()
        frames = wav.readframes(wav.getnframes())
    if width != 2:
        raise ValueError("Send 16-bit PCM WAV audio.")
    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    if rate != 16000 and len(audio):
        positions = np.linspace(0, len(audio) - 1, int(len(audio) * 16000 / rate))
        audio = np.interp(positions, np.arange(len(audio)), audio).astype(np.float32)
    return audio


class Companion:
    """Turns phone requests into PARKER replies, reusing the laptop's handlers."""

    def __init__(self, assistant, *, reminders=None, calendar=None,
                 transcribe: Callable | None = None, synthesize: Callable[[str], bytes] | None = None,
                 now: Callable[[], datetime] = datetime.now) -> None:
        self.assistant = assistant
        self.reminders = reminders
        self.calendar = calendar if calendar is not None else getattr(assistant, "calendar", None)
        self._transcribe = transcribe
        self._synthesize = synthesize
        self._now = now
        self._lock = threading.RLock()  # one phone request at a time
        self._pending: dict[str, tuple[datetime, EventRequest]] = {}

    def status(self) -> dict:
        return {"app": "parker", "model": MODEL, "owner": OWNER_NAME,
                "voice_in": self._transcribe is not None, "voice_out": self._synthesize is not None}

    def handle(self, text: str) -> dict:
        text = (text or "").strip()
        out: list[dict] = []

        def say(line: str) -> None:
            out.append({"kind": "parker", "text": line})

        def show(line: str) -> None:
            line = line.strip()
            if line.startswith("PARKER: "):
                out.append({"kind": "parker", "text": line[len("PARKER: "):]})
            elif line:
                out.append({"kind": "note", "text": line})

        def refuse_on_phone(question: str) -> str:
            show("For safety, deleting all memories only works on the laptop.")
            return "no"

        if not text:
            return {"messages": []}
        with self._lock:
            now = self._now()
            lowered = text.lower()
            if lowered == RESET_COMMAND:
                self.assistant.reset()
                show("Conversation cleared. Saved memories are kept.")
            elif lowered == "/help":
                show(HELP_TEXT.strip())
            elif handle_memory(text, self.assistant.memory, say, show, refuse_on_phone):
                pass
            elif handle_agenda(text, self.assistant.agenda, say, show, now.date()):
                pass
            elif handle_reminders(text, self.reminders, say, show, now):
                pass
            elif is_calendar_request(text, now):
                request = parse_calendar_request(text, self.calendar, show, now)
                if request is not None:
                    confirm_id = uuid.uuid4().hex
                    self._pending[confirm_id] = (now, request)
                    return {"messages": out, "confirm": {
                        "id": confirm_id, "question": f"Add {request.describe()} to your Google Calendar?"}}
            elif parse_open_request(text) or parse_find_request(text):
                show(LAPTOP_ONLY)
            elif text.startswith("/"):
                show(f"Unknown command {text.split()[0]}. Type /help for commands.")
            else:
                try:
                    say(self.assistant.ask(text))
                except BrainError as err:
                    out.append({"kind": "error", "text": str(err)})
        return {"messages": out}

    def confirm(self, confirm_id: str, yes: bool) -> dict:
        with self._lock:
            pending = self._pending.pop(confirm_id, None)
            if pending is None or self._now() - pending[0] > timedelta(seconds=CONFIRM_SECONDS):
                return {"messages": [{"kind": "note", "text": "That request expired. Please ask again."}]}
            request = pending[1]
            if not yes:
                return {"messages": [{"kind": "parker", "text": "Okay, I haven't added it."}]}
            try:
                self.calendar.add(request.title, request.start, request.end, request.all_day)
            except CalendarError as err:
                return {"messages": [{"kind": "error", "text": str(err)}]}
            return {"messages": [{"kind": "parker", "text": f"Added to your calendar: {request.describe()}."}]}

    def voice(self, wav_bytes: bytes) -> dict:
        if self._transcribe is None:
            return {"heard": "", "messages": [{"kind": "error", "text": "Speech recognition isn't ready on the laptop."}]}
        heard = self._transcribe(wav_to_audio(wav_bytes)).strip()
        if not heard:
            return {"heard": "", "messages": [{"kind": "note", "text": "Sorry, I didn't catch that."}]}
        return {"heard": heard, **self.handle(heard)}

    def speak(self, text: str) -> bytes:
        if self._synthesize is None:
            raise RuntimeError("The voice isn't ready on the laptop.")
        return self._synthesize(text)

    def today(self) -> dict:
        now = self._now()
        today = now.date()
        agenda, memory = self.assistant.agenda, self.assistant.memory
        events = events_today(agenda, self.calendar, today) if agenda is not None or self.calendar else []
        plans = agenda.open_plans() if agenda is not None else []
        week = []
        if agenda is not None:
            week += [{"text": e.text, "when": e.when(today), "source": "parker"}
                     for e in agenda.events_between(today, today + timedelta(days=7))]
        if self.calendar is not None:
            week += [{"text": e.title, "when": e.as_agenda_event().when(today), "source": "google"}
                     for e in self.calendar.cached(today, today + timedelta(days=7))]
        return {
            "greeting": build_greeting(OWNER_NAME, plans, events, now),
            "plans": [p.text for p in plans],
            "events": week,
            "reminders": [{"text": r.text, "when": r.when(now)} for r in self.reminders.upcoming()]
            if self.reminders is not None else [],
            "memories": [f.text for f in memory.all()] if memory is not None else [],
        }


def encode_audio(wav: bytes) -> str:
    return base64.b64encode(wav).decode("ascii")

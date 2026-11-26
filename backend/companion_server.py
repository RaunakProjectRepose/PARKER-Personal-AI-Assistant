"""The HTTPS API the PARKER Android app talks to.

Every endpoint needs `Authorization: Bearer <token>` from pairing.

    GET  /api/status              -> name, model, what's available
    GET  /api/today               -> greeting, plans, events, reminders, memories
    POST /api/message  {"text"}   -> {"messages": [...], "confirm"?: {"id", "question"}}
    POST /api/confirm  {"id","yes"} -> {"messages": [...]}
    POST /api/voice    (WAV body) -> {"heard", "messages", ...}
    POST /api/speak    {"text"}   -> audio/wav in PARKER's voice
"""

# No "from __future__ import annotations" here: FastAPI needs the real types of
# the request models defined inside create_app().
import hmac
import threading
import wave

from backend.companion import PORT, Companion, Identity

MAX_AUDIO_BYTES = 10 * 1024 * 1024  # ~5 minutes of 16 kHz speech


def create_app(companion: Companion, token: str):
    from fastapi import Body, Depends, FastAPI, HTTPException, Request, Response
    from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
    from pydantic import BaseModel

    app = FastAPI(title="PARKER companion", docs_url=None, redoc_url=None, openapi_url=None)
    bearer = HTTPBearer(auto_error=False)

    def paired(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> None:
        given = credentials.credentials if credentials else ""
        if not hmac.compare_digest(given.encode(), token.encode()):  # constant time
            raise HTTPException(status_code=401, detail="Not paired with this PARKER.")

    class Message(BaseModel):
        text: str

    class Confirmation(BaseModel):
        id: str
        yes: bool

    @app.get("/api/status", dependencies=[Depends(paired)])
    def status():
        return companion.status()

    @app.get("/api/today", dependencies=[Depends(paired)])
    def today():
        return companion.today()

    @app.post("/api/message", dependencies=[Depends(paired)])
    def message(body: Message):
        if len(body.text) > 2000:
            raise HTTPException(status_code=413, detail="Message too long.")
        return companion.handle(body.text)

    @app.post("/api/confirm", dependencies=[Depends(paired)])
    def confirm(body: Confirmation):
        return companion.confirm(body.id, body.yes)

    @app.post("/api/voice", dependencies=[Depends(paired)])
    async def voice(request: Request):
        audio = await request.body()
        if not audio:
            raise HTTPException(status_code=400, detail="No audio.")
        if len(audio) > MAX_AUDIO_BYTES:
            raise HTTPException(status_code=413, detail="Recording too long.")
        try:
            return companion.voice(audio)
        except (ValueError, EOFError, wave.Error) as err:
            raise HTTPException(status_code=400, detail=f"Couldn't read the audio: {err}") from err

    @app.post("/api/speak", dependencies=[Depends(paired)])
    def speak(body: Message):
        try:
            return Response(companion.speak(body.text[:2000]), media_type="audio/wav")
        except RuntimeError as err:
            raise HTTPException(status_code=503, detail=str(err)) from err

    return app


class CompanionServer:
    """Runs the API over HTTPS on a background thread; stop() shuts it down."""

    def __init__(self, companion: Companion, identity: Identity, port: int = PORT, host: str = "0.0.0.0"):
        import uvicorn

        config = uvicorn.Config(
            create_app(companion, identity.token), host=host, port=port, log_level="warning",
            ssl_certfile=str(identity.cert_path), ssl_keyfile=str(identity.key_path),
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, name="parker-companion", daemon=True)

    def start(self) -> None:
        self._thread.start()

    @property
    def started(self) -> bool:
        return self._server.started

    def stop(self) -> None:
        self._server.should_exit = True
        self._thread.join(5)

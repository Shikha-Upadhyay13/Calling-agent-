import logging

from deepgram import AsyncDeepgramClient
from deepgram.speak.v1.types.speak_v1text import SpeakV1Text

from app.config import settings

logger = logging.getLogger(__name__)

_client = AsyncDeepgramClient(api_key=settings.deepgram_api_key)

VOICE_MODEL = "aura-2-asteria-en"
VOICE_SPEED = 0.9  # slightly slower than default (1.0) for a calmer, softer pace


def open_session():
    """Async context manager yielding a live Deepgram TTS socket. Kept open
    for the whole call and reused across turns (via synthesize()) instead of
    reconnecting each time -- the connection handshake alone costs ~1-1.5s."""
    return _client.speak.v1.connect(
        model=VOICE_MODEL, encoding="mulaw", sample_rate=8000, speed=VOICE_SPEED
    )


async def synthesize(socket, text: str) -> bytes:
    """Synthesizes one reply's audio on an already-open socket (see
    open_session()). Safe to call repeatedly on the same socket across turns."""
    audio = bytearray()
    await socket.send_text(SpeakV1Text(type="Speak", text=text))
    await socket.send_flush()
    while True:
        msg = await socket.recv()
        if isinstance(msg, bytes):
            audio.extend(msg)
        elif type(msg).__name__ == "SpeakV1Flushed":
            break
    return bytes(audio)

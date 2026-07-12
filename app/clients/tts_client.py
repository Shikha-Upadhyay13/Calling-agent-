import logging

from deepgram import AsyncDeepgramClient
from deepgram.speak.v1.types.speak_v1text import SpeakV1Text

from app.config import settings

logger = logging.getLogger(__name__)

_client = AsyncDeepgramClient(api_key=settings.deepgram_api_key)

VOICE_MODEL = "aura-2-asteria-en"


async def synthesize(text: str) -> bytes:
    """Returns the full mulaw/8kHz audio for the given text, ready to send
    straight to Twilio with no format conversion."""
    logger.info("TTS: opening connection")
    audio = bytearray()
    async with _client.speak.v1.connect(
        model=VOICE_MODEL, encoding="mulaw", sample_rate=8000
    ) as socket:
        logger.info("TTS: connection open, sending text")
        await socket.send_text(SpeakV1Text(type="Speak", text=text))
        await socket.send_flush()
        logger.info("TTS: text + flush sent, waiting for audio")
        while True:
            msg = await socket.recv()
            if isinstance(msg, bytes):
                audio.extend(msg)
            else:
                logger.info("TTS: received event %s", type(msg).__name__)
                if type(msg).__name__ == "SpeakV1Flushed":
                    break
    logger.info("TTS: done, %d bytes", len(audio))
    return bytes(audio)

import logging
import struct
import wave
from pathlib import Path

from app.audio.twilio_audio import decode_media_payload

logger = logging.getLogger(__name__)

RECORDINGS_DIR = Path("recordings")


def _build_ulaw_to_linear_table() -> list[int]:
    """Standard ITU-T G.711 u-law -> 16-bit linear PCM lookup table. Built
    once at import time since mulaw is only 8 bits (256 possible values).
    Python's old `audioop.ulaw2lin` helper was removed in Python 3.13+, so
    this is done by hand instead of relying on a stdlib shortcut."""
    table = []
    for i in range(256):
        u = ~i & 0xFF
        sign = u & 0x80
        exponent = (u >> 4) & 0x07
        mantissa = u & 0x0F
        sample = ((mantissa << 3) + 0x84) << exponent
        sample -= 0x84
        if sign != 0:
            sample = -sample
        table.append(max(-32768, min(32767, sample)))
    return table


_ULAW_TO_LINEAR = _build_ulaw_to_linear_table()


def _ulaw_to_pcm16(mulaw_bytes: bytes) -> bytes:
    samples = [_ULAW_TO_LINEAR[b] for b in mulaw_bytes]
    return struct.pack(f"<{len(samples)}h", *samples)


class CallRecorder:
    """Records one call's audio (caller side only -- see note below) and
    full transcript (both sides) to disk under recordings/.

    Scope decision: this saves the caller's raw audio for playback/quality
    review, but not a separately mixed track of the agent's own voice --
    doing a properly time-aligned two-party recording would need a shared
    clock between the inbound Twilio stream and our outbound TTS sends,
    which is more engineering than this feature needs yet. The transcript
    already captures both sides in full as text, so nothing said is lost,
    just not double-recorded as audio."""

    def __init__(self, call_id: str):
        RECORDINGS_DIR.mkdir(exist_ok=True)
        self.call_id = call_id
        self._audio_path = RECORDINGS_DIR / f"{call_id}.wav"
        self._transcript_path = RECORDINGS_DIR / f"{call_id}.txt"
        self._wav = wave.open(str(self._audio_path), "wb")
        self._wav.setnchannels(1)
        self._wav.setsampwidth(2)
        self._wav.setframerate(8000)
        self._transcript_lines: list[str] = []

    def add_caller_audio(self, base64_payload: str):
        self._wav.writeframes(_ulaw_to_pcm16(decode_media_payload(base64_payload)))

    def add_transcript_line(self, speaker: str, text: str):
        self._transcript_lines.append(f"{speaker}: {text}")

    def close(self):
        self._wav.close()
        self._transcript_path.write_text("\n".join(self._transcript_lines), encoding="utf-8")
        logger.info("Saved recording: %s, %s", self._audio_path, self._transcript_path)

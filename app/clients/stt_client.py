from deepgram import AsyncDeepgramClient

from app.config import settings

_client = AsyncDeepgramClient(api_key=settings.deepgram_api_key)


def open_session():
    """Async context manager yielding a live Deepgram STT socket, pre-configured
    for Twilio's native mulaw/8kHz audio (no resampling needed) with built-in
    endpointing so we don't have to hand-roll silence detection."""
    return _client.listen.v1.connect(
        model="nova-3",
        encoding="mulaw",
        sample_rate=8000,
        channels=1,
        interim_results=True,
        endpointing=300,
        utterance_end_ms=1000,
        vad_events=True,
    )


async def wait_for_final_transcript(socket) -> str:
    """Reads STT events until one finalized utterance with real text arrives,
    or the caller stops talking (UtteranceEnd) with nothing said yet."""
    transcript_parts: list[str] = []
    while True:
        msg = await socket.recv()
        msg_type = type(msg).__name__

        if msg_type == "ListenV1Results":
            alternatives = msg.channel.alternatives
            transcript = alternatives[0].transcript if alternatives else ""
            if transcript and msg.is_final:
                transcript_parts.append(transcript)
            if msg.speech_final and transcript_parts:
                break

        elif msg_type == "ListenV1UtteranceEnd":
            if transcript_parts:
                break

    return " ".join(transcript_parts).strip()

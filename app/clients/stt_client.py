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
        endpointing=600,
        utterance_end_ms=1500,
        vad_events=True,
    )


async def wait_for_final_transcript(socket) -> str:
    """Accumulates finalized text across the whole turn and only returns once
    UtteranceEnd fires (the caller has been fully silent for utterance_end_ms).

    Deliberately does NOT return on the first speech_final segment -- a
    multi-sentence turn ("...thing one. ...thing two.") produces one
    speech_final per sentence as soon as a brief pause follows it, well
    before the caller is actually done talking. Reacting to that made the
    agent reply to sentence 1 while the caller was already on sentence 3.
    UtteranceEnd is the deliberate, slower "the whole turn is over" signal."""
    transcript_parts: list[str] = []
    while True:
        msg = await socket.recv()
        msg_type = type(msg).__name__

        if msg_type == "ListenV1Results":
            alternatives = msg.channel.alternatives
            transcript = alternatives[0].transcript if alternatives else ""
            if transcript and msg.is_final:
                transcript_parts.append(transcript)

        elif msg_type == "ListenV1UtteranceEnd":
            if transcript_parts:
                break

    return " ".join(transcript_parts).strip()

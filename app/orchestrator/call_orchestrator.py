import asyncio
import contextlib
import itertools
import logging
import re

from app.audio.twilio_audio import build_mark_message, build_media_message, decode_media_payload
from app.clients import llm_client, stt_client, tts_client

logger = logging.getLogger(__name__)

OUTBOUND_CHUNK_SIZE = 160  # 20ms of mulaw/8kHz audio per Twilio media frame
_mark_counter = itertools.count(1)
_SENTENCE_END_RE = re.compile(r"([.!?])(\s+|$)")


async def run_conversation(
    websocket, stream_sid: str, incoming_audio: "asyncio.Queue", mark_events: "asyncio.Queue"
):
    """Multi-turn conversation with persistent history and persistent STT/TTS
    connections. Replies are streamed and spoken sentence-by-sentence as soon
    as each is ready (instead of waiting for the whole reply) so turn-taking
    feels human-paced.

    Barge-in (stopping mid-sentence when the caller starts talking) was
    tried and pulled back out -- it kept self-triggering on every reply in
    testing, and without a controlled setup (headset, not phone
    speaker/earpiece) it wasn't possible to tell whether that was a real
    bug or acoustic echo. Tracked separately to revisit properly."""
    history: list[dict] = []
    stream_ended = asyncio.Event()

    async with stt_client.open_session() as stt_socket, tts_client.open_session() as tts_socket:

        async def forward_audio_to_stt():
            while True:
                payload = await incoming_audio.get()
                if payload is None:
                    stream_ended.set()
                    break
                await stt_socket.send_media(decode_media_payload(payload))

        forward_task = asyncio.create_task(forward_audio_to_stt())

        try:
            while True:
                transcript = await _next_transcript_or_end(stt_socket, stream_ended)
                if transcript is None:
                    logger.info("Call ended, stopping conversation loop")
                    break
                if not transcript:
                    if stream_ended.is_set():
                        break
                    continue

                logger.info("Caller said: %s", transcript)
                history.append({"role": "user", "content": transcript})

                reply_text = await _stream_reply_and_speak(
                    websocket, stream_sid, history, tts_socket, mark_events
                )
                if reply_text:
                    history.append({"role": "assistant", "content": reply_text})

                if stream_ended.is_set():
                    break
        finally:
            forward_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await forward_task


async def _next_transcript_or_end(stt_socket, stream_ended: asyncio.Event) -> str | None:
    """Waits for the next finalized utterance on the (already-open, shared)
    STT socket. Returns "" if the caller went quiet with nothing usable yet,
    or None if the call ended before/while waiting."""
    if stream_ended.is_set():
        return None

    transcript_task = asyncio.create_task(stt_client.wait_for_final_transcript(stt_socket))
    ended_task = asyncio.create_task(stream_ended.wait())

    done, pending = await asyncio.wait(
        {transcript_task, ended_task}, return_when=asyncio.FIRST_COMPLETED
    )
    for task in pending:
        task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await asyncio.gather(*pending, return_exceptions=True)

    if transcript_task in done:
        return transcript_task.result()
    return None


async def _stream_reply_and_speak(
    websocket, stream_sid: str, history: list[dict], tts_socket, mark_events
) -> str:
    """Streams the LLM reply, speaking each completed sentence immediately
    instead of waiting for the full reply -- this is what makes the agent
    start responding almost as soon as it starts "thinking", like a human,
    instead of one long pause for the whole answer."""
    spoken_sentences: list[str] = []
    buffer = ""

    async for delta in llm_client.stream_reply(history):
        buffer += delta
        while True:
            match = _SENTENCE_END_RE.search(buffer)
            if not match:
                break
            sentence = buffer[: match.end()].strip()
            buffer = buffer[match.end() :]
            if not sentence:
                continue
            spoken_sentences.append(sentence)
            logger.info("Agent saying: %s", sentence)
            reply_audio = await _synthesize_with_timeout(tts_socket, sentence)
            if reply_audio is not None:
                await _speak(websocket, stream_sid, reply_audio, mark_events)

    leftover = buffer.strip()
    if leftover:
        spoken_sentences.append(leftover)
        logger.info("Agent saying: %s", leftover)
        reply_audio = await _synthesize_with_timeout(tts_socket, leftover)
        if reply_audio is not None:
            await _speak(websocket, stream_sid, reply_audio, mark_events)

    return " ".join(spoken_sentences)


async def _synthesize_with_timeout(tts_socket, text: str) -> bytes | None:
    """TTS synthesis wrapped in a hard timeout -- without this, a hung
    Deepgram connection blocks the whole conversation loop indefinitely
    instead of failing loud. Returns None (skip this sentence) on timeout."""
    try:
        return await asyncio.wait_for(tts_client.synthesize(tts_socket, text), timeout=10)
    except asyncio.TimeoutError:
        logger.error("TTS synthesis timed out after 10s for: %s", text)
        return None


async def _speak(websocket, stream_sid: str, reply_audio: bytes, mark_events: "asyncio.Queue"):
    """Sends reply_audio to Twilio and waits for the mark echo confirming
    playback actually finished before returning -- without this, moving to
    the next sentence/turn can cut the caller off mid-sentence."""
    logger.info("Sending %d bytes of reply audio back to Twilio", len(reply_audio))
    for i in range(0, len(reply_audio), OUTBOUND_CHUNK_SIZE):
        chunk = reply_audio[i : i + OUTBOUND_CHUNK_SIZE]
        await websocket.send_text(build_media_message(stream_sid, chunk))
    mark_name = f"reply-done-{next(_mark_counter)}"
    await websocket.send_text(build_mark_message(stream_sid, mark_name))

    try:
        expected_playback_s = len(reply_audio) / 8000
        timeout = max(5.0, expected_playback_s + 5.0)
        while True:
            seen = await asyncio.wait_for(mark_events.get(), timeout=timeout)
            if seen == mark_name:
                break
        logger.info("Twilio confirmed playback finished")
    except asyncio.TimeoutError:
        logger.warning("Never got playback-finished confirmation from Twilio (mark echo timed out)")

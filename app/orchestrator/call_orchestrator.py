import asyncio
import contextlib
import logging

from app.audio.twilio_audio import build_mark_message, build_media_message, decode_media_payload
from app.clients import llm_client, stt_client, tts_client

logger = logging.getLogger(__name__)

OUTBOUND_CHUNK_SIZE = 160  # 20ms of mulaw/8kHz audio per Twilio media frame


async def run_conversation(
    websocket, stream_sid: str, incoming_audio: "asyncio.Queue", mark_events: "asyncio.Queue"
):
    """Milestone D: loops single exchanges into a real multi-turn conversation
    with persistent history, until the caller hangs up (Milestone C handled
    exactly one exchange and then ended the call)."""
    history: list[dict] = []

    while True:
        transcript, call_ended = await _listen_for_utterance(incoming_audio)

        if not transcript:
            if call_ended:
                logger.info("Call ended, stopping conversation loop")
                break
            # Caller went quiet without saying anything intelligible; keep listening.
            continue

        logger.info("Caller said: %s", transcript)
        history.append({"role": "user", "content": transcript})

        reply_text = await asyncio.to_thread(llm_client.generate_reply, history)
        history.append({"role": "assistant", "content": reply_text})
        logger.info("Agent replying: %s", reply_text)

        try:
            reply_audio = await asyncio.wait_for(tts_client.synthesize(reply_text), timeout=10)
        except asyncio.TimeoutError:
            logger.error("TTS synthesis timed out after 10s")
            if call_ended:
                break
            continue

        await _speak(websocket, stream_sid, reply_audio, mark_events)

        if call_ended:
            break


async def _listen_for_utterance(incoming_audio: "asyncio.Queue") -> tuple[str, bool]:
    """Opens a fresh STT session for one turn. Returns (transcript, call_ended)
    -- call_ended is True if Twilio's stream stopped before/while we listened."""
    stream_ended = asyncio.Event()

    async with stt_client.open_session() as stt_socket:

        async def forward():
            while True:
                payload = await incoming_audio.get()
                if payload is None:
                    stream_ended.set()
                    break
                await stt_socket.send_media(decode_media_payload(payload))

        forward_task = asyncio.create_task(forward())
        transcript_task = asyncio.create_task(stt_client.wait_for_final_transcript(stt_socket))
        ended_task = asyncio.create_task(stream_ended.wait())

        done, pending = await asyncio.wait(
            {transcript_task, ended_task}, return_when=asyncio.FIRST_COMPLETED
        )

        for task in pending:
            task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.gather(*pending, return_exceptions=True)

        forward_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await forward_task

        if transcript_task in done:
            return transcript_task.result(), stream_ended.is_set()
        return "", True


async def _speak(websocket, stream_sid: str, reply_audio: bytes, mark_events: "asyncio.Queue"):
    """Sends reply_audio to Twilio and waits for the mark echo confirming
    playback actually finished before returning -- without this, closing (or
    moving to the next turn) can cut the caller off mid-sentence."""
    logger.info("Sending %d bytes of reply audio back to Twilio", len(reply_audio))
    for i in range(0, len(reply_audio), OUTBOUND_CHUNK_SIZE):
        chunk = reply_audio[i : i + OUTBOUND_CHUNK_SIZE]
        await websocket.send_text(build_media_message(stream_sid, chunk))
    mark_name = "reply-done"
    await websocket.send_text(build_mark_message(stream_sid, mark_name))
    logger.info("Audio queued, waiting for Twilio to confirm playback finished")

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

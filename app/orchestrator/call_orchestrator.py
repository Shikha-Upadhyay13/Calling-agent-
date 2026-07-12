import asyncio
import contextlib
import logging

from app.audio.twilio_audio import build_mark_message, build_media_message, decode_media_payload
from app.clients import llm_client, stt_client, tts_client

logger = logging.getLogger(__name__)

OUTBOUND_CHUNK_SIZE = 160  # 20ms of mulaw/8kHz audio per Twilio media frame


async def run_single_exchange(
    websocket, stream_sid: str, incoming_audio: "asyncio.Queue", mark_events: "asyncio.Queue"
):
    """Milestone C: listen for one utterance, generate one reply, speak it, done.
    Multi-turn looping and persistent history are added in Milestone D."""

    async with stt_client.open_session() as stt_socket:

        async def forward_audio_to_stt():
            while True:
                payload = await incoming_audio.get()
                if payload is None:
                    break
                await stt_socket.send_media(decode_media_payload(payload))

        forward_task = asyncio.create_task(forward_audio_to_stt())
        try:
            transcript = await stt_client.wait_for_final_transcript(stt_socket)
        finally:
            forward_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await forward_task

    logger.info("Caller said: %s", transcript)
    if not transcript:
        logger.info("No transcript captured, ending exchange without a reply")
        return

    reply_text = await asyncio.to_thread(
        llm_client.generate_reply, [{"role": "user", "content": transcript}]
    )
    logger.info("Agent replying: %s", reply_text)

    try:
        reply_audio = await asyncio.wait_for(tts_client.synthesize(reply_text), timeout=10)
    except asyncio.TimeoutError:
        logger.error("TTS synthesis timed out after 10s")
        return

    logger.info("Sending %d bytes of reply audio back to Twilio", len(reply_audio))
    for i in range(0, len(reply_audio), OUTBOUND_CHUNK_SIZE):
        chunk = reply_audio[i : i + OUTBOUND_CHUNK_SIZE]
        await websocket.send_text(build_media_message(stream_sid, chunk))
    mark_name = "reply-done"
    await websocket.send_text(build_mark_message(stream_sid, mark_name))
    logger.info("Audio queued, waiting for Twilio to confirm playback finished")

    try:
        # Drain any stale marks, then wait for ours specifically. Playback of
        # ~25kB of mulaw/8kHz audio is roughly len(bytes)/8000 seconds; give
        # generous headroom on top of that before giving up.
        expected_playback_s = len(reply_audio) / 8000
        timeout = max(5.0, expected_playback_s + 5.0)
        while True:
            seen = await asyncio.wait_for(mark_events.get(), timeout=timeout)
            if seen == mark_name:
                break
        logger.info("Twilio confirmed playback finished")
    except asyncio.TimeoutError:
        logger.warning("Never got playback-finished confirmation from Twilio (mark echo timed out)")

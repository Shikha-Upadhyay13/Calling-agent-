import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.orchestrator.call_orchestrator import run_conversation

router = APIRouter()
logger = logging.getLogger(__name__)


@router.websocket("/media-stream")
async def media_stream(websocket: WebSocket):
    """Twilio Media Streams handler. Milestone D: runs a full multi-turn
    conversation (STT -> LLM -> TTS, looped with history) until the caller
    hangs up, instead of Milestone C's single exchange."""
    await websocket.accept()
    audio_queue: asyncio.Queue = asyncio.Queue()
    mark_events: asyncio.Queue = asyncio.Queue()
    stream_started: asyncio.Future = asyncio.get_event_loop().create_future()

    async def receive_loop():
        try:
            while True:
                raw_message = await websocket.receive_text()
                message = json.loads(raw_message)
                event = message.get("event")

                if event == "connected":
                    logger.info("Twilio media stream connected")

                elif event == "start":
                    stream_sid = message["start"]["streamSid"]
                    logger.info("Stream started: %s", stream_sid)
                    if not stream_started.done():
                        stream_started.set_result(stream_sid)

                elif event == "media":
                    await audio_queue.put(message["media"]["payload"])

                elif event == "mark":
                    await mark_events.put(message["mark"]["name"])

                elif event == "stop":
                    logger.info("Stream stopped")
                    break
        except WebSocketDisconnect:
            logger.info("WebSocket disconnected")
        except Exception:
            logger.exception("receive_loop crashed")
        finally:
            await audio_queue.put(None)
            if not stream_started.done():
                stream_started.cancel()

    receive_task = asyncio.create_task(receive_loop())

    stream_sid = None
    try:
        stream_sid = await stream_started
    except asyncio.CancelledError:
        pass

    if stream_sid:
        try:
            await run_conversation(websocket, stream_sid, audio_queue, mark_events)
        except asyncio.CancelledError:
            logger.warning("run_conversation cancelled (caller likely hung up mid-processing)")
        except Exception:
            logger.exception("run_conversation crashed")

    receive_task.cancel()
    try:
        await websocket.close()
    except Exception:
        pass

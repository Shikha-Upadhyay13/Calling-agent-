import base64
import json


def decode_media_payload(payload: str) -> bytes:
    """Twilio's inbound `media.payload` -> raw mulaw/8kHz/mono bytes."""
    return base64.b64decode(payload)


def encode_media_payload(raw_audio: bytes) -> str:
    """Raw mulaw/8kHz/mono bytes -> base64 for an outbound `media` message."""
    return base64.b64encode(raw_audio).decode("ascii")


def build_media_message(stream_sid: str, raw_audio: bytes) -> str:
    """Queue audio for Twilio to play to the caller."""
    return json.dumps(
        {
            "event": "media",
            "streamSid": stream_sid,
            "media": {"payload": encode_media_payload(raw_audio)},
        }
    )


def build_mark_message(stream_sid: str, mark_name: str) -> str:
    """Sent right after a batch of `media` messages; Twilio echoes it back
    once that audio has actually finished playing."""
    return json.dumps(
        {
            "event": "mark",
            "streamSid": stream_sid,
            "mark": {"name": mark_name},
        }
    )


def build_clear_message(stream_sid: str) -> str:
    """Flush any buffered/playing outbound audio immediately (barge-in)."""
    return json.dumps({"event": "clear", "streamSid": stream_sid})

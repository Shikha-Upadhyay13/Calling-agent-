from fastapi import APIRouter, Response
from twilio.rest import Client
from twilio.twiml.voice_response import Connect, VoiceResponse

from app.config import settings

router = APIRouter()

_twilio_client = Client(settings.twilio_account_sid, settings.twilio_auth_token)

GREETING_TEXT = (
    "Hello, this is a test call from your calling agent. "
    "This call may be recorded for quality purposes."
)


@router.post("/call/start")
def start_call():
    """Places an outbound test call to USER_PHONE_NUMBER."""
    call = _twilio_client.calls.create(
        to=settings.user_phone_number,
        from_=settings.twilio_phone_number,
        url=f"{settings.public_base_url}/twiml/answer",
    )
    return {"call_sid": call.sid, "status": call.status}


@router.api_route("/twiml/answer", methods=["GET", "POST"])
def twiml_answer():
    """Twilio fetches this once the call is answered (outbound test call
    or a real inbound call to the Twilio number). Opens a bidirectional
    Media Stream to /media-stream instead of just speaking and hanging up."""
    wss_url = settings.public_base_url.replace("https://", "wss://").replace("http://", "ws://")

    response = VoiceResponse()
    response.say(GREETING_TEXT)
    connect = Connect()
    connect.stream(url=f"{wss_url}/media-stream", track="inbound_track")
    response.append(connect)
    return Response(content=str(response), media_type="application/xml")

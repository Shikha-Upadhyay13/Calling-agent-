import logging

from fastapi import FastAPI

from app.config import settings
from app.routes import call_control, media_stream

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Calling Agent")
app.include_router(call_control.router)
app.include_router(media_stream.router)


@app.get("/health")
def health():
    return {"status": "ok", "public_base_url": settings.public_base_url}

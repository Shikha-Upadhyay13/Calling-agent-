from fastapi import FastAPI

from app.config import settings
from app.routes import call_control

app = FastAPI(title="Calling Agent")
app.include_router(call_control.router)


@app.get("/health")
def health():
    return {"status": "ok", "public_base_url": settings.public_base_url}

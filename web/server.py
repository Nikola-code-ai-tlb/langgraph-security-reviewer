"""FastAPI app: serves the UI and streams reviews over SSE.

Run it:
    uvicorn web.server:app --reload
then open http://127.0.0.1:8000

Endpoints:
    GET /                 -> the single-page UI
    GET /api/health       -> {"mode": "live"|"schematic"}
    GET /api/review?url=  -> text/event-stream of review events
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .review_service import current_mode, iter_review_events

_STATIC = Path(__file__).resolve().parent / "static"

app = FastAPI(title="LangGraph Security Reviewer")


@app.get("/api/health")
def health() -> dict:
    return {"mode": current_mode()}


@app.get("/api/review")
def review(url: str) -> StreamingResponse:
    """Stream review events as Server-Sent Events.

    Starlette runs this sync generator in a threadpool, so the blocking GitHub
    fetch and LLM calls don't stall the event loop.
    """

    def event_stream():
        for event in iter_review_events(url):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable proxy buffering if present
        },
    )


@app.get("/")
def index() -> FileResponse:
    return FileResponse(_STATIC / "index.html")


# Serve CSS/JS/assets. Mounted last so it doesn't shadow the API routes.
app.mount("/static", StaticFiles(directory=_STATIC), name="static")

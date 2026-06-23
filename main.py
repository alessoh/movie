"""FastAPI application: routes, progress stream, static serving.

Endpoints
  GET  /                      single light-mode page
  POST /api/upload            create session, save file, enforce quota
  POST /api/start/{token}     kick off the background build job
  GET  /api/status/{token}    current session status as JSON (polling fallback)
  GET  /api/stream/{token}    server-sent events stream of status updates
  GET  /api/movie/{token}     stream the finished MP4 (inline / download)

All keys live only on the server (config.py); none are ever sent to the client.
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles

from config import WEB_DIR, settings
from pipeline.orchestrator import run_job
from pipeline.state import store

app = FastAPI(title="novel-to-movie")

ALLOWED_SUFFIXES = {".txt", ".md", ".pdf", ".docx", ".doc"}
MAX_UPLOAD_BYTES = settings.max_upload_mb * 1024 * 1024


# --------------------------------------------------------------------------- #
# Startup: fail fast if required keys are missing in real mode.
# --------------------------------------------------------------------------- #
@app.on_event("startup")
async def _startup() -> None:
    missing = settings.required_keys_present()
    if missing:
        raise RuntimeError(
            "Missing required environment keys for RUN_MODE=real: "
            + ", ".join(missing)
            + ". Set them in .env, or run with RUN_MODE=mock for a free test."
        )
    mode = "MOCK" if settings.is_mock else "REAL"
    print(f"[novel-to-movie] starting in {mode} mode")
    _start_cleanup_thread()


# --------------------------------------------------------------------------- #
# Page + static assets
# --------------------------------------------------------------------------- #
@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    return HTMLResponse((WEB_DIR / "index.html").read_text(encoding="utf-8"))


app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


# --------------------------------------------------------------------------- #
# Upload + quota
# --------------------------------------------------------------------------- #
@app.post("/api/upload")
async def upload(file: UploadFile = File(...)) -> JSONResponse:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail="Please upload a plain text (.txt), Word (.docx), or PDF (.pdf) file.",
        )

    data = await file.read()
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File is too large. The limit is {settings.max_upload_mb} MB.",
        )

    session = store.create()
    work_dir = Path(session.work_dir)
    safe_name = "upload" + (suffix if suffix in ALLOWED_SUFFIXES else ".txt")
    upload_path = work_dir / safe_name
    upload_path.write_bytes(data)
    session.upload_path = str(upload_path)

    return JSONResponse({"token": session.token})


@app.post("/api/start/{token}")
async def start(token: str) -> JSONResponse:
    session = store.get(token)
    if not session:
        raise HTTPException(status_code=404, detail="Unknown session.")
    if not session.upload_path or not Path(session.upload_path).exists():
        raise HTTPException(status_code=400, detail="No uploaded file for this session.")

    # Per-session quota: one movie per visit (plus guard against double-start).
    if session.movies_made >= settings.max_movies_per_session:
        raise HTTPException(
            status_code=429,
            detail="This session has already used its free movie.",
        )
    if session.status not in ("queued",):
        return JSONResponse({"token": token, "status": session.status})

    # Run the build on a background thread (FastAPI process, in-memory job).
    store.set_phase(token, "reading", "Starting up", progress=2)
    thread = threading.Thread(target=run_job, args=(token,), daemon=True)
    thread.start()
    return JSONResponse({"token": token, "status": "started"})


# --------------------------------------------------------------------------- #
# Progress: polling + SSE
# --------------------------------------------------------------------------- #
@app.get("/api/status/{token}")
async def status(token: str) -> JSONResponse:
    session = store.get(token)
    if not session:
        raise HTTPException(status_code=404, detail="Unknown session.")
    return JSONResponse(session.public_dict())


@app.get("/api/stream/{token}")
async def stream(token: str) -> StreamingResponse:
    session = store.get(token)
    if not session:
        raise HTTPException(status_code=404, detail="Unknown session.")

    async def event_gen():
        last = None
        # Stream until the job reaches a terminal state, then close.
        while True:
            s = store.get(token)
            if not s:
                break
            payload = s.public_dict()
            snapshot = json.dumps(payload, sort_keys=True)
            if snapshot != last:
                last = snapshot
                yield f"data: {snapshot}\n\n"
            if s.status in ("ready", "error"):
                break
            await asyncio.sleep(1.0)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --------------------------------------------------------------------------- #
# Delivery
# --------------------------------------------------------------------------- #
@app.get("/api/movie/{token}")
async def movie(token: str) -> FileResponse:
    session = store.get(token)
    if not session or not session.movie_path:
        raise HTTPException(status_code=404, detail="Movie not ready.")
    path = Path(session.movie_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Movie file is gone (session expired).")
    return FileResponse(
        str(path),
        media_type="video/mp4",
        filename="your-movie.mp4",
    )


# --------------------------------------------------------------------------- #
# Cleanup sweep: delete session folders older than the TTL.
# --------------------------------------------------------------------------- #
def _start_cleanup_thread() -> None:
    def sweep_loop() -> None:
        ttl = settings.session_ttl_minutes * 60
        while True:
            try:
                now = time.time()
                for s in store.all():
                    if now - s.created_at > ttl:
                        work_dir = Path(s.work_dir)
                        _rmtree(work_dir)
                        store.delete(s.token)
            except Exception:
                pass
            time.sleep(60)

    threading.Thread(target=sweep_loop, daemon=True).start()


def _rmtree(path: Path) -> None:
    import shutil

    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=False)

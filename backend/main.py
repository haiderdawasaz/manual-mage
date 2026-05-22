# backend/main.py
"""
FastAPI application entry point.

Endpoints:
  GET  /health                          — liveness probe
  POST /jobs/start                      — upload video, start background pipeline
  GET  /download/{job_id}?token={token} — stream DOCX to browser
"""

from __future__ import annotations
import asyncio
import logging
import shutil
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import aiofiles
from fastapi import (
    BackgroundTasks,
    FastAPI,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from config import ALLOWED_ORIGINS, JOBS_BASE_DIR
from firestore_service import get_job, create_job, mark_cancelled
from models import HealthResponse, StartJobResponse
from pipeline.clip_model import is_loaded, load_model
from pipeline.asr_model import load_asr_model
from pipeline.orchestrator import run_pipeline, request_cancellation

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up — loading CLIP and Qwen3-ASR models…")
    try:
        await asyncio.to_thread(load_model)
        await asyncio.to_thread(load_asr_model)
        logger.info("Models ready (CLIP + Qwen3-ASR)")
    except Exception as exc:
        logger.error("Failed to load models: %s", exc)
    yield
    logger.info("Shutting down")


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="ManualMage API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", model_loaded=is_loaded())


# ── Job Management ────────────────────────────────────────────────────────────
@app.post("/jobs/start", response_model=StartJobResponse)
async def start_job(
    file: UploadFile,
    background_tasks: BackgroundTasks,
) -> StartJobResponse:
    """
    Accept a video upload, create Firestore record, and trigger pipeline.
    Processing happens in the background.
    """
    job_id: str = str(uuid.uuid4())
    job_dir: Path = JOBS_BASE_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    original_name = file.filename or "upload.mp4"
    video_path = job_dir / "input.mp4"

    logger.info("[%s] Receiving upload: %s", job_id, original_name)

    # Stream upload to disk
    try:
        async with aiofiles.open(video_path, "wb") as out:
            while chunk := await file.read(1024 * 1024):  # 1 MB chunks
                await out.write(chunk)
    except Exception as exc:
        logger.error("[%s] Upload write failed: %s", job_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save uploaded file.",
        )

    logger.info("[%s] Upload saved to %s", job_id, video_path)

    # 1. Create Firestore record (status: pending)
    await create_job(job_id, original_name)

    # 2. Trigger pipeline as a background task
    background_tasks.add_task(
        run_pipeline,
        job_id=job_id,
        video_file_name=original_name,
        video_path=video_path,
    )

    return StartJobResponse(job_id=job_id)


# ── Cancel ────────────────────────────────────────────────────────────────────
@app.post("/jobs/{job_id}/cancel", status_code=200)
async def cancel_job(job_id: str) -> dict:
    """
    Terminate a running (or pending) job:
      1. Signal the background pipeline to stop at its next checkpoint.
      2. Delete all files for this job from disk.
      3. Mark the Firestore document as cancelled.
    Safe to call even if the job has already finished — it will just clean up.
    """
    # 1. Signal the pipeline (no-op if it already finished)
    request_cancellation(job_id)

    # 2. Delete job directory from disk
    job_dir = JOBS_BASE_DIR / job_id
    if job_dir.exists():
        shutil.rmtree(str(job_dir), ignore_errors=True)
        logger.info("[%s] Job files deleted via cancel", job_id)

    # 3. Update Firestore (best-effort — don’t 500 if doc not found)
    try:
        await mark_cancelled(job_id)
    except Exception as exc:
        logger.warning("[%s] Could not mark cancelled in Firestore: %s", job_id, exc)

    return {"status": "cancelled", "job_id": job_id}


# ── Download ──────────────────────────────────────────────────────────────────
@app.get("/download/{job_id}")
async def download_docx(
    job_id: str,
    token: str,
) -> FileResponse:
    """
    Verify token + ownership + expiry then stream DOCX to browser.
    """
    # Fetch job from Firestore
    job_doc = await get_job(job_id)
    if not job_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")

    # Token check
    if job_doc.get("downloadToken") != token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid token.")

    # Expiry check
    expires_at = job_doc.get("expiresAt")
    if expires_at:
        expiry_dt = expires_at if hasattr(expires_at, "tzinfo") else expires_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expiry_dt:
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Download link has expired.",
            )

    # File existence check
    output_path = JOBS_BASE_DIR / job_id / "output.docx"
    if not output_path.exists():
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Document no longer available.",
        )

    video_file_name: str = job_doc.get("videoFileName", "manual")
    base_name = video_file_name.rsplit(".", 1)[0]
    download_name = f"{base_name}_manual.docx"

    logger.info("[%s] Streaming DOCX", job_id)

    return FileResponse(
        path=str(output_path),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=download_name,
        headers={"Content-Disposition": f'attachment; filename="{download_name}"'},
    )
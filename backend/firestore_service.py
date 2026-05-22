# backend/firestore_service.py
"""
Thin wrapper around Firestore operations for job documents.
Uses google-cloud-firestore AsyncClient with retries.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from google.cloud import firestore
from google.oauth2 import service_account
from models import JobProgress, JobStatus
from config import FIREBASE_CREDENTIALS_JSON

logger = logging.getLogger(__name__)

JOBS_COLLECTION = "jobs"
MAX_RETRIES = 3

# Build credentials from the service account file so no ADC / gcloud login needed.

_cred_info: dict = json.loads(FIREBASE_CREDENTIALS_JSON)
_creds = service_account.Credentials.from_service_account_info(
    _cred_info,
    scopes=["https://www.googleapis.com/auth/cloud-platform"],
)
db = firestore.AsyncClient(credentials=_creds, project=_cred_info["project_id"])

async def _retry(coro_fn, *args, **kwargs):
    """Run an async Firestore call with exponential backoff retries."""
    for attempt in range(MAX_RETRIES):
        try:
            return await coro_fn(*args, **kwargs)
        except Exception as exc:
            if attempt == MAX_RETRIES - 1:
                raise
            wait = 2 ** attempt
            logger.warning("Firestore retry %d after %ds: %s", attempt + 1, wait, exc)
            await asyncio.sleep(wait)

# ── Write helpers ─────────────────────────────────────────────────────────────

async def create_job(job_id: str, video_file_name: str) -> None:
    doc_ref = db.collection(JOBS_COLLECTION).document(job_id)
    payload = {
        "id": job_id,
        "videoFileName": video_file_name,
        "status": "pending",  # Start as pending
        "progress": {
            "stage": "idle",
            "totalFrames": 0,
            "deduplicatedFrames": 0,
            "analysedFrames": 0,
            "totalAudioChunks": 0,
            "transcribedChunks": 0,
        },
        "hasAudio": False,
        "createdAt": firestore.SERVER_TIMESTAMP,
        "updatedAt": firestore.SERVER_TIMESTAMP,
    }
    await _retry(doc_ref.set, payload)
    logger.info("[%s] Firestore job created (pending)", job_id)

async def update_job(job_id: str, **fields) -> None:
    fields["updatedAt"] = firestore.SERVER_TIMESTAMP
    doc_ref = db.collection(JOBS_COLLECTION).document(job_id)
    await _retry(doc_ref.update, fields)

async def update_progress(job_id: str, progress: JobProgress) -> None:
    await update_job(
        job_id,
        progress={
            "stage": progress.stage,
            "totalFrames": progress.total_frames,
            "deduplicatedFrames": progress.deduplicated_frames,
            "analysedFrames": progress.analysed_frames,
            "totalAudioChunks": progress.total_audio_chunks,
            "transcribedChunks": progress.transcribed_chunks,
        },
    )

async def mark_complete(
    job_id: str,
    download_token: str,
    expires_at: datetime,
    has_audio: bool,
) -> None:
    now = datetime.now(timezone.utc)
    await update_job(
        job_id,
        status=JobStatus.COMPLETE.value,
        downloadToken=download_token,
        completedAt=now,
        expiresAt=expires_at,
        hasAudio=has_audio,
    )
    logger.info("[%s] Firestore marked complete", job_id)

async def mark_error(job_id: str, error: str) -> None:
    await update_job(job_id, status=JobStatus.ERROR.value, error=error)
    logger.info("[%s] Firestore marked error: %s", job_id, error)

async def mark_expired(job_id: str) -> None:
    await update_job(job_id, status=JobStatus.EXPIRED.value)
    logger.info("[%s] Firestore marked expired", job_id)

async def mark_cancelled(job_id: str) -> None:
    await update_job(job_id, status=JobStatus.CANCELLED.value)
    logger.info("[%s] Firestore marked cancelled", job_id)

async def delete_job(job_id: str) -> None:
    """Hard-delete the Firestore document for a job."""
    doc_ref = db.collection(JOBS_COLLECTION).document(job_id)
    await _retry(doc_ref.delete)
    logger.info("[%s] Firestore document deleted", job_id)

# ── Read helpers ──────────────────────────────────────────────────────────────

async def get_job(job_id: str) -> Optional[dict]:
    doc_ref = db.collection(JOBS_COLLECTION).document(job_id)
    snap = await _retry(doc_ref.get)
    if not snap.exists:
        return None
    return snap.to_dict()
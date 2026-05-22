# backend/pipeline/orchestrator.py
"""
Pipeline orchestrator — runs all stages sequentially for a single job.
Updates Firestore status at each stage; frontend tracks progress via Firestore listeners.
"""
from __future__ import annotations

import asyncio
import logging
import secrets
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config import (
    AUDIO_CHUNK_SECONDS,
    DOWNLOAD_EXPIRY_SECONDS,
    FRAMES_PER_SECOND,
    JOBS_BASE_DIR,
    MAX_FRAME_WIDTH_PX,
)
from firestore_service import mark_complete, mark_error, mark_expired, mark_cancelled, update_progress, update_job
from models import JobProgress
from pipeline.ffmpeg_stage import (
    extract_audio,
    extract_frames,
    has_audio_stream,
    resize_frame,
    extract_audio_for_frames,
)
from pipeline.dedup_stage import deduplicate_frames
from pipeline.transcription_stage import align_transcript_to_frames, transcribe_chunks
from pipeline.analysis_stage import analyse_frames
from pipeline.docx_stage import assemble_docx

# ── Cancellation registry ─────────────────────────────────────────────────────
# Jobs added here will be stopped at the next pipeline checkpoint.
_cancelled_jobs: set[str] = set()

def request_cancellation(job_id: str) -> None:
    """Signal the running pipeline for this job to stop at its next checkpoint."""
    _cancelled_jobs.add(job_id)
    logger_instance = logging.getLogger(__name__)
    logger_instance.info("[%s] Cancellation requested", job_id)

def _check_cancelled(job_id: str) -> None:
    """Raise asyncio.CancelledError if this job has been marked for cancellation."""
    if job_id in _cancelled_jobs:
        raise asyncio.CancelledError(f"Job {job_id} was cancelled by the user")

logger = logging.getLogger(__name__)


async def run_pipeline(
    job_id: str,
    video_file_name: str,
    video_path: Path,
) -> None:
    """
    Execute the full processing pipeline.
    Progress is reported solely via Firestore updates.
    """
    job_dir = JOBS_BASE_DIR / job_id
    frames_dir = job_dir / "frames"
    resized_dir = job_dir / "resized"
    audio_dir = job_dir / "audio"
    output_path = job_dir / "output.docx"

    progress = JobProgress()
    try:
        # ── Mark as processing ───────────────────────────────────────────────
        await update_job(job_id, status="processing")
        _check_cancelled(job_id)

        # ── Stage 2: Frame extraction ─────────────────────────────────────────
        logger.info("[%s] Stage 2: extracting frames", job_id)
        progress.stage = "extracting"
        await update_progress(job_id, progress)

        audio_present = await has_audio_stream(video_path, job_id)
        all_frames = await extract_frames(video_path, frames_dir, job_id)
        progress.total_frames = len(all_frames)

        if audio_present:
            full_audio = await extract_audio(video_path, audio_dir, job_id)

        await update_progress(job_id, progress)
        _check_cancelled(job_id)

        # ── Stage 3: Frame deduplication ──────────────────────────────────────
        logger.info("[%s] Stage 3: deduplicating frames", job_id)
        progress.stage = "deduplicating"
        await update_progress(job_id, progress)

        key_frames = await deduplicate_frames(all_frames, job_id)
        progress.deduplicated_frames = len(key_frames)

        await update_progress(job_id, progress)
        _check_cancelled(job_id)

        # ── Stage 4: Audio transcription ──────────────────────────────────────
        transcript_map: dict[Path, str] = {}

        if audio_present:
            logger.info("[%s] Stage 4: transcribing audio", job_id)
            progress.stage = "transcribing"

            audio_chunks = await extract_audio_for_frames(full_audio, key_frames, audio_dir, job_id, FRAMES_PER_SECOND)
            progress.total_audio_chunks = len(audio_chunks)

            await update_progress(job_id, progress)
            _check_cancelled(job_id)

            audio_transcripts = await transcribe_chunks(audio_chunks, job_id)
            progress.transcribed_chunks = len(audio_transcripts)

            transcript_map = align_transcript_to_frames(
                audio_transcripts, key_frames
            )

            await update_progress(job_id, progress)
            _check_cancelled(job_id)
        else:
            logger.info("[%s] Stage 4: no audio — skipping transcription", job_id)

        # ── Resize frames before Gemini API calls ─────────────────────────────
        resized_dir.mkdir(parents=True, exist_ok=True)
        resized_frames: list[Path] = []

        for frame in key_frames:
            resized_path = resized_dir / frame.name
            await resize_frame(frame, resized_path, MAX_FRAME_WIDTH_PX, job_id)
            resized_frames.append(resized_path)

        # Rebuild transcript_map with resized frame keys
        resized_transcript_map: dict[Path, str] = {}
        for original, resized in zip(key_frames, resized_frames):
            resized_transcript_map[resized] = transcript_map.get(original, "")

        _check_cancelled(job_id)

        # ── Stage 5: Step analysis ────────────────────────────────────────────
        logger.info("[%s] Stage 5: analysing frames with Gemini", job_id)
        progress.stage = "analysing"
        await update_progress(job_id, progress)

        descriptions = await analyse_frames(resized_frames, resized_transcript_map, job_id)
        progress.analysed_frames = len(descriptions)

        await update_progress(job_id, progress)
        _check_cancelled(job_id)

        # ── Stage 6: Document assembly ────────────────────────────────────────
        logger.info("[%s] Stage 6: assembling DOCX", job_id)
        progress.stage = "assembling"
        await update_progress(job_id, progress)

        await asyncio.to_thread(
            assemble_docx,
            video_file_name,
            job_id,
            resized_frames,
            descriptions,
            resized_transcript_map,
            audio_present,
            output_path,
        )

        # ── Firestore: mark complete ──────────────────────────────────────────
        download_token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=DOWNLOAD_EXPIRY_SECONDS)

        await mark_complete(
            job_id,
            download_token=download_token,
            expires_at=expires_at,
            has_audio=audio_present,
        )

        logger.info("[%s] Pipeline complete", job_id)

        # ── Schedule cleanup after expiry window ──────────────────────────────
        asyncio.create_task(cleanup_job(job_id, delay_seconds=DOWNLOAD_EXPIRY_SECONDS))

    except asyncio.CancelledError:
        logger.info("[%s] Pipeline cancelled by user — cleaning up", job_id)
        _cancelled_jobs.discard(job_id)
        # Files already deleted by the cancel endpoint; just update Firestore.
        try:
            await mark_cancelled(job_id)
        except Exception as fs_exc:
            logger.warning("[%s] Could not mark cancelled in Firestore: %s", job_id, fs_exc)

    except Exception as exc:
        logger.exception("[%s] Pipeline failed: %s", job_id, exc)
        await mark_error(job_id, str(exc))


async def cleanup_job(job_id: str, delay_seconds: int = 600) -> None:
    """
    Wait delay_seconds then delete all job files from /tmp and mark Firestore expired.
    Launched as a fire-and-forget asyncio task — never awaited by the caller.
    """
    await asyncio.sleep(delay_seconds)

    job_dir = JOBS_BASE_DIR / job_id
    shutil.rmtree(str(job_dir), ignore_errors=True)
    logger.info("[%s] Job files deleted from /tmp", job_id)

    try:
        await mark_expired(job_id)
    except Exception as exc:
        logger.warning("[%s] Failed to mark expired in Firestore: %s", job_id, exc)
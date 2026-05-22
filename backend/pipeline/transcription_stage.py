# backend/pipeline/transcription_stage.py
"""
Stage 4 — Audio transcription using Qwen3-ASR.

Processes each 30-second audio chunk sequentially.
Stitches results into time-ranged transcript segments.
Aligns segments to key frame timestamps by time range (not word-level).
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from config import MAX_INFERENCE_RETRIES
from pipeline.asr_model import get_asr_model


logger = logging.getLogger(__name__)

TRANSCRIPTION_PROMPT = (
    "Transcribe the speech in this audio clip accurately. "
    "Return only the spoken words — no timestamps, no speaker labels, no commentary."
)


def _run_transcription_inference(audio_chunk_path: Path) -> str:
    """
    Inference via Qwen3-ASR (local).
    """
    model = get_asr_model()
    # Qwen3ASRModel.transcribe returns the text directly or a dict
    result = model.transcribe(str(audio_chunk_path))
    if isinstance(result, dict):
        return result.get("text", "").strip()
    return str(result).strip()


async def transcribe_chunks(
    chunks: list[Path],
    job_id: str,
) -> dict[Path, str]:
    """
    Transcribe exact audio slices concurrently.
    Returns mapping from audio slice path to transcript text.
    """
    sem = asyncio.Semaphore(3)
    results: dict[Path, str] = {}

    async def _process(chunk: Path):
        async with sem:
            for attempt in range(MAX_INFERENCE_RETRIES):
                try:
                    text = await asyncio.to_thread(_run_transcription_inference, chunk)
                    results[chunk] = text
                    logger.debug("[%s] Transcribed slice %s", job_id, chunk.name)
                    return
                except Exception as exc:
                    logger.warning(
                        "[%s] Transcription attempt %d failed for slice %s: %s",
                        job_id, attempt + 1, chunk.name, exc,
                    )
                    if attempt < MAX_INFERENCE_RETRIES - 1:
                        await asyncio.sleep(2 ** attempt)
            results[chunk] = ""

    tasks = [_process(c) for c in chunks]
    await asyncio.gather(*tasks)

    logger.info("[%s] Transcription complete: %d slices", job_id, len(results))
    return results


def align_transcript_to_frames(
    audio_transcripts: dict[Path, str],
    frame_paths: list[Path],
) -> dict[Path, str]:
    """
    Map each key frame to the transcript of its exact corresponding audio slice.
    """
    alignment: dict[Path, str] = {}

    for frame_path in frame_paths:
        expected_audio_name = f"{frame_path.stem}.mp3"
        
        matched_text = ""
        for audio_path, text in audio_transcripts.items():
            if audio_path.name == expected_audio_name:
                matched_text = text
                break
                
        alignment[frame_path] = matched_text

    return alignment
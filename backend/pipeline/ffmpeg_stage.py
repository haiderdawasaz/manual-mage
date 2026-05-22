# backend/pipeline/ffmpeg_stage.py
"""
Stage 2 — Frame & audio extraction via FFmpeg.

All FFmpeg calls use asyncio.create_subprocess_exec — never blocking subprocess.
"""
from __future__ import annotations
import subprocess
import asyncio
import logging
from pathlib import Path

from config import AUDIO_CHUNK_SECONDS, FRAMES_PER_SECOND
import sys

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

logger = logging.getLogger(__name__)


# async def _run_ffmpeg(*args: str, job_id: str) -> None:
#     """Execute an FFmpeg command, raising RuntimeError on non-zero exit."""
#     cmd = ["ffmpeg", "-y", *args]
#     logger.info("[%s] FFmpeg: %s", job_id, " ".join(cmd))

#     proc = await asyncio.create_subprocess_exec(
#         *cmd,
#         stdout=asyncio.subprocess.PIPE,
#         stderr=asyncio.subprocess.PIPE,
#     )
#     _, stderr = await proc.communicate()

#     if proc.returncode != 0:
#         error_text = stderr.decode(errors="replace")[-500:]  # last 500 chars
#         raise RuntimeError(f"FFmpeg failed (code {proc.returncode}): {error_text}")

def _run_ffmpeg_sync(*args: str, job_id: str) -> None:
    """Synchronous FFmpeg execution — intended to be called via asyncio.to_thread."""
    cmd = ["ffmpeg", "-y", *args]
    logger.info("[%s] FFmpeg: %s", job_id, " ".join(cmd))

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if result.returncode != 0:
        error_text = result.stderr.decode(errors="replace")[-500:]
        raise RuntimeError(f"FFmpeg failed (code {result.returncode}): {error_text}")


async def _run_ffmpeg(*args: str, job_id: str) -> None:
    """Async wrapper — offloads blocking FFmpeg call to a thread pool."""
    await asyncio.to_thread(_run_ffmpeg_sync, *args, job_id=job_id)


async def has_audio_stream(video_path: Path, job_id: str) -> bool:
    """Return True if the video contains at least one audio stream."""
    # proc = await asyncio.create_subprocess_exec(
    #     "ffprobe",
    #     "-v", "error",
    #     "-select_streams", "a:0",
    #     "-show_entries", "stream=codec_type",
    #     "-of", "default=noprint_wrappers=1:nokey=1",
    #     str(video_path),
    #     stdout=asyncio.subprocess.PIPE,
    #     stderr=asyncio.subprocess.PIPE,
    # )
    # stdout, _ = await proc.communicate()
    # return stdout.strip() == "audio"
    return await asyncio.to_thread(sync_has_audio, video_path)

def sync_has_audio (video_path: Path) -> bool:
    cmd = [ "ffprobe",
        "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "stream=codec_type",
        "-of", "default=noprint_wrappers=1:nokey=1", str(video_path) ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return "audio" in result.stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False
    

async def extract_frames(
    video_path: Path,
    frames_dir: Path,
    job_id: str,
) -> list[Path]:
    """
    Extract 1 frame per second as JPEG into frames_dir.
    Returns sorted list of frame paths.
    """
    frames_dir.mkdir(parents=True, exist_ok=True)

    await _run_ffmpeg(
        "-i", str(video_path),
        "-vf", f"fps={FRAMES_PER_SECOND},scale=1920:-1",
        "-q:v", "4",                          # high JPEG quality
        str(frames_dir / "frame_%04d.jpg"),
        job_id=job_id,
    )

    frames = sorted(frames_dir.glob("frame_*.jpg"))
    logger.info("[%s] Extracted %d frames", job_id, len(frames))
    return frames


async def extract_audio(
    video_path: Path,
    audio_dir: Path,
    job_id: str,
) -> Path:
    """Extract full audio track as MP3."""
    audio_dir.mkdir(parents=True, exist_ok=True)
    full_audio = audio_dir / "full.mp3"

    await _run_ffmpeg(
        "-i", str(video_path),
        "-vn",                                # no video
        "-acodec", "libmp3lame",
        "-q:a", "2",
        str(full_audio),
        job_id=job_id,
    )

    logger.info("[%s] Audio extracted to %s", job_id, full_audio)
    return full_audio


async def split_audio_chunks(
    full_audio: Path,
    audio_dir: Path,
    job_id: str,
) -> list[Path]:
    """
    Split full audio into AUDIO_CHUNK_SECONDS-second MP3 chunks.
    Returns sorted list of chunk paths.
    """
    await _run_ffmpeg(
        "-i", str(full_audio),
        "-f", "segment",
        "-segment_time", str(AUDIO_CHUNK_SECONDS),
        "-c", "copy",
        str(audio_dir / "chunk_%03d.mp3"),
        job_id=job_id,
    )

    chunks = sorted(audio_dir.glob("chunk_*.mp3"))
    logger.info("[%s] Split into %d audio chunks", job_id, len(chunks))
    return chunks


async def resize_frame(
    frame_path: Path,
    output_path: Path,
    max_width: int,
    job_id: str,
) -> None:
    """Resize a single frame to max_width px, preserving aspect ratio."""
    await _run_ffmpeg(
        "-i", str(frame_path),
        "-vf", f"scale='min({max_width},iw)':-2",
        str(output_path),
        job_id=job_id,
    )


async def extract_audio_for_frames(
    full_audio: Path,
    key_frames: list[Path],
    audio_dir: Path,
    job_id: str,
    fps: int = 1,
) -> list[Path]:
    """
    Slice the full audio into pieces matching the deduplicated frames' time intervals.
    """
    slices: list[Path] = []
    
    # Parse frame indices
    frame_times: list[tuple[Path, float]] = []
    for f_path in key_frames:
        try:
            f_idx = int(f_path.stem.split("_")[1])
            frame_times.append((f_path, f_idx / fps))
        except (IndexError, ValueError):
            pass
            
    frame_times.sort(key=lambda x: x[1])

    # For each frame, slice the audio from its time to the next frame's time
    for i, (f_path, start_time) in enumerate(frame_times):
        # We cap the maximum duration of the last chunk to a reasonable number like 600s,
        # or we just let ffmpeg run to the end by not specifying -to for the last chunk.
        # But to keep it simple, we can compute the duration.
        slice_path = audio_dir / f"{f_path.stem}.mp3"
        
        args = ["-i", str(full_audio), "-ss", str(start_time)]
        if i + 1 < len(frame_times):
            duration = frame_times[i+1][1] - start_time
            args.extend(["-t", str(duration)])
            
        args.extend(["-c", "copy", str(slice_path)])
        
        await _run_ffmpeg(*args, job_id=job_id)
        slices.append(slice_path)
        
    logger.info("[%s] Sliced %d precise audio chunks", job_id, len(slices))
    return slices
# backend/models.py
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    PROCESSING = "processing"
    COMPLETE = "complete"
    EXPIRED = "expired"
    ERROR = "error"
    CANCELLED = "cancelled"


class JobProgress(BaseModel):
    stage: Optional[str] = None
    total_frames: int = 0
    deduplicated_frames: int = 0
    analysed_frames: int = 0
    total_audio_chunks: int = 0
    transcribed_chunks: int = 0


class ProcessingJob(BaseModel):
    id: str
    user_id: str
    video_file_name: str
    status: JobStatus = JobStatus.PROCESSING
    progress: JobProgress = Field(default_factory=JobProgress)
    has_audio: bool = False
    completed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    download_token: Optional[str] = None
    error: Optional[str] = None


# ── HTTP response shapes ──────────────────────────────────────────────────────

class StartJobResponse(BaseModel):
    job_id: str


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool


# ── WebSocket event shapes (server → client) ──────────────────────────────────

class WsExtractingEvent(BaseModel):
    stage: str = "extracting"
    total_frames: int

    def to_ws(self) -> dict:
        return {"stage": "extracting", "totalFrames": self.total_frames}


class WsDeduplicatingEvent(BaseModel):
    stage: str = "deduplicating"
    kept: int
    total: int

    def to_ws(self) -> dict:
        return {"stage": "deduplicating", "kept": self.kept, "total": self.total}


class WsTranscribingEvent(BaseModel):
    stage: str = "transcribing"
    chunks_processed: int
    total_chunks: int

    def to_ws(self) -> dict:
        return {
            "stage": "transcribing",
            "chunksProcessed": self.chunks_processed,
            "totalChunks": self.total_chunks,
        }


class WsAnalysingEvent(BaseModel):
    stage: str = "analysing"
    framed: int
    total_frames: int

    def to_ws(self) -> dict:
        return {"stage": "analysing", "framed": self.framed, "totalFrames": self.total_frames}


class WsAssemblingEvent(BaseModel):
    stage: str = "assembling"

    def to_ws(self) -> dict:
        return {"stage": "assembling"}


class WsCompleteEvent(BaseModel):
    stage: str = "complete"
    download_ready: bool = True

    def to_ws(self) -> dict:
        return {"stage": "complete", "downloadReady": True}


class WsErrorEvent(BaseModel):
    stage: str = "error"
    message: str

    def to_ws(self) -> dict:
        return {"stage": "error", "message": self.message}
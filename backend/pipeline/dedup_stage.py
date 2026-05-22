# backend/pipeline/dedup_stage.py
"""
Stage 3 — Frame deduplication using Gemma 4 E4B.

Compares each frame to the previous accepted frame.
Keeps only frames that represent a meaningfully different step.
Uses a low visual token budget (140) for speed.
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

from config import MAX_INFERENCE_RETRIES
from pipeline.clip_model import get_model, get_processor

logger = logging.getLogger(__name__)

# Similarity threshold: 1.0 is identical, < 0.98 is usually "different"
DEDUP_THRESHOLD = 0.98


def _run_dedup_inference(
    current_frame_path: Path,
    previous_frame_path: Optional[Path],
) -> dict:
    """
    Compare frames using CLIP embeddings and cosine similarity.
    Returns {"different": bool, "reason": str}.
    """
    import torch
    from PIL import Image

    if previous_frame_path is None:
        return {"different": True, "reason": "First frame"}

    processor = get_processor()
    model = get_model()
    device = next(model.parameters()).device

    # Load and process images
    try:
        curr_img = Image.open(current_frame_path).convert("RGB")
        prev_img = Image.open(previous_frame_path).convert("RGB")
        
        inputs = processor(images=[curr_img, prev_img], return_tensors="pt").to(device)
        
        with torch.no_grad():
            outputs = model.get_image_features(**inputs)
            
            # In some versions of transformers, get_image_features returns a BaseModelOutputWithPooling
            image_features = outputs if isinstance(outputs, torch.Tensor) else outputs.pooler_output
            
            # Normalize embeddings
            image_features = image_features / image_features.norm(p=2, dim=-1, keepdim=True)
            
            # Cosine similarity is the dot product of normalized embeddings
            similarity = (image_features[0] @ image_features[1].T).item()
            
        is_different = similarity < DEDUP_THRESHOLD
        
        return {
            "different": is_different,
            "reason": f"Similarity: {similarity:.4f}"
        }
    except Exception as exc:
        logger.error("Deduplication error: %s", exc)
        return {"different": True, "reason": f"Error: {exc}"}


async def deduplicate_frames(
    frames: list[Path],
    job_id: str,
) -> list[Path]:
    """
    Filter frames to only those representing meaningfully different steps.
    Returns list of kept frame paths.
    """
    if not frames:
        return []

    kept: list[Path] = []
    previous_kept: Optional[Path] = None

    for i, frame in enumerate(frames):
        result = None

        for attempt in range(MAX_INFERENCE_RETRIES):
            try:
                result = await asyncio.to_thread(
                    _run_dedup_inference,
                    frame,
                    previous_kept,
                )
                break
            except Exception as exc:
                logger.warning(
                    "[%s] Dedup inference attempt %d failed for frame %d: %s",
                    job_id, attempt + 1, i, exc,
                )
                if attempt < MAX_INFERENCE_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)

        if result is None:
            # On complete failure, keep the frame (fail-safe)
            logger.error("[%s] Dedup failed for frame %d — keeping by default", job_id, i)
            kept.append(frame)
            previous_kept = frame
            continue

        if result.get("different", True):
            kept.append(frame)
            previous_kept = frame
            logger.debug(
                "[%s] Frame %d kept: %s", job_id, i, result.get("reason", "")
            )
        else:
            logger.debug(
                "[%s] Frame %d dropped: %s", job_id, i, result.get("reason", "")
            )

    logger.info(
        "[%s] Deduplication complete: kept %d of %d frames",
        job_id, len(kept), len(frames),
    )
    return kept
# backend/pipeline/asr_model.py
"""
Manages the local Qwen3-ASR model instance.
"""
from __future__ import annotations
import os
import logging
from typing import Optional
import torch
import gc

from config import LOCAL_ASR_MODEL_ID

logger = logging.getLogger(__name__)

# Module-level singleton
_asr_model: Optional[object] = None

def load_asr_model() -> None:
    """
    Initialize the Qwen3-ASR model locally.
    """
    global _asr_model
    
    try:
        from qwen_asr import Qwen3ASRModel
        
        logger.info("Loading local ASR model: %s", LOCAL_ASR_MODEL_ID)

        # Load model on GPU if available
        # Qwen3ASRModel handles device placement, but we can specify dtype for efficiency
        _asr_model = Qwen3ASRModel.from_pretrained(
            LOCAL_ASR_MODEL_ID,
            dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32,
        )
        
        gc.collect() 
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info("Qwen3-ASR model loaded successfully on %s", device)
        
    except ImportError:
        logger.error("qwen-asr package not found. Run 'pip install qwen-asr'.")
        raise
    except Exception as exc:
        logger.error("Failed to load Qwen3-ASR model: %s", exc)
        raise


def get_asr_model() -> object:
    """
    Return the loaded Qwen3-ASR model instance.
    Lazily loads if not already loaded.
    """
    global _asr_model
    if _asr_model is None:
        logger.info("ASR model not loaded yet. Loading now...")
        load_asr_model()
        if _asr_model is None:
            raise RuntimeError("Failed to load Qwen3-ASR model.")
    return _asr_model


def is_asr_loaded() -> bool:
    return _asr_model is not None

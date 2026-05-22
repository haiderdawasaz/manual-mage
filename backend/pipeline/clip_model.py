# backend/pipeline/clip_model.py
"""
Loads CLIP for visual deduplication.
Exposes shared instances to the pipeline.
"""
from __future__ import annotations
import os
import logging
from typing import Optional
from transformers import CLIPProcessor, CLIPModel
import torch
import gc

from config import HF_MODEL_ID

logger = logging.getLogger(__name__)

# Module-level singletons
_processor: Optional[CLIPProcessor] = None
_model: Optional[CLIPModel] = None

def load_model() -> None:
    """
    Load CLIP locally.
    """
    global _processor, _model

    logger.info("Loading CLIP model: %s", HF_MODEL_ID)
    # Load CLIP locally for fast embedding extraction
    _processor = CLIPProcessor.from_pretrained(HF_MODEL_ID)
    _model = CLIPModel.from_pretrained(HF_MODEL_ID)
    _model.eval()
    
    # Device management
    device = "cuda" if torch.cuda.is_available() else "cpu"
    _model.to(device)
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    
    logger.info("CLIP model loaded on %s", device)


def get_processor() -> CLIPProcessor:
    if _processor is None:
        logger.info("CLIP processor not loaded. Loading now...")
        load_model()
    return _processor


def get_model() -> CLIPModel:
    if _model is None:
        logger.info("CLIP model not loaded. Loading now...")
        load_model()
    return _model


def is_loaded() -> bool:
    return _model is not None and _processor is not None

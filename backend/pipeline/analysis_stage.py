# backend/pipeline/analysis_stage.py
"""
Stage 5 — Step description generation using Gemini 2.5 Flash API.

Sends each deduplicated key frame as a base64-encoded image.
Returns a 1–2 sentence instructional description per frame.
Uses exponential backoff on retries.
"""
from __future__ import annotations

import asyncio
import base64
import logging
from pathlib import Path

import google.generativeai as genai
from google.generativeai.types import HarmBlockThreshold, HarmCategory

from config import GEMINI_API_KEY, GEMINI_MODEL_ID, MAX_INFERENCE_RETRIES

logger = logging.getLogger(__name__)

# Configure Gemini once at import time
genai.configure(api_key=GEMINI_API_KEY)

# SYSTEM_PROMPT = (
#     "You are a technical writer producing a step-by-step user manual. "
#     "You will be provided with a sequence of screenshots, each accompanied by a transcript of the spoken audio. "
#     "For each screenshot, use the provided transcript to write exactly 1-2 sentences describing what the user "
#     "should do on that screen. Ensure the instruction is accurate to the audio. "
#     "Use imperative voice (e.g. 'Click the Save button'). "
#     "Reference specific UI elements visible in the image by name. "
#     "The manual MUST be written ONLY in English. "
#     "Output ONLY a JSON array of strings, where each string is the instruction for the corresponding image in order."
# )

SYSTEM_PROMPT = (
    "<|think|> "
    "You are a technical writer producing a step-by-step user manual using your 'Thinking Mode'. "
    "First, you must internally reason about the relationship between the visual state of the screenshots "
    "and the provided audio transcripts. Ensure your logic follows these critical rules: "
    
    "CRITICAL LOGIC: Your final instructions must be driven by the VISUAL state of the screenshot. "
    "1. If the transcript mentions an action (e.g., 'Click Export') but the screenshot shows the user "
    "   still viewing a table or scrolling, DO NOT describe the click. Instead, describe the visible "
    "   state (e.g., 'Review the generated report data'). "
    "2. Only write an 'Action' instruction (Click, Select, Type) if the mouse cursor is near the element "
    "   or if the UI has clearly changed to reflect that action. "
    "3. If the transcript is silent or irrelevant for a frame, return an empty string in the array. "
    
    "After your internal reasoning, write 1-2 sentences in English using imperative voice (e.g., 'Click the Save button'). "
    "Reference specific UI elements by their visible labels. "
    "Output ONLY a JSON array of strings, where each string corresponds to the image in the provided sequence."
)

SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}


def _encode_image(frame_path: Path) -> str:
    """Return base64-encoded JPEG bytes as a string."""
    with open(frame_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _run_gemini_batch_inference(frame_items: list[tuple[Path, str]]) -> list[str]:
    """
    Synchronous Gemini API call that processes all frames with audio at once.
    Runs in thread pool via asyncio.to_thread.
    """
    import json
    
    model = genai.GenerativeModel(
        model_name=GEMINI_MODEL_ID,
        system_instruction=SYSTEM_PROMPT,
    )

    contents = ["Generate the JSON array for these frames: ["]
    for path, text in frame_items:
        contents.append({
            "inline_data": {
                "mime_type": "image/jpeg",
                "data": _encode_image(path),
            }
        })
        contents.append(f"Transcript for above image: \"{text}\"")
        
    contents.extend(["]", "Provide the instruction for each image in order as a JSON array of strings."])

    response = model.generate_content(
        contents,
        safety_settings=SAFETY_SETTINGS,
        generation_config=genai.GenerationConfig(
            temperature=0.2,
            response_mime_type="application/json",
        ),
    )

    try:
        descriptions = json.loads(response.text)
        if not isinstance(descriptions, list):
            descriptions = [str(descriptions)]
    except Exception as exc:
        logger.error("Failed to parse Gemini response: %s\nRaw: %s", exc, response.text)
        descriptions = []

    # Ensure we have exactly the right number of descriptions
    if len(descriptions) < len(frame_items):
        fallback = "Complete the action shown on this screen."
        descriptions.extend([fallback] * (len(frame_items) - len(descriptions)))
        
    return descriptions[:len(frame_items)]


async def analyse_frames(
    frames: list[Path],
    transcript_map: dict[Path, str],
    job_id: str,
) -> list[str]:
    """
    Generate step descriptions by batching all frames into a single Gemini request
    to avoid rate limits (e.g. 5 RPM on free tier). Only processes frames with audio.
    """
    if not frames:
        return []

    # Find which frames need Gemini processing (those with transcripts)
    frames_to_process = []
    for f in frames:
        text = transcript_map.get(f, "").strip()
        if text:
            frames_to_process.append((f, text))

    if not frames_to_process:
        logger.info("[%s] No frames have audio, skipping Gemini batch", job_id)
        return [""] * len(frames)

    batch_results: list[str] = []

    for attempt in range(MAX_INFERENCE_RETRIES):
        try:
            logger.info("[%s] Sending %d frames to Gemini in a single batch", job_id, len(frames_to_process))
            batch_results = await asyncio.to_thread(_run_gemini_batch_inference, frames_to_process)
            break
        except Exception as exc:
            logger.warning(
                "[%s] Gemini batch attempt %d failed: %s",
                job_id, attempt + 1, exc,
            )
            if attempt < MAX_INFERENCE_RETRIES - 1:
                await asyncio.sleep(2 ** attempt)

    descriptions_map = {}
    if not batch_results:
        logger.error("[%s] Gemini batch completely failed — using fallbacks", job_id)
        for f_path, _ in frames_to_process:
            descriptions_map[f_path] = "Complete the action shown on this screen."
    else:
        for i, (f_path, _) in enumerate(frames_to_process):
            descriptions_map[f_path] = batch_results[i] if i < len(batch_results) else "Complete the action shown on this screen."

    final_descriptions = []
    for f in frames:
        text = transcript_map.get(f, "").strip()
        if text:
            final_descriptions.append(descriptions_map.get(f, "Complete the action shown on this screen."))
        else:
            final_descriptions.append("")

    logger.info("[%s] Step analysis complete: %d descriptions", job_id, len(final_descriptions))
    return final_descriptions

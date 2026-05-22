# backend/pipeline/docx_stage.py
"""
Stage 6 — DOCX assembly using python-docx.

Builds a fully editable Word document in memory:
  - Title page
  - Native Word TOC field (updatable after download)
  - One section per step: heading, frame image, description, transcript callout
  - Footer with generation timestamp and page numbers

All styles use built-in Word styles so the document respects the user's
Word / Google Docs theme on open.
"""
from __future__ import annotations

import io
import logging
from datetime import datetime, timezone
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from PIL import Image as PILImage

logger = logging.getLogger(__name__)

# Page margins in inches — used to calculate max image width
LEFT_MARGIN = 1.0
RIGHT_MARGIN = 1.0
PAGE_WIDTH = 8.5  # US Letter
MAX_IMAGE_WIDTH = Inches(5.0)

TRANSCRIPT_BG = RGBColor(240, 240, 240)


# ── Low-level XML helpers ─────────────────────────────────────────────────────

def _add_toc_field(paragraph) -> None:
    """Insert a native Word TOC field into a paragraph."""
    fld_char_begin = OxmlElement("w:fldChar")
    fld_char_begin.set(qn("w:fldCharType"), "begin")

    instr_text = OxmlElement("w:instrText")
    instr_text.set(qn("xml:space"), "preserve")
    instr_text.text = ' TOC \\o "1-2" \\h \\z \\u '

    fld_char_separate = OxmlElement("w:fldChar")
    fld_char_separate.set(qn("w:fldCharType"), "separate")

    fld_char_end = OxmlElement("w:fldChar")
    fld_char_end.set(qn("w:fldCharType"), "end")

    run = paragraph.add_run()
    run._r.append(fld_char_begin)
    run._r.append(instr_text)
    run._r.append(fld_char_separate)
    run._r.append(fld_char_end)


def _set_cell_shading(cell, fill_color: RGBColor) -> None:
    """Apply a solid background colour to a table cell."""
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    hex_color = str(fill_color)
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tc_pr.append(shd)


def _add_page_number_to_footer(footer) -> None:
    """Add right-aligned page number field to a footer paragraph."""
    para = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
    para.alignment = WD_ALIGN_PARAGRAPH.RIGHT

    run = para.add_run()
    fld_char1 = OxmlElement("w:fldChar")
    fld_char1.set(qn("w:fldCharType"), "begin")

    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = "PAGE"

    fld_char2 = OxmlElement("w:fldChar")
    fld_char2.set(qn("w:fldCharType"), "end")

    run._r.append(fld_char1)
    run._r.append(instr)
    run._r.append(fld_char2)


# ── Image helpers ─────────────────────────────────────────────────────────────

def _prepare_image_bytes(frame_path: Path, max_width_px: int = 1200) -> io.BytesIO:
    """
    Open frame, downscale if wider than max_width_px, return as JPEG BytesIO.
    This keeps embedded image size reasonable without separate FFmpeg resize step.
    """
    img = PILImage.open(frame_path).convert("RGB")
    if img.width > max_width_px:
        ratio = max_width_px / img.width
        new_size = (max_width_px, int(img.height * ratio))
        img = img.resize(new_size, PILImage.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    buf.seek(0)
    return buf


# ── Document assembly ─────────────────────────────────────────────────────────

def assemble_docx(
    video_file_name: str,
    job_id: str,
    frames: list[Path],
    descriptions: list[str],
    transcript_map: dict[Path, str],
    has_audio: bool,
    output_path: Path,
) -> None:
    """
    Build and save the complete DOCX to output_path.
    All arguments except output_path are pure data — no I/O side-effects.
    """
    doc = Document()
    now = datetime.now(timezone.utc)
    timestamp_str = now.strftime("%Y-%m-%d %H:%M UTC")

    # ── Document-wide margins ─────────────────────────────────────────────────
    for section in doc.sections:
        section.left_margin = Inches(LEFT_MARGIN)
        section.right_margin = Inches(RIGHT_MARGIN)
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)

    # ── Title page ────────────────────────────────────────────────────────────
    title_para = doc.add_paragraph()
    title_para.style = doc.styles["Title"]
    title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_para.add_run(video_file_name.rsplit(".", 1)[0])  # strip extension

    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle_run = subtitle.add_run(f"Generated on {timestamp_str}")
    subtitle_run.font.size = Pt(12)
    subtitle_run.font.color.rgb = RGBColor(0x80, 0x80, 0x80)

    doc.add_page_break()

    # ── Steps ─────────────────────────────────────────────────────────────────
    for i, (frame_path, description) in enumerate(zip(frames, descriptions), start=1):
        # Derive a short label from the first 6–8 words of the description
        words = description.split()
        label = " ".join(words[:7])
        if len(words) > 7:
            label += "…"

        # Step heading
        step_heading = doc.add_paragraph(f"Step {i}", style="Heading 1")
        step_heading.paragraph_format.space_before = Pt(12)
        step_heading.paragraph_format.space_after = Pt(6)
        step_heading.paragraph_format.page_break_before = False

        # Step label (sub-heading)
        # doc.add_paragraph(label, style="Heading 2")

        # Frame image
        try:
            img_bytes = _prepare_image_bytes(frame_path)
            doc.add_picture(img_bytes, width=MAX_IMAGE_WIDTH)
            # Centre the image paragraph
            doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        except Exception as exc:
            logger.warning("[%s] Could not embed image for step %d: %s", job_id, i, exc)
            doc.add_paragraph("[Image unavailable]", style="Normal")

        # Step description
        if description:
            desc_para = doc.add_paragraph(description, style="Normal")
            desc_para.paragraph_format.space_before = Pt(6)

            # Transcript callout (audio only)
            if has_audio:
                transcript_text = transcript_map.get(frame_path, "").strip()
                if transcript_text:
                    desc_para.paragraph_format.space_after = Pt(6)
                    # Single-cell bordered table for the callout block
                    table = doc.add_table(rows=1, cols=1)
                    table.style = "Table Grid"
                    cell = table.cell(0, 0)
                    _set_cell_shading(cell, TRANSCRIPT_BG)

                    cell_para = cell.paragraphs[0]
                    transcript_run = cell_para.add_run(f"Transcript: {transcript_text[transcript_text.find('text=') + 6 : transcript_text.find('time_stamps') - 3]}")
                    transcript_run.font.size = Pt(10)
                    transcript_run.font.italic = True
                    cell_para.paragraph_format.space_before = Pt(4)
                    cell_para.paragraph_format.space_after = Pt(4)
                    
                    # Margin below the transcript for the next step
                    table.rows[0].cells[0].paragraphs[-1].paragraph_format.space_after = Pt(12)
                else:
                    desc_para.paragraph_format.space_after = Pt(24)
            else:
                desc_para.paragraph_format.space_after = Pt(24)
        else:
            # No description (no audio), just add space after the image
            doc.paragraphs[-1].paragraph_format.space_after = Pt(24)

    # ── Footer: generation timestamp + page number ────────────────────────────
    for section in doc.sections:
        footer = section.footer
        footer.is_linked_to_previous = False

        # Clear default empty paragraph
        for para in footer.paragraphs:
            para.clear()

        footer_para = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
        footer_para.alignment = WD_ALIGN_PARAGRAPH.LEFT

        left_run = footer_para.add_run(f"Generated by Video-to-Doc | {timestamp_str}    ")
        left_run.font.size = Pt(8)
        left_run.font.color.rgb = RGBColor(0xAA, 0xAA, 0xAA)

        _add_page_number_to_footer(footer)

    # ── Save ──────────────────────────────────────────────────────────────────
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))
    logger.info("[%s] DOCX saved to %s", job_id, output_path)
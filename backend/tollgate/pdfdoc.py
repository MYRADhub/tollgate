"""PDF reading: text layer, page images for the vision model, and text that a
human reader cannot see (white, microscopic, or invisible-render-mode text)."""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass, field

import pypdfium2 as pdfium
from pypdf import PdfReader

MAX_PAGES = 4


@dataclass
class PdfContent:
    text: str
    page_images_b64: list[str]
    hidden_spans: list[str] = field(default_factory=list)
    page_count: int = 0


def find_hidden_text(doc: pdfium.PdfDocument, scale: float = 2.0) -> list[str]:
    """Return text present in the text layer that a person reading the page
    cannot see: text whose box on the rendered page carries no visible ink
    (white on white, invisible render mode, covered) or is microscopic."""
    spans: list[str] = []
    for i in range(min(len(doc), MAX_PAGES)):
        page = doc[i]
        img = page.render(scale=scale).to_pil().convert("L")
        page_h = page.get_height()
        tp = page.get_textpage()
        try:
            hidden_parts: list[str] = []
            for r in range(tp.count_rects()):
                left, bottom, right, top = tp.get_rect(r)
                text = tp.get_text_bounded(left, bottom, right, top).strip()
                if not text:
                    continue
                height_pt = top - bottom
                box = (
                    int(left * scale),
                    int((page_h - top) * scale),
                    max(int(right * scale), int(left * scale) + 1),
                    max(int((page_h - bottom) * scale), int((page_h - top) * scale) + 1),
                )
                lo, hi = img.crop(box).getextrema()
                invisible = (hi - lo) < 24
                microscopic = height_pt < 3.0
                if invisible or microscopic:
                    hidden_parts.append(text)
                elif hidden_parts:
                    spans.append(" ".join(hidden_parts))
                    hidden_parts = []
            if hidden_parts:
                spans.append(" ".join(hidden_parts))
        finally:
            tp.close()
    return [sp for sp in spans if len(sp) >= 3]


def read_pdf(data: bytes, render_scale: float = 1.6) -> PdfContent:
    reader = PdfReader(io.BytesIO(data))
    text = "\n".join((p.extract_text() or "") for p in reader.pages[:MAX_PAGES])
    images: list[str] = []
    doc = pdfium.PdfDocument(data)
    try:
        for i in range(min(len(doc), MAX_PAGES)):
            bitmap = doc[i].render(scale=render_scale)
            pil = bitmap.to_pil()
            out = io.BytesIO()
            pil.convert("RGB").save(out, format="JPEG", quality=85)
            images.append(base64.b64encode(out.getvalue()).decode())
        try:
            hidden = find_hidden_text(doc)
        except Exception:
            hidden = []
    finally:
        doc.close()
    return PdfContent(text=text, page_images_b64=images, hidden_spans=hidden, page_count=len(reader.pages))

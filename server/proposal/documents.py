from __future__ import annotations

import io
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Any

from docx import Document
from pypdf import PdfReader

ALLOWED_EXTENSIONS = {".docx", ".pdf", ".txt", ".md", ".png", ".jpg", ".jpeg", ".webp"}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_PDF_PAGES = 100
_OCR_LOCK = Lock()
_PDF_RENDER_LOCK = Lock()


@dataclass
class Extraction:
    text: str
    warning: str = ""
    low_confidence_count: int = 0
    status: str = "ready"
    source_pages: list[tuple[str, str]] | None = None


def _clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


@lru_cache(maxsize=1)
def _ocr_engine():
    try:
        from rapidocr import RapidOCR
    except ImportError as exc:
        raise RuntimeError(
            "本机 OCR 组件尚未安装。请在项目环境执行：pip install -r server/requirements.txt"
        ) from exc
    return RapidOCR()


def _ocr_image(image: Any) -> tuple[str, int]:
    if isinstance(image, (bytes, bytearray)):
        from PIL import Image
        import numpy as np

        image = np.asarray(Image.open(io.BytesIO(image)).convert("RGB"))
    with _OCR_LOCK:
        result = _ocr_engine()(image)
    texts = list(getattr(result, "txts", ()) or ())
    scores = list(getattr(result, "scores", ()) or ())
    lines: list[str] = []
    low = 0
    for index, value in enumerate(texts):
        value = str(value).strip()
        if not value:
            continue
        lines.append(value)
        score = float(scores[index]) if index < len(scores) else 0.0
        if score < 0.72:
            low += 1
    return "\n".join(lines), low


def extract_file(filename: str, data: bytes) -> Extraction:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"暂不支持 {ext or '无扩展名'} 文件。支持 Word、PDF、TXT、Markdown 和常见图片。")
    if not data:
        raise ValueError("上传文件为空。")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("单个文件最大支持 20 MB。")

    if ext == ".docx":
        document = Document(io.BytesIO(data))
        parts: list[tuple[str, str]] = []
        for index, paragraph in enumerate(document.paragraphs, 1):
            text = paragraph.text.strip()
            if text:
                parts.append((f"段落 {index}", text))
        for table_index, table in enumerate(document.tables, 1):
            for row_index, row in enumerate(table.rows, 1):
                row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                if row_text:
                    parts.append((f"表格 {table_index} 第 {row_index} 行", row_text))
        return Extraction(
            text=_clean_text("\n".join(f"[{ref}] {text}" for ref, text in parts)),
            source_pages=parts,
        )

    if ext in {".txt", ".md"}:
        text = data.decode("utf-8-sig", errors="replace")
        lines = [line for line in text.splitlines() if line.strip()]
        return Extraction(
            text=_clean_text("\n".join(f"[行 {i + 1}] {line}" for i, line in enumerate(lines))),
            source_pages=[(f"行 {i + 1}", line) for i, line in enumerate(lines)],
        )

    if ext == ".pdf":
        reader = PdfReader(io.BytesIO(data))
        if len(reader.pages) > MAX_PDF_PAGES:
            raise ValueError(f"PDF 最多支持 {MAX_PDF_PAGES} 页。")
        pages: list[tuple[str, str]] = []
        low_confidence = 0
        ocr_warning = ""
        with _PDF_RENDER_LOCK:
            try:
                import pypdfium2 as pdfium

                rendered_pdf = pdfium.PdfDocument(data)
            except Exception:
                rendered_pdf = None
            try:
                for page_no, page in enumerate(reader.pages, 1):
                    text = _clean_text(page.extract_text() or "")
                    if not text and rendered_pdf is not None:
                        try:
                            image = rendered_pdf[page_no - 1].render(scale=2.5).to_pil()
                            buffer = io.BytesIO()
                            image.save(buffer, format="PNG")
                            text, page_low = _ocr_image(buffer.getvalue())
                            low_confidence += page_low
                        except Exception as exc:
                            ocr_warning = f"第 {page_no} 页未能识别扫描文字：{exc}"
                    elif not text and rendered_pdf is None:
                        ocr_warning = f"第 {page_no} 页是扫描图，但 PDF 图像读取组件不可用。"
                    if text:
                        pages.append((f"第 {page_no} 页", text))
            finally:
                if rendered_pdf is not None:
                    rendered_pdf.close()
        full_text = _clean_text("\n\n".join(f"[{ref}]\n{text}" for ref, text in pages))
        status = "ready" if full_text else "needs_review"
        warnings = [w for w in [ocr_warning] if w]
        if low_confidence:
            warnings.append(f"发现 {low_confidence} 行低置信度 OCR 文字，请核对。")
        return Extraction(
            text=full_text,
            warning=" ".join(warnings),
            low_confidence_count=low_confidence,
            status=status,
            source_pages=pages,
        )

    text, low = _ocr_image(data)
    warning = f"发现 {low} 行低置信度 OCR 文字，请核对。" if low else ""
    return Extraction(
        text=_clean_text(f"[图片 OCR]\n{text}"),
        warning=warning,
        low_confidence_count=low,
        status="ready" if text.strip() else "needs_review",
        source_pages=[("图片 OCR", text)] if text.strip() else [],
    )


def split_into_chunks(text: str, max_chars: int = 900, overlap: int = 120) -> list[str]:
    """Split text into retrieval-sized chunks without losing paragraph boundaries."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n|\n", text) if p.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            start = 0
            while start < len(paragraph):
                end = min(start + max_chars, len(paragraph))
                chunks.append(paragraph[start:end])
                if end == len(paragraph):
                    break
                start = max(end - overlap, start + 1)
            continue
        if not current:
            current = paragraph
        elif len(current) + len(paragraph) + 1 <= max_chars:
            current += "\n" + paragraph
        else:
            chunks.append(current)
            tail = current[-overlap:] if overlap else ""
            current = (tail + "\n" + paragraph).strip()
    if current:
        chunks.append(current)
    return chunks

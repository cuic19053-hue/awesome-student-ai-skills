"""Embed provided or deterministically rendered roadmap pictures in Word."""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.image.image import Image
from docx.shared import Cm

from .figgen import render_flowchart


def _valid_graph(nodes: Any, edges: Any) -> bool:
    if not isinstance(nodes, list) or not nodes or not isinstance(edges, list):
        return False
    identifiers: set[str] = set()
    def identifier_value(value: Any) -> str | None:
        if isinstance(value, str) and value.strip():
            return value
        if type(value) is int:
            return str(value)
        return None
    for index, node in enumerate(nodes):
        if isinstance(node, str) and node.strip():
            identifier = f"n{index}"
        elif (isinstance(node, dict) and identifier_value(node.get("id")) is not None
              and isinstance(node.get("label"), str) and node["label"].strip()):
            identifier = identifier_value(node["id"])
        else:
            return False
        if identifier in identifiers:
            return False
        identifiers.add(identifier)
    return all(isinstance(edge, dict) and identifier_value(edge.get("from")) in identifiers
               and identifier_value(edge.get("to")) in identifiers for edge in edges)


def _embed(doc: Any, image_path: str, width_cm: float) -> None:
    # Tall graph images must fit an A4 body with room for the caption. Passing
    # only the fitted width keeps the image's original proportions intact.
    image = Image.from_file(image_path)
    fitted_width = min(Cm(width_cm), round(Cm(20) * image.width / image.height))
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    try:
        paragraph.add_run().add_picture(image_path, width=fitted_width)
    except Exception:
        paragraph._element.getparent().remove(paragraph._element)
        raise


def embed_roadmap_image(doc: Any, roadmap: dict[str, Any]) -> tuple[bool, str]:
    """Prefer the user's image; otherwise render a validated graph once.

    Word consumes picture bytes during add_picture(), so the generated file
    can be removed immediately. Only our TemporaryDirectory is cleaned up;
    user-supplied images are never changed or deleted.
    """
    user_image = roadmap.get("image_path")
    image_failed = False
    if isinstance(user_image, str) and user_image:
        try:
            if Path(user_image).is_file():
                _embed(doc, user_image, 15)
                return True, ""
        except Exception:
            pass
        image_failed = True

    nodes = roadmap.get("nodes")
    edges = roadmap.get("edges")
    edges = [] if edges is None else edges
    if not nodes:
        prefix = "提供的图片无法读取；" if image_failed else ""
        return False, prefix + "请提供路线图片，或填写节点与关联关系"
    if not _valid_graph(nodes, edges):
        return False, "节点或关联关系无效，请核对节点编号、文字与连线"
    try:
        with tempfile.TemporaryDirectory(prefix="student-roadmap-") as directory:
            output = Path(directory) / "roadmap.png"
            rendered = render_flowchart(nodes, edges, str(output))
            if not rendered or not output.is_file():
                return False, "路线图图片未生成，请检查绘图依赖或提供图片"
            _embed(doc, str(output), 12.5)
        return True, ""
    except Exception:
        return False, "路线图图片未生成或无法嵌入，请检查绘图依赖或提供图片"

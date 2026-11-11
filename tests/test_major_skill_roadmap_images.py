"""The two major competition builders deliver real, safely cleaned pictures."""
import copy
import importlib.util
import zipfile
from pathlib import Path

import pytest
from docx import Document
from docx.shared import Cm
from PIL import Image

from utils import roadmap_image


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ["innovation-research", "challenge-cup"]
NODES = [{"id": "1", "label": "需求分析"}, {"id": "2", "label": "方案设计"},
         {"id": "3", "label": "实施验证"}]
EDGES = [{"from": "1", "to": "2"}, {"from": "2", "to": "3"}]


def load_builder(skill):
    spec = importlib.util.spec_from_file_location("roadmap_" + skill.replace("-", "_"),
                                                 ROOT / "subskills" / skill / "build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ApplicationDocBuilder()


def graph(**overrides):
    return {"figure_no": "图 1", "title": "研究实施路线", "description": "仅展示已提供的研究设计。",
            "nodes": copy.deepcopy(NODES), "edges": copy.deepcopy(EDGES), **overrides}


def save_section(builder, data, target):
    builder.data = {"tech_roadmap": data}
    builder._add_tech_roadmap()
    builder.doc.save(target)
    return Document(target)


@pytest.mark.parametrize("skill", SKILLS)
def test_full_builder_embeds_real_pngs_from_graph_data_and_cleans_them(skill, tmp_path, monkeypatch):
    builder = load_builder(skill)
    outputs = []
    actual_render = roadmap_image.render_flowchart
    def render(nodes, edges, out_path):
        outputs.append(Path(out_path))
        return actual_render(nodes, edges, out_path)
    monkeypatch.setattr(roadmap_image, "render_flowchart", render)
    data = [graph(), graph(figure_no="图 2", title="方法关系图", nodes=["定义问题", "收集材料", "分析验证"], edges=[])]
    target = tmp_path / (skill + ".docx")
    builder.build({"tech_roadmap": data}, str(target))
    doc = Document(target)
    assert len(doc.inline_shapes) == 2
    assert all(shape.height <= Cm(20) + 1 for shape in doc.inline_shapes)
    with zipfile.ZipFile(target) as archive:
        media = [name for name in archive.namelist() if name.startswith("word/media/")]
        assert len(media) == 2 and all(archive.read(name).startswith(b"\x89PNG") for name in media)
    assert outputs and all(not path.exists() and not path.parent.exists() for path in outputs)


@pytest.mark.parametrize("skill", SKILLS)
def test_user_picture_precedes_graph_rendering_and_is_not_deleted(skill, tmp_path, monkeypatch):
    source = tmp_path / "provided.png"
    Image.new("RGB", (80, 40), color=(30, 60, 90)).save(source)
    source_bytes = source.read_bytes()
    monkeypatch.setattr(roadmap_image, "render_flowchart", lambda *_: pytest.fail("provided image takes priority"))
    target = tmp_path / (skill + ".docx")
    doc = save_section(load_builder(skill), [graph(image_path=str(source))], target)
    assert len(doc.inline_shapes) == 1 and source.read_bytes() == source_bytes
    with zipfile.ZipFile(target) as archive:
        media = [name for name in archive.namelist() if name.startswith("word/media/")]
        assert len(media) == 1 and archive.read(media[0]) == source_bytes


@pytest.mark.parametrize("skill", SKILLS)
@pytest.mark.parametrize("failure", ["none", "exception", "corrupt_png"])
def test_failed_render_or_embed_leaves_a_clear_placeholder_and_cleans_partial_files(skill, failure, tmp_path, monkeypatch):
    outputs = []
    def fail(_nodes, _edges, out_path):
        path = Path(out_path)
        outputs.append(path)
        path.write_bytes(b"partial image")
        if failure == "exception":
            raise OSError("renderer failed")
        return str(path) if failure == "corrupt_png" else None
    monkeypatch.setattr(roadmap_image, "render_flowchart", fail)
    doc = save_section(load_builder(skill), [graph()], tmp_path / (skill + ".docx"))
    assert not doc.inline_shapes
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "技术路线图待补充" in text and "共绘制" not in text
    assert outputs and all(not path.exists() and not path.parent.exists() for path in outputs)


@pytest.mark.parametrize("skill", SKILLS)
@pytest.mark.parametrize("data", [
    {"figure_no": "图 1", "title": "只提供了描述", "description": "描述不能充当路线图片。"},
    graph(nodes=[{"id": "1", "label": "输入"}, {"id": "1", "label": "重复编号"}]),
    graph(edges=[{"from": "1", "to": "不存在的节点"}]),
])
def test_missing_or_invalid_graph_is_not_claimed_as_a_drawn_picture(skill, data, tmp_path, monkeypatch):
    monkeypatch.setattr(roadmap_image, "render_flowchart", lambda *_: pytest.fail("invalid graph must not be rendered"))
    doc = save_section(load_builder(skill), [data], tmp_path / (skill + ".docx"))
    assert not doc.inline_shapes
    assert "技术路线图待补充" in "\n".join(p.text for p in doc.paragraphs)


@pytest.mark.parametrize("skill", SKILLS)
def test_unreadable_user_picture_can_fall_back_to_valid_graph(skill, tmp_path):
    source = tmp_path / "broken.png"
    source.write_bytes(b"not a picture")
    doc = save_section(load_builder(skill), [graph(image_path=str(source))], tmp_path / (skill + ".docx"))
    assert len(doc.inline_shapes) == 1 and source.read_bytes() == b"not a picture"


@pytest.mark.parametrize("skill", SKILLS)
def test_absent_graph_entries_leave_placeholders(skill, tmp_path):
    doc = save_section(load_builder(skill), ["仅有文字说明"], tmp_path / (skill + ".docx"))
    assert not doc.inline_shapes and "技术路线图待补充" in "\n".join(p.text for p in doc.paragraphs)

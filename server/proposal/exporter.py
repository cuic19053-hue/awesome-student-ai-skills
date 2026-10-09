from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.text.paragraph import Paragraph
from docx.shared import Cm, Pt

from .storage import Store

LABEL_FIELDS = {
    "项目名称": ("state", "project_name"),
    "课题名称": ("state", "project_name"),
    "申报级别": ("level",),
    "项目级别": ("level",),
    "所属学科": ("discipline",),
    "申报学校": ("school",),
    "项目负责人": ("state", "leader_name"),
    "负责人姓名": ("state", "leader_name"),
    "指导教师": ("state", "advisor_name"),
    "指导教师姓名": ("state", "advisor_name"),
    "项目周期": ("state", "duration"),
    "实施周期": ("state", "duration"),
    "起止时间": ("state", "duration"),
    "研究问题": ("state", "problem"),
    "研究目标": ("state", "goal"),
    "研究方法": ("state", "method"),
    "研究内容": ("section", "research_content"),
    "立项依据": ("section", "background"),
    "项目背景": ("section", "background"),
    "创新点": ("section", "innovations"),
    "技术路线": ("section", "research_route"),
    "进度安排": ("section", "schedule"),
    "预算": ("state", "budget"),
    "经费预算": ("state", "budget"),
    "前期基础": ("section", "foundation"),
    "参考文献": ("section", "references"),
    "项目简介": ("section", "abstract"),
    "摘要": ("section", "abstract"),
    "研究目的": ("section", "research_content"),
    "研究方案": ("section", "research_route"),
    "研究方法": ("state", "method"),
    "预期成果": ("state", "expected_output"),
    "成果形式": ("state", "expected_output"),
    "研究进度": ("section", "schedule"),
    "项目进度": ("section", "schedule"),
    "成员分工": ("state", "team"),
    "项目团队": ("state", "team"),
}


def _clean_label(value: str) -> str:
    return re.sub(r"[\s：:（）()【】\[\]一二三四五六七八九十、.]", "", value).strip()


def _match_section_id(label: str, project: dict[str, Any]) -> str | None:
    normalized = _clean_label(label)
    for item in project["outline"]:
        title = _clean_label(item.get("title", ""))
        if not title:
            continue
        if normalized == title or (len(normalized) >= 4 and normalized in title) or (len(title) >= 4 and title in normalized):
            return item.get("id")
    aliases = {
        "项目简介": "abstract",
        "项目摘要": "abstract",
        "摘要": "abstract",
        "立项依据": "background",
        "项目背景": "background",
        "研究内容": "research_content",
        "研究方案": "research_route",
        "研究方法": "research_route",
        "创新点": "innovations",
        "预期成果": "expected_output",
        "进度安排": "schedule",
        "项目进度": "schedule",
        "项目实施计划": "schedule",
        "预算": "budget",
        "经费预算": "budget",
        "前期基础": "foundation",
        "团队基础": "foundation",
        "参考文献": "references",
        "项目基本信息": "project_info",
    }
    return aliases.get(normalized)


def _pdf_template_headings(text: str) -> list[str]:
    headings: list[str] = []
    patterns = (
        re.compile(r"^(?:[一二三四五六七八九十]+[、.．]|（[一二三四五六七八九十]+）|\d+[.、])\s*[\u4e00-\u9fff].{1,48}$"),
        re.compile(r"^(?:项目名称|项目基本信息|项目摘要|项目简介|立项依据|项目背景|研究内容|研究方案|研究方法|创新点|预期成果|进度安排|项目实施计划|经费预算|前期基础|参考文献|团队成员|项目负责人|指导教师)\s*[:：]?$"),
    )
    for raw in text.splitlines():
        line = re.sub(r"^\[第 \d+ 页\]\s*", "", raw).strip()
        line = re.sub(r"\s+", " ", line)
        if 2 <= len(line) <= 55 and any(pattern.match(line) for pattern in patterns):
            headings.append(line)
    return list(dict.fromkeys(headings))


def _apply_pdf_outline(project: dict[str, Any], template_text: str) -> bool:
    source_headings = _pdf_template_headings(template_text)
    if len(source_headings) < 2:
        return False
    current = list(project["outline"])
    matched: list[str] = []
    for title in source_headings:
        section_id = _match_section_id(title, project)
        if section_id and any(item.get("id") == section_id for item in current):
            if section_id not in matched:
                matched.append(section_id)
    if len(matched) < 2:
        return False
    by_id = {item.get("id"): item for item in current}
    project["outline"] = [by_id[section_id] for section_id in matched]
    project["outline"].extend(item for item in current if item.get("id") not in matched)
    return True


def _field_value(project: dict[str, Any], field: tuple[str, ...]) -> str:
    if field[0] == "state":
        fallback = (
            project.get("title", "")
            if field[1] == "project_name" and project.get("title") != "我的大创项目"
            else ""
        )
        return str(project["state"].get(field[1], "") or fallback or "待补充")
    if field[0] == "section":
        return str(project["sections"].get(field[1], "") or "待补充")
    return str(project.get(field[0], "") or "待补充")


def _replace_tokens(document: Document, project: dict[str, Any]) -> int:
    replacements = {
        "project_name": str(project["state"].get("project_name", "待补充")),
        "project_level": str(project.get("level", "待补充")),
        "leader_name": str(project["state"].get("leader_name", "待补充")),
        "advisor_name": str(project["state"].get("advisor_name", "待补充")),
        "discipline": str(project.get("discipline", "待补充")),
    }
    count = 0

    def replace_in_paragraph(paragraph) -> None:
        nonlocal count
        # Join/split runs so styled Word templates still retain the paragraph style.
        original = paragraph.text
        changed = original
        for key, value in replacements.items():
            for token in (f"{{{{{key}}}}}", f"【{key}】"):
                if token in changed:
                    changed = changed.replace(token, value)
        for key, value in project["sections"].items():
            token = f"{{{{section:{key}}}}}"
            if token in changed:
                changed = changed.replace(token, str(value or "待补充"))
        if changed != original:
            paragraph.clear()
            paragraph.add_run(changed)
            count += 1

    for paragraph in document.paragraphs:
        replace_in_paragraph(paragraph)
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    replace_in_paragraph(paragraph)
    return count


def _fill_labeled_tables(document: Document, project: dict[str, Any]) -> set[str]:
    filled_sections: set[str] = set()
    replaceable = {"_", "—", "-", " ", "（", "）", "(", ")", "：", ":"}
    for table in document.tables:
        for row in table.rows:
            if len(row.cells) < 2:
                continue
            raw_label = row.cells[0].text
            label = _clean_label(raw_label)
            section_id = _match_section_id(raw_label, project)
            matching = next(
                (field for key, field in LABEL_FIELDS.items() if _clean_label(key) == label),
                None,
            )
            if section_id:
                matching = ("section", section_id)
            if not matching:
                continue
            target = row.cells[1]
            existing = target.text.strip()
            has_placeholder = (
                not existing
                or set(existing) <= replaceable
                or any(marker in existing for marker in ("请填写", "待补充", "填写", "________"))
            )
            if has_placeholder:
                value = _field_value(project, matching)
                target.text = value
                if matching[0] == "section" and value != "待补充":
                    filled_sections.add(matching[1])
    return filled_sections


def _fill_labeled_paragraphs(document: Document, project: dict[str, Any]) -> set[str]:
    """Fill an empty paragraph immediately following a recognizable template label."""
    filled_sections: set[str] = set()
    paragraphs = list(document.paragraphs)
    for index, paragraph in enumerate(paragraphs):
        raw_label = paragraph.text.strip()
        if not raw_label or len(raw_label) > 140:
            continue
        section_id = _match_section_id(raw_label, project)
        normalized = _clean_label(raw_label)
        field = next(
            (value for key, value in LABEL_FIELDS.items() if _clean_label(key) == normalized),
            None,
        )
        if section_id:
            field = ("section", section_id)
        if not field:
            continue
        value = _field_value(project, field)
        if value == "待补充":
            continue
        next_paragraph = paragraphs[index + 1] if index + 1 < len(paragraphs) else None
        if next_paragraph and (
            not next_paragraph.text.strip()
            or any(marker in next_paragraph.text for marker in ("请填写", "待补充", "________"))
        ):
            target = next_paragraph
        else:
            xml_paragraph = OxmlElement("w:p")
            paragraph._p.addnext(xml_paragraph)
            target = Paragraph(xml_paragraph, paragraph._parent)
            paragraphs.insert(index + 1, target)
        target.text = value
        if field[0] == "section":
            filled_sections.add(field[1])
    return filled_sections


def _append_draft(
    document: Document,
    project: dict[str, Any],
    include_all: bool,
    already_filled: set[str] | None = None,
) -> None:
    already_filled = already_filled or set()
    skill_id = str(project.get("state", {}).get("skill_id", "innovation-research"))
    skill_name = str(project.get("state", {}).get("skill_name", "申报材料"))
    research_project = skill_id in {
        "innovation-research", "entrepreneurship-training", "entrepreneurship-practice",
        "university-research", "college-research", "challenge-cup", "internet-plus",
        "internet-plus-red-tour",
    }
    if not project.get("_used_template"):
        title = document.add_heading(f"{skill_name}（草稿）", level=1)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        notice = document.add_paragraph(
            "草稿：提交前请核对学校最新通知、全部事实与文献来源。文中“待补充”内容不得直接提交。"
        )
        notice.alignment = WD_ALIGN_PARAGRAPH.CENTER
    elif not already_filled:
        document.add_page_break()
        notice = document.add_paragraph(
            "草稿续页：已保留原学校模板并附加 Agent 草稿内容。请核对模板中需要手工填写的栏目。"
        )
        notice.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for section in project["outline"]:
        section_id = section.get("id", "")
        if section_id in already_filled:
            continue
        section_title = section.get("title", section_id or "未命名章节")
        content = str(project["sections"].get(section_id, "") or "待补充：请提供与本章节相关的真实信息。")
        document.add_heading(section_title, level=2 if project.get("_used_template") else 1)
        lines = content.splitlines()
        index = 0
        while index < len(lines):
            line = lines[index].strip()
            if line.startswith("|") and "|" in line[1:]:
                table_lines = []
                while index < len(lines) and lines[index].strip().startswith("|"):
                    table_lines.append(lines[index].strip())
                    index += 1
                rows = []
                for table_line in table_lines:
                    cells = [cell.strip() for cell in table_line.strip("|").split("|")]
                    if cells and all(re.fullmatch(r"[:\- ]+", cell or " ") for cell in cells):
                        continue
                    rows.append(cells)
                if rows:
                    col_count = max(len(row) for row in rows)
                    table = document.add_table(rows=0, cols=col_count)
                    table.style = "Table Grid"
                    for row in rows:
                        cells = table.add_row().cells
                        for cell_index in range(col_count):
                            cells[cell_index].text = row[cell_index] if cell_index < len(row) else ""
                continue
            if line:
                _add_markdown_paragraph(document, line)
            index += 1

    diagrams = project["diagrams"]
    if diagrams:
        document.add_heading("技术路线与项目图示" if research_project else "材料图示", level=1)
        for diagram in diagrams:
            document.add_heading(diagram.get("title", "项目流程图"), level=2)
            preview = Path(diagram.get("preview", ""))
            if preview.is_file():
                try:
                    document.add_picture(str(preview), width=Cm(15))
                except Exception:
                    pass
            nodes = diagram.get("nodes", [])
            if nodes:
                document.add_paragraph(" → ".join(str(node) for node in nodes))
    elif research_project:
        document.add_heading("研究方案图表", level=1)
        table = document.add_table(rows=2, cols=2)
        table.style = "Table Grid"
        table.cell(0, 0).text = "技术路线图"
        table.cell(0, 1).text = "待补充：确认研究步骤后生成可编辑图表。"
        table.cell(1, 0).text = "项目进度图"
        table.cell(1, 1).text = "待补充：确认项目周期和阶段安排后生成。"

    image_docs = [d for d in project["_documents"] if d["kind"] == "photo" and Path(d["stored_path"]).is_file()]
    if image_docs:
        document.add_heading("项目实践照片", level=1)
        for item in image_docs:
            document.add_paragraph(f"图片：{item['original_name']}")
            try:
                document.add_picture(item["stored_path"], width=Cm(13.5))
            except Exception:
                document.add_paragraph(f"待补充：无法嵌入图片 {item['original_name']}，请检查文件。")
    elif research_project:
        document.add_heading("项目实践照片", level=1)
        placeholder = document.add_table(rows=1, cols=1)
        placeholder.cell(0, 0).text = (
            "待补充实验/调研照片\n请上传真实项目照片，并说明时间、地点、参与人员和照片内容。"
        )

    references = project["state"].get("references", [])
    if references:
        document.add_heading("参考文献（待核对）", level=1)
        for index, ref in enumerate(references, 1):
            if isinstance(ref, dict):
                authors = ", ".join(ref.get("authors", [])) or "作者待核"
                title = ref.get("title", "题名待核")
                year = ref.get("year") or "年份待核"
                venue = ref.get("venue", "")
                doi = ref.get("doi", "")
                link = ref.get("url") or (f"https://doi.org/{doi}" if doi else "")
                citation = f"[{index}] {authors}. {title}. {venue}, {year}."
                if link:
                    citation += f" {link}"
                document.add_paragraph(citation)
            else:
                document.add_paragraph(f"[{index}] {ref}")
    official_sources = project["state"].get("official_sources", [])
    if official_sources:
        document.add_heading("政策与学校通知来源", level=1)
        for index, source in enumerate(official_sources, 1):
            if isinstance(source, dict):
                published = source.get("published_at") or source.get("year") or "发布日期待核"
                document.add_paragraph(
                    f"[{index}] {source.get('title', '官方通知')} — "
                    f"{published} — {source.get('url', '')} （请核对通知年份和适用范围）"
                )
    elif include_all and research_project:
        document.add_heading("参考文献", level=1)
        document.add_paragraph("待补充：请确认并补充真实、相关且已阅读的参考文献。")


def _add_markdown_paragraph(document: Document, text: str) -> None:
    if text.startswith("### "):
        document.add_heading(text[4:].strip(), level=3)
        return
    if text.startswith("## "):
        document.add_heading(text[3:].strip(), level=2)
        return
    if text.startswith("# "):
        document.add_heading(text[2:].strip(), level=2)
        return
    style = None
    body = text
    if text.startswith(("- ", "* ")):
        style, body = "List Bullet", text[2:].strip()
    else:
        numbered = re.match(r"^\d+[.)、]\s*(.+)$", text)
        if numbered:
            style, body = "List Number", numbered.group(1)
    paragraph = document.add_paragraph(style=style) if style else document.add_paragraph()
    for part in re.split(r"(\*\*.+?\*\*)", body):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**") and len(part) >= 4:
            paragraph.add_run(part[2:-2]).bold = True
        else:
            paragraph.add_run(part)


def _apply_styles(document: Document) -> None:
    section = document.sections[0]
    section.page_width = Cm(21)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.54)
    section.bottom_margin = Cm(2.54)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.5)
    for style_name in ("Normal", "Body Text"):
        if style_name in document.styles:
            style = document.styles[style_name]
            style.font.name = "宋体"
            style.font.size = Pt(12)
            style._element.rPr.rFonts.set("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}eastAsia", "宋体")


def _add_generic_cover(document: Document, project: dict[str, Any]) -> None:
    skill_id = str(project.get("state", {}).get("skill_id", "innovation-research"))
    skill_name = str(project.get("state", {}).get("skill_name", "申报材料"))
    heading = document.add_paragraph()
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
    heading.paragraph_format.space_before = Pt(68)
    heading.paragraph_format.space_after = Pt(32)
    if skill_id == "innovation-research":
        cover_title = "大学生创新创业训练计划\n项目申报书"
    else:
        cover_title = f"{skill_name}\n申报材料"
    run = heading.add_run(cover_title)
    run.bold = True
    run.font.name = "黑体"
    run.font.size = Pt(24)
    run._element.rPr.rFonts.set("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}eastAsia", "黑体")

    title = document.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.space_before = Pt(10)
    title.paragraph_format.space_after = Pt(44)
    project_title = project.get("state", {}).get("project_name") or project.get("title")
    if not project_title or project_title == "我的大创项目" or (
        str(project_title).startswith("我的") and str(project_title).endswith("项目")
    ):
        project_title = "项目名称：待补充"
    title_run = title.add_run(project_title)
    title_run.bold = True
    title_run.font.size = Pt(18)
    title_run.font.name = "黑体"
    title_run._element.rPr.rFonts.set("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}eastAsia", "黑体")

    state = project["state"]
    if skill_id == "innovation-research":
        rows = [
            ("申报级别", project.get("level") or "待补充"),
            ("专业 / 学科", project.get("discipline") or "待补充"),
            ("学校", project.get("school") or "待补充"),
            ("项目负责人", state.get("leader_name") or "待补充"),
            ("指导教师", state.get("advisor_name") or "待补充"),
            ("团队成员", state.get("team") or "待补充"),
            ("项目周期", state.get("duration") or "待补充"),
            ("项目经费", state.get("budget") or "待补充"),
        ]
    else:
        rows = [
            ("申请人 / 负责人", state.get("applicant_name") or state.get("leader_name") or "待补充"),
            ("学校 / 单位", project.get("school") or "待补充"),
            ("学院 / 专业", project.get("discipline") or "待补充"),
            ("申请类别", skill_name),
            ("申报级别 / 年级", project.get("level") or state.get("grade") or "待补充"),
        ]
    table = document.add_table(rows=len(rows), cols=2)
    table.style = "Table Grid"
    table.alignment = 1
    for index, (label, value) in enumerate(rows):
        table.cell(index, 0).text = label
        table.cell(index, 1).text = str(value)
    note = document.add_paragraph("草稿 · 学校模板缺省，提交前请按校方通知核对")
    note.alignment = WD_ALIGN_PARAGRAPH.CENTER
    note.paragraph_format.space_before = Pt(26)
    document.add_page_break()


def export_project(store: Store, project_id: str, output_path: str | Path) -> dict[str, Any]:
    project = (
        store.project_for_export(project_id)
        if hasattr(store, "project_for_export")
        else store.get_project(project_id)
    )
    if not project:
        return {"success": False, "error": "找不到这个项目。"}
    if not project["outline"]:
        skill_id = str(project.get("state", {}).get("skill_id", "innovation-research"))
        if skill_id == "innovation-research":
            project["outline"] = [
            {"id": "project_info", "title": "项目基本信息"},
            {"id": "abstract", "title": "项目摘要"},
            {"id": "background", "title": "项目背景与研究问题"},
            {"id": "research_content", "title": "研究内容与方法"},
            {"id": "research_route", "title": "技术路线或项目方案"},
            {"id": "schedule", "title": "进度安排与预算"},
            {"id": "foundation", "title": "团队基础与实施条件"},
            {"id": "references", "title": "参考文献与资料来源"},
            ]
        else:
            project["outline"] = [
                {"id": "application_info", "title": "申请基本信息"},
                {"id": "application_content", "title": "申请内容"},
                {"id": "personal_statement", "title": "个人情况与申请理由"},
                {"id": "plan_and_commitment", "title": "计划与承诺"},
            ]
    documents = store.list_documents(project_id)
    project["_documents"] = documents
    template_id = project.get("template_document_id")
    template_doc = store.get_document(template_id) if template_id else None
    template_path = Path(template_doc["stored_path"]) if template_doc else None
    used_template = bool(template_path and template_path.suffix.lower() == ".docx" and template_path.is_file())
    warnings: list[str] = []
    if not template_doc and project["state"].get("template_preference") == "has_template":
        warnings.append("你选择了有学校模板，但尚未上传；当前先按通用格式生成草稿，请上传模板后重新导出。")
    elif not template_doc:
        warnings.append("未上传学校模板，使用通用目录和排版。请提交前按学校要求核对。")
    pdf_template = bool(template_path and template_path.suffix.lower() == ".pdf" and template_path.is_file())
    pdf_outline_applied = False
    if pdf_template and template_doc:
        pdf_outline_applied = _apply_pdf_outline(project, template_doc.get("extracted_text", ""))
        warnings.append(
            "上传的是 PDF 模板，无法原位编辑；"
            + ("已按可识别栏目顺序重建可编辑 Word 草稿。" if pdf_outline_applied else "未能识别足够栏目，使用通用目录重建可编辑 Word 草稿。")
            + "请核对排版和栏目。"
        )
    document = Document(str(template_path)) if used_template else Document()
    project["_used_template"] = used_template
    _apply_styles(document)
    if not used_template:
        _add_generic_cover(document, project)
    token_count = _replace_tokens(document, project) if used_template else 0
    table_sections = _fill_labeled_tables(document, project) if used_template else set()
    paragraph_sections = _fill_labeled_paragraphs(document, project) if used_template else set()
    filled_sections = table_sections | paragraph_sections
    table_count = len(table_sections)
    if used_template and not token_count and not filled_sections:
        warnings.append(
            "未发现可自动填写的占位符或标准字段表格；保留了原模板，并在后面附加草稿章节，请人工核对是否需要填入原表格。"
        )
    _append_draft(document, project, include_all=True, already_filled=filled_sections)
    out = Path(output_path).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(out))
    return {
        "success": True,
        "path": str(out),
        "used_original_template": used_template,
        "template_sections_filled": table_count,
        "template_paragraphs_filled": len(paragraph_sections),
        "template_placeholders_replaced": token_count,
        "pdf_template_outline_applied": pdf_outline_applied,
        "warnings": warnings,
        "draft": True,
    }

"""Inspect real Word output: a grant grade never supplies a school's amount."""
import importlib.util
from pathlib import Path

import pytest
from docx import Document


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def grant_builder():
    spec = importlib.util.spec_from_file_location(
        "grant_build_amount_test", ROOT / "subskills/grant-application/build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build(module, tmp_path, **changes):
    data = {"name": "测试申请人", "college": "测试学院", "major": "数学",
            "grade": "大二", "grant_level": "三等"}
    data.update(changes)
    builder = module.ApplicationDocBuilder()
    path = tmp_path / "grant.docx"
    builder.build(data, str(path))
    doc = Document(path)
    text = "\n".join([p.text for p in doc.paragraphs] +
                     [cell.text for table in doc.tables for row in table.rows for cell in row.cells])
    return text, builder.warnings


@pytest.mark.parametrize("level", ["一等", "二等", "三等", "学校A档"])
def test_missing_amount_is_unknown_in_real_word_for_every_level(grant_builder, tmp_path, level):
    text, warnings = _build(grant_builder, tmp_path, grant_level=level)
    assert level in text
    assert "金额待核对学校当年标准" in text
    assert not any(amount in text for amount in ("4400", "3300", "2200"))
    assert any("grant_amount" in message for message in warnings)
    assert grant_builder.compute_grant_amount(level) == 0


@pytest.mark.parametrize("amount", [None, "", 0, -1, True, "nan", "Infinity", "学校待定"])
def test_invalid_amount_never_becomes_a_grant_amount(grant_builder, tmp_path, amount):
    text, warnings = _build(grant_builder, tmp_path, grant_amount=amount)
    assert "金额待核对学校当年标准" in text
    assert any("grant_amount" in message for message in warnings)
    assert "（0 元/年）" not in text and "nan 元" not in text


@pytest.mark.parametrize("amount", [2500, "2600", 5000])
def test_explicit_school_amount_is_preserved_without_level_recalculation(grant_builder, tmp_path, amount):
    text, warnings = _build(grant_builder, tmp_path, grant_level="三等", grant_amount=amount,
                            difficulty_level="特别困难", apply_year="2026-2027 学年")
    assert f"{amount} 元/年" in text
    assert "2026-2027 学年" in text
    assert "金额待核对学校当年标准" not in text
    assert not any("grant_amount" in message or "跨档申请" in message for message in warnings)


def test_out_of_range_amount_is_exposed_for_review_not_silently_replaced(grant_builder, tmp_path):
    text, warnings = _build(grant_builder, tmp_path, grant_amount=2200)
    assert "2200 元/年" in text
    assert any("2500-5000" in message for message in warnings)


def test_missing_school_year_is_an_explicit_blank_not_an_old_year(grant_builder, tmp_path):
    text, _ = _build(grant_builder, tmp_path)
    assert "申请学年待补充" in text
    assert "2024-2025" not in text


def test_privacy_preserving_short_input_never_invents_courses_or_work_study(grant_builder, tmp_path):
    text, warnings = _build(grant_builder, tmp_path, name="林宁", college="计算机学院",
                            major="软件工程", grade="大二", word_count_version="800",
                            family_situation={"income_source": "父母务农", "family_income_year": None},
                            family_members=[], work_study=[], study_situation="")
    assert "父母务农" in text
    assert "实际学习情况待补充" in text
    assert "必修课全部及格" not in text and "勤奋上进" not in text
    assert "继续通过勤工助学" not in text and "家庭年总收入" not in text
    assert not any(marker in "\n".join(warnings) for marker in (
        "家庭成员表", "建议至少 3 人", "勤工助学经历", "家庭年总收入", "大额支出", "6 万"))


def test_explicit_course_result_is_preserved_and_school_line_is_not_inferred(grant_builder, tmp_path):
    text, _ = _build(grant_builder, tmp_path, course_failed="无", difficulty_level="困难",
                     family_situation={"family_size": 3, "family_income_year": 36000})
    assert "必修课全部及格" in text
    assert "学校家庭经济困难认定线" not in text


def test_explicit_threshold_is_not_used_to_assert_a_false_comparison(grant_builder, tmp_path):
    text, _ = _build(grant_builder, tmp_path, family_situation={
        "family_size": 3, "family_income_year": 36000, "school_line": 600, "local_min_living": 500,
    })
    assert "所提供的学校家庭经济困难认定线为 600" in text
    assert "低于学校" not in text and "低于当地" not in text

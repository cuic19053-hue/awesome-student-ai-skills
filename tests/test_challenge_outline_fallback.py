import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from proposal.outline_fallback import challenge_cup_fallback


def make_project(request="", **facts):
    return {"state": {"initial_request": request, "confirmed_facts": facts}}


def test_explicit_invention_gets_creation_and_testing_sections():
    outline, notice = challenge_cup_fallback(make_project("参加挑战杯科技发明制作，作品是无人机。"))
    titles = [item["title"] for item in outline]
    assert "设计方案与制作过程" in titles and "测试验证与结果" in titles
    assert "科技发明制作" in notice and "调查结果与分析" not in titles


def test_explicit_social_and_natural_science_use_corresponding_sections():
    social, _ = challenge_cup_fallback(make_project("挑战杯社会调查，研究校园学习习惯"))
    natural, _ = challenge_cup_fallback(make_project("挑战杯", work_type="natural_science"))
    assert "调查设计与研究方法" in [item["title"] for item in social]
    assert "研究方法与过程" in [item["title"] for item in natural]


def test_unclear_or_conflicting_category_never_guesses():
    for project in (make_project("挑战杯无人机项目"),
                    make_project("挑战杯，自然科学还是科技发明制作？"),
                    make_project("挑战杯", work_type="natural_science", category="social_science"),
                    make_project("挑战杯，例如科技发明制作")):
        outline, notice = challenge_cup_fallback(project)
        assert "请确认作品类别" in notice
        assert "作品内容与方法" in [item["title"] for item in outline]


def test_negative_category_not_selected_and_confirmed_type_beats_old_request():
    outline, notice = challenge_cup_fallback(make_project("挑战杯不是社会调查，是科技发明制作"))
    assert "科技发明制作" in notice and "设计方案与制作过程" in [item["title"] for item in outline]
    _, notice = challenge_cup_fallback(make_project("想做社会调查", work_type="tech_invention"))
    assert "科技发明制作" in notice

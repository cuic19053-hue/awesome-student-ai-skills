#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
awesome-student-ai-skills · 分流决策树 (Dispatcher)
=============================================

本模块为「大学生申报书制作 skill」提供分流决策能力。当前项目下挂 30 个子 skill，
覆盖奖学金 / 评优 / 政治材料 / 科研立项 / 学科竞赛 / 三下乡 / 其他实践 等七大类。
用户输入"我要申报 X"时往往无法判断应分流到哪个子 skill，本模块通过以下两种机制
帮助上层 agent / CLI 用户快速定位 top 3 候选子 skill：

  1. 关键词匹配 (keyword_match)：基于 index.json 中声明的 triggers 列表做加权打分，
     适合一次性给出原始文本（如 CLI：python dispatcher.py "国家级项目立项逻辑评测"）。
  2. 交互式决策树 (interactive_dispatch)：5 个问题（Q1~Q5）逐步缩小范围，适合
     用户在 CLI 中走完一次完整问答。

依赖：
  - Python 3.8+
  - 仅依赖标准库（json / os / sys / re / argparse / datetime / pathlib）

入口：
  - CLI: python dispatcher.py "国家级项目立项逻辑评测"          # 关键词匹配返回 top 3
  - CLI: python dispatcher.py -i                        # 交互式决策树
  - CLI: python dispatcher.py --list                    # 列出全部子 skill
  - CLI: python dispatcher.py --info national_project_eval  # 查看某子 skill 详情

文件位置约定：
  - 本文件：utils/dispatcher.py
  - 索引文件：../index.json  (即 skills/awesome-student-ai-skills/index.json)
  - 子 skill：../subskills/<name>/SKILL.md 与 ../subskills/<name>/build.py
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ============================================================================
# 路径常量
# ============================================================================
THIS_FILE = Path(__file__).resolve()
UTILS_DIR = THIS_FILE.parent                       # .../utils
PROJECT_DIR = UTILS_DIR.parent                     # .../awesome-student-ai-skills
INDEX_JSON_PATH = PROJECT_DIR / "index.json"
VERSION_JSON_PATH = PROJECT_DIR / "version.json"
SUBSKILLS_DIR = PROJECT_DIR / "subskills"

# ============================================================================
# 决策树定义 (5 个层级，覆盖 30 个子 skill)
# ============================================================================
# 每个节点格式：
#   {
#     "id": "Q1",
#     "question": "问题文本",
#     "options": [
#       {"label": "选项显示", "value": "选项值", "next": "下一节点 id 或叶子",
#        "skills": ["叶子节点时直接列出的子 skill name"]},
#       ...
#     ]
#   }
# 叶子节点用 "skills" 字段标记候选子 skill。
# ============================================================================

DECISION_TREE: Dict[str, Dict[str, Any]] = {
    "Q1": {
        "id": "Q1",
        "question": "你这次想申请/撰写的是什么类型？",
        "prompt_hint": "请输入选项编号或关键词",
        "options": [
            {"label": "奖学金（励志/校奖/企业/单项/助学金）", "value": "scholarship", "next": "Q2"},
            {"label": "评优（优秀学生/毕业生/班干部/文明大学生/班集体）", "value": "honor", "next": "Q3"},
            {"label": "政治材料（入团）", "value": "political", "next": "Q4"},
            {"label": "科研立项（大创/校级/院级/立项评测）", "value": "research", "next": "Q5"},
            {"label": "学科竞赛（挑战杯/互联网+）", "value": "competition", "next": "Q6"},
            {"label": "三下乡 / 暑期社会实践", "value": "practice", "next": "Q7"},
            {"label": "征兵 / 应征入伍", "value": "military", "next": "Q9"},
            {"label": "公派留学 / 交流项目", "value": "study_abroad", "next": "Q10"},
            {"label": "其他（保研/选调生/转专业）", "value": "other", "next": "Q8"},
        ],
    },
    # ----------------------------------------------------------------------
    # Q2: 奖学金细分
    # ----------------------------------------------------------------------
    "Q2": {
        "id": "Q2",
        "question": "你要申请的是哪种奖学金？",
        "prompt_hint": "看金额/排名/家庭经济情况选",
        "options": [
            {"label": "国家励志奖学金（5000 元，前 30%，家庭经济困难）", "value": "motivation",
             "skills": ["motivation_scholarship"]},
            {"label": "校级奖学金（1/2/3 等，纯看成绩）", "value": "university",
             "skills": ["university_scholarship"]},
            {"label": "企业/社会专项奖学金（看行业匹配+职业规划）", "value": "enterprise",
             "skills": ["enterprise_scholarship"]},
            {"label": "单项奖学金（科研/文体/社工/实践等单点突出）", "value": "single",
             "skills": ["single_scholarship"]},
            {"label": "国家助学金（家庭经济困难，无需成绩排名）", "value": "grant",
             "skills": ["grant_application"]},
        ],
    },
    # ----------------------------------------------------------------------
    # Q3: 评优细分
    # ----------------------------------------------------------------------
    "Q3": {
        "id": "Q3",
        "question": "你要评的是哪种荣誉？",
        "prompt_hint": "看面向群体（在校生/毕业生/班干部/毕设评优）",
        "options": [
            {"label": "优秀学生 / 三好学生（在校生学年评优）", "value": "student",
             "skills": ["outstanding_student"]},
            {"label": "优秀毕业生（应届毕业生，看四年综合）", "value": "graduate",
             "skills": ["outstanding_graduate"]},
            {"label": "优秀学生干部 / 优秀班干部", "value": "cadre",
             "skills": ["outstanding_cadre"]},
            {"label": "文明大学生 / 优秀团员", "value": "civilized",
             "skills": ["civilized_student"]},
            {"label": "优秀班集体（班级集体申报）", "value": "collective",
             "skills": ["class_collective"]},
            {"label": "优秀毕业设计/论文申报书（毕设评优）", "value": "thesis",
             "skills": ["outstanding_thesis"]},
        ],
    },
    # ----------------------------------------------------------------------
    # Q4: 政治材料细分
    # ----------------------------------------------------------------------
    "Q4": {
        "id": "Q4",
        "question": "你要写的是哪种政治材料？",
        "prompt_hint": "看身份（团员/青年）",
        "options": [
            {"label": "入团申请书（申请加入共青团）", "value": "league",
             "skills": ["youth_league_application"]},
        ],
    },
    # ----------------------------------------------------------------------
    # Q5: 科研立项细分
    # ----------------------------------------------------------------------
    "Q5": {
        "id": "Q5",
        "question": "你要申报的是哪种科研立项或评测？",
        "prompt_hint": "看级别（国家级/校级/院级）与类型（评估/学术/创业模拟/真创业）",
        "options": [
            {"label": "国家级项目立项逻辑评测（针对申报书进行逻辑纠错与诊断）", "value": "national_eval",
             "skills": ["national_project_eval"]},
            {"label": "大创 · 创新训练（学术研究，产出论文/专利）", "value": "innovation",
             "skills": ["innovation_research"]},
            {"label": "大创 · 创业训练（商业计划书模拟，不注册公司）", "value": "training",
             "skills": ["entrepreneurship_training"]},
            {"label": "大创 · 创业实践（真实注册公司运营 6 个月+）", "value": "practice",
             "skills": ["entrepreneurship_practice"]},
            {"label": "校级科研立项（SRTP，1-3 人，2000-5000 元）", "value": "university",
             "skills": ["university_research"]},
            {"label": "院级科研立项（院设，规模更小）", "value": "college",
             "skills": ["college_research"]},
        ],
    },
    # ----------------------------------------------------------------------
    # Q6: 学科竞赛细分
    # ----------------------------------------------------------------------
    "Q6": {
        "id": "Q6",
        "question": "你参加的是哪个学科竞赛？",
        "prompt_hint": "挑战杯=学术作品赛；互联网+=创业计划赛（含主赛道与红旅赛道）",
        "options": [
            {"label": "挑战杯（课外学术科技作品竞赛）", "value": "challenge",
             "skills": ["challenge_cup"]},
            {"label": "互联网+ 主赛道（大学生创新创业大赛，商业计划书）", "value": "internet",
             "skills": ["internet_plus"]},
            {"label": "互联网+ 红色之旅赛道（青年红色筑梦之旅）", "value": "red_tour",
             "skills": ["internet_plus_red_tour"]},
        ],
    },
    # ----------------------------------------------------------------------
    # Q7: 三下乡 / 暑期社会实践细分
    # ----------------------------------------------------------------------
    "Q7": {
        "id": "Q7",
        "question": "你的暑期社会实践具体是哪一类？",
        "prompt_hint": "看实践内容（调研/支教/宣讲/科技/西部）",
        "options": [
            {"label": "三下乡社会调查（问卷/访谈/调研报告）", "value": "survey",
             "skills": ["social_survey"]},
            {"label": "支教（教育帮扶）", "value": "teach",
             "skills": ["volunteer_teaching"]},
            {"label": "政策宣讲 / 理论宣讲", "value": "policy",
             "skills": ["policy_lecture"]},
            {"label": "科技服务 / 科技下乡", "value": "tech",
             "skills": ["tech_service"]},
            {"label": "西部计划（西部志愿服务）", "value": "western",
             "skills": ["western_plan"]},
        ],
    },
    # ----------------------------------------------------------------------
    # Q8: 其他类细分
    # ----------------------------------------------------------------------
    "Q8": {
        "id": "Q8",
        "question": "你要写的是哪一种？",
        "prompt_hint": "保研推免/选调生/转专业",
        "options": [
            {"label": "保研推免申请书（免试读研）", "value": "baoyan",
             "skills": ["graduate_recommendation"]},
            {"label": "选调生申请（基层公务员选调）", "value": "xuandiao",
             "skills": ["selected_graduate"]},
            {"label": "转专业申请书（校内转专业）", "value": "transfer",
             "skills": ["major_transfer"]},
        ],
    },
    # ----------------------------------------------------------------------
    # Q9: 征兵/入伍细分（当前仅 1 个子 skill，预留扩展位）
    # ----------------------------------------------------------------------
    "Q9": {
        "id": "Q9",
        "question": "你要写的是哪一种征兵/入伍材料？",
        "prompt_hint": "当前仅应征入伍申请书；后续可扩展退役优待/征兵宣传等",
        "options": [
            {"label": "应征入伍申请书（在校生/毕业生入伍）", "value": "enlistment",
             "skills": ["military_enlistment"]},
        ],
    },
    # ----------------------------------------------------------------------
    # Q10: 公派留学/交流项目细分
    # ----------------------------------------------------------------------
    "Q10": {
        "id": "Q10",
        "question": "你要申请的是哪一种留学/交流项目？",
        "prompt_hint": "CSC 公派 vs 校际交换",
        "options": [
            {"label": "CSC 国家公派留学申请书（留学基金委）", "value": "csc",
             "skills": ["csc_scholarship"]},
            {"label": "交流项目申请书（校际/院际/CSC 交换）", "value": "exchange",
             "skills": ["exchange_program"]},
        ],
    },
}

# ============================================================================
# 类别 → 中文显示名映射
# ============================================================================
CATEGORY_DISPLAY = {
    "scholarship": "奖学金",
    "honor": "评优",
    "political": "政治",
    "research": "科研",
    "competition": "竞赛",
    "practice": "三下乡/实践",
    "military": "征兵/入伍",
    "study_abroad": "公派留学/交流",
    "other": "其他",
}

# 类别关键词：用于 keyword_match 阶段一（粗筛大类）
CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "scholarship": ["奖学金", "励志", "校奖", "企业奖", "单项奖", "助学金",
                    "scholarship", "grant", "5000"],
    "honor": ["评优", "优秀学生", "三好学生", "优秀毕业生", "优秀班干部", "优秀学生干部",
              "文明大学生", "优秀团员", "优秀班集体", "honor", "outstanding"],
    "political": ["入团", "团", "political", "league"],
    "research": ["大创", "创新训练", "创业训练", "创业实践", "科研立项", "校级科研",
                 "院级科研", "SRTP", "立项评测", "逻辑评测", "国家级项目", "research", "innovation", "entrepreneurship", "national_project_eval"],
    "competition": ["挑战杯", "互联网+", "互联网＋", "创新创业大赛", "竞赛",
                    "challenge", "internet plus"],
    "practice": ["三下乡", "暑期实践", "社会实践", "支教", "政策宣讲", "理论宣讲",
                 "科技下乡", "西部计划", "practice", "volunteer", "western"],
    "military": ["入伍", "参军", "应征", "征兵", "退役", "军事", "部队", "military",
                  "enlistment"],
    "study_abroad": ["公派留学", "公派", "CSC", "留学基金委", "交换生", "交换项目",
                     "交流项目", "校际交流", "院际交流", "study abroad", "exchange"],
    "other": ["保研", "推免", "选调生", "转专业", "baoyan", "graduate recommendation",
              "selected", "transfer"],
}


# ============================================================================
# Dispatcher 主类
# ============================================================================
class Dispatcher:
    """大学生申报书分流决策树主类。

    使用方式：
        d = Dispatcher()
        top3 = d.dispatch("我想申请国奖")
        for item in top3:
            print(item["name"], item["score"], item["display_name"])

        # 交互式
        d.interactive_dispatch()
    """

    TOP_N_DEFAULT = 3
    MIN_SCORE_THRESHOLD = 1  # 低于此分数的候选项会被过滤

    def __init__(self, index_path: Optional[Path] = None) -> None:
        self.index_path: Path = index_path or INDEX_JSON_PATH
        self.index: Dict[str, Any] = {}
        self.skills: List[Dict[str, Any]] = []
        self.load_index()

    # ------------------------------------------------------------------
    # 索引加载
    # ------------------------------------------------------------------
    def load_index(self) -> Dict[str, Any]:
        """加载 index.json，返回解析后的字典。

        若 index.json 不存在或解析失败，会自动 fallback 到内置的硬编码子 skill
        元数据（保证 dispatcher 在 index.json 缺失时仍能工作）。
        """
        try:
            with open(self.index_path, "r", encoding="utf-8") as f:
                self.index = json.load(f)
            self.skills = self.index.get("skills", [])
            return self.index
        except FileNotFoundError:
            sys.stderr.write(
                f"[dispatcher] 警告：index.json 不存在 ({self.index_path})，"
                "使用内置 fallback。\n"
            )
            self.skills = _FALLBACK_SKILLS
            self.index = {"skills": self.skills, "version": "fallback"}
            return self.index
        except json.JSONDecodeError as e:
            sys.stderr.write(
                f"[dispatcher] 警告：index.json 解析失败 ({e})，使用内置 fallback。\n"
            )
            self.skills = _FALLBACK_SKILLS
            self.index = {"skills": self.skills, "version": "fallback"}
            return self.index

    # ------------------------------------------------------------------
    # 关键词匹配 (打分)
    # ------------------------------------------------------------------
    def keyword_match(self, text: str) -> List[Dict[str, Any]]:
        """对用户输入文本做关键词匹配，返回所有候选及其分数（已排序）。

        打分规则：
          - 每个 trigger 命中 +2 分
          - 子 skill name 命中 +3 分
          - 类别关键词命中 +1 分（每个类别最多 +2）
          - display_name 命中 +4 分
        """
        if not text:
            return []
        text_lower = text.lower().strip()
        results: List[Dict[str, Any]] = []

        # 1) 先粗筛大类
        category_hits: Dict[str, int] = {}
        for cat, kws in CATEGORY_KEYWORDS.items():
            hits = sum(1 for kw in kws if kw.lower() in text_lower)
            if hits > 0:
                category_hits[cat] = min(hits, 2)  # 类别最多 +2

        # 2) 对每个子 skill 打分
        for skill in self.skills:
            score = 0
            matched: List[str] = []

            # name 命中
            if skill.get("name", "").lower() in text_lower:
                score += 3
                matched.append(f"name:{skill['name']}")

            # display_name 命中
            dname = skill.get("display_name", "")
            if dname and dname.lower() in text_lower:
                score += 4
                matched.append(f"display_name:{dname}")

            # triggers 命中
            for trig in skill.get("triggers", []):
                if trig.lower() in text_lower:
                    score += 2
                    matched.append(f"trigger:{trig}")

            # 类别加分
            cat = skill.get("category", "")
            if cat in category_hits:
                score += category_hits[cat]
                matched.append(f"category:{cat}+{category_hits[cat]}")

            if score >= self.MIN_SCORE_THRESHOLD:
                results.append({
                    "name": skill.get("name"),
                    "display_name": dname,
                    "category": cat,
                    "category_display": CATEGORY_DISPLAY.get(cat, cat),
                    "description": skill.get("description", ""),
                    "score": score,
                    "matched": matched,
                    "skill_md_path": skill.get("skill_md_path", ""),
                    "build_py_path": skill.get("build_py_path", ""),
                })

        # 按分数降序，同分按 name 字母序
        results.sort(key=lambda x: (-x["score"], x["name"] or ""))
        return results

    # ------------------------------------------------------------------
    # 主分流函数 (返回 top N)
    # ------------------------------------------------------------------
    def dispatch(self, user_input: str, top_n: int = TOP_N_DEFAULT) -> List[Dict[str, Any]]:
        """根据用户输入文本，返回推荐的子 skill 列表（top N）。

        Args:
            user_input: 用户原始文本，如 "我想申请国奖" 或 "我要写申请材料"
            top_n: 返回前 N 个候选，默认 3

        Returns:
            List[Dict]，每项含 name/display_name/category/description/score/matched
        """
        candidates = self.keyword_match(user_input)
        if not candidates:
            # fallback：返回空列表，调用方可触发 interactive_dispatch
            return []
        return candidates[:top_n]

    # ------------------------------------------------------------------
    # 交互式决策树
    # ------------------------------------------------------------------
    def interactive_dispatch(self) -> List[Dict[str, Any]]:
        """CLI 交互式决策树分流。

        逐题问 Q1~Q5（视用户回答决定后续问题），最终输出叶子节点推荐的子 skill。

        Returns:
            List[Dict]，叶子节点声明的子 skill 列表
        """
        print("=" * 60)
        print("  大学生申报书分流决策树 (interactive)")
        print("  输入选项编号或关键词；输入 q 退出；输入 b 回上一题")
        print("=" * 60)

        history: List[str] = []          # 走过的节点 id
        current_id: Optional[str] = "Q1"
        last_skills: List[str] = []

        while current_id:
            node = DECISION_TREE.get(current_id)
            if not node:
                break
            history.append(current_id)

            print(f"\n[{node['id']}] {node['question']}")
            if node.get("prompt_hint"):
                print(f"    提示: {node['prompt_hint']}")
            for i, opt in enumerate(node["options"], 1):
                print(f"  {i}. {opt['label']}")

            raw = input("  > ").strip()
            if raw.lower() in ("q", "quit", "exit"):
                print("已退出。")
                return []
            if raw.lower() in ("b", "back") and len(history) >= 2:
                history.pop()  # 弹出当前
                history.pop()  # 弹出上一个
                current_id = history[-1] if history else "Q1"
                continue

            # 解析输入：优先按编号，其次按 value/label 关键词
            choice = self._parse_choice(raw, node["options"])
            if choice is None:
                print("  ⚠ 无法识别，请重新输入。")
                history.pop()
                continue

            if "skills" in choice:
                # 叶子节点
                last_skills = choice["skills"]
                break
            elif "next" in choice:
                current_id = choice["next"]
            else:
                print("  ⚠ 选项配置异常，请重新输入。")
                history.pop()
                continue

        if not last_skills:
            print("\n未匹配到任何子 skill。")
            return []

        # 展示结果
        print("\n" + "=" * 60)
        print("  推荐子 skill:")
        print("=" * 60)
        results: List[Dict[str, Any]] = []
        for sname in last_skills:
            meta = self._find_skill_by_name(sname)
            if meta:
                results.append(meta)
                print(f"  • {meta['name']}  --  {meta.get('display_name', '')}")
                print(f"      {meta.get('description', '')}")
                print(f"      SKILL.md: {meta.get('skill_md_path', '')}")
            else:
                print(f"  • {sname}  (索引中未找到详情)")
        return results

    # ------------------------------------------------------------------
    # 辅助：解析用户输入选项
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_choice(raw: str, options: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """把用户输入解析为某个 option。返回 option dict 或 None。"""
        raw = raw.strip()
        if not raw:
            return None
        # 1) 数字编号
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                return options[idx]
        # 2) value 精确匹配
        raw_lower = raw.lower()
        for opt in options:
            if opt.get("value", "").lower() == raw_lower:
                return opt
        # 3) label / value 模糊包含
        for opt in options:
            label = opt.get("label", "").lower()
            value = opt.get("value", "").lower()
            if raw_lower in label or raw_lower in value or value in raw_lower:
                return opt
        return None

    # ------------------------------------------------------------------
    # 辅助：按 name 查 skill 元数据
    # ------------------------------------------------------------------
    def _find_skill_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        for s in self.skills:
            if s.get("name") == name:
                return s
        return None

    # ------------------------------------------------------------------
    # 列出全部子 skill
    # ------------------------------------------------------------------
    def list_all(self) -> List[Dict[str, Any]]:
        """按 category 分组返回所有子 skill。"""
        return sorted(self.skills, key=lambda x: (x.get("category", ""), x.get("name", "")))

    # ------------------------------------------------------------------
    # 查看某子 skill 详情
    # ------------------------------------------------------------------
    def info(self, name: str) -> Optional[Dict[str, Any]]:
        return self._find_skill_by_name(name)

    # ------------------------------------------------------------------
    # 自检：验证 index.json 与实际 subskills/ 目录一致性
    # ------------------------------------------------------------------
    def selfcheck(self) -> Dict[str, Any]:
        """检查 index.json 中声明的 skills 是否与磁盘 subskills/ 目录一致。

        磁盘上的「真实子 skill」定义为：subskills/<name>/ 下存在 SKILL.md 文件。
        空 placeholder 目录（无 SKILL.md）会被归类到 `empty_placeholders`，
        不计入 `missing_in_index`，避免误报。

        Returns:
            Dict 含 indexed_dirs / disk_dirs / missing_in_index / missing_on_disk
                 / empty_placeholders / ok
        """
        indexed = {s["name"] for s in self.skills if "name" in s}
        real_disk = set()
        empty_placeholders: List[str] = []
        for p in SUBSKILLS_DIR.iterdir():
            if not p.is_dir():
                continue
            if (p / "SKILL.md").exists():
                real_disk.add(p.name)
            else:
                empty_placeholders.append(p.name)
        missing_in_index = sorted(real_disk - indexed)
        missing_on_disk = sorted(indexed - real_disk)
        return {
            "indexed_count": len(indexed),
            "disk_count": len(real_disk),
            "empty_placeholders": sorted(empty_placeholders),
            "missing_in_index": missing_in_index,
            "missing_on_disk": missing_on_disk,
            "ok": (not missing_in_index) and (not missing_on_disk),
        }


# ============================================================================
# Fallback 子 skill 列表（当 index.json 缺失时使用）
# 仅列 name / display_name / category / triggers / description，路径字段留空
# ============================================================================
_FALLBACK_SKILLS: List[Dict[str, Any]] = [
    {"name": "national_project_eval", "display_name": "国家级项目立项逻辑评测",
     "category": "research", "triggers": ["国家级项目立项逻辑评测", "项目立项逻辑评测", "立项逻辑评估"],
     "description": "国家级项目申报书立项逻辑评测与诊断"},
    {"name": "motivation_scholarship", "display_name": "国家励志奖学金",
     "category": "scholarship", "triggers": ["励志", "励志奖学金", "5000"],
     "description": "国家励志奖学金 5000 元/人，前 30%，家庭经济困难"},
    {"name": "university_scholarship", "display_name": "校级奖学金",
     "category": "scholarship", "triggers": ["校奖", "校级奖学金", "一等奖学金"],
     "description": "校设奖学金，1/2/3 等，纯看成绩"},
    {"name": "enterprise_scholarship", "display_name": "企业专项奖学金",
     "category": "scholarship", "triggers": ["企业奖", "专项奖", "华为奖"],
     "description": "企业/社会团体设立，看行业匹配+职业规划"},
    {"name": "single_scholarship", "display_name": "单项奖学金",
     "category": "scholarship", "triggers": ["单项奖", "科研单项", "文体单项"],
     "description": "单点突出（科研/文体/社工/实践）即可"},
    {"name": "grant_application", "display_name": "国家助学金",
     "category": "scholarship", "triggers": ["助学金", "国家助学金", "贫困生"],
     "description": "家庭经济困难认定后申请，无需成绩排名"},
    {"name": "outstanding_student", "display_name": "优秀学生/三好学生",
     "category": "honor", "triggers": ["优秀学生", "三好学生", "学年评优"],
     "description": "在校生学年评优，思想+学习+身体三方面"},
    {"name": "outstanding_graduate", "display_name": "优秀毕业生",
     "category": "honor", "triggers": ["优秀毕业生", "省优", "校优"],
     "description": "毕业前最高荣誉，看四年综合"},
    {"name": "outstanding_cadre", "display_name": "优秀学生干部",
     "category": "honor", "triggers": ["优秀班干部", "优秀学生干部", "班干部"],
     "description": "面向班干部的评优"},
    {"name": "civilized_student", "display_name": "文明大学生/优秀团员",
     "category": "honor", "triggers": ["文明大学生", "优秀团员", "文明素养"],
     "description": "侧重文明素养与团员先进性"},
    {"name": "class_collective", "display_name": "优秀班集体",
     "category": "honor", "triggers": ["优秀班集体", "班集体", "先进班级"],
     "description": "班级集体申报的荣誉"},
    {"name": "youth_league_application", "display_name": "入团申请书",
     "category": "political", "triggers": ["入团", "入团申请", "共青团"],
     "description": "申请加入共青团"},
    {"name": "innovation_research", "display_name": "大创·创新训练",
     "category": "research", "triggers": ["大创", "创新训练", "大创创新"],
     "description": "大创学术研究类，产出论文/专利"},
    {"name": "entrepreneurship_training", "display_name": "大创·创业训练",
     "category": "research", "triggers": ["创业训练", "商业计划模拟"],
     "description": "大创商业计划书模拟，不注册公司"},
    {"name": "entrepreneurship_practice", "display_name": "大创·创业实践",
     "category": "research", "triggers": ["创业实践", "真实注册公司"],
     "description": "大创真实公司运营 6 个月+"},
    {"name": "university_research", "display_name": "校级科研立项",
     "category": "research", "triggers": ["校级科研", "SRTP", "校级立项"],
     "description": "校级 SRTP，1-3 人，2000-5000 元"},
    {"name": "college_research", "display_name": "院级科研立项",
     "category": "research", "triggers": ["院级科研", "院级立项"],
     "description": "院级科研训练，规模更小"},
    {"name": "challenge_cup", "display_name": "挑战杯",
     "category": "competition", "triggers": ["挑战杯", "课外学术", "学术作品"],
     "description": "课外学术科技作品竞赛"},
    {"name": "internet_plus", "display_name": "互联网+",
     "category": "competition", "triggers": ["互联网+", "互联网＋", "创新创业大赛"],
     "description": "大学生创新创业大赛，商业计划书"},
    {"name": "social_survey", "display_name": "三下乡社会调查",
     "category": "practice", "triggers": ["三下乡", "社会调查", "暑期实践"],
     "description": "暑期社会实践，调研报告"},
    {"name": "volunteer_teaching", "display_name": "支教",
     "category": "practice", "triggers": ["支教", "教育帮扶", "志愿支教"],
     "description": "暑期支教志愿活动"},
    {"name": "policy_lecture", "display_name": "政策宣讲",
     "category": "practice", "triggers": ["政策宣讲", "理论宣讲"],
     "description": "政策/理论宣讲实践"},
    {"name": "tech_service", "display_name": "科技服务",
     "category": "practice", "triggers": ["科技服务", "科技下乡"],
     "description": "科技下乡/科技服务实践"},
    {"name": "western_plan", "display_name": "西部计划",
     "category": "practice", "triggers": ["西部计划", "西部志愿"],
     "description": "大学生志愿服务西部计划"},
    {"name": "graduate_recommendation", "display_name": "保研推免",
     "category": "other", "triggers": ["保研", "推免", "免试读研"],
     "description": "保研推免申请书/申请表"},
    {"name": "selected_graduate", "display_name": "选调生申请",
     "category": "other", "triggers": ["选调生", "基层选调"],
     "description": "选调生（基层公务员）申请"},
    {"name": "major_transfer", "display_name": "转专业申请",
     "category": "other", "triggers": ["转专业", "专业转换"],
     "description": "校内转专业申请"},
    {"name": "military_enlistment", "display_name": "应征入伍申请书",
     "category": "military", "triggers": ["应征入伍", "大学生入伍", "参军", "征兵", "入伍申请"],
     "description": "大学生应征入伍申请书，5 段结构，3 档字数版本"},
    {"name": "csc_scholarship", "display_name": "CSC 国家公派留学申请书",
     "category": "study_abroad", "triggers": ["CSC", "公派留学", "国家公派", "留学基金委"],
     "description": "国家公派留学申请书，6 段结构，3 档字数版本"},
    {"name": "exchange_program", "display_name": "交流项目申请书",
     "category": "study_abroad", "triggers": ["交流项目", "交换生", "校际交流", "交换项目"],
     "description": "大学生交流项目申请书，5 段结构"},
    {"name": "internet_plus_red_tour", "display_name": "互联网+红旅赛道",
     "category": "competition", "triggers": ["互联网+红旅", "红旅赛道", "红色之旅", "红色筑梦"],
     "description": "互联网+大赛红色之旅赛道商业计划书"},
    {"name": "outstanding_thesis", "display_name": "优秀毕业设计/论文申报书",
     "category": "honor", "triggers": ["优秀毕业设计", "优秀毕业论文", "毕设评优"],
     "description": "优秀毕业设计/论文申报书"},
]


# ============================================================================
# CLI 输出格式化辅助
# ============================================================================
def _print_top_n(results: List[Dict[str, Any]], user_input: str) -> None:
    """友好打印 top N 推荐。"""
    print(f"\n用户输入: {user_input!r}")
    print(f"匹配到 {len(results)} 个候选:\n")
    for i, r in enumerate(results, 1):
        print(f"  [{i}] {r['name']}  ({r.get('category_display', '')}) "
              f"--  {r.get('display_name', '')}")
        print(f"      分数: {r['score']}  |  命中: {', '.join(r.get('matched', []))}")
        print(f"      描述: {r.get('description', '')}")
        print(f"      SKILL.md: {r.get('skill_md_path', '')}")
        print()


def _print_list_all(skills: List[Dict[str, Any]]) -> None:
    """按类别分组打印全部子 skill。"""
    by_cat: Dict[str, List[Dict[str, Any]]] = {}
    for s in skills:
        by_cat.setdefault(s.get("category", "other"), []).append(s)
    print(f"\n共 {len(skills)} 个子 skill，分布如下:\n")
    for cat, items in sorted(by_cat.items()):
        cat_disp = CATEGORY_DISPLAY.get(cat, cat)
        print(f"  【{cat_disp}】({len(items)} 个)")
        for s in items:
            print(f"    - {s['name']:<32} {s.get('display_name', '')}")
        print()


def _print_info(skill: Optional[Dict[str, Any]]) -> None:
    if not skill:
        print("未找到该子 skill。")
        return
    print(json.dumps(skill, ensure_ascii=False, indent=2))


# ============================================================================
# CLI 主入口
# ============================================================================
def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dispatcher",
        description="大学生申报书分流决策树 (awesome-student-ai-skills)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python dispatcher.py "我想申请国奖"          # 关键词匹配，返回 top 3
  python dispatcher.py -i                        # 交互式决策树
  python dispatcher.py --list                    # 列出全部子 skill
  python dispatcher.py --info national_project_eval   # 查看某子 skill 详情
  python dispatcher.py --selfcheck               # 自检 index.json 与目录一致性
""",
    )
    parser.add_argument("query", nargs="?", default=None,
                        help="用户输入文本，如 \"我想申请国奖\"")
    parser.add_argument("-i", "--interactive", action="store_true",
                        help="进入交互式决策树")
    parser.add_argument("-l", "--list", action="store_true",
                        help="列出全部子 skill")
    parser.add_argument("--info", metavar="NAME",
                        help="查看某子 skill 详情 (name)")
    parser.add_argument("-n", "--top-n", type=int, default=Dispatcher.TOP_N_DEFAULT,
                        help=f"返回前 N 个候选，默认 {Dispatcher.TOP_N_DEFAULT}")
    parser.add_argument("--selfcheck", action="store_true",
                        help="自检 index.json 与磁盘目录一致性")
    parser.add_argument("--json", action="store_true",
                        help="以 JSON 输出（便于上层 agent 解析）")
    args = parser.parse_args(argv)

    d = Dispatcher()

    # ---- 自检 ----
    if args.selfcheck:
        result = d.selfcheck()
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 1

    # ---- 列出全部 ----
    if args.list:
        all_skills = d.list_all()
        if args.json:
            print(json.dumps(all_skills, ensure_ascii=False, indent=2))
        else:
            _print_list_all(all_skills)
        return 0

    # ---- 查看详情 ----
    if args.info:
        skill = d.info(args.info)
        if args.json:
            print(json.dumps(skill or {}, ensure_ascii=False, indent=2))
        else:
            _print_info(skill)
        return 0 if skill else 1

    # ---- 交互式 ----
    if args.interactive:
        results = d.interactive_dispatch()
        if args.json and results:
            print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0

    # ---- 关键词匹配 ----
    if args.query:
        results = d.dispatch(args.query, top_n=args.top_n)
        if args.json:
            print(json.dumps({
                "query": args.query,
                "top_n": args.top_n,
                "results": results,
            }, ensure_ascii=False, indent=2))
        else:
            if not results:
                print(f"\n未匹配到任何子 skill。输入: {args.query!r}")
                print("建议运行 `python dispatcher.py -i` 进入交互式决策树。")
                return 1
            _print_top_n(results, args.query)
        return 0

    # 无参数则打印 help
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

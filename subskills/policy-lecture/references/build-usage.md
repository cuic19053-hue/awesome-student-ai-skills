# 十二、docx 生成调用方式

> 从 `subskills/policy-lecture/SKILL.md` 外移而来（渐进式披露）。
> 何时阅读：需要调用 build.py 生成文档、或排查生成参数时。

```bash
# 数据驱动模式（推荐）
python build.py --data data.json --out output.docx

# 演示模式（内置示例数据）
python build.py --demo --out demo.docx

# 查看帮助
python build.py --help
```

**data.json 字段**：team_name / theme / location / practice_time / team_size / leader_name / leader_id / leader_major / leader_grade / leader_phone / advisor_name / advisor_title / advisor_phone / advisor_with_team / college / apply_date / team_info / members / theme_background / purpose_significance / implementation_plan（含 form/audience_analysis/schedule）/ lecture_outline（含 theme/total_minutes/segments）/ safety_plan / expected_results / budget_items / budget_total / publicity_plan / include_school_approval。

**输出格式**：A4，宋体小四正文，黑体三号标题，1.5 倍行距，首行缩进 2 字符，页边距上下 2.54cm 左右 2.5cm。

**缺失字段处理**：缺字段不阻断生成，使用占位文本 + 终端警告。P0 字段缺失会显示警告，建议补全后重新生成。

**输出栏目顺序**：封面 → 一团队信息 → 二成员表 → 三主题背景 → 四目的意义 → 五实施方案（含按场次表）→ 六宣讲大纲 → 七安全预案 → 八预期成果 → 九经费预算 → 十宣传计划 → 十一签字栏 → （可选十二学校审批）。
**字段示例（data.json 片段，完整字段见 build.py DEFAULT_DATA）**：

```json
{
  "team_name": "赴 XX 县党的二十大精神宣讲团",
  "theme": "乡村振兴",
  "implementation_plan": {
    "audience_analysis": "本村常住人口 860 人...",
    "schedule": [
      {"date": "7.16", "location": "A 村党员活动室", "audience": "党员+村干部", "count": 35, "duration": "90 分钟", "speaker": "张三"}
    ]
  },
  "lecture_outline": {
    "theme": "党的二十大精神——乡村振兴维度",
    "total_minutes": 75,
    "segments": [
      {"phase": "开场", "minutes": 5, "content": "自我介绍+主题引出", "plain": "—", "case": "—"}
    ]
  }
}
```

---


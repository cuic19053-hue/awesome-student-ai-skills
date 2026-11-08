# 十一、docx 生成调用方式

> 从 `subskills/volunteer-teaching/SKILL.md` 外移而来（渐进式披露）。
> 何时阅读：需要调用 build.py 生成文档、或排查生成参数时。

### 11.1 命令行用法

```bash
python build.py --data data.json --out output.docx
python build.py --demo --out demo.docx
```

- `--data`：数据 JSON 文件路径（与 --demo 二选一）
- `--out`：输出 docx 路径（必填，自动创建目录）
- `--demo`：使用内置示例数据生成演示文档

### 11.2 JSON 字段说明

```json
{
  "team_name": "赴 XX 县乡村振兴支教团",
  "theme": "乡村振兴",
  "location": "XX 省 XX 县 XX 镇 XX 小学",
  "practice_time": "2025.07.15-07.28（14 天）",
  "team_size": "10 人",
  "leader_name": "张三",
  "apply_date": "2025 年 5 月 20 日",
  "college": "师范学院",
  "team_info": {"team_name":"...","theme":"...","location":"...",
                "practice_time":"...","team_size":"...","leader":"...","advisor":"..."},
  "members": [{"name":"...","id":"...","major":"...","role":"...","phone":"..."}],
  "theme_background": ["...", "..."],
  "purpose_significance": ["...", "..."],
  "implementation_plan": {"form":"...","schedule":[{"date":"7.15","work":"...","periods":"0","output":"..."}]},
  "curriculum": [{"period":"第1节","time":"8:00-8:40","subject":"语文","teacher":"张三","class":"小班"}],
  "lesson_plans": [{"title":"...","class":"...","teacher":"...","objectives":["...","..."],
                    "key_points":["..."],"difficulty":"...","process":"...","homework":"..."}],
  "safety_plan": ["...", "..."],
  "expected_results": ["..."],
  "budget_items": [{"item":"交通费","amount":"3640","basis":"..."}],
  "publicity_plan": ["..."],
  "budget_total": "14600"
}
```

缺字段时 build.py 用合理默认值，不会报错，但会输出校验警告到 stderr。

### 11.3 输出路径

默认输出到当前目录。建议命名规则：`三下乡_{团队简称}_{申报日期}.docx`，如 `三下乡_XX县支教_20250520.docx`。

---


# 十一、docx 生成调用方式

> 从 `subskills/tech-service/SKILL.md` 外移而来（渐进式披露）。
> 何时阅读：需要调用 build.py 生成文档、或排查生成参数时。

### 11.1 命令行调用

```bash
# 使用自定义数据生成
python build.py --data data.json --out output.docx

# 使用内置示例数据生成（演示用）
python build.py --demo --out demo.docx

# 查看帮助
python build.py --help
```

### 11.2 data.json 字段定义

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| team_name | str | 团队名称 | 赴 XX 县数字赋能科技服务团 |
| theme | str | 实践主题 | 乡村振兴 |
| location | str | 实践地点 | XX 省 XX 县 XX 镇 3 个行政村 |
| practice_time | str | 实践时间 | 2025.07.15-07.21（7 天） |
| team_size | str | 团队人数 | 5 人 |
| leader_name / leader_id / leader_major / leader_grade / leader_phone | str | 队长信息 | 张三/202212345/计算机 2022 级/大三/138XXXXXXXX |
| advisor_name / advisor_title / advisor_phone / advisor_with_team | str | 指导教师 | 李教授/副教授/139XXXXXXXX/随队 |
| college / apply_date | str | 申报单位/日期 | 计算机科学与技术学院/2025 年 5 月 20 日 |
| members | list | 成员信息（每人 5 字段） | [{name, id, major, role, phone}] |
| team_info | dict | 团队基本信息（与上述字段冗余，优先用 team_info） | 7 行 2 列表数据 |
| theme_background | list | 实践主题与背景（3 段） | [str, str, str] |
| purpose_significance | list | 实践目的与意义（2 段） | [str, str] |
| implementation_plan | dict | 实施方案（form/questionnaire/schedule） | 含场次表 |
| service_plan | dict | 服务方案（subdirection/needs_table/sustain_mechanism） | 4 列表数据 |
| safety_plan | list | 安全保障预案（5 段 + 服务专属） | [str × 5~6] |
| expected_results | list | 预期成果（6~8 项） | [str × 6~8] |
| budget_items | list | 经费预算（5 类 + 计算依据） | [{item, amount, basis} × 5] |
| budget_total | str | 预算合计 | 10000 |
| publicity_plan | list | 宣传计划（3 类媒体） | [str × 3] |
| include_school_approval | bool | 是否含学校审批意见 | False |

### 11.3 字段缺失处理

- P0 字段缺失：触发警告（stderr 输出），仍生成 docx 但含占位文本
- P1 字段缺失：触发警告，使用默认占位文本（评审会扣大分）
- P2 字段缺失：仅提示，不影响生成

---


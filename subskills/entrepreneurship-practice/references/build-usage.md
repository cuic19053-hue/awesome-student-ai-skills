# 十一、docx 生成调用方式

> 从 `subskills/entrepreneurship-practice/SKILL.md` 外移而来（渐进式披露）。
> 何时阅读：需要调用 build.py 生成文档、或排查生成参数时。

### 11.1 命令行用法

```bash
python build.py --data data.json --out output.docx
python build.py --demo --out demo.docx
```

- `--data`：数据 JSON 文件路径（必填，与 --demo 二选一）
- `--out`：输出 docx 路径（必填，自动创建目录）
- `--demo`：使用内置示例数据生成演示文档

### 11.2 JSON 字段说明

```json
{
  "project_name": "校园自习室智能预约平台'课座'",
  "project_level": "国家级", "project_type": "创业实践项目",
  "leader_name": "张三", "leader_id": "202212345",
  "leader_major": "工商管理", "leader_grade": "2022 级 大三",
  "leader_phone": "138XXXXXXXX",
  "advisor_name": "李教授", "advisor_title": "副教授",
  "advisor_research": "创业管理",
  "college": "工商管理学院", "apply_date": "2025 年 3 月 15 日",
  "basic_info": { "industry": "...", "company_name": "...", "credit_code": "...", "duration": "...", "budget": "20000", "leader_info": "...", "team_members": "...", "advisor_info": "..." },
  "abstract": "...",
  "company_overview": { "business_info": [...], "shareholders": [...], "governance": "..." },
  "product_market": { "features": [...], "market_analysis": "...", "tech_impl": "...", "ip_status": "..." },
  "business_operation": { "model": "...", "kpi_table": [...], "milestones": [...] },
  "financial_data": { "income_statement": [...], "cash_flow": [...], "balance_sheet": [...], "burn_runway": "..." },
  "team_organization": { "members": [...], "org_structure": "...", "salary": "..." },
  "financing_plan": { "history": [...], "current_round": "...", "term_sheet": "..." },
  "risk_response": [{"type":"...","risk":"...","prob":"...","impact":"...","measure":"..."}],
  "social_benefit": "...",
  "expected_outcomes": ["..."],
  "budget_items": [{"item":"...","amount":"...","basis":"..."}],
  "budget_total": "20000", "include_school_approval": false
}
```

缺字段时 build.py 用合理默认值，不会报错。

### 11.3 输出路径

默认输出到当前目录。建议命名：`{级别}_{公司代号}_{申报日期}.docx`，如 `国家级_课座_20250315.docx`。

---


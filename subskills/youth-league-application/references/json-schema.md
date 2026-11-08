# §15 JSON Schema 完整字段定义

> 从 `subskills/youth-league-application/SKILL.md` 外移而来（渐进式披露）。
> 何时阅读：构造 --data 输入文件、或 build.py 报字段校验错误时。

### 15.1 顶层字段（21 项）

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "入团申请书数据 Schema",
  "type": "object",
  "required": [
    "name", "student_id", "gender", "birth_date",
    "college", "major", "grade", "league_branch",
    "submit_date", "political_status"
  ],
  "properties": {
    "name":              {"type": "string", "description": "申请人姓名"},
    "student_id":        {"type": "string", "description": "学号"},
    "gender":            {"type": "string", "enum": ["男", "女"]},
    "birth_date":        {"type": "string", "description": "出生年月（汉字格式 YYYY 年 M 月）"},
    "college":           {"type": "string", "description": "学院全称"},
    "major":             {"type": "string", "description": "专业全称"},
    "grade":             {"type": "string", "description": "年级"},
    "class_name":        {"type": "string", "description": "班级"},
    "league_branch":     {"type": "string", "description": "团支部全称"},
    "submit_date":       {"type": "string", "description": "递交日期（汉字格式 YYYY 年 M 月 D 日）"},
    "political_status":  {"type": "string", "enum": ["群众", "少先队员", "共青团员", "中共党员"]},
    "salutation":        {"type": "string", "default": "敬爱的团组织："},
    "word_count_version":{"type": "string", "enum": ["compact", "standard", "enhanced"], "default": "standard"},
    "school_tier":       {"type": "string", "enum": ["loose", "normal", "strict"], "default": "normal"},
    "applicant_age":     {"type": "integer", "description": "申请人年龄（覆盖自动计算）"},
    "team_join_date":    {"type": "string", "description": "加入少先队日期"},
    "motivation":        {"type": "string", "description": "入团动机（不少于 200 字）"},
    "education_history": {"type": "array",  "items": {"$ref": "#/definitions/education_item"}},
    "family_members":    {"type": "array",  "items": {"$ref": "#/definitions/family_member"}},
    "social_relations":  {"type": "array",  "items": {"$ref": "#/definitions/family_member"}},
    "ideology_story":    {"type": "array",  "items": {"$ref": "#/definitions/ideology_item"}},
    "shortcomings":      {"type": "array",  "items": {"$ref": "#/definitions/shortcoming_item"}},
    "honor_awards":      {"type": "array",  "items": {"type": "string"}},
    "include_oath":      {"type": "boolean", "default": false, "description": "是否在结尾附入团誓词（默认 false）"},
    "require_family_appendix": {"type": "boolean", "default": true, "description": "是否附家庭成员附页（默认 true）"}
  },
  "definitions": {
    "education_item": {
      "type": "object",
      "properties": {
        "stage":    {"type": "string", "description": "阶段：小学/初中/高中/大学"},
        "start":    {"type": "string", "description": "起始时间"},
        "end":      {"type": "string", "description": "结束时间"},
        "school":   {"type": "string", "description": "学校名称"},
        "position": {"type": "string", "description": "担任职务"}
      }
    },
    "family_member": {
      "type": "object",
      "properties": {
        "relation":         {"type": "string", "description": "称谓：父亲/母亲/祖父等"},
        "name":             {"type": "string"},
        "birth_date":       {"type": "string"},
        "political_status": {"type": "string", "description": "政治面貌"},
        "work_unit":        {"type": "string", "description": "工作单位"},
        "position":         {"type": "string", "description": "职务"}
      }
    },
    "ideology_item": {
      "type": "object",
      "properties": {
        "time":   {"type": "string", "description": "时间"},
        "event":  {"type": "string", "description": "事件"},
        "thought":{"type": "string", "description": "思考"},
        "change": {"type": "string", "description": "变化"}
      }
    },
    "shortcoming_item": {
      "type": "object",
      "properties": {
        "description":  {"type": "string", "description": "不足描述"},
        "manifestation":{"type": "string", "description": "具体表现"},
        "improvement":  {"type": "string", "description": "改进措施"}
      }
    }
  }
}
```

### 15.2 字段消费规则

build.py 按以下规则消费 JSON 字段：

| 字段 | 消费方法 | 必填 | 说明 |
|------|----------|------|------|
| name | `_add_signature` | P0 | 落款第一行 |
| student_id | `_add_signature` | P0 | 落款第一行 |
| gender | `_validate_data` | P0 | 年龄校验辅助 |
| birth_date | `compute_age` | P0 | 计算 14-28 周岁校验 |
| college | `_add_signature` | P0 | 落款第一行 |
| major | `_add_signature` | P0 | 落款第一行 |
| grade | `_add_signature` | P0 | 落款第一行 |
| league_branch | `_add_salutation` | P0 | 团支部全称（落款附近或正文） |
| submit_date | `_add_signature` | P0 | 落款第二行（汉字格式） |
| political_status | `_validate_data` | P0 | 政治面貌校验 |
| salutation | `_add_salutation` | P2 | 默认"敬爱的团组织：" |
| word_count_version | `_resolve_config` | P2 | 路由段落配比 |
| school_tier | `_resolve_config` | P2 | 字数下限校验 |
| applicant_age | `_validate_data` | P2 | 覆盖自动计算 |
| team_join_date | `_add_personal_experience` | P1 | 个人经历段 |
| motivation | `_add_personal_experience` | P1 | 个人经历段（入团动机） |
| education_history | `_add_personal_experience` | P1 | 个人经历段 |
| family_members | `_add_family_appendix` | P1 | 家庭成员附页 |
| social_relations | `_add_family_appendix` | P2 | 家庭成员附页 |
| ideology_story | `_add_personal_experience` | P1 | 个人经历段（思想发展） |
| shortcomings | `_add_shortcomings` | P1 | 第四段（个人不足） |
| honor_awards | `_add_personal_experience` | P2 | 个人经历段（荣誉） |
| include_oath | `_add_oath_if_required` | P2 | 是否附入团誓词 |
| require_family_appendix | `_add_family_appendix` | P2 | 是否附家庭成员附页 |

---


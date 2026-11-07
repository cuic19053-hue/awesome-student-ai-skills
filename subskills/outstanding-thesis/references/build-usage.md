# §15 build.py 接口说明

> 从 `subskills/outstanding-thesis/SKILL.md` 外移而来（渐进式披露）。
> 何时阅读：需要调用 build.py 或了解接口参数时。

### 15.1 调用方式

```bash
# 方式 1：使用 JSON 数据文件
python build.py --data data.json --out output.docx

# 方式 2：使用内置示例数据（演示用）
python build.py --demo --out /tmp/test_outstanding_thesis.docx

# 方式 3：覆盖字数版本与申报规格
python build.py --demo --word-count-version brief --out demo_brief.docx
python build.py --demo --apply-level college --out demo_college.docx

# 方式 4：查看帮助
python build.py --help
```

### 15.2 命令行参数

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| --data | str | None | 数据 JSON 文件路径（与 --demo 二选一） |
| --out | str | 必填 | 输出 docx 文件路径 |
| --demo | flag | False | 使用内置示例数据生成演示文档 |
| --word-count-version | choice | None | 覆盖字数版本（brief 短档 / standard 中档 / enhanced 长档） |
| --apply-level | choice | None | 覆盖申报规格（school 校级 / college 院级） |

### 15.3 生成流程

1. 解析 JSON（或加载 DEFAULT_DATA）
2. 字段路由解析（material_form / apply_level / word_count_version / thesis_type / graduate_type）
3. 数据校验（输出 warnings，含硬门槛 4 项校验）
4. 构建 docx（标题 → 称呼 → 开头 → 课题选择 → 研究方法 → 创新点 → 成果应用 → 结尾 → 落款 → 摘要）
5. 保存到指定路径

### 15.4 输出文件规范

- A4 纸张，上下 2.54cm 左右 2.5cm 页边距
- 黑体二号标题居中（按 thesis_type 动态生成）
- 宋体小四正文，1.5 倍行距，首行缩进 2 字符
- 中英文同步设置（eastAsia / ascii / hAnsi）
- 研究阶段表 4 列（阶段/时间/工作内容/产出）
- 创新点表 3 列（类别/创新点描述/支撑材料）
- 应用价值表 3 列（场景/价值描述/采纳证明）
- "此致"另起一行空两格，"敬礼！"另起一行顶格
- 落款右对齐（申请人 + 指导教师 + 日期，3 行）
- 页脚居中页码

### 15.5 输出文件命名建议

- 校级：`校级优秀毕业设计申报书_张明_2025.docx`
- 院级：`院级优秀毕业设计申报书_张明_2025.docx`
- 论文类：`校级优秀毕业论文申报书_张明_2025.docx`
- 硕士/博士：`优秀学位论文申报书_张明_2025.docx`

文件名包含规格、姓名、毕业年份，便于学院归档。

### 15.6 缺失字段处理

- P0 必采字段缺失：触发 warning，仍生成 docx，但对应段落用占位符 `___` 标注
- P1 重要字段缺失：触发 warning，对应段落省略或简化
- P2 可选字段缺失：不触发 warning，直接省略

### 15.7 字段与 build.py 对应关系

**通用字段（10）**：name, student_id, gender, college, major, grade, class_name, phone, apply_level, apply_year, apply_date

**毕设字段（10）**：thesis_title, thesis_type, advisor, advisor_title, defense_score, defense_rank, plagiarism_rate, defense_date, research_duration, graduate_type

**课题字段（4）**：project_source, research_problem, research_significance, research_goals

**研究方法字段（6）**：research_method, technical_route, key_technologies, data_material, research_stages, experiments

**创新点字段（1）**：innovation_points（列表，每项含 type/name/description/comparison/support_material）

**成果应用字段（4）**：achievements, application_scenarios, adoption_proofs, future_research

**摘要与控制字段（5）**：abstract, abstract_position, salutation, opening, ending

---


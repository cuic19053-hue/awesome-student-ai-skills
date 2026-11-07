# §10 build.py 接口说明

> 从 `subskills/grant-application/SKILL.md` 外移而来（渐进式披露）。
> 何时阅读：需要调用 build.py 或了解接口参数时。

### §10.1 build.py 基本信息

- 路径：`/home/z/my-project/skills/awesome-student-ai-skills/subskills/grant_application/build.py`
- 字体常量：宋体（FONT_SONG）/ 黑体（FONT_HEI）/ Times New Roman（FONT_TIMES）
- 页面：A4 纸张，页边距上下 2.54cm 左右 2.5cm
- 段落：首行缩进 2 字符，1.5 倍行距
- 标题：黑体二号居中

### §10.2 命令行接口

```bash
# Demo 模式（生成示例 docx）
python3 build.py --demo --out output.docx

# 数据模式（用 data.json 生成 docx）
python3 build.py --data data.json --out output.docx
```

| 参数 | 说明 |
|---|---|
| `--data` | JSON 数据文件路径（不填则用 demo 数据） |
| `--out` | 输出 docx 路径（必填） |
| `--demo` | 使用内置示例数据（与 --data 互斥） |

### §10.3 build.py 当前支持的字段（与 §9 Schema 对照）

build.py 采用 `_get(key, default)` 方式按需读取字段，**未严格校验 Schema**。当前 build.py 实际读取的字段如下：

| build.py 读取字段 | Schema 对应字段 | 说明 |
|---|---|---|
| `name` / `college` / `major` / `grade` / `apply_year` | 同名 | 基础信息 |
| `grant_level` / `grant_amount` | 同名 | 助学金档次与金额（金额自动推算） |
| `difficulty_level` / `difficulty_cert_no` / `poverty_category` | 同名 | 困难等级 / 编号 / 6 类类别 |
| `family_situation` 子结构 | 同名 | 家庭经济 6 大要素 |
| `family_members`（list，含 name/relation/job/income/political） | 同名 | 家庭成员表（5 列） |
| `work_study`（list，含 position/place/duration/monthly_income） | 同名 | 勤工助学表（4 列） |
| `study_situation` / `gpa` / `rank` / `course_failed` | 同名 | 在校表现（学习部分） |
| `ideology` / `party_history` / `position` / `position_work` | 同名 | 在校表现（思想与干部） |
| `volunteer_hours` / `volunteer_detail` / `lifestyle` | 同名 | 在校表现（志愿与生活） |
| `tuition` / `textbook_fee` / `monthly_food` / `loan_amount` / `monthly_income` | 同名 | 申请理由与用途 |
| `salutation` / `opening` / `ending` / `apply_date` | 同名 | 输出控制 |
| `material_type` / `word_count_version` | 同名 | 材料类型与字数版本 |

### §10.4 build.py 函数清单

| 函数名 | 作用 |
|---|---|
| `set_run_font` | 设置 run 字体（中英文字体同步） |
| `set_cell_text` | 设置表格单元格文本 |
| `add_paragraph_with_format` | 添加带格式段落（缩进/对齐/字体） |
| `add_title` | 添加黑体二号居中标题 |
| `add_body_paragraph` | 添加宋体小四正文段落（首行缩进 2 字符） |
| `add_salutation_paragraph` | 添加顶格称呼段落 |
| `add_section_heading` | 添加段内小节标题（如"二、家庭经济情况"） |
| `add_cizhi_paragraph` | 添加"此致"段落 |
| `add_jingli_paragraph` | 添加"敬礼！"段落 |
| `add_right_aligned_paragraph` | 添加右对齐段落（落款用） |
| `add_table_from_data` | 从数据生成表格（headers + rows） |
| `setup_page` | 设置 A4 页面与页边距 |
| `add_page_number` | 添加页码 |
| `compute_grant_amount` | 根据 grant_level 推算 grant_amount |
| `compute_per_capita` | 根据 family_income_year 与 family_size 推算人均收入 |
| `main` | 命令行入口 |

### §10.5 build.py 字数版本路由

build.py 根据 `word_count_version` 字段决定段落字数与表格插入策略：

| word_count_version | 段一 | 段二 | 段三 | 段四 | 段五 | 表格 |
|---|---|---|---|---|---|---|
| `"800"` | 100 字 | 350 字 | 200 字 | 100 字 | 50 字 | 仅家庭成员表（4 列简化） |
| `"1200"`（默认） | 180 字 | 480 字 | 300 字 | 150 字 | 90 字 | 家庭成员表（5 列）+ 勤工助学表（4 列） |
| `"1500"` | 220 字 | 600 字 | 380 字 | 180 字 | 120 字 | 家庭成员表（5 列）+ 勤工助学表（4 列）+ 主干课程表（3 列） |

### §10.6 build.py material_type 路由

build.py 根据 `material_type` 字段决定输出形式：

| material_type | 输出 |
|---|---|
| `"A"` | 仅打印 A 类申请理由栏 150~200 字纯文本到控制台，提示用户复制到学校模板 |
| `"B"` | 生成 B 类书信体 docx |
| `"A+B"` | 生成 B 类 docx + 控制台额外打印 A 类 200 字文本 |
| 未填 / 默认 | 生成 B 类书信体 docx（1200 字版本） |

### §10.7 build.py 数据校验

build.py 在 `_validate_data()` 方法中校验以下内容（不阻断生成，仅打印警告）：

1. P0 必采字段（name/college/major/grade/student_id/apply_year）缺失 → 警告
2. `grant_level` 不在 ["一等","二等","三等"] 内 → 警告
3. `difficulty_level` 不在 ["特别困难","困难","一般困难"] 内 → 警告
4. `grant_level` 与 `difficulty_level` 不对应（如一等 ≠ 特别困难） → 警告
5. `grant_amount` 与 `grant_level` 不对应（如一等 ≠ 4400） → 警告
6. `poverty_category` 不在 6 类内 → 警告
7. `family_situation.family_income_year` 缺失或过高（> 6 万） → 警告
8. `family_situation.local_min_living` 缺失 → 警告
9. `family_situation.large_expenses` 缺失 → 警告
10. 家庭成员表 < 3 人 → 警告
11. 勤工助学经历缺失 → 警告

---


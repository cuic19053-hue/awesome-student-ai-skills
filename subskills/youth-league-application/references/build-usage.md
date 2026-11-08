# §16 build.py 接口说明

> 从 `subskills/youth-league-application/SKILL.md` 外移而来（渐进式披露）。
> 何时阅读：需要调用 build.py 或了解接口参数时。

### 16.1 命令行调用

```bash
# 使用外部数据文件
python build.py --data data.json --out output.docx

# 使用内置示例数据
python build.py --demo --out demo.docx
```

### 16.2 build.py 方法清单

| 方法 | 功能 |
|------|------|
| `setup_page(doc)` | 设置 A4 页面与页边距（上下 2.54cm，左右 2.5cm） |
| `add_title(doc, text)` | 黑体二号居中标题 |
| `add_body_paragraph(doc, text)` | 宋体小四正文段落（1.5 倍行距，首行缩进 2 字符） |
| `add_salutation_paragraph(doc, text)` | 顶格称呼 |
| `add_cizhi_paragraph(doc, text)` | "此致"另起一行空两格 |
| `add_jingli_paragraph(doc, text)` | "敬礼！"另起一行顶格 |
| `add_right_aligned_paragraph(doc, text)` | 右对齐落款 |
| `add_page_number(doc)` | 页脚居中页码 |
| `add_page_break(doc)` | 分页符 |
| `add_table_with_style(doc, headers, rows)` | 家庭成员表格 |
| `count_chinese_chars(text)` | 统计中文字符数 |
| `normalize_date(s)` | 日期格式规范化 |
| `compute_age(birth_date, submit_date)` | 计算周岁 |
| `check_political_terms(text)` | 政治用语规范校验 |
| `check_4_theory_expressions(text)` | 4 项必引理论校验 |
| `check_plagiarism_risk(text, fragments, threshold)` | 查重风险检测 |
| `ApplicationDocBuilder.build(data, output_path)` | 主构建方法 |

### 16.3 字段消费规则

见 §15.2 字段消费规则表。

### 16.4 输出格式规范

- A4 纸张，页边距上下 2.54cm 左右 2.5cm
- 标题：黑体二号居中（"入团申请书"5 字）
- 称呼：宋体小四顶格，全角冒号
- 正文：宋体小四 1.5 倍行距首行缩进 2 字符
- "此致"另起一行空两格，"敬礼！"另起一行顶格
- 落款：右对齐两行（申请人 + 日期，日期汉字格式）
- 页脚：居中页码，宋体五号
- 附页：分页符之后，标题"家庭主要成员和主要社会关系"黑体三号居中，表格宋体小四

### 16.5 build.py 校验逻辑

build.py 的 `_validate_data` 方法须包含以下校验：

1. **年龄校验**：根据 birth_date 与 submit_date 计算是否年满 14 周岁且不满 28 周岁，未满或超龄则输出严重警告
2. **字数校验**：根据 school_tier 确定下限，统计正文字数，低于下限输出警告
3. **"志愿书"三字校验**：全文检索"志愿书"三字，输出警告（注：单独"志愿"二字合规）
4. **4 项必引理论表述校验**：见 §6.5 自检脚本
5. **日期格式校验**：submit_date 必须为汉字格式（见 §8.4）
6. **政治面貌校验**：political_status 必须为群众 / 少先队员 / 共青团员（已是团员则不需申请；中共党员提示无需再申请）
7. **家庭成员校验**：family_members 至少包含父亲、母亲
8. **入团动机校验**：motivation 字数不少于 200 字
9. **个人不足校验**：shortcomings 至少 2 项，每项 description + manifestation + improvement 齐全
10. **查重风险校验**：检测与团章原文连续 50 字雷同

### 16.6 build.py 调用示例

```python
from build import ApplicationDocBuilder, DEFAULT_DATA

# 使用默认数据
builder = ApplicationDocBuilder()
builder.build(DEFAULT_DATA, "demo.docx")

# 使用自定义数据
import json
with open("data.json", "r", encoding="utf-8") as f:
    data = json.load(f)
builder = ApplicationDocBuilder()
builder.build(data, "output.docx")
```

---


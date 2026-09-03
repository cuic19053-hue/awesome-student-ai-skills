# docx_common — awesome-student-ai-skills 共享组件库

> T39 工程化任务产出。为 22+ 个子 skill 的 `build.py` 提供统一 docx 生成基础能力，消除字体常量、页面设置、段落生成、表格生成、签字栏、页眉页脚等跨子 skill 重复代码。

- **版本**：1.0.0
- **依赖**：python-docx >= 0.8（实测 1.2.0）
- **行数**：~897 行（含注释与空行）
- **入口**：`utils.docx_common`
- **作者**：T39 工程化任务

---

## 1. 背景与动机

`skills/awesome-student-ai-skills/subskills/` 下共有 22+ 个子 skill，每个子 skill 都有自己的 `build.py`。抽样 `national_project_eval/build.py` 与 `motivation_scholarship/build.py` 后发现：

| 重复内容 | 重复次数 | 重复规模 |
|---|---|---|
| 字体常量（FONT_SONG / FONT_HEI …） | 22+ | ~10 行/文件 |
| 字号常量（SIZE_ER / SIZE_XIAO_SI …） | 22+ | ~8 行/文件 |
| 页面常量（PAGE_WIDTH_CM / MARGIN_*_CM） | 22+ | ~4 行/文件 |
| `set_run_font` | 22+ | ~15 行/文件 |
| `set_cell_text` | 22+ | ~10 行/文件 |
| `add_paragraph_with_format` | 22+ | ~15 行/文件 |
| `add_title` / `add_body_paragraph` / `add_section_heading` | 22+ | ~30 行/文件 |
| `add_cizhi_paragraph` / `add_jingli_paragraph` | 18+ | ~10 行/文件 |
| `add_table_from_data` | 15+ | ~30 行/文件 |

**保守估算**：每个 build.py 中有 100~150 行纯属重复样板，22 个文件 = **2200~3300 行重复代码**。

本模块将上述重复抽到统一库中，新增子 skill 只需 `from utils.docx_common import …` 即可，无需再写一遍。

---

## 2. 设计原则

1. **零业务耦合**：本模块只提供 docx 基础构件，不包含任何具体材料类型（奖学金/评优/三下乡/挑战杯…）的业务逻辑。
2. **覆盖现有重复模式**：12 套字体常量、5 个工具函数、15 个段落/表格/页眉构件、1 个 DocxBuilder 基类，覆盖现有 build.py 中 95% 的重复样板。
3. **不破坏向后兼容**：现有 build.py 不强制改造，本模块可被新增子 skill 直接 import 使用。
4. **可独立测试**：`example_usage.py` 跑通即视为通过。

---

## 3. 模块结构

```
utils/docx_common.py
├── 1. 字体常量       FONT_SONG / FONT_HEI / FONT_FANGSONG / FONT_KAI / FONT_TIMES
├── 2. 字号常量       SIZE_ER / SIZE_XIAO_ER / SIZE_SAN / SIZE_XIAO_SAN /
│                    SIZE_SI / SIZE_XIAO_SI / SIZE_WU / SIZE_XIAO_WU
├── 3. 页面/颜色常量  PAGE_*_CM / MARGIN_*_CM / COLOR_RED / COLOR_BLACK / COLOR_DARK_GRAY
├── 4. 工具函数       set_run_font / apply_red_text / apply_bold_text /
│                    set_cell_font / set_cell_text / add_paragraph_with_format
├── 5. 页面/标题层级  setup_a4_page / add_title / add_heading1 /
│                    add_heading2 / add_heading3 / add_paragraph / add_salutation
├── 6. 表格           add_table
├── 7. 书信体构件     add_this_salute / add_signature_block /
│                    add_date_line / add_seal_placeholder
├── 8. 页眉页脚       add_header / add_footer / add_page_number
├── 9. 字数统计/校验/保存  count_chinese_chars / count_words /
│                        validate_docx / save_docx
├── 10. DocxBuilder 基类  通用构建器，所有子 skill 可继承
├── 11. 便捷工厂       create_docx
└── 12. 模块自检       python3 docx_common.py 直接跑
```

---

## 4. API 速查

### 4.1 字体字号常量

```python
from utils.docx_common import (
    FONT_SONG, FONT_HEI, FONT_FANGSONG, FONT_KAI, FONT_TIMES,
    SIZE_ER, SIZE_XIAO_ER, SIZE_SAN, SIZE_XIAO_SAN,
    SIZE_SI, SIZE_XIAO_SI, SIZE_WU, SIZE_XIAO_WU,
)
```

| 常量 | 值 | 说明 |
|---|---|---|
| `FONT_SONG` | `"宋体"` | 正文中文 |
| `FONT_HEI` | `"黑体"` | 标题中文 |
| `FONT_FANGSONG` | `"仿宋"` | 公文正文 |
| `FONT_KAI` | `"楷体"` | 引用/署名 |
| `FONT_TIMES` | `"Times New Roman"` | 西文 |
| `SIZE_ER` | `Pt(22)` | 二号（主标题） |
| `SIZE_XIAO_ER` | `Pt(18)` | 小二 |
| `SIZE_SAN` | `Pt(16)` | 三号（A 类审批表标题） |
| `SIZE_XIAO_SAN` | `Pt(15)` | 小三（二级标题） |
| `SIZE_SI` | `Pt(14)` | 四号 |
| `SIZE_XIAO_SI` | `Pt(12)` | 小四（正文） |
| `SIZE_WU` | `Pt(10.5)` | 五号（表格） |
| `SIZE_XIAO_WU` | `Pt(9)` | 小五（页眉页脚） |

### 4.2 工具函数

| 函数 | 用途 | 关键参数 |
|---|---|---|
| `setup_a4_page(doc, margins=None)` | 设置 A4 页面与页边距 | margins: dict {top,bottom,left,right} cm |
| `set_run_font(run, font_name, font_size, bold, color, italic)` | 设置 Run 字体（中英文同步） | — |
| `apply_red_text(run)` | 红色文本 | — |
| `apply_bold_text(run)` | 加粗 | — |
| `add_paragraph_with_format(...)` | 通用段落生成（最底层） | 12 个参数 |
| `add_title(doc, text, size, align, font_name, bold, ...)` | 主标题 | 默认黑体二号居中 |
| `add_heading1(doc, text, align)` | 一级标题 | 黑体三号居中 |
| `add_heading2(doc, text, align)` | 二级标题 | 黑体小三左对齐 |
| `add_heading3(doc, text, align)` | 三级标题 | 黑体四号左对齐 |
| `add_paragraph(doc, text, indent, bold, ...)` | 正文段落 | 首行缩进 2 字符 |
| `add_salutation(doc, text)` | 称呼 | 顶格不缩进 |
| `add_table(doc, headers, rows, col_widths, caption, ...)` | 表格 | 表头加粗居中、数据居中 |
| `add_this_salute(doc, cizhi, jingli)` | 此致 / 敬礼！ | — |
| `add_signature_block(doc, signatures, align)` | 落款 | 默认右对齐 |
| `add_date_line(doc, custom_date, align)` | 落款日期 | None 自动取今天 |
| `add_seal_placeholder(doc, position, text, size_cm)` | 印章占位 | 默认右下角 |
| `add_header(doc, text)` | 页眉 | 居中小五深灰 |
| `add_footer(doc, text)` | 页脚 | 居中小五深灰 |
| `add_page_number(doc, fmt)` | 页码 | `{PAGE}` / `{NUMPAGES}` 占位 |
| `count_chinese_chars(text)` | 中文字符数 | — |
| `count_words(text)` | 中英文混合字数 | — |
| `validate_docx(doc)` | 校验 | 返回 (is_valid, issues) |
| `save_docx(doc, output_path)` | 保存 | 返回绝对路径 |

### 4.3 DocxBuilder 基类

```python
class DocxBuilder:
    def __init__(self, output_path, margins=None, with_page_number=False,
                 page_number_fmt="第 {PAGE} 页 共 {NUMPAGES} 页",
                 header=None, footer=None): ...

    # 标题
    def add_title(self, text, **kwargs): ...
    def add_heading1(self, text, **kwargs): ...
    def add_heading2(self, text, **kwargs): ...
    def add_heading3(self, text, **kwargs): ...

    # 段落
    def add_paragraph(self, text, indent=True, **kwargs): ...
    def add_salutation(self, text="尊敬的校领导："): ...
    def add_this_salute(self, cizhi="此致", jingli="敬礼！"): ...

    # 落款
    def add_signature_block(self, signatures, **kwargs): ...
    def add_date_line(self, custom_date=None, **kwargs): ...
    def add_seal_placeholder(self, position="right_bottom", **kwargs): ...

    # 表格
    def add_table(self, headers, rows, **kwargs): ...

    # 页眉页脚
    def add_header(self, text): ...
    def add_footer(self, text): ...
    def add_page_number(self, fmt=...): ...

    # 校验 / 保存
    def validate(self): ...   # -> (is_valid, issues)
    def save(self): ...       # -> 绝对路径
```

---

## 5. 快速上手

### 5.1 用 DocxBuilder 基类（推荐）

```python
from utils.docx_common import DocxBuilder

builder = DocxBuilder("/tmp/demo.docx")
builder.add_title("国家奖学金申请书")
builder.add_salutation("尊敬的校奖学金评审委员会：")
builder.add_paragraph("本人 XX，系 XX 学院 XX 专业 XX 班学生…")
builder.add_heading2("一、思想方面")
builder.add_paragraph("本人坚持…")
builder.add_this_salute()
builder.add_signature_block(["申请人：张三", "2025 年 5 月 10 日"])
builder.save()
```

### 5.2 继承 DocxBuilder 写子类

```python
from utils.docx_common import DocxBuilder, add_table

class NationalScholarshipBuilder(DocxBuilder):
    def build(self, data: dict):
        self.add_title(data["title"])
        self.add_salutation(data["salutation"])
        for para in data["body"]:
            self.add_paragraph(para)
        # 主干课程表
        self.add_table(
            headers=["课程名称", "学分", "成绩"],
            rows=data["courses"],
            caption="主干课程成绩：",
        )
        self.add_this_salute()
        self.add_signature_block([data["applicant"], data["date"]])
        return self.save()
```

### 5.3 用函数式 API（不用类）

```python
from utils.docx_common import (
    create_docx, add_title, add_paragraph, add_table,
    add_this_salute, add_signature_block, save_docx,
)

doc = create_docx("/tmp/demo.docx")
add_title(doc, "测试文档")
add_paragraph(doc, "正文段落。")
add_table(doc, headers=["A", "B"], rows=[["1", "2"]])
save_docx(doc, "/tmp/demo.docx")
```

---

## 6. 现有 build.py 迁移指南

新增子 skill 直接用本模块即可。现有 22+ 个 build.py 的迁移按"渐进式"原则：

### 6.1 不迁移（推荐）

现有 build.py 不强制改造。它们已经稳定运行，强行替换会带来回归风险。**仅新增子 skill 强制使用本模块**。

### 6.2 局部迁移（可选）

如果某个 build.py 需要新增功能（如页码、页眉），但本身已有大量代码，可以只 import 本模块的新增能力：

```python
from utils.docx_common import add_page_number, add_header

# 保留原有代码不变
# ...

# 在文档末尾追加页眉
add_header(doc, "XX 大学国家奖学金申请材料")
```

### 6.3 全量迁移（不推荐，除非重写）

仅在子 skill 大改时考虑。步骤：

1. 删除 build.py 顶部的字体常量、字号常量、页面常量、`set_run_font`、`set_cell_text`、`add_paragraph_with_format`、`add_title`、`add_body_paragraph`、`add_section_heading`、`add_cizhi_paragraph`、`add_jingli_paragraph`、`add_table_from_data` 等函数定义。
2. 顶部改为 `from utils.docx_common import *`（或显式 import 所需符号）。
3. 检查函数名差异：
   - `add_body_paragraph` → `add_paragraph`
   - `add_section_heading` → `add_heading2` 或 `add_heading3`（看原代码字号）
   - `add_cizhi_paragraph` + `add_jingli_paragraph` → `add_this_salute`
   - `add_table_from_data` → `add_table`
   - `add_right_aligned_paragraph` → `add_paragraph_with_format(..., alignment=RIGHT)`
4. 跑 `--demo` 与 `--data` 双路径验证，确认输出与原版一致。

---

## 7. 测试

### 7.1 模块自检

```bash
python3 utils/docx_common.py
# 输出：
# [self_test] saved: /tmp/_docx_common_self_test.docx
# [self_test] valid: True, issues: []
```

### 7.2 示例跑通

```bash
python3 utils/example_usage.py
# 输出：
# ✅ 示例文档已生成：/tmp/docx_common_demo.docx
# ✅ 文档校验：通过
# ✅ 字数统计：中文 23 字，混合字数 28
```

### 7.3 语法验证

```bash
python3 -c "import ast; ast.parse(open('utils/docx_common.py').read()); print('SYNTAX OK')"
```

---

## 8. 常见问题

### Q1：为什么 `set_run_font` 要同时设置 eastAsia/ascii/hAnsi？

python-docx 的 `run.font.name` 只设置 `w:ascii` 和 `w:hAnsi`，中文字符需要 `w:eastAsia` 才能生效。如果只设置 `font.name`，中英文混排时中文字符可能显示为默认字体。

### Q2：`add_page_number` 为什么用域代码（field code）？

Word 的页码是动态域，必须用 `w:fldChar` + `w:instrText` 才能在打开时自动更新。直接写死文字会失效。

### Q3：`DocxBuilder.__getattr__` 为什么 raise AttributeError？

为了不掩盖子类未定义属性的访问错误。如果子类访问 `self.xxx`，且 xxx 不存在，Python 会先走 `__getattr__`，本方法显式 raise，确保错误信息清晰。

### Q4：可以与 `pdf_export` 模块一起用吗？

可以。先生成 docx，再用 `utils.pdf_export.docx_to_pdf` 转 PDF：

```python
from utils.docx_common import DocxBuilder
from utils.pdf_export import docx_to_pdf

b = DocxBuilder("/tmp/test.docx")
b.add_title("测试")
b.save()
docx_to_pdf("/tmp/test.docx")  # 生成 /tmp/test.docx.pdf
```

### Q5：现有 build.py 中有 `add_section_heading`、`add_body_paragraph`、`add_cizhi_paragraph` 等本模块没有的函数怎么办？

本模块提供了等价 API：

| 旧函数名 | 新函数名 |
|---|---|
| `add_body_paragraph` | `add_paragraph` |
| `add_section_heading` | `add_heading2`（或 `add_heading3`，看字号） |
| `add_cizhi_paragraph` + `add_jingli_paragraph` | `add_this_salute` |
| `add_table_from_data` | `add_table` |
| `add_right_aligned_paragraph` | `add_paragraph_with_format(..., alignment=WD_ALIGN_PARAGRAPH.RIGHT)` |
| `add_salutation_paragraph` | `add_salutation` |

迁移时按上表替换即可。

---

## 9. 后续规划

1. **T40**：基于本模块的 `DocxBuilder`，进一步抽取 `PoliticalDocBuilder`（团员材料 / 汇报材料 共同基类，含政治红线、必引理论、查重检测）
2. **T41**：抽取 `ScholarshipDocBuilder`（国奖 / 励志 / 校奖 / 单项 / 企业 共同基类，含成绩表、奖项表、家庭情况表）
3. **T42**：抽取 `ResearchProjectBuilder`（科研立项 / 大创 / 挑战杯 / 互联网+ 共同基类，含研究背景、技术路线、预期成果）
4. **T43**：抽取 `SocialPracticeBuilder`（三下乡 / 志愿服务 / 西部计划 共同基类，含团队信息、服务内容、安全预案）
5. 渐进迁移现有 22+ build.py，优先迁移最近改动频繁的 5 个

---

## 10. 版本历史

| 版本 | 日期 | 说明 |
|---|---|---|
| 1.0.0 | 2025-01 | T39 工程化任务初版，提供字体/字号常量、20 个工具函数、DocxBuilder 基类 |

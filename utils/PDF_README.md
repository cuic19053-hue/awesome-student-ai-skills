# PDF 输出共享模块使用说明

> 模块路径：`utils/pdf_export.py`
> 适用范围：awesome-student-ai-skills 全部 22+ 子 skill
> 版本：1.0.0（T36 引入）

## 1. 设计目标

高校电子申报系统普遍要求 PDF 提交（部分学校明确不接受 docx）。本模块为
所有子 skill 提供统一的 PDF 输出能力，避免每个子 skill 各自实现转换逻辑。

## 2. 环境要求

| 组件 | 必要性 | 安装命令 |
|---|---|---|
| LibreOffice | **强推荐** | Ubuntu: `sudo apt install libreoffice`<br>CentOS: `sudo yum install libreoffice`<br>macOS: `brew install --cask libreoffice` |
| pypdf | 必装（页码/水印/元数据/合并/校验） | `pip install pypdf` |
| reportlab | 必装（页码/水印/兜底转换） | `pip install reportlab` |
| python-docx | 必装（兜底转换） | `pip install python-docx` |
| docx2pdf | 可选（Windows 端调用 MS Word） | `pip install docx2pdf` |

环境自检：

```bash
python3 utils/pdf_export.py --selftest
```

## 3. 转换引擎优先级

`engine="auto"` 时按以下顺序尝试，第一个成功即返回：

1. **LibreOffice headless**（首选）
   - 转换质量最高，能完整保留 docx 格式（中文字体、表格、页眉页脚、
     首行缩进、段落对齐、行距等）
   - Linux 服务器默认可用
2. **docx2pdf**（次选）
   - Windows 上调用 MS Word COM 接口，质量等同 Word 另存为 PDF
   - Linux 上内部仍调用 LibreOffice，不推荐
3. **reportlab + python-docx**（兜底）
   - 解析 docx 文本并用 reportlab 重建 PDF
   - **仅处理段落与表格，不处理页眉页脚/复杂样式**
   - 中文字体可能丢失（取决于系统是否安装 Noto CJK / 文泉驿）
   - 仅在前两种引擎均不可用时使用

## 4. API 速查

### 4.1 docx → PDF

```python
from utils.pdf_export import docx_to_pdf

# 自动同名 .pdf（与 docx 同目录）
pdf_path = docx_to_pdf("/tmp/申请.docx")
# → /tmp/申请.pdf

# 指定输出路径
pdf_path = docx_to_pdf("/tmp/申请.docx", "/tmp/output/申请.pdf")

# 强制使用指定引擎
pdf_path = docx_to_pdf("/tmp/申请.docx", engine="libreoffice")
```

### 4.2 合并多个 PDF（A+B 两套材料场景）

```python
from utils.pdf_export import merge_pdfs

# 国家奖学金：A 类审批表 + B 类申请书合并
merge_pdfs(
    ["/tmp/项目_A.pdf", "/tmp/项目_B.pdf"],
    "/tmp/项目_合并提交.pdf",
)
```

### 4.3 添加页码

```python
from utils.pdf_export import add_page_number

# 默认底部居中，格式 "1/10"
add_page_number("/tmp/申请.pdf")

# 自定义位置与格式
add_page_number(
    "/tmp/申请.pdf",
    position="bottom-right",
    format="第 {page} 页 / 共 {total} 页",
)
```

位置可选：`bottom-center`（默认）/ `bottom-right` / `bottom-left` /
`top-center` / `top-right` / `top-left`

### 4.4 添加水印

```python
from utils.pdf_export import add_watermark

# 默认斜向 45°，灰色 15% 透明度
add_watermark("/tmp/申请.pdf", "仅供提交")

# 自定义透明度/字号/颜色
add_watermark(
    "/tmp/申请.pdf",
    "草稿 DRAFT",
    opacity=0.3,
    font_size=80,
    color=(0.8, 0.2, 0.2),  # 红色
)
```

### 4.5 设置元数据

```python
from utils.pdf_export import set_pdf_metadata

set_pdf_metadata(
    "/tmp/申请.pdf",
    title="国家奖学金申请书",
    author="张三",
    subject="2024001 / 计算机学院",
    keywords="国家奖学金,2025",
    creator="awesome-student-ai-skills skill",
)
```

### 4.6 校验完整性

```python
from utils.pdf_export import validate_pdf

if validate_pdf("/tmp/申请.pdf"):
    print("PDF 完整可用")
```

校验项：文件头 `%PDF-`、EOF 标记 `%%EOF`、pypdf 可解析、页数 > 0。

## 5. CLI 用法

### 5.1 docx → PDF（最常用）

```bash
# 自动同名 .pdf
python3 utils/pdf_export.py --input xxx.docx

# 指定输出
python3 utils/pdf_export.py -i xxx.docx -o xxx.pdf

# 指定引擎
python3 utils/pdf_export.py -i xxx.docx --engine libreoffice
```

### 5.2 合并 PDF

```bash
python3 utils/pdf_export.py --merge A.pdf B.pdf -o 合并.pdf
```

### 5.3 一次性完成转换 + 页码 + 水印 + 元数据

```bash
python3 utils/pdf_export.py \
    -i 项目.docx \
    -o 项目.pdf \
    --page-number \
    --watermark "仅供提交" \
    --metadata title="国家奖学金申请书" author="张三" \
    --validate
```

### 5.4 校验已有 PDF

```bash
python3 utils/pdf_export.py -i xxx.pdf --validate
```

### 5.5 环境自检

```bash
python3 utils/pdf_export.py --selftest
```

## 6. 子 skill 集成指南

### 6.1 build.py 末尾追加 PDF 输出

```python
# 在 build.py 的 main() 末尾追加：
def main():
    ...
    # 原有 docx 生成逻辑
    docx_path = build_docx(data, out_path)
    print(f"✅ docx 已生成：{docx_path}")

    # 新增：自动转 PDF（用户传 --pdf 参数时）
    if args.pdf:
        from utils.pdf_export import docx_to_pdf
        # 假设 utils 在父目录
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from utils.pdf_export import docx_to_pdf, add_page_number
        pdf_path = docx_to_pdf(docx_path)
        add_page_number(pdf_path)
        print(f"✅ PDF 已生成：{pdf_path}")
```

### 6.2 在子 skill 中添加 --pdf 参数

```python
parser.add_argument("--pdf", action="store_true",
                    help="同时输出 PDF（需 LibreOffice）")
```

### 6.3 A+B 两套材料合并示例

```python
# 国家奖学金 A+B 类
docx_a = build_docx(data_a, "项目_A.docx")
docx_b = build_docx(data_b, "项目_B.docx")

if args.pdf:
    pdf_a = docx_to_pdf(docx_a)
    pdf_b = docx_to_pdf(docx_b)
    merge_pdfs([pdf_a, pdf_b], "项目_提交.pdf")
    add_page_number("项目_提交.pdf")
    print("✅ 合并 PDF 已生成：项目_提交.pdf")
```

## 7. 常见问题

### Q1：转换后中文字体变成方块？

**A**：LibreOffice 未找到对应字体。安装中文字体：
```bash
sudo apt install fonts-wqy-zenhei fonts-wqy-microhei fonts-noto-cjk
```

### Q2：LibreOffice 转换很慢？

**A**：首次启动需初始化 user profile。后续转换会复用，正常应在 5~15 秒内完成。
若超过 60 秒，检查系统内存是否足够（建议 ≥ 2GB）。

### Q3：并发转换冲突？

**A**：本模块已为每次转换使用独立的 `UserInstallation` profile 目录
（`-env:UserInstallation=file://...`），可安全并发。

### Q4：报错 "LibreOffice 未安装"？

**A**：按 §2 安装。若已安装但 `which libreoffice` 找不到，手动指定路径：
```bash
which libreoffice soffice
# 将路径加入 PATH，或修改 pdf_export.py 顶部 _candidate 列表
```

### Q5：兜底引擎（reportlab）转换后格式错乱？

**A**：兜底引擎仅处理简单 docx。**强烈建议安装 LibreOffice**。
若环境限制无法安装，请在生成 docx 时尽量使用基础段落 + 简单表格，
避免使用页眉页脚/分栏/嵌套表格等复杂特性。

## 8. 已集成的子 skill

T36 完成后，以下子 skill 可直接 `import` 使用（待后续 task 逐个接入
`--pdf` 参数）：

- scholarship 类：national / motivation / university / enterprise / single
- competition 类：challenge_cup / internet_plus
- research 类：innovation_research / college_research / university_research
- entrepreneurship 类：entrepreneurship_training / entrepreneurship_practice
- party 类：youth_league_application / youth_league_application / summary_report
- honor 类：outstanding_student / outstanding_graduate / outstanding_cadre /
  civilized_student
- others：grant_application / graduate_recommendation / selected_graduate /
  social_survey / class_collective / major_transfer / policy_lecture /
  tech_service / volunteer_teaching / western_plan / youth_league_application

## 9. 退出码

| 退出码 | 含义 |
|---|---|
| 0 | 成功 |
| 1 | 输入文件不存在 |
| 2 | 转换失败（所有引擎均不可用） |
| 3 | PDF 完整性校验失败 |
| 4 | 参数错误 |

## 10. 变更历史

- v1.0.0 (T36)：首次引入，提供 docx_to_pdf / merge_pdfs / add_page_number /
  add_watermark / set_pdf_metadata / validate_pdf 六大能力 + CLI 接口

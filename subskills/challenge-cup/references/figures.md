# 二十七、配图规范（v2.2 新增）

> 从 `subskills/challenge-cup/SKILL.md` 外移而来（渐进式披露）。
> 何时阅读：需要生成或插入技术路线图、对比表、统计图时。

> **v2.2 背景**：v2.1 的"技术路线图"以节点表格 + 关联关系表格呈现，本质是伪图；正文却存在"详见图 3、表 4"式引用，形成悬空引用。科技发明制作类与自然科学类评审对图的预期高（技术路线图、数据对比图、实物照片），本节规定全部数据类配图必须以**代码渲染的真图**交付。

### 27.1 硬性原则：数据图一律代码渲染，禁止 AI 文生图

| 图类型 | 生成方式 | 原因 |
|--------|----------|------|
| 技术路线图 / 流程图 | matplotlib / graphviz 代码渲染 | 节点文字必须与正文章节严格对应，文生图中文必乱码 |
| 甘特图 / 进度图 | matplotlib 代码渲染 | 时间轴必须与 duration、研究方法章节一致 |
| 数据对比图 / 占比图 | matplotlib 代码渲染 | 数值必须来自 data.json，文生图会编造数字 |
| 示意渲染图 / 封面插画 | AI 文生图（可选，需用户确认） | 仅限非数据类装饰图，正式申报材料慎用 |

文生图画数据图的三大硬伤（评审一眼识别）：① 中文乱码或错字；② 数字与正文不一致（有造假嫌疑）；③ 节点与章节编号不对应。

**执行方式**：宿主 Agent（WorkBuddy / Claude Code / Codex / Cursor 等）在运行时按本节模板现场编写 Python 绘图代码并本地执行，产出 PNG 后嵌入 docx。这是"照规范发挥"，不是"自由发挥"：字体、配色、图注、编号必须遵守 27.2~27.4，图型选择遵守 27.3，特殊图型可现场扩展代码但不得突破本规范。

### 27.2 标准代码模板（字体 / 配色 / 尺寸）

```python
# -*- coding: utf-8 -*-
"""挑战杯配图标准模板：所有配图必须基于本模板绘制。"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

# 1) 中文字体 fallback 链（Win/macOS/Linux 通吃；缺字=质检不通过）
_available = {f.name for f in font_manager.fontManager.ttflist}
for _f in ("SimHei", "Microsoft YaHei", "Noto Sans CJK SC",
           "PingFang SC", "Heiti SC", "Arial Unicode MS"):
    if _f in _available:
        plt.rcParams["font.family"] = [_f]
        break
plt.rcParams["axes.unicode_minus"] = False

# 2) 统一配色 token（全套图共用，禁止每张图自定配色）
INK, GREY = "#111827", "#4B5563"      # 正文文字 / 辅助文字
BLUE, BLUEF = "#1E40AF", "#DBEAFE"    # 主色（框线 / 填充）
RED, REDF = "#B91C1C", "#FECACA"      # 强调（预期成果 / 本系统）
AMBER, AMBERF = "#B45309", "#FDE68A"  # 次强调（开发 / 过程类）
GREEN, GREENF = "#15803D", "#BBF7D0"  # 验证 / 通过类

# 3) 尺寸：正文版心宽约 15.5cm，dpi=200，白底
#    全宽图 figsize≈(7.5, h)，嵌入 15.5cm；大图（竖版流程图）嵌入 ≤12.5cm
def save(fig, path):
    fig.savefig(path, dpi=200, bbox_inches="tight",
                facecolor="white", pad_inches=0.12)
```

### 27.3 图型选择速查

| 数据场景 | 图型 | 数据来源 |
|----------|------|----------|
| 技术路线 / 研究内容关系 | 分层流程图（拓扑分层布局 + 阶段色带） | tech_roadmap[*].nodes/edges |
| 分阶段实施路线 | 阶段卡片图 + 时间轴 | tech_roadmap（阶段型节点） |
| 研究进度 | 甘特图 | duration + 采集的各任务起止时间 |
| 传统模式 vs 本作品指标对比 | 分组柱状图（每指标注明单位） | economic_benefits[*] |
| 构成占比（模态贡献 / 样本构成等） | 环图 | 信息采集 |
| 算法 / 方法对比 | 表格（遵循第 7 章，勿重复画图） | algorithm_comparison |

禁止：3D 饼图、渐变发光堆砌、装饰性图标铺满画面、Excel 默认配色。

### 27.4 编号与图注规则

1. **全文连续编号**：图 1、图 2……技术路线图并入全文图号，不再独立成系；表格单独编"表 N"。
2. **图注置于图下方居中**：格式为"图 N + 空格 + 标题"，可带括号注数据来源，如"图 5 项目研究进度甘特图（2026.06—2027.06，共 12 个月）"；宋体小五加粗。
3. **正文必须至少一处引用**："如图 N 所示""详见图 N"。无引用的图不得出现。
4. **图数一致**：图中数值必须来自 data.json；正文数值修改后必须重绘图。

### 27.5 锚点插入方法（python-docx 模板）

```python
from docx.shared import Cm, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph

def _para_after(el, parent):
    p = OxmlElement("w:p")
    el.addnext(p)
    return Paragraph(p, parent)

def insert_figure(anchor_p, img_path, width_cm, caption=None):
    """在段落 anchor_p 之后插入居中图片 + 图注。
    锚点按'标题段文本前缀'或'特征句前缀'在 doc.paragraphs 中查找。"""
    pic = _para_after(anchor_p._p, anchor_p._parent)
    pic.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pic.add_run().add_picture(img_path, width=Cm(width_cm))
    if caption:
        cap = _para_after(pic._p, pic._parent)
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = cap.add_run(caption)
        run.font.name = "宋体"
        run.font.size = Pt(9)
        run.font.bold = True
        run._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), "宋体")
```

锚点选取优先级：小节标题段（图插在标题下）＞ 特征句段落（如"（一）主要发现"段后）＞ 表格元素后（对 `tbl` 元素直接 `addnext`）。批量插图时先收集全部锚点再依次插入，插入后重扫全文核对图号连续。

### 27.6 悬空引用自检脚本（生成后必跑）

```python
# 用法：python check_fig_refs.py 申报书.docx（退出码非 0 = 不得交付）
import re
import sys
from docx import Document

doc = Document(sys.argv[1])
captions, refs = set(), set()
for p in doc.paragraphs:
    line = p.text.strip()
    m = re.match(r"^图\s*(\d+)", line)
    if m and len(line) < 60:              # 图注行（图 N 开头且为短行）
        captions.add(int(m.group(1)))
        continue
    for r in re.finditer(r"图\s*(\d+)", line):
        refs.add(int(r.group(1)))

missing = refs - captions        # 正文引用了但图不存在（悬空引用）
unref = captions - refs          # 有图但正文从未引用
print("悬空引用:", sorted(missing) or "无")
print("未被引用的图:", sorted(unref) or "无")
sys.exit(1 if (missing or unref) else 0)
```

### 27.7 反例与正例

**反例**：
- 用文生图画"技术路线图"：节点中文乱码、数字编造、与章节不对应（一票否决）
- 节点表格 + 关联关系表格直接充当"技术路线图"（v2.1 遗留问题，v2.2 起禁止；build.py 生成的节点表格至多作为附录数据保留，不得占据正文图的位置）
- 图无图注，或正文无"如图 N"引用（悬空图）
- 每张图各用一套配色、字体，风格散乱

**正例**：
- 照 27.2 模板渲染，全套图同字体、同配色、同线宽、同 dpi
- 图注含数据来源，如"（3 个消防站 3 个月实地测试统计）"
- 生成后跑 27.6 自检脚本，悬空引用与未引用图清零后才交付

---


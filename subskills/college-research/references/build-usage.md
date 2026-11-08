# 十八、build.py 接口说明【v2.1 必加章节 9】

> 从 `subskills/college-research/SKILL.md` 外移而来（渐进式披露）。
> 何时阅读：需要调用 build.py 或了解接口参数时。

### 18.1 命令行用法

```bash
# 使用数据文件生成
python build.py --data data.json --out output.docx

# 使用内置示例数据生成演示文档
python build.py --demo --out demo.docx
```

参数：
- `--data`：数据 JSON 文件路径（必填，与 --demo 二选一）
- `--out`：输出 docx 路径（必填，自动创建目录）
- `--demo`：使用内置示例数据生成演示文档

### 18.2 架构概览

```
build.py
├── 字体与格式常量（FONT_SONG / SIZE_XIAO_SI / ...）
├── 工具函数（set_run_font / set_cell_text / add_paragraph_with_format / ...）
├── GB/T 7714 参考文献格式化（format_journal_ref / format_book_ref / ...）
├── ApplicationDocBuilder 主类
│   ├── __init__ / _get / add_h1 / add_h2 / add_para / add_table
│   ├── _add_cover                          # 封面
│   ├── _add_leader_members                 # §1 负责人+成员
│   ├── _add_basic_info                     # §2/3/4 课题名/起止/类型
│   ├── _add_background                     # §5 背景与意义
│   ├── _add_policy_citations              # §5.5 国家政策引用（v2.1 新增）
│   ├── _add_research_status                # §6 国内外研究现状（简版）
│   ├── _add_literature_review             # §6.5 综述详尽版（v2.1 新增）
│   ├── _add_research_content               # §7 研究目标/内容/关键问题
│   ├── _add_scientific_challenges         # §7.5 科学挑战（v2.1 新增）
│   ├── _add_research_scheme                # §8 研究方案及技术路线
│   ├── _add_method_comparison             # §8.5 方法对比表（v2.1 新增）
│   ├── _add_formulas                      # §8.6 数学公式（v2.1 新增）
│   ├── _add_tech_roadmap                  # §8.7 技术路线图（v2.1 新增）
│   ├── _add_innovation                     # §9 创新之处
│   ├── _add_research_basis                 # §10 研究基础
│   ├── _add_expected_results               # §11 预期成果
│   ├── _add_social_benefits               # §11.5 社会效益量化（v2.1 新增）
│   ├── _add_schedule                       # §12 进度安排（4 阶段 6 个月）
│   ├── _add_budget                         # §13 经费预算
│   ├── _add_references                     # §14 参考文献
│   ├── _add_review_section                 # §15/16 指导教师+学院评审
│   ├── build                               # 主构建方法
│   ├── _save                               # 保存文档
│   └── _validate_data                      # 数据校验
├── DEFAULT_DATA 默认示例数据（含 v2.1 全部字段）
└── main CLI 入口
```

### 18.3 核心方法

| 方法 | 作用 | 触发字段 |
|------|------|----------|
| build(data, output_path) | 主构建方法，编排 16+9 章节 | 全部字段 |
| _validate_data() | 数据校验，记录警告不阻断 | P0/P1 字段 |
| _get(*keys, default) | 安全取嵌套字段 | - |
| _add_*() | 各章节渲染方法 | 对应字段 |

### 18.4 _validate_data 校验规则

| 校验项 | 阈值 | 警告级别 |
|--------|------|----------|
| 经费合计 | ≤2000 元 | 超 2000 警告 |
| 团队人数 | ≤2 人 | 超 2 警告 |
| 周期月数 | 3~6 个月 | 超 6 或低于 3 警告 |
| 参考文献数 | ≥5 条 | <5 警告 |
| 参考文献类型覆盖 | ≥3 类 | <3 警告 |
| 英文文献数（v2.1） | ≥3 篇 | <3 警告 |
| 国家政策引用数（v2.1） | ≥3 条 | <3 警告 |
| 文献综述条数（v2.1） | ≥10 条 | <10 警告 |
| 科学挑战数（v2.1） | ≥1 个 | <1 警告 |
| 方法对比方法数（v2.1） | ≥2 方法 | <2 警告 |
| 社会效益项数（v2.1） | ≥3 项 | <3 警告 |
| 进度阶段数（v2.1） | ≥4 阶段 | <4 警告 |

### 18.5 字体规范常量

```python
FONT_SONG = "宋体"          # 正文
FONT_HEI = "黑体"           # 标题
FONT_FANGSONG = "仿宋"      # 备注
FONT_KAI = "楷体"           # 引用
FONT_TIMES = "Times New Roman"  # 英文/数字

SIZE_ER = Pt(22)            # 二号（封面标题）
SIZE_SAN = Pt(16)           # 三号（一级标题）
SIZE_XIAO_SAN = Pt(15)      # 小三（二级标题）
SIZE_SI = Pt(14)            # 四号（三级标题）
SIZE_XIAO_SI = Pt(12)       # 小四（正文）
SIZE_WU = Pt(10.5)          # 五号（表格、参考文献）
```

### 18.6 输出路径

默认输出到当前目录。建议命名规则：`院级_{课题简称}_{申报日期}.docx`，如 `院级_学习拖延干预_20250310.docx`。

---


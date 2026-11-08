# §12 build.py 接口说明

> 从 `subskills/military-enlistment/SKILL.md` 外移而来（渐进式披露）。
> 何时阅读：需要调用 build.py 或了解接口参数时。

### §12.1 命令行接口

```bash
python build.py --data data.json --out output.docx
python build.py --demo --out demo.docx
```

参数说明：
- `--data`：JSON 文件路径，与 --demo 二选一
- `--out`：输出 docx 路径，必填
- `--demo`：使用内置 DEFAULT_DATA 生成演示文档

### §12.2 类与主要方法

`ApplicationDocBuilder` 类（详见 build.py）：

| 方法 | 用途 | 输出 |
|------|------|------|
| `__init__()` | 初始化 Document + 设置页面与默认字体 | — |
| `build(data, output_path)` | 主构建方法 | str（实际保存路径） |
| `_validate_data()` | 数据校验（P0 必填、入伍类型、体检政审等） | List[str]（警告列表） |
| `_add_cover()` | 封面 | 标题 + 6 行信息 |
| `_add_basic_info()` | 一、个人基本情况 | 段落 + 基本信息表 + 体检政审表 |
| `_add_motivation()` | 二、入伍动机 | 4 子段 + 引用文件 |
| `_add_abilities()` | 三、个人素质 | 3 子段 |
| `_add_military_adaptability()` | 四、部队适应能力 | 3 子段 |
| `_add_family_attitude()` | 五、家人态度与决心 | 2 子段 |
| `_add_signature_section()` | 签字栏 | 申请人 + 学校武装部 + 县级征兵办 |
| `_save(output_path)` | 保存文档 | str |

### §12.3 格式规范（与所有子 skill 统一）

- A4 纸张（21.0 × 29.7 cm）
- 页边距：上下 2.54cm，左右 2.5cm
- 正文：宋体小四（12pt），1.5 倍行距，首行缩进 2 字符
- 一级标题：黑体三号（16pt），居中，段前段后 12pt
- 二级标题：黑体小三（15pt），左对齐，段前段后 6pt
- 三级标题：宋体四号加粗（14pt），左对齐
- 表格：宋体五号（10.5pt），居中
- 页脚：居中页码

### §12.4 校验规则（_validate_data）

build.py 的 _validate_data 方法执行以下校验：

**P0 必填校验（缺失即警告）**：
- applicant_name / applicant_political / applicant_degree
- enlistment_type（必须为 在校生入伍 / 毕业生入伍 之一）
- age / height_cm / weight_kg / left_eye_vision / right_eye_vision
- physical_exam / political_review
- motivation（必须有 4 段）
- abilities（必须有 3 子段）
- military_adaptability（必须有 3 子段）
- family_attitude（必须有 2 子段）
- military_doc_cited（至少 1 项）

**入伍类型与年龄匹配校验**：
- enlistment_type == 在校生入伍 → age 须为 18-22
- enlistment_type == 毕业生入伍 → age 男兵 18-24，女兵 18-22

**体检硬条件校验**：
- 男 height_cm ≥ 160，女 height_cm ≥ 158
- 陆勤 left_eye_vision ≥ 4.5，right_eye_vision ≥ 4.6（数值化校验）
- physical_exam 含"合格"关键词
- political_review 含"合格"关键词

**家人态度校验**：
- family_attitude 必含"沟通"或"告知"关键词（确保有沟通过程）
- 不含则警告

**字数校验**：
- 总字数（5 段合计）应在 1500-2500 字
- 不足 1500 字 → 警告"字数偏少，建议补充"
- 超过 2500 字 → 警告"字数偏多，建议精简"

**政治面貌校验**：
- applicant_political 须为 中共党员/共青团员/群众/中共预备党员 之一

---


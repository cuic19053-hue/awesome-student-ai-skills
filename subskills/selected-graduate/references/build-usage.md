# §11 build.py 接口说明

> 从 `subskills/selected-graduate/SKILL.md` 外移而来（渐进式披露）。
> 何时阅读：需要调用 build.py 或了解接口参数时。

### 11.1 命令行用法

```bash
# 生成 demo 文档（使用内置 DEFAULT_DATA）
python build.py --demo --out demo.docx

# 使用外部 data.json 生成
python build.py --data data.json --out output.docx

# 指定字数版本（覆盖 JSON 中的 word_version）
python build.py --data data.json --out output.docx --word-version 2000

# 指定选调类型（覆盖 JSON 中的 selection_type）
python build.py --data data.json --out output.docx --selection-type central
```

### 11.2 参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `--demo` | flag | 否 | 使用内置 DEFAULT_DATA 生成 demo 文档 |
| `--data` | path | 否 | 输入 JSON 文件路径 |
| `--out` | path | 是 | 输出 docx 文件路径 |
| `--word-version` | int | 否 | 覆盖字数版本（2000/2500/3000） |
| `--selection-type` | str | 否 | 覆盖选调类型（central/directional/non_directional） |

### 11.3 输出格式规范

- A4 纸张（21cm × 29.7cm）
- 页边距：上下 2.54cm，左右 2.5cm
- 一级标题：黑体三号居中
- 二级标题：黑体小三左对齐
- 正文：宋体小四，1.5 倍行距，首行缩进 2 字符
- 签字栏：宋体小四右对齐
- 输出文件：docx 格式

### 11.4 输出文档结构

```
[一级标题] 选调生申请书
[正文段一] 一、个人基本情况
[正文段二] 二、报考选调生动机
  [二级标题] 政治立场方面
  [正文]
  [二级标题] 服务基层方面
  [正文]
  [二级标题] 事业追求方面
  [正文]
  [二级标题] 家乡情怀方面
  [正文]
[正文段三] 三、个人能力素质
  [二级标题] 政治素质方面
  [正文]
  [二级标题] 学习能力方面
  [正文]
  [二级标题] 组织协调方面
  [正文]
  [二级标题] 群众工作方面
  [正文]
  [二级标题] 抗压能力方面
  [正文]
[正文段四] 四、基层工作意愿
[正文段五] 五、个人发展规划
[签字栏] 申请人：XXX  日期：YYYY-MM-DD
```

### 11.5 错误处理

build.py 在以下情况会报错并退出：
- JSON 字段缺失（必填字段未提供）
- 政治面貌不是党员或预备党员
- 字数版本不是 2000/2500/3000 之一
- 选调类型不是 central/directional/non_directional 之一
- 禁用句检测命中（见 §8.2 雷区 2）

---


# §7 build.py 接口说明（必加章节 7）

> 从 `subskills/class-collective/SKILL.md` 外移而来（渐进式披露）。
> 何时阅读：需要调用 build.py 或了解接口参数时。

### 7.1 命令行接口

```bash
# 方式 1：使用 demo 数据生成示例文档
python build.py --demo --out demo.docx

# 方式 2：使用用户提供的数据生成正式文档
python build.py --data data.json --out output.docx

# 方式 3：同时指定字数版本（覆盖 data.json 中的 word_count_version）
python build.py --data data.json --out output.docx --word-count 5000
```

### 7.2 参数说明

| 参数 | 必填 | 说明 |
|------|------|------|
| `--demo` | 二选一 | 使用内置 DEFAULT_DATA 生成示例文档 |
| `--data` | 二选一 | 用户数据 JSON 文件路径 |
| `--out` | 是 | 输出 docx 文件路径 |
| `--word-count` | 否 | 字数版本（3000/4000/5000），覆盖 JSON 中的设置 |

### 7.3 输出格式标准

- **纸张**：A4（21.0 × 29.7 cm）
- **页边距**：上下 2.54 cm，左右 2.5 cm
- **标题**：黑体二号（22pt），居中
- **正文**：宋体小四（12pt），1.5 倍行距，首行缩进 2 字符
- **段落标题**：黑体小三（15pt），加粗
- **表格**：宋体五号（10.5pt），居中，表头加粗
- **落款**：右对齐，含班长 / 团支书 / 班主任签字位
- **页眉页脚**：页脚居中页码

### 7.4 输出文档结构

1. **封面**（首页）：标题（"XX 班集体申报书"）+ 班级全称 + 申报类别 + 申报日期
2. **正文 6 段**：班级概况 → 思想建设 → 学风建设 → 班级活动 → 班级荣誉 → 工作展望
3. **5 维度量化表**（嵌入 §5 班级荣誉段或附录）
4. **班委建制表**（嵌入 §1 班级概况段）
5. **班级荣誉表**（嵌入 §5 班级荣誉段）
6. **落款**：班长签字 + 团支书签字 + 班主任签字 + 学院盖章位 + 日期

### 7.5 错误处理

- JSON 字段缺失：报错并提示缺失字段名
- 字数版本非法：报错"word_count_version 必须为 3000/4000/5000"
- collective_type 非法：报错"collective_type 必须为 advanced_class/good_study_class/may_fourth_flag/civilized_class"
- 5 维度分数超限：报错并提示具体超限项
- 班级人数与硬门槛不符：警告（不阻塞生成）

---


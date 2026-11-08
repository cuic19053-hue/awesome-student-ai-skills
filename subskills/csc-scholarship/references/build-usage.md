# §10 build.py 接口说明

> 从 `subskills/csc-scholarship/SKILL.md` 外移而来（渐进式披露）。
> 何时阅读：需要调用 build.py 或了解接口参数时。

### §10.1 命令行调用

```bash
# 使用内置示例数据生成演示文档
python build.py --demo --out /tmp/demo_csc.docx

# 使用用户提供的 JSON 数据生成
python build.py --data data.json --out output.docx

# 指定字数版本
python build.py --demo --word-count 3000 --out /tmp/demo_3000.docx

# 指定项目类型
python build.py --demo --csc-type phd --out /tmp/demo_phd.docx
```

### §10.2 参数说明

| 参数 | 必填 | 说明 |
|---|---|---|
| `--out` | ✅ | 输出 docx 文件路径 |
| `--data` | 二选一 | JSON 数据文件路径 |
| `--demo` | 二选一 | 使用内置示例数据 |
| `--word-count` | ❌ | 字数版本（2500 / 3000 / 4000），默认按 csc_type 自动 |
| `--csc-type` | ❌ | 项目类型（phd / joint_phd / master / visiting_scholar），默认 joint_phd |

### §10.3 输出说明

- 控制台：打印生成进度与警告
- 输出文件：A4 docx，包含 6 段结构 + 表格（基本信息表、留学时间表、研究计划表、预期成果表、归国去向表）
- 退出码：成功 0，失败 1

### §10.4 字体与格式标准

- 纸张：A4（21cm × 29.7cm）
- 页边距：上下 2.54cm，左右 2.5cm
- 标题：黑体二号（22pt），居中，段前后 12pt
- 二级标题（一、二、三…）：黑体小四（12pt）加粗，首行缩进 2 字符
- 正文：宋体小四（12pt），1.5 倍行距，首行缩进 2 字符
- 称呼：顶格宋体小四
- 落款：右对齐宋体小四
- 表格：宋体五号（10.5pt），表头加粗居中，数据居中

---


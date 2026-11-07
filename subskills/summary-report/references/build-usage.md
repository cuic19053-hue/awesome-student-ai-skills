# 十一、JSON 字段与 build.py 接口说明

> 从 `subskills/summary-report/SKILL.md` 外移而来（渐进式披露）。
> 何时阅读：需要调用 build.py 或了解接口参数时。

### 11.1 命令行调用

```bash
# 用外部数据文件生成
python build.py --data data.json --out 阶段思想汇报.docx

# 用内置演示数据生成
python build.py --demo --out demo.docx

# 套用学校版式（可选）
python build.py --data data.json --out 阶段思想汇报.docx --school pku
```

### 11.2 字段定义（build.py 实际消费的字段）

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `title` | string | 否 | `阶段思想汇报` | 标题，居中黑体二号 |
| `salutation` | string | 否 | `尊敬的党组织：` | 称呼，顶格 |
| `reporter_name` | string | 否 | `汇报人：李明` | 落款第一行（含"汇报人："前缀） |
| `report_date` | string | 否 | `2026年  月  日` | 落款第二行 |
| `paragraphs` | string[] | 否 | 内置 5 段演示 | 正文段落列表，逐段写入 |

> ⚠️ build.py 只渲染 `paragraphs` 中的文本，"此致 / 敬礼！"与落款由脚本固定追加，**不需要**写进 `paragraphs`。

### 11.3 JSON 示例

```json
{
  "title": "2026年第三季度思想汇报",
  "salutation": "尊敬的党组织：",
  "reporter_name": "汇报人：李明",
  "report_date": "2026年09月30日",
  "paragraphs": [
    "自被确定为入党积极分子以来……向党组织作如下汇报。",
    "在思想政治方面……",
    "在专业学习方面……",
    "在日常工作与社会服务方面……",
    "总结近期表现……请党组织在实践中继续检验我。"
  ]
}
```

### 11.4 学校模板（`--school`）

支持 `pku` / `tsinghua` / `whu` / `zju`（或中文校名），分别套用 `utils/schools/template_*.json` 的页边距、页眉、页脚等版式；不传则用默认版式。个别模板可带印章位，须与支部要求核对后使用。

### 11.5 build.py 的校验逻辑

- 输出路径父目录不存在时自动创建；
- `--data` 与 `--demo` 都不给时，使用内置 5 段演示数据；
- 字段缺失回落默认值，不报错——因此**质检（§十）必须人工/脚本复核内容**，不能只依赖脚本跑通。

---


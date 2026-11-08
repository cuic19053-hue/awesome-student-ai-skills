# 十一、JSON 字段与 build.py 接口说明

> 从 `subskills/youth-league-conversion/SKILL.md` 外移而来（渐进式披露）。
> 何时阅读：需要调用 build.py 或了解接口参数时。

### 11.1 命令行调用

```bash
python build.py --data data.json --out 转正申请书.docx
python build.py --demo --out demo.docx
python build.py --data data.json --out 转正申请书.docx --school tsinghua
```

### 11.2 字段定义（build.py 实际消费的字段）

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `salutation` | string | 否 | `尊敬的党组织：` | 称呼，顶格 |
| `applicant_name` | string | 否 | `申请人：王伟`（脚本内置占位，**必须覆盖**） | 落款第一行（含"申请人："前缀） |
| `application_date` | string | 否 | `2026年  月  日` | 落款第二行 |
| `paragraphs` | string[] | 否 | 内置 4 段演示 | 正文段落列表 |

> ⚠️ 标题由脚本固定生成"转正申请书"，**无需**在字段中提供 `title`。
> ⚠️ "此致 / 敬礼！"亦由脚本固定追加，不要写进 `paragraphs`。
> ⚠️ 脚本内置的姓名、日期、段落全部是演示占位，**照抄生成的 docx 就是编造材料**；
> 实际使用时必须用 `--data` 传入用户本人数据。

### 11.3 JSON 示例

```json
{
  "salutation": "尊敬的党组织：",
  "applicant_name": "申请人：[姓名]",
  "application_date": "[YYYY]年[M]月[D]日",
  "paragraphs": [
    "[YYYY]年[M]月[D]日，经党支部大会讨论通过、上级党组织批准，我成为一名中共预备党员。截至[YYYY]年[M]月[D]日，我的预备期已满一年。今天，我向党组织提出按期转正申请。",
    "在思想政治方面……",
    "在专业学习与科研方面……",
    "回顾预备期，组织曾指出我……",
    "如果党组织批准我按期转正……如果党组织认为我还不够成熟……"
  ]
}
```

### 11.4 学校模板（`--school`）

支持 `pku` / `tsinghua` / `whu` / `zju`（或中文校名），套用 `utils/schools/template_*.json` 的版式；不传则默认版式。

### 11.5 build.py 的校验逻辑

- 输出父目录自动创建；
- `--data`/`--demo` 均缺省时用内置 4 段演示数据；
- 字段缺失回落默认值，不报错——**内容正确性必须靠 §十 质检人工/脚本复核**。

---


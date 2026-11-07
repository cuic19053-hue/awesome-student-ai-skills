# 十、docx 生成调用方式

> 从 `subskills/single-scholarship/SKILL.md` 外移而来（渐进式披露）。
> 何时阅读：需要调用 build.py 生成文档、或排查生成参数时。

### 10.1 命令

```bash
python build.py --data data.json --out output.docx
```

### 10.2 内置 demo

```bash
python build.py --demo --out demo.docx
```

### 10.3 JSON 字段

见 SKILL.md 第三章信息采集清单。data.json 必含字段：
- category：子方向（research/social_work/art_sport/progress）
- name/major/grade/college：申请人基本信息
- 该方向专属字段（3.3~3.6 之一）
- 其他方面字段（3.7，简略）

### 10.4 输出格式

- A4 纸张，页边距上下 2.54cm，左右 2.5cm
- 标题：黑体二号，居中
- 称呼：顶格，宋体小四，全角冒号
- 正文：宋体小四，1.5 倍行距，首行缩进 2 字符
- 单项表格：宋体五号，居中
- "此致"另起一行空两格，"敬礼！"另起一行顶格
- 落款：右对齐
- 页脚：居中页码

### 10.5 子方向切换

build.py 按 data.category 动态选择表格类型：
- research → 论文表+专利表+大创表
- social_work → 履职表+志愿服务表
- art_sport → 获奖作品表
- progress → GPA 提升表+进步课程对比表

---


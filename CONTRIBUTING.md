# 贡献指南

感谢你对本项目的关注！欢迎提 Issue 和 PR。

---

## 可以贡献什么

| 类型 | 示例 |
|---|---|
| 🐛 Bug 修复 | SKILL.md 里的格式错误、build.py 的 bug |
| 📝 内容补充 | 新增赛道、补充评审标准、完善案例 |
| 🌐 学校适配 | 新增学校模板（`utils/schools/`） |
| 📚 文档改进 | README 说明、使用教程 |
| 🎨 模板优化 | demo .docx 的排版改进 |
| 💡 新功能建议 | 新的工程化能力、新的输出格式 |

---

## 贡献前请阅读

1. **[README.md](./README.md)** — 了解项目定位和核心设计原则
2. **[SKILL.md](./SKILL.md)** — 了解路由设计和 35 个子 skill 的索引
3. **[references/writing_guide.md](./references/writing_guide.md)** — 了解撰写规范

---

## 诚实底线（必须遵守）

本项目有严格的诚实底线，所有贡献必须遵守：

1. **只写用户能提供证据的事实** —— 不替用户编造奖项、绩点、经历
2. **不放大、不润色** —— "班级第二"不能写成"成绩优异名列前茅"
3. **不留模糊占位** —— 拿不准的信息要追问，不写"获得多项荣誉"
4. **提醒用户复核** —— 生成后明确提示用户逐项核对真实性
5. **禁抄袭** —— 不复制网络模板原文
6. **禁虚构** —— 不编造案例数据
7. **案例脱敏** —— 任何案例不得包含学校名称、真实人名、联系方式

---

## 如何贡献

### 方式 1：提 Issue（最简单）

发现问题但不会写代码？直接提 Issue：

1. 点击 [Issues](https://github.com/cuic19053-hue/awesome-student-ai-skills/issues)
2. 点击 **New Issue**
3. 选择模板（Bug 报告 / 内容建议 / 新赛道请求）
4. 填写信息并提交

### 方式 2：提 PR（直接修改代码）

1. **Fork** 本仓库
2. **Clone** 到本地：
   ```bash
   git clone https://github.com/<你的用户名>/awesome-student-ai-skills.git
   ```
3. **新建分支**：
   ```bash
   git checkout -b feature/add-new-skill
   ```
4. **修改文件**
5. **提交**：
   ```bash
   git add .
   git commit -m "Add: 新增 XX 赛道 SKILL.md"
   ```
6. **推送**：
   ```bash
   git push origin feature/add-new-skill
   ```
7. **创建 PR**：在 GitHub 页面点击 **Compare & pull request**

---

## 新增赛道的规范

如果要新增一个赛道，请遵循以下结构：

```
subskills/<skill_id>/
├── SKILL.md    # 必须包含：适用场景、信息采集清单、工作流程、格式要求
└── build.py    # 必须包含：--demo 和 --data 两种模式
```

### SKILL.md 必含章节

1. YAML frontmatter（name、description、triggers）
2. 适用场景与触发条件
3. 硬门槛检查（如有）
4. 信息采集清单（字段名、示例、追问策略、优先级）
5. 工作流程（采集 → 撰写 → 生成 → 质检）
6. 格式要求（字体、页边距、字数等）
7. 质检清单
8. 禁止行为

### build.py 必须支持

```bash
# 生成 demo（用内置示例数据）
python build.py --demo --out demo.docx

# 用真实数据生成
python build.py --data data.json --out output.docx
```

---

## 提交信息规范

| 前缀 | 含义 | 示例 |
|---|---|---|
| `Add:` | 新增内容 | `Add: 新增节能减排大赛 SKILL.md` |
| `Fix:` | 修复 bug | `Fix: 修正国奖 SKILL.md 的字数要求` |
| `Update:` | 更新内容 | `Update: 互联网+ 2026 新评审标准` |
| `Refactor:` | 重构 | `Refactor: 重写 dispatcher.py 决策树` |
| `Docs:` | 文档 | `Docs: 完善使用指南` |
| `Chore:` | 杂项 | `Chore: 更新 .gitignore` |

---

## Review 流程

1. 所有 PR 需要至少 1 位 maintainer review
2. CI 检查通过（如果有）
3. 符合诚实底线和撰写规范
4. 合并后会在 README 致谢区署名（如愿意）

---

## 联系方式

- 提 Issue：[Issues](https://github.com/cuic19053-hue/awesome-student-ai-skills/issues)
- 邮件：通过 GitHub 个人主页联系

---

*感谢每一位贡献者。你们让更多同学少走了弯路。*

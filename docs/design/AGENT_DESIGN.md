# 对话式 AI Agent 设计文档

> 目标：用户输入项目简介 → AI 基于 SKILL.md 追问 → 信息齐全后自动生成图文并茂申报书

---

## 1. 核心原理

**SKILL.md 即 Agent。** 不需要额外编写"对话逻辑"，SKILL.md 里已经包含了：

- 要问什么（信息采集清单）
- 怎么问（追问话术）
- 什么必问（P0/P1/P2 优先级）
- 什么时候可以生成（工作流程四阶段）

**对话引擎只做一件事**：把 SKILL.md 喂给大模型当 System Prompt，让大模型按 SKILL.md 的指令行事。

---

## 2. 对话状态机

```
┌──────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────┐
│  START   │────→│  COLLECTING  │────→│  GENERATING  │────→│  DONE    │
│ 用户输入   │     │ AI 追问信息    │     │ 生成文档      │     │ 下载     │
│ 项目简介   │     │ 5-10 轮对话   │     │ 30-60 秒     │     │          │
└──────────┘     └──────┬───────┘     └──────────────┘     └──────────┘
                        │
                        │ 用户说"不确定""跳过"
                        ▼
                 ┌──────────────┐
                 │  FALLBACK    │
                 │ AI 提供默认值 │
                 │ 或标注为待补充 │
                 └──────────────┘
```

### 状态说明

| 状态 | 触发条件 | AI 行为 |
|---|---|---|
| START | 用户输入项目简介 | 加载 SKILL.md，识别赛道，检查硬门槛 |
| COLLECTING | 信息不齐全 | 按 P0→P1→P2 顺序追问，每轮 1-3 个问题 |
| GENERATING | 所有 P0 已采集 | 调用文本 API + 图片 API，组装 .docx |
| DONE | 文档生成完成 | 返回下载链接 |
| FALLBACK | 用户不回答 | 提供默认值或标注"待补充" |

---

## 3. 对话轮次设计

### 典型对话流程（以国家奖学金为例，约 7 轮）

```
轮次 1（AI 开场）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AI: "好的，国家奖学金申请书。先确认硬门槛：
     GPA 排名需要专业前 5%，你的排名是多少？"
用户: "1/87，GPA 3.92"
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

轮次 2（采集 P0 基础信息）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AI: "达标。请提供：你的姓名、学院、专业、年级、班级？"
用户: "张明，计算机学院，计算机科学与技术，2022级，计科2201班"
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

轮次 3（采集 P0 学业信息）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AI: "主干课程成绩呢？列出 5-8 门核心课的成绩，以及 CET-4/6 分数？"
用户: "高数95，线代93，数据结构91，操作系统89，计网90。CET-4 568，CET-6 542"
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

轮次 4（采集 P0 荣誉经历）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AI: "你参加过什么竞赛？获得过什么奖项？请提供时间、名称、级别。"
用户: "2025年数学建模国赛国家二等奖，2024年校级一等奖学金"
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

轮次 5（采集 P1 科研经历）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AI: "有科研经历或论文吗？"
用户: "大创项目《基于深度学习的图像识别》，国家级，负责人"
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

轮次 6（采集 P1 社会实践）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AI: "学生干部经历？志愿服务时长？"
用户: "班长，志愿服务120小时，三下乡社会调查"
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

轮次 7（确认 + 生成）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AI: "信息已齐全。确认无误？[是/修改]"
用户: "是"
AI: "正在生成申报书... ✅ 已生成，请下载：[国家奖学金申请书.docx]"
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### 追问策略

| 用户回答 | AI 策略 |
|---|---|
| 信息完整 | 记录 → 下一题 |
| 信息模糊（"我参加过竞赛"） | 追问："竞赛全称？奖项级别？时间？你是队长还是队员？" |
| 跳过（"不记得了""不方便说"） | P0 字段：必须追问。P1/P2：标注"待补充"，继续 |
| 多轮后仍不回答 | 用默认值（如"参与多项竞赛活动"），标注黄色高亮提醒用户修改 |

---

## 4. 信息齐全检测

### 检测逻辑（detector.py）

```python
def is_complete(skill_id: str, collected: dict) -> tuple[bool, list[str]]:
    """
    返回 (是否齐全, 缺失字段列表)
    """
    schema = load_schema(skill_id)  # 从 SKILL.md 自动提取
    missing = []
    
    for field in schema["p0_required"]:  # P0 必填
        if field not in collected or not collected[field]:
            missing.append(field)
    
    return (len(missing) == 0, missing)
```

### 检测时机

**每轮对话后自动检测**，不依赖大模型判断（大模型可能漏检）。

---

## 5. 生成阶段

### 5.1 文本生成

```
System Prompt:
  SKILL.md 全文（包含格式要求、字数要求、评审标准）

User Prompt:
  用户已采集的信息（JSON 格式）+ "请生成完整申报书正文，Markdown格式输出"
```

### 5.2 图片生成

```
文本中的标记 → 图片引擎 → PNG 图片

标记示例：
  <!--CHART:flowchart,技术路线图,{nodes:[...],edges:[...]}-->
  <!--CHART:gantt,进度甘特图,{tasks:[...]}-->
  <!--CHART:pie,经费预算,{items:[...]}-->
  <!--IMAGE:cover,封面图,{prompt:"无人机路径规划技术路线",style:"technical"}-->
```

### 5.3 文档组装

```
Markdown 正文 + PNG 图片 → python-docx → .docx 文件
```

---

## 6. 技术实现

### 6.1 核心文件

| 文件 | 行数 | 功能 |
|---|---|---|
| `agent/conversation.py` | ~200 | 对话引擎：加载 SKILL.md → 调用 DeepSeek → 多轮对话 |
| `agent/detector.py` | ~80 | 信息齐全检测 |
| `agent/generator.py` | ~150 | 文本生成 + 图片生成 |
| `agent/assembler.py` | ~100 | Markdown + 图片 → .docx |
| `cli.py` | ~50 | 命令行入口 |

### 6.2 conversation.py 核心逻辑

```python
class ConversationAgent:
    def __init__(self, skill_id: str):
        # 1. 加载 SKILL.md
        self.skill_md = load_skill_md(skill_id)
        # 2. 提取信息采集 schema
        self.schema = extract_schema(self.skill_md)
        # 3. 初始化 DeepSeek 客户端
        self.llm = DeepSeekClient()
        # 4. 信息存储
        self.collected = {}
        # 5. 对话历史
        self.history = [
            {"role": "system", "content": self.skill_md}
        ]
    
    def chat(self, user_input: str) -> str:
        """处理用户输入，返回 AI 回复"""
        # 1. 追加用户消息
        self.history.append({"role": "user", "content": user_input})
        
        # 2. 调用 LLM
        response = self.llm.chat(self.history)
        self.history.append({"role": "assistant", "content": response})
        
        # 3. 从回复中提取信息
        self.extract_info(user_input, response)
        
        # 4. 检测是否齐全
        complete, missing = is_complete(self.skill_id, self.collected)
        
        if complete:
            return self.trigger_generation()
        
        return response
    
    def trigger_generation(self) -> str:
        """触发文档生成"""
        self.history.append({
            "role": "system",
            "content": "信息已齐全，请生成完整申报书正文，Markdown格式输出。"
        })
        text = self.llm.chat(self.history)
        
        # 生成图片
        images = generate_images(text)
        
        # 组装文档
        docx = assemble_docx(text, images)
        
        return f"✅ 申报书已生成，请下载：{docx}"
```

### 6.3 命令行使用

```bash
# 启动对话
python cli.py --skill innovation_research

# 输出：
# 你: 我要做大创，课题是无人机路径规划
# AI: 好的，大创创新训练项目。先确认：你是负责人还是参与人？你的专业排名是多少？
# 你: 负责人，排名1/87
# AI: 收到。你的项目有什么创新点？
# ...
# AI: ✅ 申报书已生成 → output/innovation_research_20260726_143022.docx
```

---

## 7. 与现有 SKILL.md 的兼容性

**完全兼容，零修改。** 对话引擎的设计原则：

- SKILL.md 作为 System Prompt 直接传入，不改一个字
- 信息采集 schema 从 SKILL.md 的表格中自动解析
- 追问话术复用 SKILL.md 中已有的话术
- 生成格式复用 SKILL.md 中已有的格式要求

---

## 8. 下一步

| 步骤 | 内容 | 工作量 |
|---|---|---|
| 1. 创建 `agent/` 目录 | 新建 4 个核心文件 | 1 天 |
| 2. 实现 CLI 对话 | 命令行跑通一个赛道 | 1 天 |
| 3. 接入图片生成 | Mermaid + matplotlib | 1 天 |
| 4. 测试完整流程 | 大创赛道端到端 | 半天 |
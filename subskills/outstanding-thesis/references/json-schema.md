# §14 JSON Schema 完整字段定义

> 从 `subskills/outstanding-thesis/SKILL.md` 外移而来（渐进式披露）。
> 何时阅读：构造 --data 输入文件、或 build.py 报字段校验错误时。

### 14.1 通用字段（10）

```json
{
  "name": "张明",
  "student_id": "2021123456",
  "gender": "男",
  "college": "计算机科学与技术学院",
  "major": "计算机科学与技术",
  "grade": "2021 级 大四",
  "class_name": "计科 2101 班",
  "phone": "138XXXXXXXX",
  "apply_level": "school",  // school 校级 / college 院级
  "apply_year": "2025 届",
  "apply_date": "2025 年 6 月 10 日"
}
```

### 14.2 毕设字段（10）

```json
{
  "thesis_title": "基于对比学习的小样本医学影像分割方法研究",
  "thesis_type": "experimental",  // experimental / engineering / theoretical / software / art_design
  "advisor": "张伟 教授",
  "advisor_title": "教授",
  "defense_score": "92",
  "defense_rank": "1/87",
  "plagiarism_rate": "8.5%",
  "defense_date": "2025 年 5 月 28 日",
  "research_duration": "2024.09-2025.05（9 个月）",
  "graduate_type": "undergraduate"  // undergraduate / master / doctor / junior_college
}
```

### 14.3 课题字段（4）

```json
{
  "project_source": "导师国家自然科学基金子课题（项目编号 62XXXXXXXX）",
  "research_problem": "现有监督学习方法在小样本场景下精度不足",
  "research_significance": "学术：改进对比学习迁移性能；应用：服务基层医院 AI 辅助诊断",
  "research_goals": [
    "构建小样本医学影像数据集",
    "设计对比学习分割网络",
    "在公开数据集上验证方法有效性"
  ]
}
```

### 14.4 研究方法字段（6）

```json
{
  "research_method": "文献调研 → 实验设计 → 数据采集 → 模型训练 → 性能评估",
  "technical_route": "基于对比学习预训练 + Transformer 分割网络 + 迁移学习策略",
  "key_technologies": [
    {"name": "对比学习预训练", "application_step": "特征学习阶段", "problem_solved": "小样本场景特征学习不足"},
    {"name": "Transformer 分割网络", "application_step": "分割阶段", "problem_solved": "医学影像全局依赖建模"},
    {"name": "迁移学习策略", "application_step": "跨设备适配阶段", "problem_solved": "跨设备数据分布差异"}
  ],
  "data_material": "ISIC 2018 数据集（2 595 张皮肤镜图像）+ 自建数据集（300 张基层医院皮肤镜图像，已脱敏）",
  "research_stages": [
    {"stage": "1 文献调研", "time": "2024.09-2024.10", "content": "调研 50+ 篇文献", "output": "文献综述报告"},
    {"stage": "2 实验设计", "time": "2024.11-2024.12", "content": "设计实验方案", "output": "实验方案文档"},
    {"stage": "3 数据采集", "time": "2025.01-2025.02", "content": "采集 300 张图像", "output": "数据集"},
    {"stage": "4 模型训练", "time": "2025.03-2025.04", "content": "训练对比学习模型", "output": "训练日志"},
    {"stage": "5 性能评估", "time": "2025.04-2025.05", "content": "对比实验 + 消融实验", "output": "实验报告"}
  ],
  "experiments": [
    {"name": "小样本分割对比实验", "dataset": "ISIC 2018", "metric": "Dice", "baseline": "0.785", "ours": "0.870", "improvement": "+8.5%"}
  ]
}
```

### 14.5 创新点字段（1 列表，每项 5 字段）

```json
{
  "innovation_points": [
    {
      "type": "theoretical",  // theoretical 理论 / method 方法 / application 应用
      "name": "对比学习小样本分割理论框架",
      "description": "首次将对比学习引入皮肤镜图像分割任务，构建小样本场景下的分割理论框架",
      "comparison": "与 U-Net、DeepLab v3+ 相比，Dice 系数提升 8.5%",
      "support_material": "SCI 二区论文 1 篇（已发表）"
    },
    {
      "type": "method",
      "name": "多尺度特征融合模块 MSFF",
      "description": "设计跨尺度注意力机制，实现病灶边界精修",
      "comparison": "与基线 U-Net 相比，边界 IoU 提升 5.2%",
      "support_material": "发明专利 1 项（实质审查中）"
    },
    {
      "type": "application",
      "name": "基层医院皮肤镜辅助诊断部署",
      "description": "将所提方法部署于基层医院皮肤镜设备，实现 0.3 秒/张实时分割",
      "comparison": "已与 XX 县人民医院合作验证，诊断准确率提升 12%",
      "support_material": "合作验证报告 1 份"
    }
  ]
}
```

### 14.6 成果与应用价值字段（4）

```json
{
  "achievements": [
    {"category": "论文", "name": "基于对比学习的法律问答系统", "level": "SCI 二区", "author_order": "第一作者", "time": "2025.03"},
    {"category": "专利", "name": "一种基于对比学习的法律问答方法", "level": "发明专利", "author_order": "第一发明人", "time": "实质审查中"},
    {"category": "软著", "name": "皮肤镜图像分割软件 V1.0", "level": "软件著作权", "author_order": "第一完成人", "time": "2025.02"},
    {"category": "代码", "name": "MSFF 开源代码", "level": "GitHub 开源", "author_order": "维护者", "time": "2025.04"}
  ],
  "application_scenarios": [
    {"scene": "基层医院皮肤镜辅助诊断", "value": "诊断准确率提升 12%", "evidence": "XX 县人民医院合作报告"},
    {"scene": "在线医疗 AI 接口", "value": "已接入 XX 互联网医院", "evidence": "接入证明"},
    {"scene": "医学院教学辅助", "value": "已用于 XX 医学院皮肤科教学", "evidence": "教学应用证明"}
  ],
  "adoption_proofs": [
    {"unit": "XX 县人民医院", "content": "合作验证皮肤镜辅助诊断系统", "date": "2025.04", "proof_no": "XX-2025-001"}
  ],
  "future_research": [
    {"problem": "多模态融合诊断（CT + 皮肤镜）", "breakthrough": "提升诊断准确率至 95%+", "prospect": "应用于综合医院"},
    {"problem": "联邦学习框架下的隐私保护分割", "breakthrough": "实现跨医院数据协作", "prospect": "推广至全国医院"}
  ]
}
```

### 14.7 摘要与撰写控制字段（5）

```json
{
  "abstract": "本课题研究基于对比学习的小样本医学影像分割方法……（300~500 字，4 句结构）",
  "abstract_position": "end",  // end 末尾 / page 独立页
  "salutation": "尊敬的评审委员会：",
  "opening": "",
  "ending": ""
}
```

### 14.8 字段优先级速查

| 优先级 | 字段 |
|--------|------|
| P0 必采 | name, major, grade, thesis_title, thesis_type, advisor, defense_score, innovation_points |
| P1 重要 | project_source, research_problem, research_method, key_technologies, research_stages, achievements, application_scenarios |
| P2 可选 | student_id, phone, plagiarism_rate, adoption_proofs, future_research, experiments |

---


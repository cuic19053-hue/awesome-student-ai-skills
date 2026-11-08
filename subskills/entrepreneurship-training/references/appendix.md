# 十三、附录

> 从 `subskills/entrepreneurship-training/SKILL.md` 外移而来（渐进式披露）。
> 何时阅读：遇到正文未覆盖的边界问题、或查常见疑问时。

### 13.1 案例 2 完整章节结构（79 页）

```
封面
一、基本信息（项目名称/关键词/学科/类型/类别/实施时间/负责人及成员/指导教师）
项目简介（200 字）
项目优势总结（10 条）
二、项目介绍
  1. 项目的立项依据
    1.1 国家规划与技术需求
      （1）国家规划（10+ 政策）
      （2）技术需求
    科学挑战一/二/三
    1.2 研究意义与国内外研究现状
      1.2.1 研究意义（3 段）
      1.2.2 国内外研究现状（3 个方向）
      (3) 对现有研究现状的总结与分析
    参考文献（31 篇）
  2. 项目的研究内容、研究目标，以及拟解决的关键科学问题
    2.1 硬件基础
      2.1.1 消防水枪无人机
      2.1.2 高空切割无人机
    2.2 研究内容（3 部分）
    2.3 研究目标（3 个）
    2.4 拟解决关键科学问题（3 个）
  3. 拟采取的研究方案
    3.1 研究方案
      3.1.1 研究方法和思路（图 13）
      3.1.2 技术路线（图 14）
    3.2 实验方法和关键技术
      3.2.1 多模态融合感知与重构算法实施方案（图 15-18，含 ASCN/Fire-Transformer/Fire-LIO-SAM）
      3.2.2 火场极端环境轻量化层次化感知耦合网络设计（图 19-23）
      3.2.3 物理安全约束的三维路径规划（图 24-27，含 PI-STGNN/CA/SC-RL/PF-RRT）
  4. 本项目的特色与创新之处（3 条）
  5. 社会经济效益分析
    5.1 综合效益概述（图 28）
    5.2 社会效益（3 条）
    5.3 经济效益（3 条 + 表 2 经济效益量化评估表 12 项）
    5.4 政治与战略效益（3 条）
  6. 市场分析
    6.1 总体市场规划（图 29）
    6.2 市场组合定位
      6.2.1 产品策略（图 26 产品生命周期 4P 营销组合图）
      6.2.2 渠道策略
      6.2.3 价格策略（图 27 3C 定价模型）
      6.2.4 促销策略（表 3 社会公共关系促销方式 + 表 4 促销模式）
    6.3 推广方式（图 28 多平台媒体推广模式）
    6.4 供应链优化（图 29 供应链优化模式 + 图 30 盈利模式）
7. 实践过程（图 31-37 共 7 张照片）
三、市场分析（5 小节）
四、营销模式（4P）
五、财务分析（资金筹备+表 5-14 共 10 张表+利润预计+风险+退出）
六、风险预期（6 类风险）
七、项目进度安排（4 阶段 + 合作协议图 39-42）
八、技术壁垒（图 43-50 共 8 张）
九、创业愿景
十、经费预算（表 15）
十一、指导教师意见
十二、学院意见
```

### 13.2 案例 2 算法清单（10 个核心算法）

| 算法 | 全称 | 章节 | 解决挑战 |
|------|------|------|---------|
| ASCN | Adaptive Sparse Convolution Network | 3.2.1(1) | 挑战一·点云稀疏 |
| Fire-Transformer | Fire-Scene Cross-Modal Transformer | 3.2.1(2) | 挑战一·模态失效 |
| Fire-LIO-SAM | Fire-Resilient LIO-SAM | 3.2.1(3) | 挑战一·几何退化 |
| IAT+YOLO+FFA | Illumination Adaptive Transformer + YOLO + Feature Filtering and Aggregation | 3.2.2(1) | 挑战二·光照异常 |
| FPN | Feature Pyramid Network | 3.2.2(2) | 挑战二·多尺度 |
| MobileNetV3 | MobileNetV3-Small | 3.2.2(3) | 挑战二·轻量化 |
| Coupled-DetSeg | Coupled Detection-Segmentation Network | 3.2.2(4) | 挑战二·多任务 |
| PI-STGNN | Physics-Informed Spatio-Temporal Graph Neural Network | 3.2.3(1) | 挑战三·数据缺失 |
| CA | Cellular Automata Dynamic Evolution Algorithm | 3.2.3(2) | 挑战三·轻量化 |
| SC-RL | Safety-Constrained Reinforcement Learning | 3.2.3(3) | 挑战三·安全约束 |
| PF-RRT | Potential Field-Guided RRT* | 3.2.3(4) | 挑战三·高维规划 |

### 13.3 案例 2 图表清单

**图清单**（共 50 张）：
- 图 1-3：政策架构图
- 图 4-5：火灾数据/烟囱效应
- 图 6-9：研究意义架构图
- 图 10-11：硬件模型图
- 图 12-14：技术路线图（3 张必备）
- 图 15-27：算法架构与流程图（13 张）
- 图 28：社会经济效益对比图
- 图 29-30：市场规划与盈利模式
- 图 31-37：实践过程照片（7 张必备）
- 图 38-42：合作协议（4 张）
- 图 43-50：技术壁垒（8 张）

**表清单**（共 15 张）：
- 表 1：主流自适应路径规划算法对比表
- 表 2：经济效益量化评估表（12 项）
- 表 3：社会公共关系促销方式
- 表 4：促销模式
- 表 5：预计销售数量和销售收入表
- 表 6：产品成本预测表
- 表 7：管理费用预测表
- 表 8：销售费用预测表
- 表 9：项目现金流量预测表
- 表 10：净现值表
- 表 11：盈利能力指标表
- 表 12：项目资产负债表
- 表 13：短期偿债能力指标表
- 表 14：长期偿债能力指标表
- 表 15：经费预算表

### 13.4 案例 2 文献清单（31 篇）

详见 build.py 中 DEFAULT_DATA["literature_review"]["references"] 字段，含：
- 英文期刊 22 篇（IEEE Transactions × 3、Springer × 2、Computer Networks、Artificial Intelligence Review、Drones、Sensors × 2、Engineering Applications of Artificial Intelligence × 2、ISPRS、Applied Sciences、Soft Computing、Automation in Construction、Advanced Engineering Informatics、Cluster Computing、Electronic Imaging、Artificial Intelligence for the Earth Systems 等）
- 中文文献 9 篇（软件学报、北京邮电大学学报、传感器、西安邮电大学学报、无人系统技术、工业仪表与自动化装置、博硕论文 × 2）
- 英文专著 1 篇（Springer）

### 13.5 build.py 函数索引

| 函数名 | 用途 | 章节 |
|--------|------|------|
| setup_page | A4 页面设置 | 通用 |
| add_page_number | 页脚页码 | 通用 |
| add_heading_level1/2/3 | 三级标题 | 通用 |
| add_body_paragraph | 正文段落 | 通用 |
| add_table_from_data | 数据表格 | 通用 |
| add_canvas_9grid | 商业模式画布 9 宫格 | 商业模式 |
| _add_cover | 封面 | 第一章 |
| _add_basic_info_table | 基本信息 | 第二章 |
| _add_abstract_and_advantages | 项目简介+10 优势 | 第三章 |
| _add_policy_citations | 国家政策 10+ | 立项依据 |
| _add_scientific_challenges | 科学挑战 3 段 | 立项依据 |
| _add_literature_review | 文献综述 30+ | 立项依据 |
| _add_hardware_basis | 硬件基础 2 类 | 研究内容 |
| _add_research_content | 研究内容 3 部分 | 研究内容 |
| _add_research_goals | 研究目标 3 个 | 研究内容 |
| _add_key_scientific_problems | 关键科学问题 3 个 | 研究内容 |
| _add_algorithm_comparison | 算法对比表 | 研究方案 |
| _add_tech_roadmap | 技术路线图 3 张 | 研究方案 |
| _add_formulas | 数学公式 4 个 | 研究方案 |
| _add_innovations | 创新点 3 条 | 研究方案 |
| _add_economic_benefits | 经济效益 12 项 | 社会效益 |
| _add_social_political_benefits | 社会/政治效益 | 社会效益 |
| _add_market_analysis_5sections | 市场分析 5 小节 | 市场分析 |
| _add_marketing_4p | 4P 营销 | 营销模式 |
| _add_pricing_3c | 3C 定价 | 营销模式 |
| _add_promotion_strategy | 促销策略 | 营销模式 |
| _add_supply_chain | 供应链优化 5 子节 | 营销模式 |
| _add_financial_statements | 5 年三表 10 张 | 财务分析 |
| _add_practice_process | 实践过程 7 照片 | 实践 |
| _add_cooperation_agreements | 合作协议 4 家 | 实践 |
| _add_tech_barriers | 技术壁垒 4 专利+检测+实物 | 壁垒 |
| _add_project_schedule | 4 阶段甘特 | 进度 |
| _add_team_intro | 团队介绍 | 团队 |
| _add_risk_analysis | 风险分析 | 风险 |
| _add_expected_results | 预期成果 | 成果 |
| _add_budget | 经费预算 | 预算 |
| _add_signature_section | 签字栏 | 签字 |

---


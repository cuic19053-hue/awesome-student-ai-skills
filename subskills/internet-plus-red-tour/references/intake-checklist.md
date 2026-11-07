# §2 信息采集清单

> 从 `subskills/internet-plus-red-tour/SKILL.md` 外移而来（渐进式披露）。
> 何时阅读：需要逐条向用户提问采集信息时。

### §2.1 通用必采（15 字段）

| 字段 | 说明 | 示例 |
|------|------|------|
| project_name | 项目名称（≤25 字，含产品代号 + 助农属性） | "红土蜜语——井冈山老区蜂蜜电商助农平台" |
| track | 赛道（固定 red_journey） | "red_journey" |
| red_theme | 红旅主题（4 选 1：乡村振兴/革命老区/民族团结/西部开发） | "革命老区" |
| rural_county | 帮扶县/乡/村名称（必填，需精确到行政村） | "江西省吉安市井冈山市茅坪镇神山村" |
| team_name | 团队名称 | "红土蜜语团队" |
| leader_name | 负责人姓名 | "张三" |
| leader_id | 学号 | "202212345" |
| leader_major | 专业 | "农林经济管理" |
| leader_grade | 年级 | "2022 级 大三" |
| leader_phone | 联系电话 | "138XXXXXXXX" |
| advisor_name | 指导教师姓名 | "李教授" |
| advisor_title | 指导教师职称 | "副教授" |
| college | 学院 | "经济管理学院" |
| school | 学校 | "XX 大学" |
| apply_date | 申报日期 | "2025 年 5 月 20 日" |

### §2.2 项目核心（12 字段）

| 字段 | 说明 |
|------|------|
| executive_summary | 执行摘要（800~1000 字，六要素 + 红色基因 + 帮扶成效） |
| red_gene.red_study | 党史学习情况（学习内容 + 学习方式 + 学习成效） |
| red_gene.revolution_spirit | 革命精神传承（井冈山/延安/西柏坡等精神 + 项目中的具体体现） |
| red_gene.red_culture | 红色文化传承（红色资源对接 + 红色文化产品） |
| red_gene.typical_case | 典型案例（学习的老区典型 + 项目对标） |
| rural_revival.industry | 产业振兴（带动什么产业 + 规模 + 农户参与数） |
| rural_revival.talent | 人才振兴（培训农户数 + 培养本土带头人 + 大学生返乡） |
| rural_revival.culture | 文化振兴（红色文化/非遗/民俗活化） |
| rural_revival.ecology | 生态振兴（绿色生产/生态保护/可持续） |
| rural_revival.organization | 组织振兴（与党支部结对 + 合作社组织 + 集体经济） |

### §2.3 帮扶成效素材（必采）

| 字段 | 说明 | 示例 |
|------|------|------|
| service_content.service_county | 服务覆盖县数 | 3 |
| service_content.service_township | 服务覆盖乡镇数 | 8 |
| service_content.service_village | 服务覆盖行政村数 | 25 |
| service_content.farmer_count | 带动农户数 | 156 户 |
| service_content.income_increase | 户均增收金额/年 | 4800 元/户·年 |
| service_content.coverage_month | 持续服务月数 | 18 个月 |
| service_content.coop_count | 合作社数量 | 4 个 |
| service_content.party_branch_pair | 党支部结对数 | 3 个 |
| coverage_data.field_visit_count | 老区行/乡村行次数 | 6 次 |
| coverage_data.field_visit_days | 累计蹲点天数 | 42 天 |
| coverage_data.interview_count | 访谈样本量 | 156 人 |
| coverage_data.survey_report | 调研报告产出 | 2 份 |

### §2.4 商业模式与可持续造血

| 字段 | 说明 |
|------|------|
| business_model.canvas | 商业模式画布 9 要素（含老区/农户/合作社作为重要伙伴） |
| business_model.revenue_streams | 收入来源（造血式，非捐赠输血） |
| business_model.pricing | 定价策略（含农户分红比例） |
| business_model.blood_making | 可持续造血模式说明（不依赖外部捐赠的可复制模式） |
| business_model.self_sufficiency_rate | 财务自给率（≥70% 为健康） |

### §2.5 团队素材（含思政要素）

| 字段 | 说明 |
|------|------|
| team_intro.members | 核心成员表（5~8 人，含政治面貌列） |
| team_intro.member_details | 成员简介（含优秀团员/积极分子/党员发展情况） |
| team_intro.advisor_bg | 指导教师背景（建议含思政教师/涉农专业教师） |
| team_intro.party_branch_pair | 与老区/乡村党支部结对情况 |
| team_intro.volunteer_hours | 团队成员累计志愿服务时长 |

### §2.6 字段优先级与追问

- **P0 字段缺失**（必采）：project_name / red_theme / rural_county / executive_summary / red_gene / rural_revival / service_content → 必须追问
- **P1 字段缺失**（建议采）：business_model / financial_forecast / team_intro / coverage_data → 提示用户补充
- **P2 字段缺失**（可选）：financing_plan / personal_growth → 用合理默认值

采集话术示例："请问你的项目帮扶的县乡村全称是什么？（如'江西省吉安市井冈山市茅坪镇神山村'）帮扶主题是乡村振兴/革命老区/民族团结/西部开发哪个？红色基因传承怎么体现？带动了多少农户？户均增收多少？这些数据必须有真实出处，不能编造。"

---


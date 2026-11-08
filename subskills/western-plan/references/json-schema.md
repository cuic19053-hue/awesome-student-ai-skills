# §11 docx 生成调用规范与 JSON Schema

> 从 `subskills/western-plan/SKILL.md` 外移而来（渐进式披露）。
> 何时阅读：构造 --data 输入文件、或 build.py 报字段校验错误时。

### §11.1 命令行用法

```bash
# 使用自定义数据生成
python build.py --data data.json --out output.docx

# 演示模式（内置示例数据）
python build.py --demo --out demo.docx
```

- `--data`：数据 JSON 文件路径（与 --demo 二选一）
- `--out`：输出 docx 路径（必填，自动创建目录）
- `--demo`：使用内置示例数据生成演示文档

### §11.2 JSON Schema 完整字段（与 build.py 一一对应）

#### §11.2.1 顶层字段

```json
{
  "applicant_name": "张三",
  "applicant_gender": "男",
  "applicant_ethnicity": "汉族",
  "applicant_birth": "2002 年 5 月",
  "applicant_political": "中共党员",
  "applicant_native_place": "四川省凉山彝族自治州西昌市",
  "applicant_id": "2022012345",
  "applicant_major": "汉语言文学（师范）",
  "applicant_grade": "2022 级",
  "applicant_school": "XX 师范大学文学院",
  "applicant_degree": "本科应届毕业",
  "applicant_graduation": "2026 年 6 月",
  "applicant_phone": "138XXXXXXXX",
  "applicant_email": "zhangsan@example.com",

  "apply_year": "2025",
  "service_preference": "education_service",
  "second_preference": "youth_work",
  "service_years": 1,
  "service_region_preference": "四川省凉山彝族自治州",
  "accept_redeployment": true,

  "academic_rank": "专业前 15%（8/52）",
  "gpa": "3.6/4.0",
  "core_courses": "现代汉语 92 / 古代文学 89 / 语文教学论 95 / 教育学 88",
  "certificates": ["高级中学教师资格证（语文）", "普通话二级甲等", "CET-6"],
  "honors": ["2024 年国家奖学金", "2023 年校级一等奖学金", "校级优秀学生干部"],
  "publications": [],
  "competitions": ["2024 年"挑战杯"省级一等奖", "2023 年师范生教学技能大赛省级二等奖"],

  "political_detail": "2023 年 6 月加入中国共产党，推荐人为辅导员李老师与班主任王老师。在校期间认真学习党的理论，研读《习近平与大学生朋友们》《习近平的七年知青岁月》等著作，完成'青年大学习'52 期，撰写阶段汇报 6 篇。曾任院学生党支部宣传委员，组织主题党日活动 8 次。",

  "practice_experience": [
    {"role": "院学生会主席", "period": "2023.09-2024.06", "work": "组织学院迎新晚会、运动会、辩论赛等大型活动 12 次", "result": "覆盖同学 1500 人次，获评校级优秀学生干部"},
    {"role": "暑期支教志愿者", "period": "2023.07-2023.08", "work": "赴四川省凉山州西昌市安宁镇中心小学支教 21 天，承担语文、音乐教学", "result": "教学课时 60 节，受益学生 45 人"}
  ],
  "volunteer_id": "SC5101234567890",
  "volunteer_hours": 280,

  "physical_check": "2025 年 3 月 XX 师范大学校医院体检合格，无重大疾病史",
  "physical_test": "国家学生体质健康标准良好",
  "psychological_test": "校级心理测评结论良好",
  "adaptability": "曾独立骑行 318 国道（成都—拉萨，21 天），具备跨文化适应基础",

  "motivation": [
    "本人认真学习了团中央、教育部、财政部、人社部联合印发的《2025 年大学生志愿服务西部计划实施方案》及《关于做好 2025 年大学生志愿服务西部计划工作的通知》，深入了解西部计划自 2003 年实施以来累计选派 50 余万名志愿者的项目历程，明确西部计划与暑期'三下乡'社会实践、三支一扶、特岗教师等项目的区别——西部计划是 1-3 年全职志愿服务，三下乡是 7-15 天暑期实践，三支一扶是 2-3 年人社部项目，特岗教师是 3 年教育部项目。本人报考的是西部计划，志愿赴西部基层服务 1 年。",
    "触发本人报考西部计划的，是 2023 年暑期到四川省凉山州西昌市安宁镇中心小学支教时结识的一位彝族女孩阿依。阿依家在大凉山腹地，每天走 2 小时山路到镇中心校上学，她说她的梦想是'考上大学回村当老师'。这一刻让本人深刻理解了'用一年时间做一件终生难忘的事'这句话的分量，也坚定了本人报考西部计划教育服务专项的志向。",
    "本人生于四川、长于四川，对凉山有天然的情感认同。在校期间两次到凉山州参加社会实践，亲眼看到凉山州师生比 1:25（低于全国平均 1:16）、普通话普及率不足 60% 的现状。本人愿用 1 年时间扎根西昌市某乡镇小学，从一名普通语文教师做起，为凉山教育事业发展贡献力量。"
  ],

  "abilities": [
    "（政治素质）本人政治面貌为中共党员，2023 年 6 月入团，推荐人为辅导员李老师与班主任王老师。在校期间认真学习党的理论，研读《习近平与大学生朋友们》《习近平的七年知青岁月》等著作，完成'青年大学习'52 期，撰写阶段汇报 6 篇。曾任院学生党支部宣传委员，组织主题党日活动 8 次，培养了对党忠诚、服务人民的信念。",
    "（专业能力）本人在校期间学业成绩 GPA 3.6/4.0，排名专业前 15%（8/52）。已取得高级中学教师资格证（语文）、普通话二级甲等证书，具备从事中小学语文教学的能力。曾获 2024 年国家奖学金、2023 年校级一等奖学金、2024 年'挑战杯'省级一等奖，专业能力与所报教育服务专项匹配度高。",
    "（实践经历）本人在校期间担任院学生会主席 1 年，组织迎新晚会、运动会等大型活动 12 次，覆盖同学 1500 人次。注册志愿者编号 SC5101234567890，累计志愿服务时长 280 小时，参与 2023 年暑期凉山支教（21 天，教学 60 课时）、2024 年社区防疫志愿服务（48 小时）等典型项目。曾于 2024 年 7-8 月在 XX 师范大学附属中学实习 2 个月，承担初二语文教学 30 课时，积累了实际教学经验。",
    "（身心素质）本人 2025 年 3 月校医院体检合格，无重大疾病史，国家学生体质健康标准良好。心理测评结论良好。曾独立骑行 318 国道（成都—拉萨，21 天），具备较强的抗压能力与跨文化适应能力。生活自理能力强，能适应西部基层生活条件。"
  ],

  "service_preference_detail": [
    "（专项选择）本人志愿报考西部计划教育服务专项。选择该专项的原因有三：一是所学专业汉语言文学（师范）与教育服务专项高度匹配；二是本人已取得高级中学教师资格证（语文）与普通话二级甲等证书，具备从事中小学语文教学的能力；三是四川省 2024 年该项目办招募教育服务专项志愿者 280 名，缺口 80 名，需求量大。本人第二志愿为青年工作专项（曾任院学生党支部宣传委员），可服从调剂。",
    "（服务地选择）本人意向服务地为四川省凉山彝族自治州。选择该地的原因有二：一是本人生于四川、长于四川，对凉山有天然的情感认同，且 2023 年暑期曾在凉山州西昌市安宁镇中心小学支教，建立了感情连接；二是凉山州是国家乡村振兴重点帮扶县集中区域，2024 年该州招募教育服务专项志愿者 60 名，重点分布在西昌市、昭觉县、布拖县等 7 个县（市）。本人服从服务地调剂，愿意赴国家乡村振兴重点帮扶县服务。",
    "（服务年限）本人申请服务 1 年。选择 1 年期的原因是本人计划 2026 年服务期满后报考硕士研究生（享受西部计划志愿者考研加分 10 分政策），1 年期已满足政策要求。服务期满后，本人计划报考教育学硕士（学科教学·语文方向），将西部服务经历转化为长期教育事业。"
  ],

  "family_attitude": [
    "（家人态度）本人于 2025 年 3 月向家人正式告知报考西部计划的决定。父母初始反应是担忧本人安全与未来出路。经过 3 次深入沟通，家人从担忧转为支持。父亲表示：'西部计划是国家项目，我们支持你的选择，但要照顾好自己。'母亲表示：'家里有我们，你安心服务。'家人最终态度为支持，已签署家长知情同意书。具体顾虑化解：（1）父亲担忧本人安全，本人向父亲展示了西部计划志愿者保险条款（保额 50 万元）与服务地住宿条件后，父亲态度转为支持；（2）母亲担忧本人未来出路，本人向母亲说明西部计划服务期满后享受考研加分、考公定向、学费代偿等政策，母亲表示理解。",
    "（决心表态）本人郑重表态：志愿赴四川凉山基层服务 1 年，服务期间服从组织安排，遵守志愿者管理办法，完成本职工作，不擅自离岗，不挑拣岗位。本人将以'用一年时间做一件终生难忘的事'为座右铭，扎根凉山、服务基层，把青春奉献给祖国最需要的地方，让西部服务经历成为人生最宝贵的财富。"
  ],

  "version": "standard",
  "include_signature": true,
  "tuancentral_doc_cited": [
    "《2025 年大学生志愿服务西部计划实施方案》",
    "《关于做好 2025 年大学生志愿服务西部计划工作的通知》"
  ]
}
```

#### §11.2.2 字段约束

| 字段 | 类型 | 必填 | 约束 |
|------|------|------|------|
| applicant_name | str | P0 | 申请人姓名 |
| applicant_gender | str | P0 | 性别（男/女） |
| applicant_ethnicity | str | P0 | 民族（如汉族） |
| applicant_birth | str | P0 | 出生年月 |
| applicant_political | str | P0 | 政治面貌（中共党员/共青团员/群众） |
| applicant_native_place | str | P0 | 籍贯（省+市+县） |
| applicant_id | str | P0 | 学号 |
| applicant_major | str | P0 | 专业年级 |
| applicant_grade | str | P0 | 年级（如 2022 级） |
| applicant_school | str | P0 | 学校全称 |
| applicant_degree | str | P0 | 学历层次（本科应届毕业/硕士应届毕业/博士应届毕业/在读硕士/在读博士） |
| applicant_graduation | str | P0 | 预计毕业时间 |
| applicant_phone | str | P0 | 联系电话 |
| applicant_email | str | P1 | 邮箱 |
| apply_year | str | P0 | 申请年份（如 2025） |
| service_preference | str | P0 | 8 专项之一：education_service / health_service / agritech_service / rural_revitalization / youth_work / grassroots_governance / rural_construction / youth_league_work |
| second_preference | str | P1 | 第二志愿专项（8 专项之一或空） |
| service_years | int | P0 | 服务年限（1/2/3） |
| service_region_preference | str | P0 | 意向服务省（区、市） |
| accept_redeployment | bool | P0 | 是否服从调剂 |
| academic_rank | str | P0 | 学业排名 |
| gpa | str | P0 | GPA |
| core_courses | str | P1 | 核心课程成绩 |
| certificates | list[str] | P0 | 资格证书列表（教育专项须含教师资格证） |
| honors | list[str] | P1 | 荣誉列表 |
| publications | list[str] | P2 | 论文列表 |
| competitions | list[str] | P1 | 竞赛获奖列表 |
| political_detail | str | P0 | 政治素质详情（党员/团员/群众必写） |
| practice_experience | list[dict] | P0 | 实践经历列表（每项含 role/period/work/result） |
| volunteer_id | str | P1 | 注册志愿者编号 |
| volunteer_hours | int | P1 | 累计志愿服务时长（小时） |
| physical_check | str | P0 | 体检结论 |
| physical_test | str | P0 | 体测达标情况 |
| psychological_test | str | P0 | 心理测评结论 |
| adaptability | str | P0 | 适应能力（具体事例） |
| motivation | list[str] | P0 | 报考动机 3 段（政策认知+个人志向+服务地情感） |
| abilities | list[str] | P0 | 能力素质 4 子段（政治+专业+实践+身心） |
| service_preference_detail | list[str] | P0 | 服务岗位意愿 3 子段（专项+服务地+年限） |
| family_attitude | list[str] | P0 | 家人态度 2 子段（态度+决心） |
| version | str | P1 | 字数版本：compact / standard / full |
| include_signature | bool | P1 | 是否生成签字栏（默认 true） |
| tuancentral_doc_cited | list[str] | P0 | 引用的团中央文件列表（至少 1 项） |

#### §11.2.3 service_preference 8 专项取值对照

| 取值 | 专项全称 |
|------|----------|
| education_service | 教育服务专项 |
| health_service | 卫生服务专项 |
| agritech_service | 农技推广专项 |
| rural_revitalization | 乡村振兴专项 |
| youth_work | 青年工作专项 |
| grassroots_governance | 基层社会治理专项 |
| rural_construction | 乡村建设专项 |
| youth_league_work | 共青团工作专项 |

### §11.3 输出路径与命名

默认输出到当前目录。建议命名规则：`西部计划_{申请人姓名}_{申请年份}.docx`，如 `西部计划_张三_2025.docx`。

### §11.4 build.py 字段消费规则

build.py 按以下规则消费 JSON 字段：

1. **封面（_add_cover）**：使用 applicant_name / applicant_school / applicant_major / service_preference（自动转换为中文全称）/ service_region_preference / apply_year
2. **个人基本情况（_add_basic_info）**：使用 applicant_* 全部字段，输出段落 + 基本信息表（11 行 2 列）
3. **报考动机（_add_motivation）**：使用 motivation 列表，每元素一段；引用文件单独列示
4. **能力素质（_add_abilities）**：使用 abilities 列表（4 子段）+ 政治素质详情
5. **服务岗位意愿（_add_service_preference）**：使用 service_preference_detail 列表（3 子段）+ 8 专项对照表
6. **家人态度与决心（_add_family_attitude）**：使用 family_attitude 列表（2 子段）
7. **签字栏（_add_signature_section）**：申请人签字 + 日期 + 学校项目办审核 + 省项目办审核

---


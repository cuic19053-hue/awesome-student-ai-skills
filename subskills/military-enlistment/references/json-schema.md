# §11 docx 生成调用规范与 JSON Schema

> 从 `subskills/military-enlistment/SKILL.md` 外移而来（渐进式披露）。
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
  "applicant_birth": "2003 年 5 月",
  "applicant_political": "中共党员",
  "applicant_native_place": "四川省成都市武侯区",
  "applicant_id": "2022012345",
  "applicant_major": "计算机科学与技术",
  "applicant_grade": "2022 级",
  "applicant_school": "XX 大学计算机学院",
  "applicant_degree": "本科在读",
  "applicant_graduation": "2026 年 6 月",
  "applicant_phone": "138XXXXXXXX",
  "applicant_email": "zhangsan@example.com",

  "apply_year": "2025",
  "enlistment_type": "在校生入伍",
  "age": 22,
  "height_cm": 175,
  "weight_kg": 68,
  "left_eye_vision": "4.8",
  "right_eye_vision": "4.9",
  "physical_exam": "2025 年 2 月成都市武侯区人民医院征兵体检合格（身高 175cm，体重 68kg，左眼裸眼视力 4.8，右眼裸眼视力 4.9，无重大疾病史）",
  "political_review": "2025 年 2 月成都市武侯区公安分局政治考核合格（本人及家庭主要成员无违法犯罪记录）",

  "academic_rank": "专业前 15%（8/52）",
  "gpa": "3.6/4.0",
  "core_courses": "数据结构 92 / 操作系统 89 / 计算机网络 95 / 数据库 88",
  "certificates": ["CET-6", "计算机二级（C 语言）", "全国计算机等级三级（网络技术）"],
  "honors": ["2024 年国家奖学金", "2023 年校级一等奖学金", "校级优秀学生干部"],
  "publications": [],
  "competitions": ["2024 年挑战杯省级一等奖", "2023 年蓝桥杯省级二等奖"],

  "political_detail": "2023 年 6 月加入中国共产党，推荐人为辅导员李老师与班主任王老师。在校期间认真学习党的理论，研读《习近平与大学生朋友们》《习近平的七年知青岁月》等著作，完成'青年大学习'52 期，撰写阶段汇报 6 篇。曾任院学生党支部宣传委员，组织主题党日活动 8 次。",

  "physical_test": "国家学生体质健康标准良好",
  "physical_fitness": {
    "run_1000m": "3 分 45 秒",
    "pull_up": "12 个",
    "standing_long_jump": "2.45 米"
  },

  "motivation": [
    "（爱国情怀）本人认真学习了《中华人民共和国兵役法》《征兵工作条例》《应征公民体格检查标准》等法律法规与《2025 年大学生应征入伍优惠政策》。本人深刻认识到，依照法律服兵役和参加民兵组织是中华人民共和国公民的光荣义务，是保家卫国的神圣职责。本人理解应征入伍是党中央、国务院、中央军委推进国防和军队现代化建设的重要举措，是优化兵员结构、提升部队战斗力的重要途径。本人愿以青春之我，护卫盛世之中华。",
    "（责任担当）触发本人应征入伍决心的，是 2020 年 6 月中印加勒万河谷冲突中陈红军、陈祥榕、肖思远、王焯冉等烈士的英勇事迹。陈祥榕烈士牺牲时年仅 19 岁，他在战斗前写下的'清澈的爱，只为中国'八字战斗宣言深深震撼了本人。'国家兴亡，匹夫有责'，本人作为新时代大学生，理应接过烈士的钢枪，到祖国最需要的地方去。",
    "（个人成长）本人理解，部队是一座大熔炉、一所大学校。两年义务兵役将塑造本人严明的纪律性、坚韧的意志力、强烈的责任感和过硬的抗压能力。本人深知'当兵后悔两年，不当兵后悔一辈子'这句话的分量——两年军旅生涯将成为本人一生最宝贵的财富，远胜任何奖学金与实习经历。",
    "（职业规划）本人服役期满后的初步规划是退役复学完成本科学业，随后报考硕士研究生（享受退役大学生士兵专项研究生招生计划与考研加 10 分政策）。本人已了解大学生入伍优待政策：本人在校期间学费将获得每年最高 16000 元的补偿代偿；退役复学后可申请转专业；享受专升本免试、考研加分、专项研究生计划、考公定向等政策。本人将以军旅生涯为起点，将军人精神带入未来职业，无论身在何处，都以'退伍不褪色'的标准要求自己。"
  ],

  "abilities": [
    "（政治素质）本人政治面貌为中共党员，2023 年 6 月入团，推荐人为辅导员李老师与班主任王老师。在校期间认真学习党的理论，研读《习近平与大学生朋友们》《习近平的七年知青岁月》等著作，完成'青年大学习'52 期，撰写阶段汇报 6 篇。曾任院学生党支部宣传委员，组织主题党日活动 8 次，培养了对党忠诚、服务人民的信念。本人政治立场坚定，拥护党的领导，自觉抵制各种错误思潮。",
    "（专业能力）本人在校期间学业成绩 GPA 3.6/4.0，排名专业前 15%（8/52）。已通过 CET-6、计算机二级（C 语言）、全国计算机等级三级（网络技术），具备扎实的计算机理论基础与编程能力。所学专业计算机科学与技术与通信兵、电子对抗兵、网络空间部队等兵种高度匹配，可发挥专业特长服务部队信息化建设。",
    "（身体素质）本人 2025 年 2 月参加成都市武侯区人民医院征兵体检，结论为合格（身高 175cm，体重 68kg，左眼裸眼视力 4.8，右眼裸眼视力 4.9，无重大疾病史）。国家学生体质健康标准良好。1000 米跑 3 分 45 秒，引体向上 12 个，立定跳远 2.45 米，体能基础良好，能适应部队高强度训练。校级心理测评结论良好。"
  ],

  "military_adaptability": [
    "（纪律性）本人在校期间严格遵守校规校纪，无任何违纪记录，出勤率 100%，诚信考试无作弊。本人理解部队纪律是战斗力的根本保证，包括条令条例、内务管理、请示报告等。本人已通过早起作息训练（连续 100 天 6 点起床）、自律打卡（连续 200 天运动）为适应部队纪律做好充分准备，能够在服从命令、听从指挥方面做到不打折扣、不搞变通。",
    "（集体生活适应能力）本人大学三年住宿生活和谐，曾担任宿舍长 2 年，组织宿舍卫生评比、节庆活动等。在校 ACM 算法社团担任技术副部长 1 年，与不同性格同学协作完成 3 个开源项目。本人理解部队是高度集体化的组织，本人将与战友同吃同住同训练，做到团结友爱、互帮互助、共同进步。",
    "（抗压能力）本人在校期间曾同时承担学业、学生工作、志愿服务三线任务（期末备考 + 学生会换届 + 凉山支教），均圆满完成，体现较强抗压能力。本人 2024 年 9 月参加校级心理测评，结论为良好。本人已通过长跑训练（累计 500 公里）、户外拉练（318 国道骑行 21 天）增强体能储备，通过心理建设提升抗压能力，能够适应部队高强度训练与突发任务。"
  ],

  "family_attitude": [
    "（家人态度）本人于 2025 年 1 月向家人正式告知应征入伍的决定。父母初始反应是担忧本人安全与未来出路。经过 3 次深入沟通，家人从担忧转为支持。父亲表示：'保家卫国是男子汉的本分，我们支持你的选择，但要照顾好自己。'母亲表示：'家里有我们，你安心服役。'家人最终态度为支持，已签署家长知情同意书。具体顾虑化解：（1）父亲担忧本人安全，本人向父亲展示了部队保险条款与军人优待政策后，父亲态度转为支持；（2）母亲担忧本人未来出路，本人向母亲说明入伍保留学籍、学费补偿、考研加分等政策，母亲表示理解。",
    "（决心表态）本人郑重表态：志愿应征入伍服 2 年义务兵役，服役期间服从命令、听从指挥、严守纪律、刻苦训练，以优异成绩完成各项任务。本人将以'清澈的爱，只为中国'为座右铭，到祖国最需要的地方去，把青春奉献给国防事业。退伍后无论从事何种职业，都将以'退伍不褪色'的标准要求自己，将军人精神融入血脉。"
  ],

  "version": "standard",
  "include_signature": true,
  "military_doc_cited": [
    "《中华人民共和国兵役法》（2021 年修订）",
    "《征兵工作条例》（2023 年修订）",
    "《2025 年大学生应征入伍优惠政策》"
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
| applicant_degree | str | P0 | 学历层次（本科在读/硕士在读/本科应届毕业/硕士应届毕业/博士应届毕业） |
| applicant_graduation | str | P0 | 预计毕业时间 |
| applicant_phone | str | P0 | 联系电话 |
| applicant_email | str | P1 | 邮箱 |
| apply_year | str | P0 | 申请年份（如 2025） |
| enlistment_type | str | P0 | 入伍类型（在校生入伍/毕业生入伍） |
| age | int | P0 | 年龄（18-24 周岁） |
| height_cm | int/float | P0 | 身高（男 ≥ 160，女 ≥ 158） |
| weight_kg | int/float | P0 | 体重 |
| left_eye_vision | str | P0 | 左眼裸眼视力（陆勤 ≥ 4.5） |
| right_eye_vision | str | P0 | 右眼裸眼视力（陆勤 ≥ 4.6） |
| physical_exam | str | P0 | 体检结论（征兵办指定医院） |
| political_review | str | P0 | 政审结论（县级征兵办政治考核组） |
| academic_rank | str | P0 | 学业排名 |
| gpa | str | P0 | GPA |
| core_courses | str | P1 | 核心课程成绩 |
| certificates | list[str] | P0 | 资格证书列表 |
| honors | list[str] | P1 | 荣誉列表 |
| publications | list[str] | P2 | 论文列表 |
| competitions | list[str] | P1 | 竞赛获奖列表 |
| political_detail | str | P0 | 政治素质详情（党员/团员/群众必写） |
| physical_test | str | P0 | 体测达标情况 |
| physical_fitness | dict | P1 | 体能成绩（run_1000m/pull_up/standing_long_jump） |
| motivation | list[str] | P0 | 入伍动机 4 段（爱国情怀+责任担当+个人成长+职业规划） |
| abilities | list[str] | P0 | 个人素质 3 子段（政治+专业+身体） |
| military_adaptability | list[str] | P0 | 部队适应能力 3 子段（纪律+集体+抗压） |
| family_attitude | list[str] | P0 | 家人态度 2 子段（态度+决心） |
| version | str | P1 | 字数版本：compact / standard / full |
| include_signature | bool | P1 | 是否生成签字栏（默认 true） |
| military_doc_cited | list[str] | P0 | 引用的征兵政策文件列表（至少 1 项） |

#### §11.2.3 enlistment_type 取值对照

| 取值 | 含义 | 适用人群 |
|------|------|----------|
| 在校生入伍 | 在校生应征入伍（保留学籍） | 普通高校在校本专科生、研究生 |
| 毕业生入伍 | 应届毕业生应征入伍 | 普通高校应届本专科毕业生、研究生 |

### §11.3 输出路径与命名

默认输出到当前目录。建议命名规则：`应征入伍_{申请人姓名}_{申请年份}.docx`，如 `应征入伍_张三_2025.docx`。

### §11.4 build.py 字段消费规则

build.py 按以下规则消费 JSON 字段：

1. **封面（_add_cover）**：使用 applicant_name / applicant_school / applicant_major / enlistment_type / apply_year
2. **个人基本情况（_add_basic_info）**：使用 applicant_* 全部字段 + age/height_cm/weight_kg/left_eye_vision/right_eye_vision/physical_exam/political_review，输出段落 + 基本信息表 + 体检政审表
3. **入伍动机（_add_motivation）**：使用 motivation 列表，每元素一段；引用文件单独列示
4. **个人素质（_add_abilities）**：使用 abilities 列表（3 子段）+ 政治素质详情
5. **部队适应能力（_add_military_adaptability）**：使用 military_adaptability 列表（3 子段）
6. **家人态度与决心（_add_family_attitude）**：使用 family_attitude 列表（2 子段）
7. **签字栏（_add_signature_section）**：申请人签字 + 日期 + 学校武装部审核 + 县级征兵办审核

---


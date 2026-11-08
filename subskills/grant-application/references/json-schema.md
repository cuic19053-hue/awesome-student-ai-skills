# §9 JSON Schema 完整字段

> 从 `subskills/grant-application/SKILL.md` 外移而来（渐进式披露）。
> 何时阅读：构造 --data 输入文件、或 build.py 报字段校验错误时。

### §9.1 Schema 总览

```jsonc
{
  // ===== 基础信息 =====
  "name": "张三",                          // 必填，学生姓名
  "gender": "男",                          // 必填，男/女
  "ethnicity": "汉族",                     // 选填，民族
  "college": "计算机科学与技术学院",         // 必填，学院全称
  "major": "计算机科学与技术",              // 必填，专业全称
  "grade": "2024 级 大一",                 // 必填，年级（含"大一"等标识）
  "class_name": "计科 2401 班",            // 选填，班级
  "student_id": "2024010101",              // 必填，学号
  "political_status": "共青团员",          // 必填，政治面貌
  "phone": "138XXXXXXXX",                 // 选填，联系电话

  // ===== 申请信息 =====
  "apply_year": "2024-2025 学年",          // 必填，申请学年
  "apply_date": "2024 年 9 月 20 日",      // 必填，申请日期（建议 9.1~9.30）
  "grant_level": "一等",                   // 必填，助学金档次（一等/二等/三等）
  "grant_amount": 4400,                    // 自动推算（一等4400/二等3300/三等2200）
  "difficulty_level": "特别困难",          // 必填，困难认定等级
  "difficulty_cert_no": "GZ2024-00123",   // 必填，认定编号/建档立卡号/低保号
  "poverty_category": "建档立卡",          // 必填，6类困难之一

  // ===== 家庭经济子结构（核心段数据）=====
  "family_situation": {
    "family_size": 5,                      // 必填，家庭常住人口数
    "college_students": 2,                 // 必填，在校大学生数
    "elderly_count": 1,                    // 选填，需赡养老人数
    "hometown": "XX 省 XX 县农村家庭",     // 必填，家庭住址
    "zip_code": "XXXXXX",                  // 选填，邮政编码
    "father_name": "张 XX",                // 必填，父亲姓名
    "father_job": "XX 县 XX 厂下岗工人",   // 必填，父亲职业
    "father_income_detail": "下岗失业，打零工月收入约 1800 元",  // 必填
    "mother_name": "李 XX",                // 必填，母亲姓名
    "mother_job": "在家务农 + 镇上家政",   // 必填，母亲职业
    "mother_income_detail": "种植玉米 3 亩年产值 4500 元 + 家政月收入 1200 元",  // 必填
    "income_source": "父亲打零工 + 母亲务农与家政",  // 必填，收入来源汇总
    "family_income_year": 41000,           // 必填，家庭年总收入（元）
    "per_capita_year": 8200,               // 自动推算 = family_income_year / family_size
    "per_capita_month": 680,               // 自动推算 = per_capita_year / 12
    "local_min_living": 750,               // 必填，当地最低生活保障标准（元/月）
    "school_line": 400,                    // 必填，学校对应档次认定线（元/月）
    "large_expenses": "2024.03 祖父确诊肺癌自付医疗费 4.5 万元；2024.09 妹妹考入大学学费 6000 元/年",  // 必填
    "debt_total": 68000,                   // 选填，家庭债务总额（元）
    "debt_relative": 48000,                // 选填，亲戚借款（元）
    "debt_loan": 20000,                    // 选填，助学贷款（元）
    "debt_bank": 0,                        // 选填，银行贷款（元）
    "debt_reason": "支付医疗费与两人学费"  // 选填，借贷原因
  },

  // ===== 家庭成员表（5 列）=====
  "family_members": [
    {"name": "张 XX", "relation": "父亲", "job": "XX 县下岗工人", "income": 21600, "political": "群众"},
    {"name": "李 XX", "relation": "母亲", "job": "在家务农 + 家政", "income": 18000, "political": "群众"},
    {"name": "张 X",  "relation": "妹妹", "job": "XX 大学在读", "income": 0, "political": "共青团员"},
    {"name": "王 XX", "relation": "祖父", "job": "在家休养（肺癌术后）", "income": 0, "political": "群众"},
    {"name": "张三",  "relation": "本人", "job": "XX 大学大一", "income": 0, "political": "共青团员"}
  ],

  // ===== 勤工助学表（4 列）=====
  "work_study": [
    {"position": "图书馆管理员", "place": "学校图书馆", "duration": "2024.09~至今 每周 8 小时", "monthly_income": 400},
    {"position": "食堂帮厨", "place": "学校一食堂", "duration": "2024.10~2024.12 每周 6 小时", "monthly_income": 600},
    {"position": "家教（高中数学）", "place": "学生家中", "duration": "2024.03~2024.07 每周 4 小时", "monthly_income": 600}
  ],

  // ===== 在校表现 =====
  "study_situation": "本学年必修课全部及格，主干课平均成绩 82 分，CET-4 510 分",
  "gpa": "3.20/4.0",                       // 选填（助学金不要求，建议简述或不写）
  "rank": "30/120",                        // 选填（助学金不要求，建议不写）
  "rank_total": "120",                     // 选填
  "course_failed": "无",                   // 选填，"无"/"X门必修课不及格"
  "ideology": "拥护党的领导，2024.10 列为优秀团员/积极分子",
  "party_history": "学院分党校第 38 期培训班结业",
  "position": "班级学习委员",
  "position_work": "组织 5 次学习经验交流会",
  "volunteer_hours": 50,
  "volunteer_detail": "敬老院慰问 3 次、三下乡 1 次",
  "lifestyle": "月伙食费 800 元以内，教材通过二手或图书馆获取",
  "dorm_role": "宿舍长",
  "dorm_honor": "文明宿舍",

  // ===== 申请理由与感恩表态 =====
  "tuition": 6000,                         // 必填，学费（元/年）
  "textbook_fee": 800,                     // 选填，教材费（元/年）
  "monthly_food": 800,                     // 选填，月伙食费（元）
  "loan_amount": 8000,                     // 选填，助学贷款（元/年）
  "monthly_income": 1600,                  // 选填，勤工助学月收入（元）

  // ===== 输出控制 =====
  "material_type": "B",                    // 默认 B（A/A+B/B）
  "word_count_version": "1200",            // 默认 1200（800/1200/1500）
  "salutation": "尊敬的学院领导、评审委员会：",
  "opening": "",                           // 留空则按 §7.1 模板生成
  "ending": "",                            // 留空则按 §7.5 模板生成
  "apply_date": "2024-09-20"
}
```

### §9.2 字段填写完整度校验

| 字段类别 | 必填字段数 | 建议填字段数 | 校验规则 |
|---|---|---|---|
| 基础信息 | 8（name/gender/college/major/grade/student_id/political_status/apply_year） | 11 | 任一缺失 build.py 报警告 |
| 申请信息 | 5（grant_level/grant_amount/difficulty_level/difficulty_cert_no/poverty_category） | 6 | grant_level 必须与 difficulty_level 对应 |
| 家庭经济 | 5（family_situation.family_size/income_source/family_income_year/local_min_living/large_expenses） | 12 | family_situation 子结构必须完整 |
| 家庭成员表 | 3（每人含 name/relation/job/income/political 5 列） | 5 | 至少 3 人（父母+本人） |
| 勤工助学 | 2（每项含 position/place/duration/monthly_income 4 列） | 3 | 至少 1 项，建议 2~3 项 |
| 在校表现 | 3（study_situation/ideology/position） | 8 | 影响 §5.4 段三字数 |
| 输出控制 | 3（material_type/word_count_version/apply_date） | 5 | material_type 默认 "B"，word_count_version 默认 "1200" |

### §9.3 grant_level 与 difficulty_level 对应关系

| grant_level | grant_amount（元/年） | difficulty_level | 备注 |
|---|---|---|---|
| 一等 | 4400 | 特别困难 | 严格对应，跨档申请材料退回 |
| 二等 | 3300 | 困难 | 严格对应 |
| 三等 | 2200 | 一般困难 | 严格对应 |

---


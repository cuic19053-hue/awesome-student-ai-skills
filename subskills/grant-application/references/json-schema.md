# 国家助学金申请书：输入字段

构造 build.py 输入时读取。本结构是空白采集表，不是学生事实；金额、学年与困难认定结果须按学生提供的信息填写。未知值用 null/空字符串，不按档次或困难程度推算。

```json
{
  "name": "",
  "college": "",
  "major": "",
  "grade": "",
  "student_id": "",
  "class_name": "",
  "apply_year": "",
  "apply_date": "",
  "grant_level": "",
  "grant_amount": null,
  "difficulty_level": "",
  "difficulty_cert_no": "",
  "poverty_category": "",
  "family_situation": {
    "family_size": null,
    "college_students": null,
    "elderly_count": null,
    "income_source": "",
    "family_income_year": null,
    "local_min_living": null,
    "school_line": null,
    "large_expenses": "",
    "debt_total": null,
    "debt_reason": ""
  },
  "family_members": [],
  "work_study": [],
  "study_situation": "",
  "position_work": "",
  "volunteer_detail": "",
  "application_reason": "",
  "word_count_version": "1200",
  "salutation": "尊敬的学校资助工作负责老师："
}
```

family_members 有实际需要时填写 name/relation/job/income/political；work_study 只填写已提供的 position/place/duration/monthly_income，没有经历保持空数组。已有审阅正文可用 opening/family_economy/study_situation/application_reason/gratitude。不要把结构中的键名当作全部必须公开填写的要求。

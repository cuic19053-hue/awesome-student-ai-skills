# 国家助学金申请书：构建与核对
执行仓库构建器时读取；写作和政策边界以父目录 SKILL.md 为准。

```bash
python subskills/grant-application/build.py --data data.json --out application-draft.docx
```

可选 --school 使用仓库已收录的通用版式；它不证明是学校当年正式模板。word_count_version 的 800/1200/1500 是写作篇幅选项，不是全国统一最低字数。

- grant_amount 仅采用显式提供的有限正数；null、缺项或非法值显示待核对，不按grant_level计算。
- compute_grant_amount 是历史兼容函数，返回0表示未知，不能把0当真实资助金额。
- apply_year 缺少时留申请学年待补充，不默认往年。
- difficulty_level 与 grant_level 的关系、金额、证明材料和困难认定线由学校确定。
- family_economy、study_situation、application_reason 等可传已审阅的段落；自定义正文中的事实和金额仍需人工核对。
- 不提供父母姓名也可写已提供的income_source；不提供收入就不写收入数值。
- 不提供学习情况不写全部及格，work_study空数组不补勤工经历。
- --demo 是合成排版示例；不得将其人物、家庭及经历当作申报人的事实。
- 下载前核对实际Word的学校栏目、正文、表格、金额、学年和签名。构建成功不等于正式材料完整或资格合格。

# 示例文档索引（v2.1）

本目录存放各子 skill 的 demo docx 文件，由 `subskills/<skill>/build.py --demo --out <path>` 自动生成。
所有 demo 均使用各子 skill 内置的示例数据，可直接打开预览效果，无需用户填写任何信息。

## 文档清单（10 个）

| 序号 | 文件名 | 子 skill | 类型 | 说明 |
|------|--------|----------|------|------|
| 1 | `demo_national_project_eval.docx` | 国家奖学金申请书 | 奖学金 | 8000 元国奖，前 10% GPA |
| 2 | `demo_challenge_cup.docx` | 申请材料 | 政治 | 4000 字，含入团志愿+认识+经历+不足 |
| 3 | `demo_challenge_cup.docx` | 挑战杯作品申报书 | 竞赛 | 自然科学类学术论文 |
| 4 | `demo_internet_plus.docx` | 互联网+商业计划书 | 竞赛 | 创业大赛，2025 新评审维度 |
| 5 | `demo_innovation_research.docx` | 大创创新训练 | 科研 | 国家级，研究报告/论文产出 |
| 6 | `demo_outstanding_graduate.docx` | 优秀毕业生申请书 | 评优 | 省级+校级，四年综合表现 |
| 7 | `demo_college_research.docx` | 院级科研立项 | 科研 | SRTP，含参考文献 |
| 8 | `demo_military_enlistment.docx` | 应征入伍申请书 | 征兵 | 2025 上半年应征 |
| 9 | `demo_csc_scholarship.docx` | CSC 国家公派留学 | 公派 | 联合培养博士研究生 |
| 10 | `demo_entrepreneurship_training.docx` | 大创创业训练（v2.1） | 科研 | 消防无人机项目，对齐案例 2 |

## 使用方式

### 1. 直接打开预览

```bash
# macOS
open demo_national_project_eval.docx

# Linux
xdg-open demo_national_project_eval.docx

# Windows
start demo_national_project_eval.docx
```

### 2. 用真实数据重新生成

```bash
# 准备 data.json（字段定义见各 subskills/<skill>/SKILL.md）
python3 subskills/national_project_eval/build.py --data my_data.json --out my_output.docx
```

### 3. 导出为 PDF

```bash
# 使用 utils/pdf_export.py（依赖 libreoffice）
python3 utils/pdf_export.py --input demo_national_project_eval.docx --output demo_national_project_eval.pdf
```

## 重新生成全部 demo

```bash
cd /home/z/my-project/skills/awesome-student-ai-skills/subskills
for skill in national_project_eval youth_league_application challenge_cup internet_plus innovation_research outstanding_graduate college_research military_enlistment csc_scholarship entrepreneurship_training; do
  python3 "$skill/build.py" --demo --out "../examples/demos/demo_${skill}.docx"
done
```

## v2.1 重点演示：entrepreneurship_training

`demo_entrepreneurship_training.docx` 是 v2.1 的核心展示样本，对齐真实案例 2（姚奕晗消防无人机创业训练项目）：

- ✅ 总段落 402，含 18 张表格
- ✅ 政策引用 10+ 条（含 4 要素：标题/文号/条款/对项目的指导意义）
- ✅ 文献综述 31 篇（英文 22 篇，占比 71%）
- ✅ 算法对比表 1 张（3 算法 × 3 维度）
- ✅ 技术路线图 3 张
- ✅ 数学公式 6 个（含编号+变量定义）
- ✅ 经济效益表 12 项 × 4 列
- ✅ 4P 营销 + 3C 定价 + SWOT 分析
- ✅ 5 年三表 10 张（销售/成本/管理费/销售费/现金流/NPV/盈利/资产负债/短/长期偿债）
- ✅ 实践过程 7 张照片描述 + 4 家合作协议
- ✅ 技术壁垒 4 项专利 + 2 份检测报告 + 2 张实物验证
- ✅ 4 阶段甘特图（调研设计/硬件算法/集成验证/总结结题）

# 八、build.py 接口说明

> 从 `subskills/entrepreneurship-training/SKILL.md` 外移而来（渐进式披露）。
> 何时阅读：需要调用 build.py 或了解接口参数时。

### 8.1 命令行调用

```bash
# 使用自定义数据
python build.py --data data.json --out output.docx

# 使用内置 demo（消防无人机创业训练，对齐案例 2）
python build.py --demo --out demo.docx

# 指定字数版本（影响 placeholder 提示详细度）
python build.py --data data.json --out output.docx --level national   # 国家级
python build.py --data data.json --out output.docx --level provincial # 省级
python build.py --data data.json --out output.docx --level school     # 校级
```

### 8.2 输出文档结构（11 大章）

调用 `builder.build(data, output_path)` 后生成的 docx 包含以下章节：

1. **封面**（项目名称、负责人、指导教师、学院、申报日期）
2. **一、基本信息**（9 行 2 列表格）
3. **二、项目简介与优势**（200 字简介 + 10 条优势）
4. **三、立项依据**（3.1 国家政策 10+、3.2 科学挑战 3 段、3.3 文献综述 30+）
5. **四、研究内容与目标**（硬件基础 2 类、研究内容 3 部分、研究目标 3 个、关键科学问题 3 个）
6. **五、研究方案**（算法对比表、技术路线图 3 张、数学公式 4 个、创新点 3 条）
7. **六、社会经济效益**（12 项量化指标 + 社会效益 3 维 + 政治战略 3 维）
8. **七、市场分析**（5 小节 + SWOT）
9. **八、营销模式**（4P + 3C 定价 + 促销策略 + 供应链 5 子节）
10. **九、财务分析**（5 年三表 10 张 + 资金筹备 + 利润预计 + 风险 + 退出）
11. **十、实践过程与技术壁垒**（7 张照片 + 4 家合作 + 4 项专利 + 检测报告 + 实物验证）
12. **十一、项目进度安排**（4 阶段甘特）
13. **十二、经费预算**
14. **十三、团队与风险**
15. **十四、预期成果**
16. **十五、签字栏**

### 8.3 自定义扩展点

- 自定义章节顺序：修改 `ApplicationDocBuilder.build()` 方法中的章节调用顺序
- 自定义字体/字号：修改文件头部的 `FONT_*` 与 `SIZE_*` 常量
- 自定义表格列宽：在 `add_table()` 调用时传入 `col_widths` 参数
- 自定义页眉页脚：在 `setup_page()` 后调用 `add_page_number()` 或自定义函数

---


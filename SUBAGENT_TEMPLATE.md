# 子智能体任务模板（每个工作子智能体收到的标准任务描述）

## 标准任务接收模板

每个子智能体收到任务时，任务描述包含：
1. Task ID（如 T01）
2. 任务类型（修复/优化/新增/工程化）
3. 工作目录（绝对路径）
4. 必读文件清单
5. 必读 worklog（路径：/home/z/my-project/worklog.md）
6. 完成标准
7. 追加日志要求

## 完成后必须做的事

1. `wc -l` 确认产出文件行数符合预期
2. `python -c "import ast; ast.parse(open('XXX.py').read())"` 验证 Python 语法（如适用）
3. 在 `/home/z/my-project/worklog.md` 末尾**追加**一节，格式如下：

```markdown
---
Task ID: T01
Agent: general-purpose
Task: 修复 national_project_eval build.py

Work Log:
- Read SKILL.md 找出新增字段 material_type/project_level/...
- Read 现有 build.py 了解结构
- 重写 build.py 支持新字段
- 验证语法通过

Stage Summary:
- 产出文件：subskills/national_project_eval/build.py（XXXX 行）
- 新增字段：material_type（A/B/A+B 分流）, project_level, ...
- 兼容性：保留旧字段兼容
```

## 重要约束

- ❌ 禁止覆盖 worklog.md 已有内容
- ❌ 禁止修改其他子智能体负责的目录
- ❌ 禁止生成 README.md 等非任务要求文件
- ✅ 所有路径用绝对路径
- ✅ 所有文件存放在 `/home/z/my-project/skills/awesome-student-ai-skills/` 下

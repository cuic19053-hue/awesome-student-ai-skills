# 大创创新训练图文链路（实现与验收）

## 边界

仅 `innovation-research` 且 `MATERIAL_PIPELINE_ENABLED=true` 接入。默认关闭；
其他材料类型仍走原链路。没有部署 Worker 或应用迁移时，不打开试点。
不改变价格、免费次数、充值规则，不自动付费重绘。真实模型测试另行批准预算。

统一上下文复用项目字段，计划与事实分离；用户确认不等于外部核验。
适用要求顺序：正式要求、用户要求、大创规则、示例、默认。正式要求必须确认范围；
同级冲突不自动选取，上传文件中的指令不能覆盖安全规则。

## 本机测试（不是生产部署）

```sh
uv pip install --python .venv/bin/python -r infra/material-worker/requirements.txt
# 本机 Chromium 可通过 MATERIAL_CHROMIUM_PATH 指定，否则：
.venv/bin/python -m playwright install chromium
MATERIAL_PIPELINE_ENABLED=true MATERIAL_WORKER_READY=true \
  .venv/bin/python -m uvicorn app:app --app-dir server --host 127.0.0.1 --port 8765
# 单独终端，使用与 API 相同的本机数据目录：
MATERIAL_PIPELINE_ENABLED=true .venv/bin/python server/material_worker.py \
  --local-data "$PWD/.agent-data"
```

`--once` 处理一个任务，适合故障注入；不要用本机模式承接线上用户。
仅 SVG/Python 绘图和导出不调用模型；正文、GPT 图在用户确认后才提交。
BYOK 配置加密后保存至任务，需要 API 与 Worker 配置相同的
`USER_CONFIG_ENCRYPTION_KEY`；任务终态清除凭据密文，不保存用户 JWT。

## 云端部署顺序（本次不执行）

1. 按仓库规范先检查 `git status`，保护工作进度，再同步远程；在最新基线测试。
2. 在测试数据库应用 `20261022154243_material_pipeline.sql`。新增项目版本、
   持久任务和不可变章节版本，不迁移钱包、不重置积分或免费次数。
3. 用安全渠道生成专用随机 Worker 密钥；只在数据库管理员会话写入哈希：
   ```sql
   insert into material_private.worker_capability(singleton,secret_hash)
   values(true,sha256(convert_to('<专用随机密钥>','UTF8')))
   on conflict(singleton) do update set secret_hash=excluded.secret_hash;
   ```
   不把真实密钥写入终端历史、仓库或日志；实际通过受控秘密管理操作。
4. 在另行确认的**独立云端资源**构建运行：
   `docker build -f infra/material-worker/Dockerfile -t stardust-material-worker .`。
   不复用其他项目服务器，不使用旧电脑。容器以非 root 运行。
5. Worker 配置 Supabase URL、publishable key、Worker 密钥；
   如需要平台模型，沿用现有平台服务配置和暂停开关；
   如需 BYOK，配置相同的凭据加密密钥。禁止配置 project-wide service-role。
6. Worker 无需用户长期 JWT。仅通过有密钥、租约校验的 RPC 领取任务、记录状态、
   使用该任务的计费额度。原文件和产物通过项目范围的限时签名地址传输。
7. 测试中文字体、Chromium、LibreOffice、下载和签名上传。Noto 字体随 Debian
   授权包安装；可查看 `/usr/share/doc/fonts-noto-cjk/copyright`。
   正式指定字体不能满足时需提示，不能宣称已完全匹配。
8. Vercel 保持当前项目 `stardust-agent` / `sin1`；确认 Worker 能工作再设置
   `MATERIAL_PIPELINE_ENABLED=true`、`MATERIAL_WORKER_READY=true`，灰度启用。
9. 检查真实业务链路：登录、资料确认、要求、计划、图表、导出、预览、计费。
   `/api/health` 通过不代表完整验收。

不修改旧版本历史；开启试点后的云端章节版本使用 `material_revisions`。
关闭开关回到原界面，但数据库和新产物保留。回滚时不能删除新增表、重放模型请求
或重置账本。旧临时任务库中的历史记录不自动删除。

## API

均在 `/api/projects/{project_id}/material` 下，沿用当前用户鉴权：

| 方法 / 子路径 | 用途 |
| --- | --- |
| GET `/` | 上下文、适用要求、图表计划、最近任务、Worker 开关 |
| PUT `/requirements` | `revision, items`，确认要求和范围 |
| POST `/acknowledge` | `revision, snapshot, nodes`，核对当前关联提醒 |
| PUT `/plans` | `revision, items`，受控图表配置，不执行代码 |
| POST `/jobs` | `revision, kind, target, idempotency_key, confirm_paid, llm_config` |
| GET `/jobs/{id}` | 状态与产物元数据，不返回凭据和内部输入 |
| POST `/jobs/{id}/cancel` | 取消后续执行，不承诺退还已发生费用 |
| POST `/jobs/{id}/apply` | 原子提交结果；输入变化则保留备选 |
| POST `/figures/{id}/confirm-text` | 人工核对当前图片场景文字 |
| GET `/jobs/{id}/files/{name}` | 用户授权后下载白名单产物 |

图表类型：`svg`（程序布局）、`python`（结构化数据）、`gpt`（概念场景）、
`overlay`（复用底图加字）。图表配置不接受 HTML、脚本或执行命令。
数据图必须填来源与计划/实测性质。普通文字放独立说明层，不盲目覆盖原图；
复杂透视文字不自动修复，显示待核对；OCR 命中不等于人工确认。

## 任务与安全

任务按项目幂等，活跃同目标互斥。租约 120 秒、心跳 20 秒。
非模型步骤可在租约丢失后重新执行；可能调用模型的任务租约过期进入
`needs_review`，不能自动重发。取消后，后续调用和结果提交必须被拒绝。
单张图最多一次平台图调用，章节维持现有最多三轮撰写/评审（最多六次），
不改变原定价。结果不确定保留原账本核对路径。

输入签名地址有效两小时；超时任务明确失败/待核对，不重复调用模型。
产物 ZIP 限制 100MB、170 项、解压 350MB，只接受平面白名单文件，拒绝路径穿越。
Word 最大自动预览 160 页；超过限制保留草稿，提示拆分人工检查。
Worker 只访问配置的 Supabase 存储源，不跟随签名地址重定向。

## 质量检查与已知边界

使用示例的 A4、页边距、正文层级等规则，不复制针对固定页数手调的空白高度。
图表按章节/块锚点插入，`[[figure:图ID]]` 为插图，`[[ref:图ID]]` 为引用。
没有锚点默认放在所属章节末尾。学校模板使用可识别栏目/占位符；
复杂模板无法可靠映射时保留并显示“适配未完成”，不能冒充完成。

DOCX -> PDF -> 每页 PNG 后检查。静态检查复用现有检查器；
页面几何分析依赖 PyMuPDF；失败/缺工具必须标 `not_checked`，不能算通过。
人工需要最终检查字体替代、复杂重叠、场景文字和学校模板；机器不承诺“绝对完美”。
不为了消除告警删除正文或把字号缩到不可读。学校模板不执行通用硬化，避免破坏版式。

## 测试

```sh
.venv/bin/python -m pytest tests/test_material_pipeline.py tests/test_material_api.py -q
RUN_POSTGRES_POLICY_TESTS=1 .venv/bin/python -m pytest tests/test_material_postgres.py -q
node --check server/static/material.js
node --check server/static/app.js
```

真实 PostgreSQL 测试使用已有镜像的临时容器，无对外端口、不连接生产。
默认全部模型为假模型。部署前必须另行完成容器镜像、Supabase Storage 签名传输、
获准预算内的真实模型与费用验证；这些不由离线测试替代。

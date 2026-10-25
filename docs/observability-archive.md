# 工作台全链路日志与 Mac 归档（v1）

## 边界

业务事实仍来自任务主表、草稿和计费账本。新增的 `observability` 私有 schema
仅存元数据和归档回执，绝不用于重新发起模型调用、退款、扣费或补造历史。
本方案不增加管理员网页，不采集点击、轮询、心跳、逐 token 输出。

- API：请求编号独立于业务追踪编号，认证成功后绑定内部用户编号；错误响应
  `X-Support-ID` 可交给运维，所有响应还有 `X-Request-ID` 和 `X-Trace-ID`。
- 上传：代理只在已验证用户、项目权限或有效签名续传会话后记录创建、完成、失败。
  上传、登记和解析使用同一 `sha256("upload:owner:document")[:32]`。
- 材料任务：提交、数据库状态、Worker 租约验证后的检查点、推理代理和下载使用
  同一 `sha256("job:owner:job")[:32]`。数据库事件不冒充 Worker 执行事实。
- 计费：原有 `usage_request_id` 原样关联预留、结算、待对账和退款；
  数据库触发器只报告实际账本提交，不复制卡密、金额响应或 reference 原文。
- HTTP 返回、模型业务完成、任务持久化分别表示不同事实。
  `download.served` 只表示服务端成功发送响应，不表示文件已写入用户磁盘。

字段固定为 v1 投影，禁止隐式序列化整个任务对象。元数据为 1 KB 白名单，
仅允许 MIME、非负字节/章节/token 计数、billable 和账本类型枚举。
不存正文、文件名、学校、手机号、Key、JWT、卡密、租约、模型配置、签名链接或异常原文。
日志失败只能输出固定错误码 `observability_gap` 和已脱敏事件，不改变业务结果。

## 权限与数据库

迁移：`supabase/migrations/*_observability_events_and_archive.sql`。
默认关闭；所有表启用 RLS，普通账号无直接读写权限。
`public.observability_api` 是 SECURITY INVOKER 包装，窄 SECURITY DEFINER 实现留在非暴露私有 schema，固定 search_path；
它只接受专用随机能力，数据库只保存 SHA-256。能力至少 256 bit 随机熵：

| scope | 允许 | 禁止 |
|---|---|---|
| api | 严格白名单追加 API 事件 | 查询、归档、账本变更 |
| upload | 仅追加 upload 事件 | 其他流程、查询、归档 |
| ops | 查询、固定批次、确认、受限过期清理 | 追加事件、模型、余额、任意删除 |

不要复用管理员、service_role 或 Worker 密钥。Worker 日志使用现有 Worker
能力和当前有效租约，服务端覆盖用户、项目、任务、时间和追踪编号，不返回材料 payload。
日志查询接口 `/api/ops/logs` 使用 Bearer 能力，不使用浏览器用户 JWT。
凭据禁止进入 URL、仓库、shell 历史、命令参数和截图。撤销能力时更新
`observability.capabilities.enabled=false`；轮换时只通过受控部署渠道传输新原文。

容量：300 MB 预警（`archive status`），400 MB 停止普通 info 事件，
450 MB 停止全部入库，回退平台脱敏日志并明确缺口。
生产启用时将事件表预算统一设为 400 MB，不提前停止普通成功事件。
不强删未归档记录，不自动升级套餐。
文件库容量和数据库容量是不同指标；状态命令报告当前数据库及事件表字节数。

## 运维命令

安装后命令的稳定绝对路径是：

```sh
OPS="$HOME/Library/Application Support/StardustOps/stardust-ops"
"$OPS" logs list --since 24h --operation upload
"$OPS" logs list --job-id 合法任务编号 --error-code STORAGE_UNSUPPORTED_MIME
"$OPS" logs trace 合法追踪编号
"$OPS" logs stats --since 7d
"$OPS" logs list --source local
"$OPS" archive status
"$OPS" archive run
"$OPS" archive verify
```

查询按 event_id 去重并按入库时间排序。默认合并云端和本地。
断网时返回已验证本地结果并标记 `coverage_gap`，退出状态非零，
绝不把部分结果声称为完整统计。过去未采集或已过本地保留期的日志不可恢复。

## 归档协议与恢复

1. 数据库事务固定一个批次最多 5,000 条未归档记录；只选择至少两分钟前入库的记录。
   批内分页最多 200 条，不依赖全局递增游标，因此晚提交记录进入下一批。
2. 服务器按 event_id 排序生成固定 v1 NDJSON，LF 结尾，提供 SHA-256 与计数。
3. Mac 检查磁盘至少 1 GiB，获取单实例锁和 Keychain AES-256 密钥。
   gzip 后使用 cryptography AES-256-GCM，每文件独立随机 nonce；
   格式版本、批次、密钥编号、计数和摘要作为认证头。
4. 仅密文写临时文件，fsync、原子替换；重新解密并核对计数、摘要、唯一事件编号，
   然后提交确认回执。恢复、重复确认和“服务器确认后响应丢失”均幂等。
5. **每次云端清理前重新验证所有现有本地归档，并与云端近 180 天已确认批次清单核对**。
   文件被删除、归档目录丢失也会停止，而不只是检测仍存在文件的损坏。只有属于已确认批次、
   且入库超过 30 天的事件能被受限 RPC 清理（每次 1,000 条）。
   账本、任务、用户材料不在删除 SQL 中。
6. 本地保留 180 天，从本地收到归档确认完成回执起算，不从事件时间起算。
   删除前仍需解密验证；无完成时间的旧格式回执保守保留。

归档目录固定默认为 `$HOME/Private/stardust-log-archive/`，目录 0700、文件 0600。
禁止配置到 Git 工作区内或经符号链接跳转。密钥和 ops 能力保存在登录钥匙串，
客户端版本锁定为 keyring 25.7.0，非 macOS 后端一律拒绝。
该版本忽略 keychain 路径参数，因此程序核验实际默认钥匙串为 login，并在每次读写前
通过系统 Security API 检查解锁状态；禁止弹出交互解锁窗口，锁定时立即停机，绝不落明文。

```sh
"$OPS" key backup /单独安全介质/stardust-recovery.skey
"$OPS" key restore /单独安全介质/stardust-recovery.skey
```

必须本机交互输入恢复口令（至少 12 字符）；Scrypt 派生独立密钥加密恢复包。
备份只包含归档解密密钥，不复制 ops 能力。恢复文件不能放在归档目录或其子目录。
设备、唯一副本或密钥丢失仍可能永久丢失历史；服务器无法证明文件将永远存在。
用户已接受仅一份 Mac 加密副本后清云端的风险，仍建议离线备份恢复包。

## 安装及发布顺序

按 `dev → main` PR 流程；pull、PR、合并及部署前先检查 git status，保护未提交工作。
以下步骤不得跳过验证后直接声称上线：

1. 本地隔离 PostgreSQL、Python、JS 回归通过；先部署默认关闭的增量数据库。
2. 用安全渠道生成三个独立能力，数据库只注册摘要；API 写入能力放 Vercel
   `OBSERVABILITY_WRITE_KEY`，代理 upload 能力放 Cloudflare
   `OBSERVABILITY_UPLOAD_KEY`（Wrangler secret，不进 vars）。
3. 部署 Vercel（stardust-agent / sin1）、独立受控 Linux Worker 和上传代理。
   Worker 镜像构建传 `--build-arg APP_VERSION=完整提交SHA`。
   未定位和验证 Worker 主机前不猜测部署目标，不部署到旧电脑。
4. 分阶段启用数据库配置
   `update observability.config set enabled=true,event_budget_bytes=400000000 where singleton;`、
   Vercel/Worker `OBSERVABILITY_ENABLED=true`、
   上传代理 `BUSINESS_LOGS_ENABLED=true`；通过合成账号验证日志，不额外调用付费模型。
5. 在 Mac 执行安装脚本（初次用已有 Python+cryptography 环境运行）：

   ```sh
   .venv/bin/python ops/install_macos.py
   "$HOME/Library/Application Support/StardustOps/stardust-ops" init
   .venv/bin/python ops/install_macos.py --activate
   ```

   init 交互输入**专用 ops 能力**并生成本机 AES 密钥，已有配置不覆盖。
   安装使用哈希锁文件和独立 Python 3.12.14 版本化 venv，不依赖项目运行时；
   定时执行不访问源码 checkout，不调用模型，不依赖 Codex。
   `--activate` 先实际归档及验证，成功才加载 LaunchAgent：
   `$HOME/Library/LaunchAgents/website.stardust.logarchive.plist`。
   安装时要求系统时区为 UTC+08:00（本机北京时间），不擅改系统时区。
6. LaunchAgent 每天 09:00、RunAtLoad、每小时启动检查。按北京时间计算槽位，
   当天成功跳过；macOS 睡眠错过日历事件会在唤醒后补拉。
   Keychain 锁定、断网或磁盘不足记失败状态并等待下次检查。
   状态在独立运行目录 `state.json`，脱敏错误日志自动轮转（1 MB × 3）。
7. 检查 `launchctl print gui/$(id -u)/website.stardust.logarchive`、
   `archive status/verify` 及健康检查，验收后才报告完成。

暂停定时任务：

```sh
launchctl bootout "gui/$(id -u)" "$HOME/Library/LaunchAgents/website.stardust.logarchive.plist"
```

紧急停采：关闭 OBSERVABILITY_ENABLED / BUSINESS_LOGS_ENABLED 及数据库 config.enabled。
只回滚应用代码即可恢复旧业务路径，不删私有表、已归档文件或计费记录。

## 离线验收

```sh
.venv/bin/python -m pytest tests/test_observability.py -q
RUN_POSTGRES_POLICY_TESTS=1 .venv/bin/python -m pytest tests/test_observability_postgres.py -q
node --test tests/js/*.test.js infra/storage-worker/worker.test.mjs
.venv/bin/python -m pytest tests -q
```

测试数据均为合成账号和事件；真实用户、学校、聊天或生产凭据不得提交公开仓库。
单元/隔离数据库测试不等于真实 Keychain 锁定、唤醒调度或生产端到端验收，
这些项目应在实际部署记录中逐项标明结果，不伪造通过。

# 生产部署、验证与回滚规范指南 (Deployment & Rollback Guide)

本文档面向 `agent.stardust.website` 生产环境及离线开发环境，详细记录完整的上线、健康检查、监控排障与应急回滚步骤。

---

## 一、生产环境拓扑

* **域名**：[https://agent.stardust.website](https://agent.stardust.website)
* **托管平台**：Vercel (Production) / Python 3.12 Runtime
* **数据底座**：Supabase (Cloud Mode) / SQLite (Local Fallback)
* **模型网关**：Wopally Workbench Gateway / 自定义 OpenAI 兼容端点

---

## 二、部署前环境检查清单 (Pre-flight Checklist)

在触发部署前，必须确认以下环境变量已在 Vercel 或生产环境配置完整：

| 环境变量名 | 作用 | 检查标准 |
| :--- | :--- | :--- |
| `SUPABASE_URL` | 云端数据库主地址 | 必须为 `https://...` |
| `SUPABASE_PUBLISHABLE_KEY` | 客户端访问公共密钥 | 必须以 `sb_...` 开头 |
| `WOPALLY_MODEL_BASE_URL` | 模型网关服务地址 | 生产转发端点 |
| `WOPALLY_WORKBENCH_API_KEY` | 模型网关调用凭据 | 必须保密，不可泄露至客户端 |
| `WORKBENCH_BACKEND_SECRET` | 积分账本后端操作签名 | 用于防篡改 |

---

## 三、部署与发布流程

1. **运行本地全量测试门禁**：
   ```bash
   .venv/bin/python -m pytest tests -q -rs
   ```
   *要求：所有单元测试必须 100% 绿灯通过，无任一失败。*

2. **代码合并与推送**：
   ```bash
   git checkout main
   git merge codex/engineering-core
   git push origin main
   ```

3. **执行生产部署**：
   ```bash
   vercel --prod --yes
   ```
   *注意观察终端输出：确保出现 `▲ Aliased https://agent.stardust.website` 且 `readyState: READY`。*

---

## 四、线上健康检查与验证清单 (Post-Deployment Verification)

部署完成后，依次执行以下健康检查：

1. **系统存活与赛道加载检查**：
   ```bash
   curl -sL https://agent.stardust.website/api/health
   ```
   *预期响应*：`{"status":"ok","skills_loaded":35,...}`

2. **前端资源完整性验证**：
   * 打开浏览器访问 [https://agent.stardust.website](https://agent.stardust.website)；
   * 打开 DevTools Console，确认无静态资源 404 或 JS 报错；
   * 检查静态版本卡片与章节编辑器渲染是否正常。

3. **核心业务冒烟验证**：
   * 创建测试项目：`POST /api/projects`；
   * 目录更新与确认：`PUT /api/projects/{id}/outline`；
   * 提交章节生成任务：`POST /api/projects/{id}/sections/{sec}/jobs`；
   * 验证任务状态流转至 `completed`。

---

## 五、故障排障与一键回滚指南 (Rollback Procedure)

若部署后发现严重线上事故（如核心 API 500、登录会话异常）：

1. **查看线上实时日志**：
   ```bash
   vercel logs agent.stardust.website
   ```

2. **一键回滚至上一稳定版本**：
   * 在终端执行：
     ```bash
     vercel rollback
     ```
     或直接在 Vercel Dashboard -> Deployments 中，找到上一个稳定运行的 Deployment（如 `dpl_C7wBG9Eg3GYJeaegme5UsmLooAUY`），点击右侧 `...` -> `Instant Rollback`。
   * 回滚后公网域名 `agent.stardust.website` 会在 10 秒内透明切换回旧版本。

3. **本地代码回退**：
   ```bash
   git revert HEAD
   git push origin main
   ```


## 五、2026-10-20 性能与凭据同步发布规范

### 实际拓扑与性能边界
- Supabase 项目 `jcenwtgwbsmaufskxgup` 的实际区域为 `ap-southeast-1`（新加坡，已通过项目 API 核实），Vercel Functions 采用 `sin1`。同区域不等于同机房内网，不能保证 2–5ms 或 100% 可达。
- Auth SDK 的登录、注册、刷新、用户验证和退出走受限的 `/api/auth/proxy/*` 同源代理。旧 `/api/auth/login`、`/api/auth/signup` 保留兼容。只转发公开密钥和当前用户 JWT，不信任客户端自报 IP，不绕过 Supabase 风控；高并发下需另外评估平台限流。
- Auth 使用 ASGI lifespan 的异步 HTTP 连接池；REST/Storage 使用进程级同步 HTTP 连接池。凭据按请求传入，不设置全局用户 Authorization，不重试非幂等充值/注册/写入操作。
- 首屏赛道和预设列表采用 7 天有效的版本化本地缓存及后台刷新。认证不等待这两类数据，首次无缓存仍需网络；站点配置、Key、余额及项目数据不放进公共缓存。
- HTML `no-cache, must-revalidate`；JS/CSS 引用以文件内容摘要自动版本化。`no-cache` 允许存储但要求重新验证，并非“禁止存储”。所有 API 为 `private, no-store`。

### 模型 Key 云端安全
- 必须先应用 `encrypted_user_model_config` 迁移，再配置 Vercel 环境变量 `USER_CONFIG_ENCRYPTION_KEY`（独立 32 字节 URL-safe Base64）。不要与充值卡密加密密钥共用。
- `GET/POST/DELETE /api/user/llm-config` 全部要求已验证用户 JWT。保存响应不回显 Key；读取仅返回本账号配置，明确禁用缓存。模型推理仍使用原 BYOK 路径，不扣平台积分。
- AES-GCM 的附加认证数据绑定 owner_id；数据库仅存密文。RLS 同时限制读取、插入、更新和删除，禁止变更 owner 为他人。
- 这不是端到端加密：Vercel 需在内存解密后供用户及模型调用，运行环境管理员、恶意同源脚本仍可能读取。不得在日志、Auth metadata/JWT、项目导出及错误响应中保存或回显 Key。
- 清理浏览器数据、退出登录不删除云端配置。主动“删除云端配置”才删除；其他已打开设备通过重新登录/同步按钮读取最新状态。无实时远程清除保证，撤销被泄露 Key 应去服务商控制台。
- 云端保存失败时不显示成功、不覆盖当前配置。没有云端记录时回退平台默认配置；旧标签页临时 Key 不自动上传，用户需主动保存一次。
- 首次生成的加密主密钥备份仅保存在本机忽略目录 `.agent-data/secrets/`（目录 0700，文件 0600），应纳入受控密钥备份；丢失主密钥后已有密文无法恢复。不得在有数据后随意替换，轮换需双密钥迁移。

### 心跳监控（待接入外部监控账号）
- 提供 `GET /api/ping`，只返回存活状态，不访问数据库、Ollama或模型。可供外部监控使用。
- Vercel Hobby 原生 Cron 最小间隔为每日一次，不加入无效的每十分钟 Cron。无论外部心跳还是 Cron，均不能保证实例常驻或消除所有冷启动；监控调用也计入函数用量。
- 有监控账号后可创建 HTTP GET 监控，路径 `/api/ping`，5 分钟检查；只在故障/恢复时告警。当前发布不声明已创建此监控。

### Cloudflare 接入（需要域名管理员操作，未切 DNS）
- 当前权威 DNS 为阿里云 `dns27.hichina.com` / `dns28.hichina.com`；未获得域名/Cloudflare Zone 管理授权，不自动切 Nameservers。
- CF 免费 Anycast 不保证走香港，不可通过挑选任意 IP 锁定专线。Vercel 已有边缘网络，叠加 CF 可能更慢，不能承诺 60–80ms。
- 接入前导出所有 DNS（含邮件 MX/TXT/CAA 等），从 Vercel Domain 设置获取当前项目的准确目标，不盲填通用 CNAME。先在可撤销测试子域名验证，SSL 为 Full (Strict)，不启用改写 JS 的 Rocket Loader。
- 仅缓存 `/static/`，保留完整查询字符串作为缓存键，遵守源站缓存头；主页和 `/api/*`、携带 Authorization 或 Set-Cookie 的响应都绕过边缘缓存，不配全站 Cache Everything。
- 用相同浏览器、相同运营商、多时段比较未代理和代理的成功率及 p50/p95 TTFB；只有连续测试有改善才切主域。回滚为 DNS-only 并清除边缘静态缓存，不影响数据库。

### 发布验证与回滚
- 本地运行全部 Python/JS 测试，以及 `RUN_POSTGRES_POLICY_TESTS=1` 的隔离 PostgreSQL RLS 验证。
- 先上线增量表和加密主密钥，再部署代码。用两个临时测试账号及伪造测试 Key 验证跨设备读写/删除、越权拒绝、不回显、无缓存；测试后删除临时账号。
- 线上检查 `/api/ping`、Auth 错误响应、HTML 文件摘要及部署函数区域。不能用一例错误密码响应代表所有用户已成功登录。
- 代码回滚使用 Vercel 上一个已验证部署；保留加密主密钥及专用表，不 DROP 数据。若回滚到不支持同步的版本，云端配置仅暂时不可用。

参考：[Vercel Cron 限制](https://vercel.com/docs/cron-jobs/usage-and-pricing)、[Supabase RLS](https://supabase.com/docs/guides/database/postgres/row-level-security)。

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

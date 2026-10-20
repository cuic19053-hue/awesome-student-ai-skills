# 大文件通道：Cloudflare Worker + Supabase TUS

## 范围与真实限制

- `agent.stardust.website/uploads/*` 必须由 Cloudflare Worker 接管，**不是 Vercel rewrite**。
- 浏览器每片 6 MiB（Supabase 当前要求）；单文件应用上限为 **50,000,000 字节**。Worker、存储桶、应用三个上限均须配置，实际取最小值。
- 原始文件不经过 Vercel；小型材料登记 JSON 和文字解析仍在 Vercel。文件预览/下载也走 Worker，避免大响应再次经过函数。
- 支持现有的 DOCX/PDF/TXT/Markdown/PNG/JPG/WebP。**本次未增加 PPT/PPTX/ZIP 格式解析**。
- 上传成功不代表解析成功。原文件先登记保存，识别另发请求。解析失败/超时不自动删除原文件，可在材料卡片“重试文字识别”。这不是持久任务队列，也没有解除 Vercel 的解析执行时长上限。复杂扫描件仍需独立任务服务/OCR。
- PDF 现有上限 100 页；DOCX 解压后上限 150 MB、XML 单条目上限 10 MB；TXT/Markdown 提取前 100 万字符，原文件完整保留。
- 网络速度和 Cloudflare 大陆可达性没有保证。Worker 请求、出站流量和存储消耗平台配额，不承诺零成本。

## 安全设计

- Worker 仅可访问部署环境指定的 Supabase 地址，不接受任意目标 URL，不跟随重定向、不转发 Cookie。
- 每个文件请求通过 Supabase Auth 验证用户 JWT；新建上传时再用当前用户 JWT 通过 Projects RLS 校验项目。
- 固定私有桶和 `user_id/project_id/document_id.ext` 路径；继续由 Storage RLS 校验对象权限。**不使用 service_role**。
- 续传地址是 24 小时有效、绑定用户和文件总长的 HMAC 签名会话。每个分片仍需登录 JWT；仅持有续传 URL 不能上传他人文件。
- `UPLOAD_SESSION_SECRET` 只存在 Worker secret 中，不发往前端、不写数据库。更换会使进行中的续传失效，不影响已保存对象。不要在访问日志中记录完整续传地址/Authorization。
- 上传信息本地只保存用户/项目范围内的续传标识，不保存 JWT。退出/切换账号后无法借该标识上传到另一个用户目录。
- 暂未实现全用户存储配额/孤立文件自动清理/恶意频繁上传限流。开放大规模注册前需添加限制和监控。

## 部署顺序（未验证前不要开启前端开关）

1. 在 `infra/storage-worker` 运行 `npm ci`、`npm test`、`npm run check`。
2. 登录自己的 Cloudflare 账户：`npx wrangler login`。确认 `stardust.website` 已激活，`agent` 开启橙云。`workers.dev` 已禁用，不能用它代替自有域名通道。
3. 设置两个 Worker secrets：
   - `npx wrangler secret put SUPABASE_PUBLISHABLE_KEY`（使用当前项目公开 key，**不是 service_role**）。
   - `npx wrangler secret put UPLOAD_SESSION_SECRET`（独立随机值，至少 32 字符；安全保存，别在聊天或终端日志展示）。
4. `npm run deploy`。只部署精确 `/uploads/*` 路由，不修改其他域名或路径。
5. 通过 Supabase Storage 管理 API/控制台，将 `stardust-project-files` 的文件大小上限调为 **50,000,000**；保留 `public=false`、现有 MIME 列表及 RLS。如果项目全局上限更低也需调整。不要随意修改 Storage 对象元数据或放宽权限。
6. 验证 `/uploads/health`，未登录 POST 应返回 401。使用专用测试账号在生产完成下述验收。
7. 将 Vercel 环境变量 `STORAGE_UPLOAD_PROXY_ENABLED=true` 后，按当前 Vercel 项目发布流程重新部署；该开关默认关闭。**没有 Worker 路由时不能开启**，否则上传会退回 Vercel 而失败。

本地 Worker 无需真实账户即可完成单元测试；`wrangler deploy --dry-run` 只是打包检查，不是上线。

## 验收

自动化测试：

```sh
.venv/bin/python -m pytest tests -q
node --test tests/js/*.test.js
cd infra/storage-worker && npm test && npm run check
```

Worker 模拟上游测试覆盖 5 MB、20 MB、49,999,999 字节上传，逐片偏移、响应丢失后 HEAD 恢复、最终 SHA-256 一致；另验证身份隔离、篡改/过期续传地址、跨站请求、SSRF、超限/错误分片和下载 Range。**模拟通过不能代替生产 Supabase TUS 验收**。

真实生产需另验：
- 使用专用账号创建项目，上传正常且可解析的 5 MB/20 MB/接近上限文件。
- 浏览器断网后恢复、刷新后重新选择同一文件，检查是否续传；存储禁用时允许新传但不保证跨刷新恢复。
- 下载原文件校验 SHA-256，验证处理结果、预览和删除。
- 换另一账号尝试 HEAD/PATCH/下载原用户会话，均应拒绝。
- 测试解析失败、504 与登记响应丢失：原文件仍在，重新登记不创建重复材料。
- 关闭 Worker/配置错误时显示通道故障，不虚假提示上传成功。

## 回滚

优先保留 Worker 作为已有大文件的下载通道；回滚前端/后端代码后检查其兼容性。若关闭 `STORAGE_UPLOAD_PROXY_ENABLED`，大于 4 MB 的新上传会提前报“通道尚未启用”，不是重新经过 Vercel 试传。已上传文件不因开关变化自动删除；旧 Vercel 下载路径可能无法返回大文件，不能将关闭开关当成完整的大文件回滚。

参考：[Supabase TUS](https://supabase.com/docs/guides/storage/uploads/resumable-uploads)、[文件限制](https://supabase.com/docs/guides/storage/uploads/file-limits)。

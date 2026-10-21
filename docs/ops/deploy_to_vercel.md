# 部署到生产（Vercel）· 可直接转交的提示词

> 用途：把一次已经跑过测试、推送到 `main` 的改动发布到 `agent.stardust.website`。
> 使用方式：复制下面「提示词正文」整段，连同仓库路径一起发给执行部署的 agent。

---

## 提示词正文

```
任务：把 awesome-student-ai-skills 的最新 main 部署到 Vercel 生产环境，并确认线上跑的是新版本。

【背景】
- 仓库：https://github.com/cuic19053-hue/awesome-student-ai-skills
- 本地路径：<把仓库根目录的绝对路径填在这里>
  如果这台机器上没有这个仓库，先执行：
    git clone https://github.com/cuic19053-hue/awesome-student-ai-skills.git
- 目标提交：dfd37f7（"ping 增加 layout_rev 发版标记，部署后可直接核对线上版本"）
- Vercel 项目名：stardust-agent
- 团队：cuic19053-hues-projects
- 生产域名：https://agent.stardust.website
- 本次上线内容：新增排版审计器与硬化器，导出接口的响应里会多一个 layout.score 字段；
  健康接口 /api/ping 新增 layout_rev 字段（旧版没有这个字段），用它判断是否部署成功。
- 线上当前是 1 天前的旧版本。

【前置检查】任一项不满足就停下并报告，不要自行猜测或跳过：
1) cd 到仓库根目录后，git status --short 必须为空输出。
   有改动就先停下报告，不要 stash、不要 commit。
2) git log --oneline -1 必须是 dfd37f7 或它的后代。
   落后就先 git pull --ff-only origin main，再复查一次。
3) vercel whoami 必须输出 cuic19053-hue。
   不是的话运行 vercel login 完成登录后继续。
4) 如果 .vercel/project.json 不存在，执行：
   vercel link --yes --project stardust-agent --team cuic19053-hues-projects

【部署】在仓库根目录执行：
   vercel deploy --prod --yes
成功标志：输出里出现 Production 环境与形如
https://stardust-agent-<hash>-cuic19053-hues-projects.vercel.app 的地址，状态 Ready。
构建通常 30–90 秒，不要中途打断。

【验证】三项全部通过才算成功，必须用命令验证，不要只看网页截图：
1) curl -s https://agent.stardust.website/api/ping
   期望返回里含 "layout_rev":1
   判定：layout_rev 必须是 1。如果只返回 {"status":"ok"}，说明域名还指向旧部署。
2) curl -s -o /dev/null -w "%{http_code}\n" https://agent.stardust.website/
   期望：200
3) vercel ls stardust-agent
   最新一条（Age 最小）必须是 Ready 且 Environment 为 Production

【第 1 项没通过时】
- 先等 30 秒重试（CDN 与函数冷启动都有延迟），最多重试 3 次。
- 仍不对：用 vercel ls stardust-agent 确认是否真的产生了新的 Production 部署。
  如果新部署已 Ready 但域名没切过去，执行：
     vercel alias set <新部署的完整 URL> agent.stardust.website
  然后再验证第 1 项。
- 仍失败就停止，不要继续折腾。把 vercel deploy --prod 的完整输出贴出来。

【禁止】
- 不要修改任何代码、配置、环境变量、依赖版本
- 不要 git commit / git push / 改分支
- 不要 vercel remove 任何部署或项目，不要删 .vercel
- 不要改 DNS，不要把生产域名指向 Preview 部署
- 不要为了让验证通过去改 /api/ping 的实现

【交付报告】用下面的格式回我，不要写别的：
- 部署 URL：
- 目标 commit：dfd37f7（线上 commit 若能从 ping 读到也一并写）
- 验证 1（ping）：<原始输出一行>
- 验证 2（首页状态码）：<原始输出一行>
- 验证 3（vercel ls 首行）：<原始输出一行>
- 结论：成功 / 失败（失败时补一句卡在哪一步 + 原始报错）
```

---

## 为什么验证要看 `layout_rev`

`vercel deploy` 是**把当前目录打包上传**，不是从 Git 拉取。所以「部署命令成功」不等于「线上是新代码」——只等于「某个版本部署好了」。域名可能因为别名、缓存或误操作仍指向旧部署。

`/api/ping` 返回 `layout_rev` 是一个写死的发版号，不依赖任何环境变量（CLI 直接部署时 Vercel 不会注入 `VERCEL_GIT_COMMIT_SHA`），因此是外部唯一可靠的版本信号。以后每次涉及导出/排版的改动，把 `server/app.py` 里的 `LAYOUT_REV` 加 1 即可继续用它验收。

---

## 本次上线包含的内容（供部署后抽查）

| 项 | 验证方式 |
|---|---|
| 导出接口返回 `layout.score` | 登录后导出任意项目，看响应 JSON；或看前端是否显示排版得分 |
| 排版硬化生效 | 导出的 .docx 用 Word 打开：表格不会被拆到两页、图注与图同页、页脚有「第 N 页 共 M 页」 |
| 排版审计器可用 | 本地 `python utils/layout_audit.py <导出的.docx>` 应输出得分与条款明细 |

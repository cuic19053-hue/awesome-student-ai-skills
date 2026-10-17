# 前端重做说明（2026-10 · v2）

本文件记录 `server/static/` 新一代工作台前端的结构、接口约定与已知边界。历史文档保持只读，不改写。

## 设计方向

- 参考 Qificai 的“暖白页面 + 内嵌圆角画布”布局：页面留白、工作区是一块浮起的画布，用阴影与色阶区分层级，不再用横线/竖线分割。
- 深色与浅色双主题，可跟随系统；切换即时生效并记住选择。
- 欢迎页与页面切换使用轻量位移动画；列表、卡片、弹窗、文档预览都有过渡；尊重 `prefers-reduced-motion`。
- 不出现 emoji，图标统一为内联 SVG。
- 文案只讲用户能获得什么，不描述界面布局（避免“左边是…右边是…”式宣传语）。

## 文件结构

```
server/static/
├─ index.html          外壳（主题预置脚本 + 挂载点 + 脚本顺序）
├─ app.css             设计系统 v2（双主题 tokens / 内嵌画布 / 动效 / 响应式）
├─ js/core.js          window.S：图标、API、存储、Toast、弹窗、Markdown、主题、View Transitions
├─ js/settings.js      设置中心：账户 / 购买与积分 / 模型配置 / 用量明细 / 关于
├─ js/project.js       项目空间 + 对话 + 文档预览（大纲 / 文件 / 白纸预览）
└─ js/app.js           路由、侧边栏、欢迎页、首页、新建项目
```

旧文件（`index-kimi.html`、`kimi-*.js|css`、`index-new.html`、`app-new.*`、`v1` 样式备份）保留但不再引用。

## 路由

| hash | 视图 |
| --- | --- |
| `#/` | 首页 |
| `#/new` | 新建项目（图标与名称 → 准备申报材料） |
| `#/p/<projectId>/conversations` | 项目 · 会话 |
| `#/p/<projectId>/files` | 项目 · 文件 |
| `#/p/<projectId>/memory` | 项目 · 共同记忆 |
| `#/p/<projectId>/document` | 项目 · 申报书 |
| `#/p/<projectId>/c/<threadId>` | 项目 · 具体会话（含文档预览） |

## 主题与动效

- 主题存于 `localStorage` 的 `stardust_theme_v1`（`light` / `dark` / `auto`）；`index.html` 内联脚本在首屏前应用，避免闪白/闪黑。
- 页面切换优先使用 View Transitions API，不支持时直接切换；所有过渡在减少动态效果偏好下关闭。
- 弹窗统一支持 `X`、遮罩点击、`Esc`（keydown/keyup 双通道，避免个别浏览器只派发其中一个）。

## 文档预览面板

- 存在于对话页，可收起；宽屏默认展开。
- 「大纲」页签：可折叠层级、逐章预览已写入的章节内容。
- 「文件」页签：列出项目文件，PDF/图片内嵌预览，Word/TXT 显示提取文本（白纸样式）。
- Agent 调用写入类工具（`save_section` / `export_docx` / `save_diagram` / `generate_image` / `save_project_fact`）时，预览面板自动展开并显示本轮草稿。
- 工具调用以可折叠的「使用 N 个工具」分组展示。

## 复用后端接口（未改后端代码）

`/api/config`、`/api/skills`、`/api/projects*`、`/api/route`、`/api/documents*`、`/api/projects/{id}/chat`、`/api/projects/{id}/facts`、`/api/projects/{id}/validate`、`/api/projects/{id}/export`、`/api/projects/{id}/download`、`/api/user/balance`、`/api/pay/redeem`、`/api/model-config/test`、`/api/token-stats`。

## 本地状态

| key | 位置 | 内容 |
| --- | --- | --- |
| `stardust_ui_v1` | localStorage | 欢迎页已读、侧边栏折叠、称呼、项目图标、项目指令 |
| `stardust_theme_v1` | localStorage | 主题模式 |
| `stardust_threads_v1` | localStorage | 每个项目的会话线程与消息 |
| `stardust_model_v1` | sessionStorage | 模型来源、Base URL、模型名、Key（仅当前标签页）、演示模式 |

## 已知边界

- 会话线程为前端持久化：后端 `/api/projects/{id}/chat` 仍是单一消息流，真正“独立会话”需要后端提供 thread 维度接口。
- 项目指令只在本机保存，尚未进入后端提示词。
- 账号登录、卡密兑换在本地环境按 `/api/config` 能力开关降级展示。
- 文档预览中的 Word 内容来自后端提取文本，复杂排版仍以导出文件为准。

## 本地运行与验证

```bash
cd <repo>
.venv/bin/python -m uvicorn app:app --app-dir server --host 127.0.0.1 --port 8765
```

截图冒烟使用仓库外的 `tools/cdp_shot.py`（无头 Chrome + CDP）：

```bash
./awesome-student-ai-skills/.venv/bin/python tools/cdp_shot.py \
  --url http://127.0.0.1:8765/ --out tools/shots --steps tools/steps-home.json \
  --width 1440 --height 1000
```

已验证：欢迎页明暗两套、首页、新建项目两步、项目四页签、对话 + 文档预览（自动展开、文件/大纲预览）、设置五分区（含主题切换）、导出 Word、移动端 390×844、弹窗三种关闭方式。


## 交互与 UX（2026-10 第二轮）

- **快速跳转（⌘K）**：搜索项目与会话，或直接执行动作（新建会话 / 新建项目 / 设置 / 切换主题 / 返回首页），支持 ↑↓ 与 Enter。
- **开始准备引导卡**：项目首次打开时显示三步清单（放入材料 → 确认事实 → 生成大纲），完成项自动打勾，点击直达对应页签。
- **文件确认**：文件行可点击，弹窗展示可编辑的提取文本，确认后才进入检索；拖拽上传对列表底部与空状态两个区域都生效。
- **章节编辑**：点击申报书任意章节打开编辑弹窗，可保存、或让 Agent 生成本章；生成结果自动落盘并刷新状态。
- **对话**：
  - 发送期间锁定输入框与发送按钮，避免重复提交；
  - 消息悬停出现“复制”；
  - 会话头部「…」支持重命名 / 删除 / 返回项目；
  - 当用户向上翻阅历史时，新消息不再强行拉到底部，而是出现“回到底部”按钮；
  - 打开会话时桌面端自动聚焦输入框。
- **错误恢复**：首页在项目/赛道列表加载失败时显示重试条；文档提取失败给出明确说明。
- **创建流程**：第二步顶部显示已选赛道，未选择时说明默认赛道；选中后自动滚动到该赛道。
- **移动端**：首页与新建项目页提供侧边栏入口；Esc 可收起文档预览；输入框字号 16px 避免 iOS 聚焦缩放。

## 交付前审查（2026-10）

**已修复的阻断问题**
- 启动崩溃：`refreshScrim()` 中 `app` 的 TDZ（监听已移到 `bindGlobalEvents`，只注册一次）。
- 首页/新建项目的 click 委托改为绑定到每次渲染的新根节点，避免监听器在常驻 `#main` 上累积。
- “生成大纲”两个入口接反的问题已对调；生成成功后自动调用 `PUT /api/projects/{id}/outline` 确认目录，之后“生成本章”不会再报“请先确认或修改申报书目录”。
- PDF 预览改为 Blob URL（后端 `/file` 返回 attachment），不再变成下载。
- 快速切路由、发送中离开会话的异步竞态已加守卫（`viewSeq` / `isConnected`）。
- 损坏的 localStorage 线程数据会做结构校验与归一化。

**已知边界（交付时需知）**
- 本地版未启用登录：默认只监听 `127.0.0.1`，不要直接暴露公网。
- `cloud_mode=true`（配置了 Supabase）时，前端尚未实现登录态与 `Authorization` 头，接口会返回 401；当前按本地版交付。
- 默认模型来源为“平台预设”，本地 `/api/config.preset_enabled` 为 false 时首条消息会 503；对话页会提示去设置选择 Ollama 或自备 API。
- 会话线程、项目指令仅保存在本机浏览器；后端 `/chat` 仍是单消息流。
- 文档预览的 Word/TXT 内容来自后端提取文本，复杂排版以导出的 Word 为准。
- `server/static/` 下仍有未被引用的旧实验文件（`app-new.*`、`index-new.html`、`index-kimi.html`、`kimi-*`、`styles.css`，以及被 git 跟踪的旧 `app.js`），交付前可清理。
- 后端全量测试中 7 个用例依赖未安装的可选依赖（`numpy`/`matplotlib`/`rapidocr`），与本次前端改动无关。

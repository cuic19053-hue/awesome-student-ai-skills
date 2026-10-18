# 🤝 Stardust 双人敏捷协作与发布守则 (Team Collaboration Playbook)

> **致崔灏与 Richy**：  
> 本项目凝聚了我们从 2026 年 7 月至今的所有心血。我们一个是“赛事实战、公文规范与业务增长的掌舵人”，一个是“前沿架构、体验审美与技术极客的打磨者”。  
> 本规范不搞大厂官僚审批，只定 4 条最实在、最能落地的默契约定，保障我们两个人协作时：**改得爽、测得快、上线稳、不背刺**。

---

## 一、 核心铁律：主干与开发解耦（双分支模型）

```
[本地开发 / Trae / IDE]          [开发联调分支]                  [正式生产部署]
feat/new-ui        ───────┐
                          ├─────►  dev 分支 (日常联调场)  ──(验证OK)──►  main 分支 (生产环境)
fix/backend-jobs   ───────┘             │                                │
                                  Vercel Preview                   agent.stardust.website
```

### 1. `main` 分支是神圣生产分支
* **唯一对应线上正式域名**：`https://agent.stardust.website`；
* **严禁任何人直接 `git push origin main`**；
* 只有在 `dev` 分支上完整验证通过、测试全绿、端到端跑通后，由崔灏统一合并至 `main` 触发生产自动上线。

### 2. `dev` 分支是二人日常协作的主战场
* 日常功能开发、新 UI 实验、后端调优一律在 `dev` 分支；
* **每次开工前，第一动作永远是更新公共基线**：
  ```bash
  git checkout dev
  git pull origin dev
  git checkout -b feat/your-feature-name
  ```
  > ⚠️ **血泪经验**：切分支前必须确认当前位于最新的 `origin/dev`，**坚决杜绝从未知的旧提交、历史本地分支或临时 feature 分支上拉出新分支**，避免把未测试完的代码带入新分支。

---

## 二、 前端与 UI 改版保护线（防丢功能 Checklist）

Richy 具备极佳的前端审美与现代设计品味（Qific 风格的内嵌画布与质感动效非常优秀）。未来我们依然鼓励升级前端，但为了防止“页面变漂亮了，成熟业务功能却丢了”，**任何涉及页面重写/改版的 PR，合并前必须由两人逐项对照以下 5 项业务底线**：

| 检查项 | 必须保障的业务底线 | 翻车教训与避坑要点 |
| :--- | :--- | :--- |
| **1. 模型自适应** | 未登录/本地模式/无平台密钥时，**必须自动回退至本地 Ollama 或提示填写自定义 API Key**。 | 严禁把默认值硬编码为 `preset` 导致新用户/本地运行直接抛 503。 |
| **2. 技术路线图 (Diagrams)** | 必须保留点击「AI 推荐架构图」与 Mermaid 流程图、时序图、技术路线图的实时预览与编辑入口。 | 挑战杯/大创/科研赛道极度依赖技术路线图，此功能不可裁剪。 |
| **3. AI 事实抽取 (proposeFacts)** | 上传申报指南/通知文件后，必须保留点击「智能提取关键事实」自动填入 13 项关键要素的逻辑。 | 用户不想纯手工一行行敲事实，AI 预填是核心卖点。 |
| **4. 一键批量生成全篇** | 确认大纲后，必须保留「一键批量生成全文草稿」的能力（按顺序串行生成并实时落盘）。 | 单章一个个手动点生成体验断层，批量生成是长文痛点。 |
| **5. 本地缓存兼容性** | 尽量不要随意改写 `sessionStorage` 与 `localStorage` 的缓存 Key。 | 若必须升级存储结构，需提供平滑读旧 Key 的兼容 fallback，防止老用户配置被清空。 |

---

## 三、 前后端解耦准则（改动范围不越界）

1. **改 UI / 前端的 PR**：
   * 改动范围原则上**只准包含** `server/static/*` 目录及相关文档；
   * **严禁夹带** `server/app.py`、`server/proposal/*` 等核心 Python 后端改动；
   * PR 提交前使用 `git status` 确认没有意外 stage 后端文件。
2. **改后端的 PR**：
   * 必须在提交前运行本地全量测试门禁：
     ```bash
     .venv/bin/python -m pytest -q
     ```
   * 确保 200+ 单元测试 100% 绿灯通过，无任何断言失败；
   * 在涉及用户身份与模型计量的逻辑上，**严禁使用 ThreadPoolExecutor 假异步**。
3. **前后端需联调的新接口**：
   * 后端同学先出接口规范并在 `dev` 上打好 Mock / 真实接口；
   * 前端同学基于 `dev` 上的稳定接口进行页面联调。

---

## 四、 敏捷协作命令速查表 (Git Cheatsheet)

### 1. 开启一个新功能开发
```bash
# 1. 确保本地 dev 是最新的
git checkout dev
git pull origin dev

# 2. 从 dev 切出特性分支
git checkout -b feat/beautify-dashboard
```

### 2. 本地开发与提测
```bash
# 查看改动文件，确认没有误带不相干的文件
git status

# 运行本地测试（若动了后端）
.venv/bin/python -m pytest -q

# 提交并推送到 GitHub
git add .
git commit -m "feat(ui): 优化工作台卡片阴影与响应式间距"
git push -u origin feat/beautify-dashboard
```

### 3. 合并到 dev（两人联调）
在 GitHub 上创建 Pull Request：
* **Base 分支选 `dev`**（千万别选 `main`）；
* 两人互相 Review，确认勾选了《防丢功能 Checklist》后合并进 `dev`。

### 4. 发布上线（dev -> main）
当 `dev` 分支积累了一批稳定功能且通过测试后：
```bash
git checkout main
git pull origin main
git merge dev --ff-only   # 快速推进合并
git push origin main      # 触发 Vercel 生产自动构建上线
```

---

## 五、 线上生产事故应急指南 (10 秒止血)

如果线上发布后出现紧急阻断（如核心模型报 500、白屏）：

1. **第 1 步：先止血，不要现场慌乱改代码**  
   * 打开 [Vercel Dashboard](https://vercel.com) -> 进入 `stardust-agent` 项目；
   * 在 Deployments 列表找到上一个稳定运行的 Deployment（带绿色 ● 标志）；
   * 点击右侧 `...` -> 选择 **`Instant Rollback`**；
   * **10 秒钟内，生产域名透明恢复至上一版，彻底止血。**
2. **第 2 步：微信群同步**  
   * 发一条消息：“已一键回滚生产，线上已恢复正常，我们在 dev 分支排查复现。”
3. **第 3 步：在 `dev` 分支从容排查**  
   * 本地切到 `dev` 查日志复现，修完跑通单测，再走正规 PR 合并进 `main`。

---

> **结语**：规范不是束缚，而是两个人走得更快、更远的登山绳。携手打造全国最好的大学生 AI 工具！🚀

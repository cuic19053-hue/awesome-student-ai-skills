(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const llmConfigKey = "innovation-proposal-agent-llm-config";

  const activeProjectKey = "stardust-agent-active-project-id";

  function readSavedLlmConfig() {
    const fallback = { provider: "ollama", model: "qwen2.5:7b", base_url: "", api_key: "" };
    try {
      localStorage.removeItem(llmConfigKey);
      const saved = JSON.parse(sessionStorage.getItem(llmConfigKey) || "null");
      if (saved && ["ollama", "openai_compatible"].includes(saved.provider)) return { ...fallback, ...saved };
    } catch {}
    return fallback;
  }

  const state = {
    project: null,
    projectsList: [],
    documents: [],
    messages: [],
    uploadKind: "source",
    outline: [],
    diagrams: [],
    editingDiagramId: "",
    llmConfig: readSavedLlmConfig(),
    chatCollapsed: false,
    cloudMode: false,
    authClient: null,
    authSession: null,
    authMode: "signin",
    appStarted: false,
    skills: [],
    pendingProject: null,
    activeTab: "all",
  };

  function countWords(str) {
    if (!str) return 0;
    const cjk = (str.match(/[\u4e00-\u9fa5]/g) || []).length;
    const en = (str.replace(/[\u4e00-\u9fa5]/g, " ").match(/[a-zA-Z0-9_-]+/g) || []).length;
    return cjk + en;
  }

  const labels = {
    problem: "要解决的问题",
    project_name: "项目名称",
    target_user: "服务对象 / 场景",
    method: "拟采用的方法",
    foundation: "现有基础 / 资源",
    goal: "目标",
    expected_output: "预期产出",
    constraints: "项目限制",
    budget: "预算",
    team: "团队",
    duration: "项目周期",
    leader_name: "负责人",
    advisor_name: "指导教师",
  };

  function toast(message, isError = false) {
    const node = $("#toast");
    if (!node) return;
    node.textContent = message;
    node.classList.toggle("error", isError);
    node.classList.remove("hidden");
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => node.classList.add("hidden"), 3800);
  }

  // Lightweight safe Markdown renderer for Stardust Agent message bubbles
  function renderMarkdownSafe(text) {
    if (!text) return "";
    let escaped = text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");

    // Code blocks ```code```
    escaped = escaped.replace(/```([\s\S]*?)```/g, (match, code) => {
      return `<pre><code>${code.trim()}</code></pre>`;
    });

    // Inline code `code`
    escaped = escaped.replace(/`([^`]+)`/g, "<code>$1</code>");

    // Headers
    escaped = escaped.replace(/^### (.*$)/gim, "<h4>$1</h4>");
    escaped = escaped.replace(/^## (.*$)/gim, "<h3>$1</h3>");
    escaped = escaped.replace(/^# (.*$)/gim, "<h2>$1</h2>");

    // Bold & Italic
    escaped = escaped.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    escaped = escaped.replace(/\*([^*]+)\*/g, "<em>$1</em>");

    // Blockquote
    escaped = escaped.replace(/^\> (.*$)/gim, "<blockquote>$1</blockquote>");

    // Lists
    escaped = escaped.replace(/^\s*-\s+(.*$)/gim, "<li>$1</li>");
    escaped = escaped.replace(/^\s*\d+\.\s+(.*$)/gim, "<li>$1</li>");
    escaped = escaped.replace(/(<li>[\s\S]*?<\/li>)/g, "<ul>$1</ul>");
    escaped = escaped.replace(/<\/ul>\s*<ul>/g, "");

    // Paragraphs & Line breaks
    const paragraphs = escaped.split(/\n{2,}/).map(p => {
      p = p.trim();
      if (!p) return "";
      if (p.startsWith("<h") || p.startsWith("<ul") || p.startsWith("<pre") || p.startsWith("<blockquote")) {
        return p;
      }
      return `<p>${p.replace(/\n/g, "<br>")}</p>`;
    }).filter(Boolean);

    return paragraphs.join("");
  }

  async function api(url, options = {}) {
    const requestOptions = { ...options };
    const headers = new Headers(requestOptions.headers || {});
    if (state.authSession?.access_token) {
      headers.set("Authorization", `Bearer ${state.authSession.access_token}`);
    }
    const method = (requestOptions.method || "GET").toUpperCase();
    const path = new URL(url, window.location.href).pathname;
    const usesLlm = method === "POST" && /\/api\/projects\/[^/]+\/(?:chat|outline\/generate|sections\/[^/]+\/generate|diagrams\/propose|facts\/propose)$/.test(path);
    if (usesLlm) {
      let body = {};
      if (typeof requestOptions.body === "string" && requestOptions.body) {
        try { body = JSON.parse(requestOptions.body); } catch {}
      }
      body.llm_config = { ...state.llmConfig };
      headers.set("Content-Type", "application/json");
      requestOptions.body = JSON.stringify(body);
    }
    requestOptions.headers = headers;
    const response = await fetch(url, requestOptions);
    const type = response.headers.get("content-type") || "";
    const body = type.includes("application/json") ? await response.json() : await response.text();
    if (!response.ok) {
      const detail = typeof body === "object" ? body.detail || body.error : body;
      throw new Error(detail || `请求失败 (${response.status})`);
    }
    return body;
  }

  function button(label, cls = "button button-small button-secondary") {
    const node = document.createElement("button");
    node.type = "button";
    node.className = cls;
    node.textContent = label;
    return node;
  }

  function updateTemplateExplain() {
    const has = $('input[name="hasTemplate"]:checked')?.value === "yes";
    $("#templateExplain").textContent = has
      ? "上传 Word 模板时会尽量参考原文件栏目；PDF 模板会参考栏目生成 Word，并提醒你核对。"
      : "没有模板时，Agent 会按所选赛道拟定通用结构，并提醒你提交前按学校要求核对。";
  }

  function showModelStatus(localStatus) {
    const status = $("#modelStatus");
    if (state.llmConfig.provider === "openai_compatible") {
      status.textContent = `自定义 API · ${state.llmConfig.model || "未设置模型"}`;
      status.classList.remove("offline");
      status.classList.add("remote-warning");
      const privacy = $(".privacy-note");
      if (privacy) {
        privacy.classList.add("remote-warning");
        privacy.lastChild.textContent = "当前使用自定义远程模型；对话内容会发送到此 Agent 服务，再转发给你填写的模型服务商。";
      }
      return;
    }
    if (!localStatus) {
      status.textContent = `本地模型 · ${state.llmConfig.model || "qwen2.5:7b"}（请测试连接）`;
      status.classList.remove("offline", "remote-warning");
      return;
    }
    const ready = localStatus.ollama_available && localStatus.ollama_model_installed;
    const model = state.llmConfig.model || localStatus.ollama_model;
    const selectedIsHealthModel = model === localStatus.ollama_model;
    status.textContent = ready && selectedIsHealthModel
      ? `本地引擎已连接 · ${model}`
      : localStatus.ollama_available && selectedIsHealthModel
        ? `缺少模型 · 请先 ollama pull ${model}`
        : localStatus.ollama_available
          ? `本地 Ollama · ${model}（请测试连接）`
      : !localStatus.ollama_available
        ? `Ollama 未启动 · ${model}`
        : `缺少模型 · 请先 ollama pull ${model}`;
    status.classList.toggle("offline", !localStatus.ollama_available || (selectedIsHealthModel && !ready));
    status.classList.remove("remote-warning");
    const privacy = $(".privacy-note");
    if (privacy) {
      privacy.classList.toggle("remote-warning", !localStatus.ollama_local);
      if (!localStatus.ollama_local) {
        privacy.lastChild.textContent = "当前 Ollama 位于远程主机；聊天与检索内容会发送到该主机。请勿上传不应外传的资料。";
      }
    }
  }

  function selectedLlmConfig() {
    const provider = $('input[name="llmProvider"]:checked')?.value || "ollama";
    if (provider === "ollama") {
      return {
        provider,
        model: $("#localModelName").value.trim() || "qwen2.5:7b",
        base_url: "",
        api_key: "",
      };
    }
    return {
      provider,
      base_url: $("#customModelBase").value.trim(),
      model: $("#customModelName").value.trim(),
      api_key: $("#customModelKey").value.trim(),
    };
  }

  function syncModelSettingsForm() {
    const config = state.llmConfig;
    $("#providerOllama").checked = config.provider === "ollama";
    $("#providerCustom").checked = config.provider === "openai_compatible";
    $("#localModelName").value = config.provider === "ollama" ? config.model : "qwen2.5:7b";
    $("#customModelBase").value = config.provider === "openai_compatible" ? config.base_url : "";
    $("#customModelName").value = config.provider === "openai_compatible" ? config.model : "";
    $("#customModelKey").value = config.provider === "openai_compatible" ? config.api_key : "";
    updateModelFields();
    $("#modelConfigFeedback").textContent = "";
    $("#modelConfigFeedback").className = "model-config-feedback";
  }

  function updateModelFields() {
    const custom = $("#providerCustom").checked;
    $("#localModelFields").classList.toggle("hidden", custom);
    $("#customModelFields").classList.toggle("hidden", !custom);
  }

  function storeLlmConfig(config) {
    state.llmConfig = config;
    try {
      sessionStorage.setItem(llmConfigKey, JSON.stringify(config));
    } catch {
      toast("浏览器无法保存本次模型配置；本次页面仍可继续使用。", true);
    }
    showModelStatus(null);
  }

  async function testSelectedLlmConfig() {
    const config = selectedLlmConfig();
    const feedback = $("#modelConfigFeedback");
    const testButton = $("#testModelConfigBtn");
    feedback.textContent = "正在测试连接…";
    feedback.className = "model-config-feedback";
    testButton.disabled = true;
    try {
      const result = await api("/api/model-config/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      });
      feedback.textContent = `连接成功：${result.model}`;
      feedback.className = "model-config-feedback success";
    } catch (error) {
      feedback.textContent = error.message;
      feedback.className = "model-config-feedback error";
    } finally {
      testButton.disabled = false;
    }
  }

  function saveSelectedLlmConfig() {
    const config = selectedLlmConfig();
    if (config.provider === "openai_compatible" && (!config.base_url || !config.model || !config.api_key)) {
      $("#modelConfigFeedback").textContent = "请填写 API 地址、模型名称和 API Key。";
      $("#modelConfigFeedback").className = "model-config-feedback error";
      return;
    }
    storeLlmConfig(config);
    $("#modelSettingsDialog").close();
    toast(`已切换为${config.provider === "ollama" ? "本地模型" : "自定义 API"}：${config.model}`);
  }

  function showAuthGate(message = "") {
    state.appStarted = false;
    $("#appShell").classList.add("hidden");
    $("#authGate").classList.remove("hidden");
    $("#signOutBtn").classList.add("hidden");
    $("#authFeedback").textContent = message;
  }

  async function startApplication(session = null) {
    if (state.appStarted) return;
    state.authSession = session;
    state.appStarted = true;
    $("#authGate").classList.add("hidden");
    $("#appShell").classList.remove("hidden");
    $("#signOutBtn").classList.toggle("hidden", !state.cloudMode);
    await Promise.all([checkHealth(), refreshProjects()]);
    const projects = await api("/api/projects");
    if (projects.projects?.length) {
      const lastId = localStorage.getItem(activeProjectKey);
      const target = projects.projects.find((project) => project.id === lastId) || projects.projects[0];
      await loadProject(target.id);
    } else {
      $("#workspace").classList.add("hidden");
      $("#welcome").classList.remove("hidden");
    }
  }

  async function initializeCloudAuth(config) {
    state.cloudMode = Boolean(config.cloud_mode);
    if (!state.cloudMode) {
      await startApplication();
      return;
    }
    const localBadge = $(".sidebar-footer .local-badge");
    if (localBadge) localBadge.textContent = "账号隔离 · 云端存储";
    const sidebarNote = $(".sidebar-footer p");
    if (sidebarNote) sidebarNote.textContent = "登录后仅能访问自己的项目；项目材料保存在云端私有存储中。";
    const privacy = $(".privacy-note");
    if (privacy) {
      privacy.classList.add("remote-warning");
      privacy.lastChild.textContent = "云端版：项目材料存入 Supabase 私有存储，并受账号权限隔离；模型 API Key 不写入项目数据库。";
    }
    const modelIntro = $(".model-settings-intro");
    if (modelIntro) {
      modelIntro.textContent = "云端版通过用户自备的 OpenAI 兼容 API 推理；模型服务费用由你与提供商结算。";
    }
    if (!window.supabase?.createClient) {
      showAuthGate("登录组件暂不可用，请刷新页面后重试。");
      return;
    }
    state.llmConfig = {
      provider: "openai_compatible",
      model: "",
      base_url: "",
      api_key: "",
    };
    $("#providerOllama").closest(".model-provider-option")?.classList.add("hidden");
    state.authClient = window.supabase.createClient(
      config.supabase_url,
      config.supabase_publishable_key,
      { auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true } }
    );
    const { data, error } = await state.authClient.auth.getSession();
    if (error) {
      showAuthGate("无法读取登录状态，请重试。");
      return;
    }
    state.authClient.auth.onAuthStateChange((event, session) => {
      state.authSession = session;
      if (session && !state.appStarted) {
        void startApplication(session);
      } else if (!session && event === "SIGNED_OUT") {
        state.appStarted = false;
        state.project = null;
        state.messages = [];
        state.documents = [];
        sessionStorage.removeItem(llmConfigKey);
        state.llmConfig = { provider: "openai_compatible", model: "", base_url: "", api_key: "" };
        showAuthGate("已退出登录。");
      }
    });
    if (data.session) {
      await startApplication(data.session);
    } else {
      showAuthGate();
    }
  }

  async function submitAuthForm(event) {
    event.preventDefault();
    const email = $("#authEmail").value.trim();
    const password = $("#authPassword").value;
    const submit = $("#authSubmitBtn");
    const feedback = $("#authFeedback");
    submit.disabled = true;
    feedback.className = "auth-feedback";
    feedback.textContent = state.authMode === "signup" ? "正在创建账号…" : "正在登录…";
    try {
      const result = state.authMode === "signup"
        ? await state.authClient.auth.signUp({
            email,
            password,
            options: { emailRedirectTo: window.location.origin },
          })
        : await state.authClient.auth.signInWithPassword({ email, password });
      if (result.error) throw result.error;
      if (result.data.session) {
        await startApplication(result.data.session);
      } else if (state.authMode === "signup") {
        feedback.textContent = "账号已创建。请查收邮箱并完成验证后登录。";
        feedback.classList.add("success");
      } else {
        feedback.textContent = "登录成功，正在载入你的项目…";
      }
    } catch (error) {
      feedback.textContent = error.message || "登录失败，请检查邮箱和密码。";
      feedback.classList.add("error");
    } finally {
      submit.disabled = false;
    }
  }

  async function signOutCloudUser() {
    if (!state.authClient) return;
    const { error } = await state.authClient.auth.signOut();
    if (error) toast("退出失败：" + error.message, true);
  }

  async function refreshProjects(filterKeyword = "") {
    const response = await api("/api/projects");
    state.projectsList = response.projects || [];
    const list = $("#projectList");
    const countBadge = $("#projectCountBadge");
    if (countBadge) countBadge.textContent = state.projectsList.length;
    list.replaceChildren();

    const query = filterKeyword.trim().toLowerCase();
    const filtered = query
      ? state.projectsList.filter(p => {
          const title = (p.title || "").toLowerCase();
          const skill = (p.state?.skill_name || "").toLowerCase();
          return title.includes(query) || skill.includes(query);
        })
      : state.projectsList;

    if (!filtered.length) {
      const empty = document.createElement("div");
      empty.className = "project-list-empty";
      empty.textContent = query ? "未找到匹配的项目" : "暂无归档项目";
      list.append(empty);
      return;
    }

    for (const project of filtered) {
      const item = document.createElement("button");
      item.className = `project-item ${state.project?.id === project.id ? "active" : ""}`;

      const body = document.createElement("div");
      body.className = "proj-body";
      const titleRow = document.createElement("div");
      titleRow.className = "proj-title-row";
      const icon = document.createElement("span");
      icon.className = "proj-icon";
      const category = project.state?.skill_category || "";
      icon.textContent = category === "scholarship" ? "🎖️" : category === "practice" ? "🌾" : category === "competition" ? "🏆" : "📄";
      const name = document.createElement("span");
      name.className = "proj-name";
      name.textContent = project.title || "未命名项目";
      titleRow.append(icon, name);

      const tag = document.createElement("span");
      tag.className = `proj-skill-tag cat-${category || "other"}`;
      tag.textContent = project.state?.skill_name || "申报材料";
      body.append(titleRow, tag);

      const delBtn = document.createElement("span");
      delBtn.className = "proj-del-icon";
      delBtn.innerHTML = "×";
      delBtn.title = "删除此项目";
      delBtn.addEventListener("click", async (e) => {
        e.stopPropagation();
        if (!confirm(`确定删除项目“${project.title}”吗？`)) return;
        try {
          await api(`/api/projects/${project.id}`, { method: "DELETE" });
          if (state.project?.id === project.id) {
            showWelcomeView();
            state.project = null;
          }
          await refreshProjects($("#projectSearchInput")?.value || "");
          toast("项目已删除。");
        } catch (err) {
          toast(err.message, true);
        }
      });

      item.title = `${project.title || "项目"} (${project.state?.skill_name || "申报材料"})`;
      item.append(body, delBtn);
      item.addEventListener("click", () => loadProject(project.id));
      list.append(item);
    }
  }

  async function checkHealth() {
    try {
      showModelStatus(await api("/api/health"));
    } catch {
      if (state.llmConfig.provider === "openai_compatible") showModelStatus(null);
      else {
        $("#modelStatus").textContent = "Agent 服务暂不可用";
        $("#modelStatus").classList.add("offline");
      }
    }
  }

  function showProject() {
    $("#welcome").classList.add("hidden");
    $("#createPanel").classList.add("hidden");
    $("#workspace").classList.remove("hidden");
    $("#crumbProject").textContent = state.project?.title || "项目";
    const skillBadge = $("#crumbSkillBadge");
    if (skillBadge) {
      skillBadge.textContent = state.project?.state?.skill_name || "通用材料";
      skillBadge.classList.remove("hidden");
    }
    $("#quickExportTopBtn")?.classList.remove("hidden");
  }

  function showWelcomeView() {
    $("#workspace").classList.add("hidden");
    $("#createPanel").classList.add("hidden");
    $("#welcome").classList.remove("hidden");
    $("#crumbProject").textContent = "欢迎";
    $("#crumbSkillBadge")?.classList.add("hidden");
    $("#quickExportTopBtn")?.classList.add("hidden");
    $$(".project-item").forEach(item => item.classList.remove("active"));
  }

  async function loadProject(projectId) {
    try {
      const project = await api(`/api/projects/${projectId}`);
      state.project = project;
      try { localStorage.setItem(activeProjectKey, projectId); } catch {}
      state.documents = project.documents || [];
      state.messages = project.messages || [];
      state.outline = project.outline || [];
      state.diagrams = project.diagrams || [];
      showProject();
      configureSkillWorkspace(project);
      $("#projectHeading").textContent = project.title;
      $("#projectSkillName").textContent = project.state?.skill_name || "申报材料工作区";
      $("#projectMetaLevel").textContent = project.level || "级别暂未确定";
      $("#projectMetaDiscipline").textContent = project.discipline || "学科待补充";
      const schoolEl = $("#projectMetaSchool");
      if (schoolEl) schoolEl.textContent = project.school || "高校待补充";
      renderTemplateStatus(project);
      renderDocuments();
      renderFacts();
      renderConfirmedSources();
      renderOutline();
      renderSections();
      renderDiagrams();
      renderMessages();
      updateTemplateQuickActions(project);
      await refreshProjects();
    } catch (error) {
      toast(error.message, true);
    }
  }

  function configureSkillWorkspace(project) {
    const skillId = project?.state?.skill_id || "innovation-research";
    const skillMeta = state.skills.find((skill) => skill.id === skillId);
    const category = project?.state?.skill_category || skillMeta?.category || "";
    const researchOrCompetition = ["research", "competition"].includes(category);
    const practical = category === "practice";
    const diagramsAvailable = researchOrCompetition || practical;
    const paperSearch = $("#paperQuery")?.closest(".source-search-row");
    if (paperSearch) paperSearch.classList.toggle("hidden", !researchOrCompetition);
    const diagramTab = $('.workspace-tab-btn[data-target="diagrams-panel"]');
    if (diagramTab) diagramTab.classList.toggle("hidden", !diagramsAvailable);
    const diagramPanel = $("#diagrams-panel");
    if (diagramPanel) diagramPanel.classList.toggle("hidden", !diagramsAvailable);
    const photoTab = $('.upload-tab[data-kind="photo"]');
    if (photoTab) photoTab.classList.toggle("hidden", !(researchOrCompetition || practical));
    $("#officialQuery").placeholder = `输入「${project?.state?.skill_name || "申报材料"}」相关的学校或当年通知关键词`;
    $("#factsSummary").dataset.skillId = skillId;

    // 动态调整右侧对话快捷提示词
    const toolsRoot = $("#chatTools");
    if (toolsRoot) {
      toolsRoot.replaceChildren();
      let customPrompts = [];
      if (category === "scholarship") {
        customPrompts = [
          { label: "🎖️ 突出学业与排名优势", prompt: "请根据我的成绩与GPA排名信息，帮我撰写突出学业优异、刻苦钻研的申请段落。" },
          { label: "🤝 整理家庭经济与资助情况", prompt: "请帮我规范整理家庭经济困难依据与家庭实际开支，语言真诚朴素、数据翔实。" },
          { label: "💼 梳理勤工助学经历", prompt: "请帮我总结在校期间参加勤工助学、自立自强的具体岗位与收获体会。" },
          { label: "📋 检查书信体规范与称呼", prompt: "请帮我检查当前申请书的抬头、称呼、此致敬礼与落款格式是否符合标准公文规范。" },
          { label: "🔍 查高校奖助学金评审细则", prompt: "请帮我检索本年度高校奖学金评定的一般门槛和打分偏向。" },
        ];
      } else if (category === "practice") {
        customPrompts = [
          { label: "🌾 规划三下乡调研路线", prompt: "请帮我设计为期 7 天的社会实践调研日程、点位安排与走访对象分类。" },
          { label: "📊 设计问卷调查 5 维度", prompt: "请针对本次实践主题设计 5 个维度的问卷结构框架与抽样测算依据。" },
          { label: "🛡️ 完善安全应急防范预案", prompt: "请帮我拟定实践团队行前准备、防汛防暑与突发事件的安全防范预案。" },
          { label: "📰 梳理成果输出与宣传方案", prompt: "请帮我规划调研报告、纪实短片、主流媒体发稿等预期产出清单。" },
          { label: "💰 核算实践经费预算细目", prompt: "请按交通、食宿、物资、印刷等科目，帮我核算详细且合理的实践预算表。" },
        ];
      } else if (researchOrCompetition) {
        customPrompts = [
          { label: "⌕ 查项目材料依据", prompt: "请根据我已确认的项目材料，找出与当前项目相关的依据，并标明文件和页码。" },
          { label: "⌕ 查相关前沿论文", prompt: "请搜索与当前项目方向相关的真实论文，给出标题、作者、年份、DOI/链接和摘要；不要编造。" },
          { label: "⌕ 查官方立项通知", prompt: "请查找当前学校或官方机构发布的大创申报通知，给出年份、来源链接；没有结果就明确说查不到。" },
          { label: "💡 提炼核心科学难点", prompt: "请根据当前研究构思，帮我提炼项目的核心科学挑战与关键技术路线。" },
          { label: "⏰ 规划甘特图里程碑", prompt: "请帮我拟订一个为期一年的实施进度安排与甘特图里程碑节点。" },
        ];
      } else {
        customPrompts = [
          { label: "⭐ 提炼个人综合亮点", prompt: "请根据我的基本情况，帮我提炼出最核心的竞争优势与思想学业闪光点。" },
          { label: "🏛️ 阐明思想认识与成长", prompt: "请帮我撰写思想品德与政治素养成长的心路历程，表述庄重大方、积极向上。" },
          { label: "👥 总结学生干部履职成效", prompt: "请帮我把学生干部与服务同学的琐碎工作，量化转化为有成效的履职总结。" },
          { label: "🎯 规划下一阶段发展目标", prompt: "请帮我结合未来学业与职业规划，撰写切实可行、态度明确的承诺与展望。" },
          { label: "📋 检查材料完整性与格式", prompt: "请核对本申报材料的各个段落是否齐全、格式是否规范无错漏。" },
        ];
      }
      for (const item of customPrompts) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.textContent = item.label;
        btn.dataset.prompt = item.prompt;
        btn.addEventListener("click", () => {
          $("#chatInput").value = item.prompt;
          $("#chatInput").focus();
        });
        toolsRoot.append(btn);
      }
    }
  }

  async function renameCurrentProject() {
    if (!state.project) return;
    const currentTitle = state.project.title || "";
    const newTitle = window.prompt("请输入新的项目 / 课题名称：", currentTitle);
    if (!newTitle || newTitle.trim() === currentTitle) return;
    try {
      const updated = await api(`/api/projects/${state.project.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: newTitle.trim() }),
      });
      state.project = updated;
      $("#projectHeading").textContent = updated.title;
      $("#crumbProject").textContent = updated.title;
      await refreshProjects($("#projectSearchInput")?.value || "");
      toast("课题名称已更新。");
    } catch (err) {
      toast(err.message, true);
    }
  }

  function createPanel() {
    $("#welcome").classList.add("hidden");
    $("#workspace").classList.add("hidden");
    $("#createPanel").classList.remove("hidden");
  }

  async function startConversation() {
    $("#projectRequest").value = "";
    $("#projectSkill").value = "";
    $("#routeCandidates").replaceChildren();
    $("#routeCandidates").classList.add("hidden");
    createPanel();
    $("#projectRequest").focus();
  }

  async function loadSkills() {
    const result = await api("/api/skills");
    state.skills = result.skills || [];
    const select = $("#projectSkill");
    const first = select.options[0];
    select.replaceChildren(first);
    const groups = new Map();
    for (const skill of state.skills) {
      const category = skill.category || "other";
      if (!groups.has(category)) {
        const group = document.createElement("optgroup");
        group.label = ({
          scholarship: "奖学金", honor: "评优", political: "政治材料",
          research: "科研立项", competition: "竞赛", practice: "实践",
          military: "征兵入伍", study_abroad: "留学交流", other: "其他",
        })[category] || "其他";
        groups.set(category, group);
        select.append(group);
      }
      const option = document.createElement("option");
      option.value = skill.id;
      option.textContent = skill.name;
      groups.get(category).append(option);
    }
  }

  function showRouteCandidates(candidates, message) {
    const box = $("#routeCandidates");
    box.replaceChildren();
    const intro = document.createElement("p");
    intro.textContent = message || "请确认最符合你需求的申报赛道：";
    box.append(intro);
    for (const candidate of candidates) {
      const choice = button(candidate.name, "button button-small button-secondary");
      choice.addEventListener("click", () => {
        if (!state.pendingProject) return;
        state.pendingProject.skill_id = candidate.id;
        completeProjectCreation(state.pendingProject);
      });
      box.append(choice);
    }
    box.classList.remove("hidden");
  }

  async function completeProjectCreation(payload) {
    const submit = $('#createForm button[type="submit"]');
    submit.disabled = true;
    try {
      const project = await api("/api/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      state.pendingProject = null;
      $("#routeCandidates").classList.add("hidden");
      $("#createForm").reset();
      updateTemplateExplain();
      await refreshProjects();
      await loadProject(project.id);
      if (payload.initial_request) {
        await sendChat(null, payload.initial_request);
      }
      toast(`已进入「${project.state?.skill_name || "申报材料"}」工作区。`);
      if (payload.has_template) {
        setUploadKind("template");
        $("#documentsList").scrollIntoView({ behavior: "smooth", block: "center" });
      } else {
        $("#chatInput").focus();
      }
    } catch (error) {
      toast(error.message, true);
    } finally {
      submit.disabled = false;
    }
  }

  function updateTemplateQuickActions(project) {
    const bar = $("#templateQuickActions");
    const needsAnswer = project?.state?.template_preference === "not_asked";
    bar.classList.toggle("hidden", !needsAnswer);
    const privacy = $(".privacy-note");
    if (privacy) {
      privacy.lastChild.textContent = project?.state?.template_preference === "not_asked"
        ? "先通过对话回答模板问题；上传资料只有经你确认后才进入当前项目检索。"
        : "测试版默认本机处理。资料只有经你确认后才进入当前项目检索。";
    }
  }

  function renderTemplateStatus(project) {
    const box = $("#templateStatus");
    const template = (project.documents || []).find((document) => document.kind === "template");
    box.classList.remove("hidden", "warning", "ready");
    if (template) {
      box.classList.add("ready");
      box.textContent = template.original_name.toLowerCase().endsWith(".docx")
        ? "已上传 Word 模板：导出时会尽量在原模板字段内填写；无法识别的位置会保留并提示核对。"
        : "已上传 PDF 模板：会参考识别到的栏目生成可编辑 Word，但版式需要人工核对。";
    } else if (project.state?.template_preference === "not_asked") {
      box.textContent = "还没确认是否有学校模板；先在右侧对话回答，Agent 会根据你的选择继续。";
    } else if (project.state?.template_preference === "has_template") {
      box.classList.add("warning");
      box.textContent = "你选择了有学校模板，但还没有上传。请先在“项目材料 → 学校模板”中上传，否则只能按通用模板生成草稿。";
    } else {
      box.textContent = "当前使用通用模板。提交前请对照学校通知和官方申报表核对栏目与排版。";
    }
  }

  async function createProject(event) {
    event.preventDefault();
    const request = $("#projectRequest").value.trim();
    const manuallySelected = $("#projectSkill").value;
    if (!request && !manuallySelected) {
      toast("请先描述你要准备的材料，或手动选择一个赛道。", true);
      $("#projectRequest").focus();
      return;
    }
    const payload = {
      title: $("#projectTitle").value.trim(),
      level: $("#projectLevel").value,
      discipline: $("#projectDiscipline").value.trim(),
      school: $("#projectSchool").value.trim(),
      has_template: $('input[name="hasTemplate"]:checked')?.value === "yes",
      skill_id: manuallySelected,
      initial_request: request,
    };
    if (!manuallySelected && request) {
      const submit = $('#createForm button[type="submit"]');
      submit.disabled = true;
      try {
        const route = await api("/api/route", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query: request }),
        });
        if (route.selected) {
          payload.skill_id = route.selected.id;
        } else {
          state.pendingProject = payload;
          const candidates = route.candidates?.length
            ? route.candidates
            : state.skills.slice(0, 35).map((skill) => ({ id: skill.id, name: skill.name }));
          showRouteCandidates(candidates, route.message);
          return;
        }
      } catch (error) {
        toast(`自动识别失败：${error.message}。你可以手动选择赛道。`, true);
        return;
      } finally {
        submit.disabled = false;
      }
    }
    await completeProjectCreation(payload);
  }

  function setUploadKind(kind) {
    state.uploadKind = kind;
    $$(".upload-tab").forEach((tab) => tab.classList.toggle("active", tab.dataset.kind === kind));
    const copy = {
      source: ["把项目信息材料拖到这里", "Word、PDF、扫描件或照片 · 单个文件最大 20 MB"],
      template: ["上传学校下发的申报模板", "Word 模板尽量原位填写；PDF 模板会参考重建"],
      photo: ["上传真实实验 / 调研照片", "没有照片时 Word 会放“待补充”占位，不会生成假图"],
    }[kind];
    $("#uploadTitle").textContent = copy[0];
    $("#uploadHint").textContent = copy[1];
    $("#fileInput").accept = kind === "photo" ? ".png,.jpg,.jpeg,.webp" : ".docx,.pdf,.txt,.md,.png,.jpg,.jpeg,.webp";
  }

  async function uploadFiles(fileList, kind = state.uploadKind, fromChat = false) {
    if (!state.project || !fileList.length) return;
    if (fileList.length > 12) return toast("一次最多上传 12 个文件。", true);
    const form = new FormData();
    for (const file of fileList) form.append("files", file);
    const names = fileList.map((file) => file.name);
    const query = new URLSearchParams({ kind });
    try {
      toast(state.cloudMode ? "正在安全上传并识别材料…" : "正在本机识别文件…");
      const result = state.cloudMode
        ? await uploadFilesToCloud(fileList, kind)
        : await api(`/api/projects/${state.project.id}/documents?${query}`, { method: "POST", body: form });
      const failed = (result.documents || []).filter((d) => d.error);
      const uploaded = (result.documents || []).filter((d) => !d.error);
      await loadProject(state.project.id);
      toast(failed.length ? "部分文件未能识别，请查看提示。" : "文件已读取。请核对文字，再确认用于检索。", failed.length > 0);
      if (fromChat && uploaded.length) {
        const labels = { source: "项目信息材料", template: "学校申报模板", photo: "实验 / 调研照片" };
        const successfulNames = uploaded.map((item) => item.document?.original_name).filter(Boolean);
        await sendChat(
          undefined,
          `我刚上传了${labels[kind] || "材料"}：${(successfulNames.length ? successfulNames : names).join("、")}。请告诉我下一步怎么处理。`
        );
      }
      if (fromChat && failed.length) {
        appendMessage("assistant", `我收到文件了，但有些文件没有成功识别：${failed.map((item) => item.document?.original_name || item.original_name || item.name || "文件").join("、")}。请查看项目材料区的错误提示后重试。`);
      }
    } catch (error) {
      toast(error.message, true);
      if (fromChat) appendMessage("assistant", `上传没有完成：${error.message}`);
    }
    $("#fileInput").value = "";
    $("#chatFileInput").value = "";
  }

  async function uploadFilesToCloud(fileList, kind) {
    if (!state.authClient || !state.authSession?.user?.id) {
      throw new Error("登录状态已失效，请重新登录后上传。");
    }
    const mimeByExtension = {
      ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      ".pdf": "application/pdf",
      ".txt": "text/plain",
      ".md": "text/markdown",
      ".png": "image/png",
      ".jpg": "image/jpeg",
      ".jpeg": "image/jpeg",
      ".webp": "image/webp",
    };
    const documents = [];
    for (const file of fileList) {
      const extension = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
      const documentId = crypto.randomUUID().replaceAll("-", "");
      const storagePath = `${state.authSession.user.id}/${state.project.id}/${documentId}${extension}`;
      const contentType = file.type || mimeByExtension[extension] || "application/octet-stream";
      const { error: uploadError } = await state.authClient.storage
        .from("stardust-project-files")
        .upload(storagePath, file, { contentType, upsert: false });
      if (uploadError) {
        documents.push({ error: uploadError.message, document: { original_name: file.name } });
        continue;
      }
      try {
        const registered = await api(`/api/projects/${state.project.id}/documents/from-storage`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            document_id: documentId,
            original_name: file.name,
            storage_path: storagePath,
            kind,
            content_type: contentType,
          }),
        });
        documents.push(...(registered.documents || []));
      } catch (error) {
        await state.authClient.storage.from("stardust-project-files").remove([storagePath]);
        documents.push({ error: error.message, document: { original_name: file.name } });
      }
    }
    return { documents };
  }

  function chatUploadAccept(kind) {
    if (kind === "photo") return ".png,.jpg,.jpeg,.webp";
    if (kind === "template") return ".docx,.pdf";
    return ".docx,.pdf,.txt,.md,.png,.jpg,.jpeg,.webp";
  }

  function renderDocuments() {
    const list = $("#documentsList");
    list.replaceChildren();
    if (!state.documents.length) return;
    for (const doc of state.documents) {
      const card = document.createElement("div");
      card.className = "document-card";
      const top = document.createElement("div");
      top.className = "doc-top";
      const type = document.createElement("div");
      type.className = "doc-type";
      type.textContent = (doc.original_name.split(".").pop() || "FILE").slice(0, 4).toUpperCase();
      const name = document.createElement("div");
      name.className = "doc-name";
      name.textContent = doc.original_name;
      const badge = document.createElement("span");
      badge.className = `doc-state ${doc.confirmed ? "confirmed" : ""}`;
      badge.textContent = doc.kind === "template" ? "模板" : doc.confirmed ? "已确认" : "待核对";
      top.append(type, name, badge);
      card.append(top);
      if (doc.kind === "photo") {
        const image = document.createElement("img");
        image.src = `/api/documents/${doc.id}/file`;
        image.alt = doc.original_name;
        image.style.cssText = "max-width:100%;max-height:220px;object-fit:contain;margin-top:10px;border-radius:8px;background:#f8fafc;border:1px solid #e2e8f0";
        card.append(image);
      }
      if (doc.extraction_warning) {
        const warning = document.createElement("div");
        warning.className = "doc-warning";
        warning.textContent = doc.extraction_warning;
        card.append(warning);
      }
      const text = document.createElement("textarea");
      text.className = "doc-text";
      text.rows = Math.min(7, Math.max(3, Math.ceil((doc.extracted_text || "").length / 95)));
      text.value = doc.extracted_text || (doc.extraction_status === "error" ? "识别失败，请重新上传或手动补充内容。" : "");
      text.readOnly = doc.kind === "template" || doc.confirmed;
      text.setAttribute("aria-label", `识别文字：${doc.original_name}`);
      card.append(text);
      const actions = document.createElement("div");
      actions.className = "doc-actions";
      if (doc.kind !== "template" && !doc.confirmed) {
        const confirm = button("确认文字并加入检索", "button button-small button-primary");
        confirm.addEventListener("click", async () => {
          try {
            await api(`/api/documents/${doc.id}/confirm`, {
              method: "PATCH",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ confirmed: true, corrected_text: text.value }),
            });
            await loadProject(state.project.id);
            toast("材料已确认，可用于当前项目检索。");
          } catch (error) {
            toast(error.message, true);
          }
        });
        actions.append(confirm);
      } else if (doc.kind !== "template") {
        const edit = button("修改识别文字", "button button-small button-secondary");
        edit.addEventListener("click", () => {
          text.readOnly = !text.readOnly;
          if (!text.readOnly) {
            const save = button("保存修改", "button button-small button-primary");
            save.addEventListener("click", async () => {
              try {
                await api(`/api/documents/${doc.id}/confirm`, {
                  method: "PATCH",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ confirmed: true, corrected_text: text.value }),
                });
                await loadProject(state.project.id);
                toast("识别文字已更新。");
              } catch (error) {
                toast(error.message, true);
              }
            });
            actions.append(save);
          }
        });
        actions.append(edit);
      }
      const remove = button("移除", "button button-small button-quiet");
      remove.addEventListener("click", async () => {
        if (!confirm(`确定从本项目移除“${doc.original_name}”吗？`)) return;
        try {
          await api(`/api/documents/${doc.id}`, { method: "DELETE" });
          await loadProject(state.project.id);
          toast("材料和对应索引已删除。");
        } catch (error) {
          toast(error.message, true);
        }
      });
      actions.append(remove);
      card.append(actions);
      list.append(card);
    }
  }

  function renderFacts() {
    const facts = { ...(state.project?.state?.confirmed_facts || {}) };
    const factSources = state.project?.state?.fact_sources || {};
    const summary = $("#factsSummary");
    summary.replaceChildren();
    const researchKeys = ["project_name", "problem", "target_user", "method", "foundation", "goal", "expected_output", "constraints", "duration", "budget", "leader_name", "advisor_name", "team"];
    const keys = state.project?.state?.skill_id === "innovation-research"
      ? [...new Set([...researchKeys, ...Object.keys(facts)])]
      : Object.keys(facts);
    for (const key of keys) {
      if (key.startsWith("skill_") || key.startsWith("template_") || key.startsWith("fact_")) continue;
      const box = document.createElement("div");
      box.className = `fact-chip ${facts[key] ? "" : "missing"}`;
      const label = document.createElement("small");
      label.textContent = labels[key] || key.replace(/_/g, " ");
      const value = document.createElement("span");
      value.textContent = facts[key] || "待补充";
      box.append(label, value);
      if (factSources[key]) {
        const source = document.createElement("small");
        source.className = "fact-source";
        source.textContent = `依据：“${factSources[key]}”`;
        box.append(source);
      }
      summary.append(box);
      const input = $(`[data-fact="${key}"]`);
      if (input) input.value = facts[key] || "";
    }
    const dynamic = $("#dynamicFactsGrid");
    if (dynamic) {
      dynamic.replaceChildren();
      for (const [key, value] of Object.entries(facts)) {
        if (key in labels || key.startsWith("skill_") || key.startsWith("template_") || key.startsWith("fact_")) continue;
        appendDynamicFact(key, value);
      }
    }
    $$("[data-project]").forEach((field) => {
      field.value = state.project?.[field.dataset.project] || "";
    });
  }

  function appendDynamicFact(key, value = "") {
    const grid = $("#dynamicFactsGrid");
    if (!grid) return;
    const field = document.createElement("label");
    field.className = "field";
    const caption = document.createElement("span");
    caption.textContent = `赛道信息 · ${key.replace(/_/g, " ")}`;
    const input = document.createElement("textarea");
    input.dataset.fact = key;
    input.rows = 2;
    input.value = value || "";
    field.append(caption, input);
    grid.append(field);
  }

  function addCustomFact() {
    const facts = state.project?.state?.confirmed_facts || {};
    let index = 1;
    while (`custom_field_${index}` in facts || $(`[data-fact="custom_field_${index}"]`)) index += 1;
    appendDynamicFact(`custom_field_${index}`);
    $("#dynamicFactsGrid").lastElementChild?.querySelector("textarea")?.focus();
  }

  function renderConfirmedSources() {
    const target = $("#confirmedSources");
    target.replaceChildren();
    const stateData = state.project?.state || {};
    const all = [
      ...(stateData.references || []).map((item) => ({ ...item, _kind: "paper" })),
      ...(stateData.official_sources || []).map((item) => ({ ...item, _kind: "official" })),
    ];
    if (!all.length) return;
    const label = document.createElement("div");
    label.className = "inline-hint";
    label.style.marginTop = "12px";
    label.style.fontWeight = "600";
    label.textContent = "✓ 已由你核验确认的立项依据";
    target.append(label);
    for (const source of all) {
      const line = document.createElement("div");
      line.className = "source-card";
      const title = document.createElement("h3");
      title.textContent = `${source._kind === "paper" ? "学术文献" : "官方立项通知"}：${source.title || "未命名来源"}`;
      const link = document.createElement("a");
      link.href = source.url || (source.doi ? `https://doi.org/${source.doi}` : "#");
      link.textContent = link.href === "#" ? "缺少链接" : source.url || `DOI: ${source.doi}`;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      line.append(title, link);
      target.append(line);
    }
  }

  function renderSourceCards(items, kind) {
    const target = $("#sourceResults");
    target.replaceChildren();
    if (!items?.length) {
      const note = document.createElement("div");
      note.className = "empty-note";
      note.textContent = "没有找到匹配结果。可以更换检索关键词，或直接粘贴官网链接。";
      target.append(note);
      return;
    }
    for (const source of items) {
      const card = document.createElement("div");
      card.className = "source-card";
      const title = document.createElement("h3");
      title.textContent = source.title || "未命名来源";
      const details = document.createElement("p");
      details.textContent = kind === "paper"
        ? `${(source.authors || []).join(", ") || "作者待核"} · ${source.year || "年份待核"} · ${source.venue || "出版信息待核"}${source.doi ? ` · DOI ${source.doi}` : ""}`
        : `${source.source_domain || ""} · ${source.published_at || "发布日期待核"} · ${source.snippet || ""}`;
      card.append(title, details);
      if (source.url) {
        const link = document.createElement("a");
        link.href = source.url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = source.url;
        card.append(link);
      }
      const warning = document.createElement("p");
      warning.className = "source-warning";
      warning.textContent = kind === "paper"
        ? (source.content_checked
          ? "检索到摘要/元数据，不代表已读全文；请先核对内容。"
          : "只有题名/元数据，不能据此写研究结论。")
        : "搜索摘要不是通知全文；请打开原始页面核对年份和适用对象。";
      card.append(warning);
      const add = button("我已核对，加入来源", "button button-small button-primary");
      add.addEventListener("click", () => confirmSource(source, kind, add));
      card.append(add);
      target.append(card);
    }
  }

  async function confirmSource(source, kind, btn) {
    btn.disabled = true;
    try {
      const yearValue = typeof source.year === "number"
        ? source.year
        : (/^\d{4}$/.test(String(source.year || "")) ? Number(source.year) : null);
      await api(`/api/projects/${state.project.id}/references/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: source.title || "未命名来源",
          authors: source.authors || [],
          year: yearValue,
          venue: source.venue || "",
          doi: source.doi || "",
          url: source.url || "",
          abstract: source.abstract || source.snippet || "",
          source_type: kind === "paper" ? "paper" : "official",
          published_at: source.published_at || "",
        }),
      });
      await loadProject(state.project.id);
      toast("来源已加入项目；仍请核对其是否支持正文中的具体论断。");
    } catch (error) {
      toast(error.message, true);
      btn.disabled = false;
    }
  }

  async function searchSources(kind) {
    const input = kind === "paper" ? $("#paperQuery") : $("#officialQuery");
    const query = input.value.trim();
    if (query.length < 2) return toast("请输入至少两个字的关键词。", true);
    const btn = kind === "paper" ? $("#paperSearchBtn") : $("#officialSearchBtn");
    btn.disabled = true;
    btn.textContent = "搜索中…";
    $("#sourceResults").replaceChildren();
    const loading = document.createElement("div");
    loading.className = "source-loading";
    loading.textContent = kind === "paper" ? "正在查 Crossref 论文元数据…" : "正在检索官方域名…";
    $("#sourceResults").append(loading);
    try {
      const endpoint = kind === "paper" ? "papers" : "official";
      const result = await api(`/api/projects/${state.project.id}/search/${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
      });
      renderSourceCards(result.results, kind);
      if (result.error) toast(result.error, true);
    } catch (error) {
      toast(error.message, true);
      $("#sourceResults").replaceChildren();
    } finally {
      btn.disabled = false;
      btn.textContent = kind === "paper" ? "检索学术论文" : "查官方指南";
    }
  }

  async function previewOfficialUrl() {
    const url = $("#officialUrl").value.trim();
    if (!url) return toast("请先粘贴学校或政府官网的 HTTPS 通知链接。", true);
    const btn = $("#officialUrlBtn");
    btn.disabled = true;
    btn.textContent = "读取中…";
    try {
      const result = await api(`/api/projects/${state.project.id}/official/preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      const target = $("#sourceResults");
      target.replaceChildren();
      const card = document.createElement("div");
      card.className = "source-card";
      const title = document.createElement("h3");
      title.textContent = result.title || "官方通知";
      const link = document.createElement("a");
      link.href = result.url;
      link.textContent = result.url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      const excerpt = document.createElement("p");
      excerpt.textContent = (result.content || "").slice(0, 4000);
      const date = document.createElement("p");
      date.textContent = result.published_at
        ? `页面发布日期：${result.published_at} · 抓取时间 UTC：${result.retrieved_at_utc}`
        : `页面未标明发布日期 · 抓取时间 UTC：${result.retrieved_at_utc}`;
      const warning = document.createElement("p");
      warning.className = "source-warning";
      warning.textContent = result.warning || "请核对页面年份和适用范围。";
      const add = button("我已核对，将全文加入当前项目材料", "button button-small button-primary");
      add.addEventListener("click", async () => {
        add.disabled = true;
        try {
          const imported = await api(`/api/projects/${state.project.id}/official/import`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url: result.url }),
          });
          await loadProject(state.project.id);
          toast(imported.note || "官方通知已读取；确认文字后才能进入 RAG。");
        } catch (error) {
          toast(error.message, true);
          add.disabled = false;
        }
      });
      card.append(title, link, date, excerpt, warning, add);
      target.append(card);
    } catch (error) {
      toast(error.message, true);
    } finally {
      btn.disabled = false;
      btn.textContent = "直接抓取原文";
    }
  }

  async function saveFacts() {
    const payload = {};
    $$("[data-fact]").forEach((field) => {
      if (field.value.trim()) payload[field.dataset.fact] = field.value.trim();
    });
    const projectFields = {};
    $$("[data-project]").forEach((field) => {
      projectFields[field.dataset.project] = field.value.trim();
    });
    try {
      await api(`/api/projects/${state.project.id}/facts`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      await api(`/api/projects/${state.project.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(projectFields),
      });
      await loadProject(state.project.id);
      $("#factsEditor").classList.add("hidden");
      toast("已保存为你确认的项目事实。");
    } catch (error) {
      toast(error.message, true);
    }
  }

  async function proposeFacts() {
    const btn = $("#proposeFactsBtn");
    btn.disabled = true;
    btn.textContent = "提取中…";
    const root = $("#factCandidates");
    root.replaceChildren();
    try {
      const result = await api(`/api/projects/${state.project.id}/facts/propose`, { method: "POST" });
      if (!result.candidates?.length) {
        const note = document.createElement("div");
        note.className = "empty-note";
        note.textContent = "没有找到带有明确原文依据的新事实。你可以在“编辑”中手动补充并确认。";
        root.append(note);
        return;
      }
      for (const candidate of result.candidates) {
        const card = document.createElement("div");
        card.className = "fact-candidate";
        const title = document.createElement("strong");
        title.textContent = labels[candidate.key] || candidate.key;
        const value = document.createElement("p");
        value.textContent = candidate.value;
        const evidence = document.createElement("small");
        evidence.textContent = `原文依据：“${candidate.source_quote}”`;
        const confirm = button("我已核对，确认保存", "button button-small button-primary");
        confirm.addEventListener("click", async () => {
          confirm.disabled = true;
          try {
            await api(`/api/projects/${state.project.id}/facts/confirm`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(candidate),
            });
            card.remove();
            await loadProject(state.project.id);
            toast("已保存你确认的项目事实。");
          } catch (error) {
            toast(error.message, true);
            confirm.disabled = false;
          }
        });
        card.append(title, value, evidence, confirm);
        root.append(card);
      }
    } catch (error) {
      toast(error.message, true);
    } finally {
      btn.disabled = false;
      btn.textContent = "从对话提取候选事实";
    }
  }

  async function generateOutline() {
    const btn = $("#generateOutlineBtn");
    btn.disabled = true;
    btn.textContent = "正在整理…";
    try {
      const result = await api(`/api/projects/${state.project.id}/outline/generate`, { method: "POST" });
      state.outline = result.outline;
      renderOutline();
      $("#outlineActions").classList.remove("hidden");
      $("#outlineWarning").textContent = result.warning || "";
    } catch (error) {
      toast(error.message, true);
    } finally {
      btn.disabled = false;
      btn.textContent = "拟一份目录";
    }
  }

  function renderOutline() {
    const list = $("#outlineList");
    list.replaceChildren();
    if (!state.outline?.length) {
      list.className = "outline-list empty-note";
      list.textContent = "还没有目录。点击“拟一份目录”开始。";
      $("#outlineActions").classList.add("hidden");
      return;
    }
    list.className = "outline-list";
    state.outline.forEach((section, index) => {
      const row = document.createElement("div");
      row.className = "outline-row";
      const mark = document.createElement("span");
      mark.className = "drag-mark";
      mark.textContent = String(index + 1).padStart(2, "0");
      const input = document.createElement("input");
      input.value = section.title;
      input.addEventListener("input", () => { section.title = input.value; });
      const up = button("↑", "remove-outline");
      up.title = "上移";
      up.addEventListener("click", () => {
        if (index === 0) return;
        [state.outline[index - 1], state.outline[index]] = [state.outline[index], state.outline[index - 1]];
        renderOutline();
      });
      const remove = button("×", "remove-outline");
      remove.title = "删除章节";
      remove.addEventListener("click", () => {
        state.outline.splice(index, 1);
        renderOutline();
      });
      row.append(mark, input, up, remove);
      list.append(row);
    });
    const add = button("＋ 添加章节", "button button-small button-quiet");
    add.addEventListener("click", () => {
      state.outline.push({ id: `section_${Date.now()}`, title: "新章节" });
      renderOutline();
    });
    list.append(add);
    $("#outlineActions").classList.remove("hidden");
  }

  async function saveOutline() {
    try {
      const result = await api(`/api/projects/${state.project.id}/outline`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ outline: state.outline }),
      });
      state.outline = result.outline;
      $("#outlineActions").classList.add("hidden");
      renderOutline();
      renderSections();
      toast("目录已确认。现在可以逐章生成或编辑。");
    } catch (error) {
      toast(error.message, true);
    }
  }

  function renderSections() {
    const root = $("#draftSections");
    root.replaceChildren();
    if (!state.outline?.length) {
      const note = document.createElement("div");
      note.className = "empty-note";
      note.textContent = "确认目录后，这里会出现章节编辑器。";
      root.append(note);
      return;
    }
    for (const section of state.outline) {
      const wrapper = document.createElement("div");
      wrapper.className = "draft-section";
      const head = document.createElement("div");
      head.className = "draft-section-head";

      const titleGroup = document.createElement("div");
      titleGroup.className = "draft-title-group";
      const foldToggle = document.createElement("button");
      foldToggle.type = "button";
      foldToggle.className = "fold-toggle-btn";
      foldToggle.textContent = "▼";
      foldToggle.title = "展开/折叠章节内容";

      const title = document.createElement("strong");
      title.textContent = section.title;

      const wordBadge = document.createElement("span");
      wordBadge.className = "section-word-badge";
      const initialWords = countWords(state.project.sections?.[section.id] || "");
      wordBadge.textContent = `${initialWords} 字`;

      titleGroup.append(foldToggle, title, wordBadge);

      const actions = document.createElement("div");
      actions.className = "draft-section-actions";

      const copy = button("📋 复制", "button button-small button-quiet");
      copy.title = "复制本章节草稿正文到剪贴板";

      const generate = button("生成草稿", "button button-small button-secondary");
      const save = button("保存", "button button-small button-primary");
      actions.append(copy, generate, save);
      head.append(titleGroup, actions);

      const bodyWrapper = document.createElement("div");
      bodyWrapper.className = "draft-section-body";

      const editor = document.createElement("textarea");
      editor.value = state.project.sections?.[section.id] || "";
      editor.placeholder = "点击“生成草稿”，或直接在这里撰写。没有依据的内容标为待补充。";

      editor.addEventListener("input", () => {
        wordBadge.textContent = `${countWords(editor.value)} 字`;
      });

      editor.addEventListener("keydown", (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === "s") {
          e.preventDefault();
          save.click();
        }
      });

      foldToggle.addEventListener("click", () => {
        const isFolded = bodyWrapper.classList.toggle("folded");
        foldToggle.textContent = isFolded ? "▶" : "▼";
      });

      const sources = document.createElement("div");
      sources.className = "source-hints";
      sources.textContent = "尚无本章节材料来源标记";

      copy.addEventListener("click", async () => {
        if (!editor.value) {
          toast("当前章节内容为空，暂无可复制文本", true);
          return;
        }
        try {
          await navigator.clipboard.writeText(editor.value);
          toast(`已复制“${section.title}”正文`);
        } catch {
          editor.select();
          document.execCommand("copy");
          toast(`已复制“${section.title}”正文`);
        }
      });

      generate.addEventListener("click", async () => {
        generate.disabled = true;
        generate.textContent = "生成中…";
        wrapper.classList.add("generating");
        try {
          const result = await api(`/api/projects/${state.project.id}/sections/${section.id}/generate`, { method: "POST" });
          editor.value = result.content;
          wordBadge.textContent = `${countWords(result.content)} 字`;
          const evidence = (result.evidence || []).map((e) => `${e.source_name} · ${e.source_ref}`).join("；");
          sources.textContent = evidence ? `检索依据：${evidence}` : "未检索到可用材料；请补充事实或保留“待补充”标记。";
          state.project.sections = state.project.sections || {};
          state.project.sections[section.id] = result.content;
          toast("章节草稿已生成，记得核对并保存修改。");
        } catch (error) {
          toast(error.message, true);
        } finally {
          generate.disabled = false;
          generate.textContent = "生成草稿";
          wrapper.classList.remove("generating");
        }
      });
      save.addEventListener("click", async () => {
        try {
          await api(`/api/projects/${state.project.id}/sections/${section.id}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ content: editor.value }),
          });
          state.project.sections = state.project.sections || {};
          state.project.sections[section.id] = editor.value;
          toast(`已保存“${section.title}”。`);
        } catch (error) {
          toast(error.message, true);
        }
      });

      bodyWrapper.append(editor, sources);
      wrapper.append(head, bodyWrapper);
      root.append(wrapper);
    }
  }

  async function proposeDiagram() {
    const btn = $("#proposeDiagramBtn");
    btn.disabled = true;
    btn.textContent = "请稍候…";
    try {
      const result = await api(`/api/projects/${state.project.id}/diagrams/propose`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: $("#diagramType").value }),
      });
      $("#diagramTitle").value = result.title;
      $("#diagramNodes").value = result.nodes.join("\n");
      $("#diagramEditor").classList.remove("hidden");
      toast("图表节点已拟好，请修改和确认后再生成。");
    } catch (error) {
      toast(error.message, true);
    } finally {
      btn.disabled = false;
      btn.textContent = "请 Agent 提建议";
    }
  }

  async function saveDiagram() {
    const nodes = $("#diagramNodes").value.split(/\r?\n/).map((n) => n.trim()).filter(Boolean);
    try {
      const result = await api(`/api/projects/${state.project.id}/diagrams`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: $("#diagramTitle").value || $("#diagramType").value,
          nodes,
          diagram_id: state.editingDiagramId,
        }),
      });
      state.project.diagrams = state.project.diagrams || [];
      const diagram = result.diagram;
      if (diagram.preview) diagram.preview_url = `/api/projects/${state.project.id}/diagrams/${diagram.id}/preview`;
      state.project.diagrams = state.project.diagrams.filter((d) => d.id !== diagram.id).concat(diagram);
      state.diagrams = state.project.diagrams;
      renderDiagrams();
      $("#diagramEditor").classList.add("hidden");
      state.editingDiagramId = "";
      $("#saveDiagramBtn").textContent = "确认并生成图";
      toast(result.warning || "图表已保存。");
    } catch (error) {
      toast(error.message, true);
    }
  }

  function renderDiagrams() {
    const gallery = $("#diagramGallery");
    gallery.replaceChildren();
    for (const diagram of state.diagrams || []) {
      const card = document.createElement("div");
      card.className = "diagram-card";
      const title = document.createElement("h3");
      title.textContent = diagram.title;
      card.append(title);
      if (diagram.preview || diagram.preview_url) {
        const image = document.createElement("img");
        image.src = diagram.preview_url || `/api/projects/${state.project.id}/diagrams/${diagram.id}/preview`;
        image.alt = diagram.title;
        card.append(image);
      }
      const steps = document.createElement("p");
      steps.textContent = (diagram.nodes || []).join(" → ");
      const edit = button("编辑步骤", "button button-small button-secondary");
      edit.addEventListener("click", () => {
        state.editingDiagramId = diagram.id;
        $("#diagramTitle").value = diagram.title;
        $("#diagramNodes").value = (diagram.nodes || []).join("\n");
        $("#diagramEditor").classList.remove("hidden");
        $("#saveDiagramBtn").textContent = "保存图表修改";
        $("#diagramEditor").scrollIntoView({ behavior: "smooth", block: "center" });
      });
      card.append(steps, edit);
      gallery.append(card);
    }
  }

  function renderMessages() {
    const root = $("#chatMessages");
    root.replaceChildren();
    if (!(state.messages || []).length) {
      appendMessage(
        "assistant",
        state.project?.state?.template_preference === "not_asked"
          ? `开始准备「${state.project?.state?.skill_name || "申报材料"}」前，想先确认你是否有学校或单位下发的模板？`
          : `你好！我是 **Stardust Agent** 申报材料助手，将按「${state.project?.state?.skill_name || "当前赛道"}」要求协助你。你可以先描述目标，或上传已有材料。`
      );
      return;
    }
    for (const message of state.messages || []) appendMessage(message.role, message.content);
  }

  function appendMessage(role, text) {
    const root = $("#chatMessages");
    const row = document.createElement("div");
    row.className = `message ${role === "user" ? "user" : "assistant"}`;
    if (role !== "user") {
      const avatar = document.createElement("div");
      avatar.className = "message-avatar";
      avatar.textContent = "✦";
      row.append(avatar);
    }
    const bubble = document.createElement("div");
    bubble.className = "message-bubble";
    if (role === "assistant") {
      bubble.innerHTML = renderMarkdownSafe(text);
    } else {
      bubble.textContent = text;
    }
    row.append(bubble);
    root.append(row);
    root.scrollTop = root.scrollHeight;
    return row;
  }

  async function sendChat(event, messageOverride = null) {
    event?.preventDefault();
    const input = $("#chatInput");
    const message = messageOverride === null ? input.value.trim() : messageOverride.trim();
    if (!message || !state.project) return;
    if (messageOverride === null) input.value = "";
    appendMessage("user", message);
    const pending = appendMessage("assistant", "正在整理并按需检索项目材料与学术依据…");
    pending.classList.add("thinking");
    try {
      const result = await api(`/api/projects/${state.project.id}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      });
      pending.remove();
      appendMessage("assistant", result.message || "本轮没有生成文字。");
      state.messages.push({ role: "user", content: message }, { role: "assistant", content: result.message || "" });
      if (result.setup_updated || (result.tool_calls || []).some((name) => ["save_project_fact", "save_section"].includes(name))) {
        await loadProject(state.project.id);
      }
      await refreshProjects();
    } catch (error) {
      pending.remove();
      const projectId = state.project.id;
      await loadProject(projectId);
      appendMessage("assistant", `暂时无法完成：${error.message}`);
    }
  }

  async function validate() {
    try {
      const result = await api(`/api/projects/${state.project.id}/validate`, { method: "POST" });
      const box = $("#validationResult");
      box.replaceChildren();
      box.classList.remove("hidden", "pass", "warn");
      box.classList.add(result.passed ? "pass" : "warn");
      const title = document.createElement("strong");
      title.textContent = result.passed ? "基础检查通过" : "草稿仍有待补充项";
      box.append(title);
      const list = document.createElement("ul");
      for (const missing of result.missing_facts || []) {
        const item = document.createElement("li");
        item.textContent = missing.label;
        list.append(item);
      }
      for (const name of result.unconfirmed_documents || []) {
        const item = document.createElement("li");
        item.textContent = `未确认材料：${name}`;
        list.append(item);
      }
      for (const section of result.missing_sections || []) {
        const item = document.createElement("li");
        item.textContent = `未填写章节：${section}`;
        list.append(item);
      }
      for (const warning of result.consistency_warnings || []) {
        const item = document.createElement("li");
        item.textContent = warning;
        list.append(item);
      }
      for (const item of result.low_confidence_ocr || []) {
        const li = document.createElement("li");
        li.textContent = `OCR 低置信度：${item.name}（${item.count} 行）`;
        list.append(li);
      }
      const photo = document.createElement("li");
      photo.textContent = result.photo_notice;
      list.append(photo);
      box.append(list);
      if (result.draft_notice) {
        const note = document.createElement("div");
        note.textContent = result.draft_notice;
        box.append(note);
      }
    } catch (error) {
      toast(error.message, true);
    }
  }

  async function runReview() {
    const buttonNode = $("#reviewBtn");
    buttonNode.disabled = true;
    buttonNode.textContent = "评审中…";
    try {
      const result = await api(`/api/projects/${state.project.id}/review`, { method: "POST" });
      if (result.error) throw new Error(result.error);
      const report = result.report || {};
      const box = $("#reviewResult");
      box.replaceChildren();
      box.classList.remove("hidden");
      const summary = document.createElement("div");
      const total = report.total_score ?? "—";
      const grade = report.grade ?? "—";
      const summaryText = document.createElement("strong");
      summaryText.textContent = `模拟结果：${String(total)} / ${String(report.max_score ?? 100)} · ${String(grade)}`;
      summary.append(summaryText);
      box.append(summary);
      for (const dimension of report.dimensions || []) {
        const row = document.createElement("div");
        row.className = "review-dimension";
        const label = document.createElement("b");
        label.textContent = `${dimension.name || "评审维度"}：${dimension.weighted_score ?? dimension.score ?? "—"}`;
        const detail = document.createElement("div");
        detail.textContent = dimension.comment || "";
        row.append(label, detail);
        box.append(row);
      }
      const note = document.createElement("div");
      note.className = "inline-hint";
      note.textContent = result.notice || "结果仅供修改参考。";
      box.append(note);
    } catch (error) {
      toast(error.message, true);
    } finally {
      buttonNode.disabled = false;
      buttonNode.textContent = "开启模拟评审";
    }
  }

  async function exportDoc() {
    const btn = $("#exportBtn");
    btn.disabled = true;
    btn.textContent = "正在生成…";
    try {
      const result = await api(`/api/projects/${state.project.id}/export`, { method: "POST" });
      $("#exportResult").replaceChildren();
      const text = document.createElement("span");
      text.textContent = result.warnings?.length ? `已生成草稿。${result.warnings.join(" ")}` : "Word 草稿已生成。";
      const link = document.createElement("a");
      link.href = result.download_url;
      link.textContent = "下载 Word 申报书";
      link.download = `${state.project?.state?.skill_name || "申报材料"}草稿.docx`;
      $("#exportResult").append(text, link);
      toast("Word 草稿已生成。提交前请核对学校要求。");
    } catch (error) {
      toast(error.message, true);
    } finally {
      btn.disabled = false;
      btn.innerHTML = '生成并下载 Word 申报书 <span>↓</span>';
    }
  }

  async function deleteCurrentProject() {
    if (!state.project || !confirm(`确定删除“${state.project.title}”及其本机材料吗？删除后无法恢复。`)) return;
    try {
      await api(`/api/projects/${state.project.id}`, { method: "DELETE" });
      state.project = null;
      await refreshProjects();
      $("#workspace").classList.add("hidden");
      $("#welcome").classList.remove("hidden");
      $("#crumbProject").textContent = "欢迎";
      toast("项目和关联材料已从本机删除。");
    } catch (error) {
      toast(error.message, true);
    }
  }

  function toggleChatColumn() {
    const grid = $("#workspaceGrid");
    if (!grid) return;
    state.chatCollapsed = !state.chatCollapsed;
    grid.classList.toggle("chat-collapsed", state.chatCollapsed);
    const btn = $("#toggleChatBtn");
    if (btn) {
      btn.textContent = state.chatCollapsed ? "💬 展开助理" : "💬 对话助理";
    }
  }

  function handleTabNavigation(targetId) {
    state.activeTab = targetId;
    $$(".workspace-tab-btn").forEach(btn => {
      btn.classList.toggle("active", btn.dataset.target === targetId);
    });
    const panels = $$(".workspace-main .panel");
    if (targetId === "all") {
      panels.forEach(panel => panel.classList.remove("hidden"));
    } else {
      panels.forEach(panel => {
        const isMatch = panel.id === targetId || panel.classList.contains(targetId);
        panel.classList.toggle("hidden", !isMatch);
      });
      const targetPanel = $(`#${targetId}`);
      if (targetPanel) {
        targetPanel.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    }
  }

  function setupResizeHandles() {
    const navHandle = $("#navResizeHandle");
    const workspaceHandle = $("#workspaceResizeHandle");

    if (navHandle) {
      let isDraggingNav = false;
      navHandle.addEventListener("mousedown", (e) => {
        isDraggingNav = true;
        navHandle.classList.add("active");
        document.body.style.cursor = "col-resize";
        document.body.style.userSelect = "none";
      });

      window.addEventListener("mousemove", (e) => {
        if (!isDraggingNav) return;
        const newWidth = Math.max(180, Math.min(480, e.clientX));
        document.documentElement.style.setProperty("--sidebar-width", `${newWidth}px`);
      });

      window.addEventListener("mouseup", () => {
        if (isDraggingNav) {
          isDraggingNav = false;
          navHandle.classList.remove("active");
          document.body.style.cursor = "";
          document.body.style.userSelect = "";
        }
      });
    }

    if (workspaceHandle) {
      let isDraggingWorkspace = false;
      workspaceHandle.addEventListener("mousedown", (e) => {
        isDraggingWorkspace = true;
        workspaceHandle.classList.add("active");
        document.body.style.cursor = "col-resize";
        document.body.style.userSelect = "none";
      });

      window.addEventListener("mousemove", (e) => {
        if (!isDraggingWorkspace) return;
        const windowWidth = window.innerWidth;
        const chatWidth = Math.max(280, Math.min(650, windowWidth - e.clientX - 32));
        const grid = $("#workspaceGrid");
        if (grid && !state.chatCollapsed) {
          grid.style.gridTemplateColumns = `minmax(0, 1.25fr) 4px ${chatWidth}px`;
        }
      });

      window.addEventListener("mouseup", () => {
        if (isDraggingWorkspace) {
          isDraggingWorkspace = false;
          workspaceHandle.classList.remove("active");
          document.body.style.cursor = "";
          document.body.style.userSelect = "";
        }
      });
    }
  }

  function bindEvents() {
    $("#newProjectBtn").addEventListener("click", startConversation);
    $("#welcomeCreateBtn").addEventListener("click", startConversation);
    $("#welcomeSetupBtn").addEventListener("click", createPanel);
    $("#heroStartBtn")?.addEventListener("click", triggerHeroStart);
    $("#heroProjectRequest")?.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        triggerHeroStart();
      }
    });
    $$(".quick-tag-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        const query = btn.dataset.query || btn.textContent.trim();
        const heroInput = $("#heroProjectRequest");
        if (heroInput) {
          heroInput.value = query;
          triggerHeroStart();
        }
      });
    });
    $("#projectSearchInput")?.addEventListener("input", (e) => {
      refreshProjects(e.target.value);
    });
    $("#homeBreadcrumbBtn")?.addEventListener("click", showWelcomeView);
    $("#quickExportTopBtn")?.addEventListener("click", exportDoc);
    $("#headingExportBtn")?.addEventListener("click", exportDoc);
    $("#renameProjectBtn")?.addEventListener("click", renameCurrentProject);
    $("#projectHeading")?.addEventListener("click", renameCurrentProject);
    $("#closeCreateBtn").addEventListener("click", () => {
      $("#createPanel").classList.add("hidden");
      $("#welcome").classList.remove("hidden");
    });
    $("#createForm").addEventListener("submit", createProject);
    $$('input[name="hasTemplate"]').forEach((radio) => radio.addEventListener("change", updateTemplateExplain));
    $$(".upload-tab").forEach((tab) => tab.addEventListener("click", () => setUploadKind(tab.dataset.kind)));
    $("#chooseFileBtn").addEventListener("click", () => $("#fileInput").click());
    $("#fileInput").addEventListener("change", (event) => uploadFiles([...event.target.files]));
    $("#chatAttachBtn").addEventListener("click", () => $("#chatFileInput").click());
    $("#chatUploadKind").addEventListener("change", (event) => {
      $("#chatFileInput").accept = chatUploadAccept(event.target.value);
    });
    $("#chatFileInput").addEventListener("change", (event) => {
      uploadFiles([...event.target.files], $("#chatUploadKind").value, true);
    });
    $("#dropZone").addEventListener("dragover", (event) => { event.preventDefault(); event.currentTarget.classList.add("dragover"); });
    $("#dropZone").addEventListener("dragleave", (event) => event.currentTarget.classList.remove("dragover"));
    $("#dropZone").addEventListener("drop", (event) => {
      event.preventDefault();
      event.currentTarget.classList.remove("dragover");
      uploadFiles([...event.dataTransfer.files]);
    });
    $("#editFactsBtn").addEventListener("click", () => {
      $("#factsEditor").classList.toggle("hidden");
      renderFacts();
    });
    $("#addFactBtn").addEventListener("click", addCustomFact);
    $("#saveFactsBtn").addEventListener("click", saveFacts);
    $("#proposeFactsBtn").addEventListener("click", proposeFacts);
    $("#paperSearchBtn").addEventListener("click", () => searchSources("paper"));
    $("#officialSearchBtn").addEventListener("click", () => searchSources("official"));
    $("#officialUrlBtn").addEventListener("click", previewOfficialUrl);
    $("#generateOutlineBtn").addEventListener("click", generateOutline);
    $("#saveOutlineBtn").addEventListener("click", saveOutline);
    $("#proposeDiagramBtn").addEventListener("click", proposeDiagram);
    $("#saveDiagramBtn").addEventListener("click", saveDiagram);
    $("#chatForm").addEventListener("submit", sendChat);
    $("#chatInput").addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        sendChat();
      }
    });
    $$(".chat-tools button").forEach((button) => button.addEventListener("click", () => {
      $("#chatInput").value = button.dataset.prompt;
      $("#chatInput").focus();
    }));
    $$("#templateQuickActions button").forEach((button) => button.addEventListener("click", () => {
      $("#chatInput").value = button.dataset.templateAnswer;
      sendChat();
    }));
    $("#validateBtn").addEventListener("click", validate);
    $("#reviewBtn").addEventListener("click", runReview);
    $("#exportBtn").addEventListener("click", exportDoc);
    $("#deleteProjectBtn").addEventListener("click", deleteCurrentProject);
    $("#clearChatBtn").addEventListener("click", () => toast(
      state.cloudMode ? "对话记录随项目保存在账号隔离的云端项目空间。" : "对话记录保存在当前本机项目库中。"
    ));
    $("#toggleChatBtn")?.addEventListener("click", toggleChatColumn);

    $$(".workspace-tab-btn").forEach(btn => {
      btn.addEventListener("click", () => handleTabNavigation(btn.dataset.target));
    });

    $("#modelSettingsBtn").addEventListener("click", () => {
      syncModelSettingsForm();
      $("#modelSettingsDialog").showModal();
    });
    $("#closeModelSettingsBtn").addEventListener("click", () => $("#modelSettingsDialog").close());
    $$('input[name="llmProvider"]').forEach((input) => input.addEventListener("change", updateModelFields));
    $("#testModelConfigBtn").addEventListener("click", testSelectedLlmConfig);
    $("#saveModelConfigBtn").addEventListener("click", saveSelectedLlmConfig);
    $("#authForm").addEventListener("submit", submitAuthForm);
    $("#authModeToggle").addEventListener("click", () => {
      state.authMode = state.authMode === "signin" ? "signup" : "signin";
      $("#authTitle").textContent = state.authMode === "signup" ? "创建你的项目空间" : "登录你的项目空间";
      $("#authSubmitBtn").textContent = state.authMode === "signup" ? "创建账号" : "登录";
      $("#authModeToggle").textContent = state.authMode === "signup"
        ? "已有账号？返回登录"
        : "还没有账号？创建账号";
      $("#authPassword").autocomplete = state.authMode === "signup" ? "new-password" : "current-password";
      $("#authFeedback").textContent = "";
    });
    $("#signOutBtn").addEventListener("click", signOutCloudUser);
  }

  async function init() {
    setupResizeHandles();
    bindEvents();
    updateTemplateExplain();
    $("#chatFileInput").accept = chatUploadAccept($("#chatUploadKind").value);
    await loadSkills();
    const config = await api("/api/config");
    await initializeCloudAuth(config);
  }

  document.addEventListener("DOMContentLoaded", () => {
    init().catch((error) => toast(error.message, true));
  });
})();
  async function triggerHeroStart() {
    const input = $("#heroProjectRequest");
    const query = input?.value?.trim();
    if (!query) {
      toast("请先输入你的申报需求，例如：我要申请国家励志奖学金", true);
      input?.focus();
      return;
    }
    $("#projectRequest").value = query;
    const startBtn = $("#heroStartBtn");
    if (startBtn) {
      startBtn.disabled = true;
      startBtn.innerHTML = '<span>匹配赛道中…</span>';
    }
    try {
      const route = await api("/api/route", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
      });
      if (route.selected) {
        await completeProjectCreation({
          title: "",
          level: "",
          discipline: "",
          school: "",
          has_template: false,
          skill_id: route.selected.id,
          initial_request: query,
        });
      } else {
        const box = $("#heroRouteCandidates");
        if (box) {
          box.replaceChildren();
          const intro = document.createElement("p");
          intro.textContent = route.message || "为你匹配到以下赛道，请确认：";
          box.append(intro);
          const candidates = route.candidates?.length ? route.candidates : state.skills.slice(0, 6);
          for (const cand of candidates) {
            const chip = button(cand.name, "button button-small button-secondary");
            chip.addEventListener("click", () => {
              completeProjectCreation({
                title: "",
                level: "",
                discipline: "",
                school: "",
                has_template: false,
                skill_id: cand.id,
                initial_request: query,
              });
            });
            box.append(chip);
          }
          box.classList.remove("hidden");
        }
      }
    } catch (err) {
      toast(`赛道匹配失败：${err.message}`, true);
    } finally {
      if (startBtn) {
        startBtn.disabled = false;
        startBtn.innerHTML = '<span>立即开启</span><span class="arrow">→</span>';
      }
    }
  }

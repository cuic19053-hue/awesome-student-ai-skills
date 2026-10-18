(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const llmConfigKey = "innovation-proposal-agent-llm-config";
  const MICRO_CNY_PER_CREDIT = 100000; // ¥1 = 10 workbench credits

  const activeProjectKey = "stardust-agent-active-project-id";

  function readSavedLlmConfig() {
    const fallback = {
      provider: "preset",
      model: "workbench-bundle",
      base_url: "",
      api_key: "",
      image_model: "",
      image_base_url: "",
      image_api_key: "",
      image_reuse_text: false,
    };
    try {
      localStorage.removeItem(llmConfigKey);
      const saved = JSON.parse(sessionStorage.getItem(llmConfigKey) || "null");
      if (saved && ["ollama", "openai_compatible", "preset"].includes(saved.provider)) return { ...fallback, ...saved };
    } catch {}
    return fallback;
  }

  const state = {
    project: null,
    projectsList: [],
    documents: [],
    messages: [],
    uploadKind: "source",
    uploading: false,
    outline: [],
    diagrams: [],
    editingDiagramId: "",
    llmConfig: readSavedLlmConfig(),
    chatCollapsed: false,
    cloudMode: false,
    ollamaLocal: null,
    userCredits: null,
    freeChatsRemaining: 0,
    cardRedemptionEnabled: false,
    cardShopUrl: "",
    presetModels: [],
    rechargePlans: [],
    authClient: null,
    authStatus: "loading",
    authBusy: false,
    authInitializing: false,
    authConfig: null,
    authSubscription: null,
    authSession: null,
    authMode: "signin",
    turnstileSiteKey: "",
    turnstileWidgetId: null,
    turnstileToken: "",
    appStarted: false,
    balanceRequestSeq: 0,
    skills: [],
    pendingProject: null,
    activeTab: "all",
    batchGenerating: false,
    batchAbort: false,
    chatSending: false,
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
    leader_photo: "负责人照片",
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
    const usesLlm = method === "POST" && /\/api\/projects\/[^/]+\/(?:chat|outline\/generate|sections\/[^/]+\/generate|diagrams\/propose|facts\/propose|images\/generate)$/.test(path);
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
  const originalApi = api;

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

  function renderPrivacyNotice(project = state.project) {
  }

  function showModelStatus(localStatus) {
    if (typeof localStatus?.ollama_local === "boolean") {
      state.ollamaLocal = localStatus.ollama_local;
    }
    renderPrivacyNotice();
    const status = $("#modelStatus");
    if (state.llmConfig.provider === "preset") {
      status.textContent = "平台融合模型 · DeepSeek Flash + GPT Image";
      status.classList.remove("offline");
      status.classList.add("remote-warning");
      return;
    }
    if (state.llmConfig.provider === "openai_compatible") {
      const imgTag = state.llmConfig.image_model ? ` + ${state.llmConfig.image_model}` : "";
      status.textContent = `自定义 API · ${state.llmConfig.model || "未设置模型"}${imgTag}`;
      status.classList.remove("offline");
      status.classList.add("remote-warning");
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
  }

  function selectedLlmConfig() {
    const provider = $('input[name="llmProvider"]:checked')?.value || "preset";
    if (provider === "preset") {
      return {
        provider,
        model: "workbench-bundle",
        base_url: "",
        api_key: "",
      };
    }
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
      image_model: $("#customImageModel") ? $("#customImageModel").value.trim() : "",
      image_base_url: $("#customImageBase") ? $("#customImageBase").value.trim() : "",
      image_api_key: $("#customImageKey") ? $("#customImageKey").value.trim() : "",
      image_reuse_text: $("#customImageReuseText") ? Boolean($("#customImageReuseText").checked) : false,
    };
  }

  function syncModelSettingsForm() {
    const config = state.llmConfig;
    if ($("#providerPreset")) $("#providerPreset").checked = config.provider === "preset";
    $("#providerOllama").checked = config.provider === "ollama";
    $("#providerCustom").checked = config.provider === "openai_compatible";
    $("#localModelName").value = config.provider === "ollama" ? config.model : "qwen2.5:7b";
    $("#customModelBase").value = config.provider === "openai_compatible" ? config.base_url : "";
    $("#customModelName").value = config.provider === "openai_compatible" ? config.model : "";
    $("#customModelKey").value = config.provider === "openai_compatible" ? config.api_key : "";
    if ($("#customImageModel")) $("#customImageModel").value = config.image_model || "";
    if ($("#customImageBase")) $("#customImageBase").value = config.image_base_url || "";
    if ($("#customImageKey")) $("#customImageKey").value = config.image_api_key || "";
    if ($("#customImageReuseText")) {
      $("#customImageReuseText").checked = Boolean(config.image_reuse_text);
      $("#customImageSeparateFields")?.classList.toggle("hidden", Boolean(config.image_reuse_text));
    }
    updateModelFields();
    $("#modelConfigFeedback").textContent = "";
    $("#modelConfigFeedback").className = "model-config-feedback";
  }

  function updateModelFields() {
    const provider = $('input[name="llmProvider"]:checked')?.value || "preset";
    const isPreset = provider === "preset";
    const isOllama = provider === "ollama";
    const custom = provider === "openai_compatible";
    if ($("#presetModelFields")) $("#presetModelFields").classList.toggle("hidden", !isPreset);
    $("#localModelFields").classList.toggle("hidden", !isOllama);
    $("#customModelFields").classList.toggle("hidden", !custom);
    const canImage = isPreset || custom;
    $("#workbenchImageControls")?.classList.toggle("hidden", !canImage);
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
    if (config.provider === "preset" && !state.presetModels.some((model) => model.id === "workbench-bundle" && model.available)) {
      $("#modelConfigFeedback").textContent = "平台融合模型尚未接通，请先使用自带 Key 或本地模型。";
      $("#modelConfigFeedback").className = "model-config-feedback error";
      return;
    }
    if (config.provider === "openai_compatible" && (!config.base_url || !config.model || !config.api_key)) {
      $("#modelConfigFeedback").textContent = "请填写文本 API 地址、模型名称和 API Key。";
      $("#modelConfigFeedback").className = "model-config-feedback error";
      return;
    }
    storeLlmConfig(config);
    $("#modelSettingsDialog").close();
    const provName = config.provider === "preset" ? "平台融合模型包" : config.provider === "ollama" ? "本地模型" : "自定义 API";
    const imgInfo = config.image_model ? ` · 生图: ${config.image_model}` : "";
    toast(`已切换为${provName}：${config.model}${imgInfo}`);
  }

  async function loadUserBalance() {
    const requestSeq = ++state.balanceRequestSeq;
    const accountId = state.authSession?.user?.id || null;
    if (state.cloudMode && !accountId) return;
    try {
      const data = await api("/api/user/balance");
      if (requestSeq !== state.balanceRequestSeq) return;
      if (state.cloudMode && (accountId !== state.authSession?.user?.id || data.user_id !== accountId)) return;
      state.userCredits = data.credits;
      state.freeChatsRemaining = Number(data.free_chats_remaining || 0);
      if ($("#userCreditsValue")) $("#userCreditsValue").textContent = data.credits;
      if ($("#rechargeModalCredits")) $("#rechargeModalCredits").textContent = data.credits;
      if ($("#presetDialogCredits")) $("#presetDialogCredits").textContent = data.credits;
      renderFreeChatsIndicator();
      renderCreditTransactions(data.transactions || []);
    } catch (e) {
      console.warn("加载用户积分失败", e);
      if (requestSeq === state.balanceRequestSeq && state.userCredits === null) {
        if ($("#userCreditsValue")) $("#userCreditsValue").textContent = "加载失败";
        if ($("#rechargeModalCredits")) $("#rechargeModalCredits").textContent = "加载失败";
      }
    }
  }

  function openRechargeDialog() {
    $("#rechargeDialog")?.showModal();
    void loadUserBalance();
  }

  function renderFreeChatsIndicator() {
    const badge = $("#freeChatsTopbarBadge");
    const hint = $("#freeChatHint");
    const countNum = $("#freeChatCountNum");
    const remaining = Number(state.freeChatsRemaining || 0);
    if (remaining > 0) {
      if (badge) {
        badge.textContent = `🎁 免费对话剩 ${remaining} 次`;
        badge.classList.remove("hidden");
      }
      if (hint) {
        if (countNum) countNum.textContent = String(remaining);
        hint.classList.remove("hidden");
      }
    } else {
      if (badge) badge.classList.add("hidden");
      if (hint) hint.classList.add("hidden");
    }
  }

  function renderCreditTransactions(transactions) {
    const container = $("#creditTransactions");
    if (!container) return;
    container.replaceChildren();
    if (!transactions.length) {
      const empty = document.createElement("p");
      empty.className = "balance-sub";
      empty.textContent = "暂无积分流水";
      container.appendChild(empty);
      return;
    }
    transactions.slice(0, 10).forEach((tx) => {
      const row = document.createElement("div");
      row.className = "credit-transaction-row";
      const label = document.createElement("span");
      label.textContent = tx.kind === "card_redeem" ? "卡密充值"
        : tx.kind === "usage_reserve" ? `模型调用 · ${tx.model || "平台模型"}`
          : tx.kind === "admin_adjustment" ? "异常补偿 / 人工调整"
          : tx.kind === "usage_refund" || tx.kind === "usage_settle" ? "用量结算"
            : "积分变动";
      const amount = document.createElement("strong");
      const delta = Number(tx.delta_micro_cny || 0) / MICRO_CNY_PER_CREDIT;
      amount.textContent = `${delta > 0 ? "+" : ""}${delta.toFixed(4)} 点`;
      amount.classList.toggle("credit-positive", delta > 0);
      const time = document.createElement("time");
      time.textContent = (tx.created_at || "").replace("T", " ").slice(0, 16);
      row.append(label, amount, time);
      container.appendChild(row);
    });
  }

  async function openUsageDialog() {
    try {
      const data = await api("/api/admin/usage-details");
      const stats = data.stats || {};
      const logs = data.logs || [];

      if ($("#statCallCount")) $("#statCallCount").textContent = (stats.call_count || 0).toLocaleString();
      if ($("#statGrandTokens")) $("#statGrandTokens").textContent = (stats.grand_total_tokens || 0).toLocaleString();
      if ($("#statAvgLatency")) $("#statAvgLatency").textContent = `${Math.round(stats.avg_latency_ms || 0)} ms`;
      if ($("#statEstimatedCost")) {
        $("#statEstimatedCost").textContent = data.billing_status === "provider_cost_reconciled"
          ? `¥${Number(data.actual_provider_cost || 0).toFixed(2)}`
          : "待核对";
      }

      // 模型分布标签
      const tagsContainer = $("#usageModelTags");
      if (tagsContainer) {
        tagsContainer.innerHTML = "";
        const byModel = stats.by_model || [];
        if (byModel.length === 0) {
          tagsContainer.innerHTML = '<span class="text-muted" style="font-size:12px;">暂无模型调用数据</span>';
        } else {
          byModel.forEach((bm) => {
            const tag = document.createElement("span");
            tag.className = "usage-tag";
            tag.innerHTML = `${bm.model || "未知"} · ${bm.count} 次 <small>(${bm.tokens.toLocaleString()} tokens)</small>`;
            tagsContainer.appendChild(tag);
          });
        }
      }

      // 流水表格
      const tbody = $("#usageTableBody");
      if (tbody) {
        tbody.innerHTML = "";
        if (logs.length === 0) {
          tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted">暂无调用明细</td></tr>';
        } else {
          logs.forEach((log) => {
            const tr = document.createElement("tr");
            const timeStr = (log.created_at || "").replace("T", " ").slice(5, 19);
            tr.innerHTML = `
              <td style="color:var(--text-muted);">${timeStr}</td>
              <td><strong>${log.project_title || log.project_id || "全局"}</strong></td>
              <td><span style="background:#f1f5f9;padding:2px 6px;border-radius:4px;">${log.task_type || "chat"}</span></td>
              <td><span style="font-family:monospace;color:#7e22ce;">${log.model}</span></td>
              <td>${(log.prompt_tokens || 0).toLocaleString()}</td>
              <td>${(log.completion_tokens || 0).toLocaleString()}</td>
              <td><strong>${(log.total_tokens || 0).toLocaleString()}</strong></td>
              <td style="color:var(--text-muted);">${log.latency_ms || 0} ms</td>
            `;
            tbody.appendChild(tr);
          });
        }
      }

      $("#usageDialog")?.showModal();
    } catch (e) {
      toast(e.message || "加载用量明细失败", true);
    }
  }

  let currentOnboardingStep = 1;

  function setOnboardingStep(step) {
    currentOnboardingStep = Math.max(1, Math.min(4, step));
    $$(".onboarding-step-tab").forEach((tab) => {
      const tabStep = parseInt(tab.dataset.step, 10);
      tab.classList.toggle("active", tabStep === currentOnboardingStep);
    });
    $$(".onboarding-step-content").forEach((content) => {
      const contentStep = parseInt(content.dataset.step, 10);
      content.classList.toggle("hidden", contentStep !== currentOnboardingStep);
    });

    const prevBtn = $("#prevOnboardingBtn");
    const nextBtn = $("#nextOnboardingBtn");
    const finishBtn = $("#finishOnboardingBtn");

    if (prevBtn) prevBtn.classList.toggle("hidden", currentOnboardingStep === 1);
    if (nextBtn) {
      nextBtn.classList.toggle("hidden", currentOnboardingStep === 4);
      nextBtn.textContent = `下一步 (${currentOnboardingStep}/4)`;
    }
    if (finishBtn) {
      finishBtn.classList.toggle("hidden", currentOnboardingStep !== 4);
    }
  }

  function openOnboardingDialog() {
    setOnboardingStep(1);
    $("#onboardingDialog")?.showModal();
  }

  function closeOnboardingDialog() {
    if ($("#dontShowOnboardingAgain")?.checked) {
      try {
        localStorage.setItem("stardust_onboarding_dismissed", "true");
      } catch {}
    }
    $("#onboardingDialog")?.close();
  }

  function checkInitialOnboarding() {
    try {
      if (!localStorage.getItem("stardust_onboarding_dismissed")) {
        openOnboardingDialog();
      }
    } catch {}
  }

  async function loadPresetModelsAndPlans() {
    try {
      const data = await api("/api/models/preset");
      state.presetModels = data.models || [];
      renderPresetModelCards();
    } catch (e) {
      console.warn("加载模型及套餐失败", e);
    }
  }

  function renderPresetModelCards() {
    const container = $("#presetModelCards");
    if (!container) return;
    container.replaceChildren();
    const bundle = state.presetModels.find((model) => model.id === "workbench-bundle");
    const card = document.createElement("div");
    card.className = `preset-model-card active${bundle?.available ? "" : " unavailable"}`;
    const top = document.createElement("div");
    top.className = "preset-card-top";
    const title = document.createElement("span");
    title.className = "preset-card-title";
    title.textContent = "DeepSeek Flash 写作 + GPT Image 生图";
    const cost = document.createElement("span");
    cost.className = "preset-card-cost";
    cost.textContent = bundle?.available ? "按实际用量计费" : "尚未开通";
    top.append(title, cost);
    const description = document.createElement("div");
    description.className = "preset-card-desc";
    description.textContent = bundle?.available
      ? "Agent 会按任务自动路由两种能力，统一从当前账户积分扣费。"
      : "服务账户、卡密核验与成本结算尚未全部接通；当前不会调用或扣费。";
    card.append(top, description);
    container.appendChild(card);
  }

  async function handleRedeemCode() {
    const input = $("#redeemCodeInput");
    const code = input ? input.value.trim() : "";
    if (!code) {
      toast("请输入有效的兑换卡密", true);
      return;
    }
    const btn = $("#submitRedeemBtn");
    btn.disabled = true;
    try {
      const res = await api("/api/pay/redeem", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code }),
      });
      if (res.pending) {
        toast(res.message || "兑换正在核对，请勿重复提交。", true);
        return;
      }
      toast(res.message || "兑换成功！");
      if (input) input.value = "";
      await loadUserBalance();
    } catch (e) {
      toast(e.message || "兑换失败", true);
    } finally {
      btn.disabled = false;
    }
  }

  async function makePilotFingerprint() {
    const code = $("#redeemCodeInput").value.trim();
    if (!code) return toast("请先粘贴已购买的卡密", true);
    try {
      const result = await api("/api/pay/card-fingerprint", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code }),
      });
      $("#pilotFingerprintOutput").value = result.fingerprint;
      toast("已生成核对编号；这一步未兑换、未消耗卡密。");
    } catch (error) {
      toast(error.message, true);
    }
  }

  function updateTurnstileState() {
    const slot = $("#turnstileWidget");
    if (!slot) return;
    const isSignup = state.authMode === "signup";
    if (!isSignup || !state.turnstileSiteKey) {
      slot.classList.add("hidden");
      return;
    }
    slot.classList.remove("hidden");
    const renderWidget = () => {
      if (!window.turnstile || state.turnstileWidgetId !== null) return;
      try {
        state.turnstileWidgetId = window.turnstile.render("#turnstileWidget", {
          sitekey: state.turnstileSiteKey,
          callback: (token) => {
            state.turnstileToken = token;
            const feedback = $("#authFeedback");
            if (feedback && feedback.textContent === "请先完成人机安全验证。") {
              feedback.textContent = "";
            }
          },
          "expired-callback": () => {
            state.turnstileToken = "";
          },
          "error-callback": () => {
            state.turnstileToken = "";
          },
          theme: "auto",
        });
      } catch (err) {
        console.warn("Turnstile render error:", err);
      }
    };
    if (window.turnstile) {
      renderWidget();
    } else {
      let attempts = 0;
      const timer = setInterval(() => {
        attempts++;
        if (window.turnstile) {
          clearInterval(timer);
          renderWidget();
        } else if (attempts > 20) {
          clearInterval(timer);
        }
      }, 250);
    }
  }

  function syncAuthControls() {
    const ready = state.authStatus === "ready" && Boolean(state.authClient?.auth);
    const submit = $("#authSubmitBtn");
    submit.disabled = !ready || state.authBusy;
    submit.textContent = state.authBusy
      ? state.authMode === "signup" ? "正在创建账号…" : "正在登录…"
      : ready ? state.authMode === "signup" ? "创建账号" : "登录"
      : state.authStatus === "loading" ? "正在加载登录组件…" : "登录服务暂不可用";
    $("#authModeToggle").disabled = !ready || state.authBusy;
    $("#retryAuthBtn").classList.toggle("hidden", state.authStatus !== "error");
  }

  function showAuthGate(message = "") {
    state.appStarted = false;
    $("#appShell").classList.add("hidden");
    $("#authGate").classList.remove("hidden");
    $("#signOutBtn").classList.add("hidden");
    $("#authFeedback").textContent = message;
    syncAuthControls();
    updateTurnstileState();
  }

  async function startApplication(session = null) {
    if (state.appStarted) return;
    state.authSession = session;
    state.appStarted = true;
    $("#authGate").classList.add("hidden");
    $("#appShell").classList.remove("hidden");
    $("#signOutBtn").classList.toggle("hidden", !state.cloudMode);
    await loadUserBalance();
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
    checkInitialOnboarding();
  }

  async function initializeCloudAuth(config) {
    if (state.authInitializing) return;
    state.authConfig = config;
    state.cloudMode = Boolean(config.cloud_mode);
    renderPrivacyNotice();
    if (!state.cloudMode) {
      await startApplication();
      return;
    }
    const localBadge = $(".sidebar-footer .local-badge");
    if (localBadge) localBadge.textContent = "云端同步 · 安全存储";
    const sidebarNote = $(".sidebar-footer p");
    if (sidebarNote) sidebarNote.textContent = "项目与材料已安全同步，可根据需要随时导出为 Word。";
    const modelIntro = $(".model-settings-intro");
    if (modelIntro) {
      modelIntro.textContent = config.preset_enabled
        ? "默认使用平台融合模型，按当前账号积分结算；也可选择自带 Key。"
        : "通过用户配置的 OpenAI 兼容 API 推理；模型服务费用由你与服务商直接结算。";
    }
    if (!window.supabase?.createClient) {
      state.authClient = null;
      state.authStatus = "error";
      showAuthGate("登录组件加载失败，请点击“重新连接登录服务”；无需更换邮箱或密码。");
      return;
    }
    if (config.preset_enabled) {
      // Preserve an intentional BYOK choice for this tab; otherwise the
      // platform bundle is the zero-configuration default.
      if (state.llmConfig.provider !== "openai_compatible" || !state.llmConfig.api_key) {
        storeLlmConfig({ provider: "preset", model: "workbench-bundle", base_url: "", api_key: "" });
      }
    } else {
      state.llmConfig = { provider: "openai_compatible", model: "", base_url: "", api_key: "" };
    }
    $("#providerOllama").closest(".model-provider-option")?.classList.add("hidden");
    state.authInitializing = true;
    state.authStatus = "loading";
    state.authClient = null;
    state.authSubscription?.unsubscribe();
    state.authSubscription = null;
    syncAuthControls();
    let data;
    try {
      const client = window.supabase.createClient(
        config.supabase_url,
        config.supabase_publishable_key,
        { auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true } }
      );
      const result = await client.auth.getSession();
      if (result.error) throw result.error;
      data = result.data;
      state.authClient = client;
      state.authStatus = "ready";
    } catch {
      state.authStatus = "error";
      showAuthGate("无法初始化登录服务，请点击“重新连接登录服务”或稍后重试。");
      return;
    } finally {
      state.authInitializing = false;
      syncAuthControls();
    }
    const subscription = state.authClient.auth.onAuthStateChange((event, session) => {
      state.authSession = session;
      if (session && !state.appStarted) {
        void startApplication(session);
      } else if (!session && event === "SIGNED_OUT") {
        state.appStarted = false;
        state.userCredits = null;
        state.balanceRequestSeq++;
        if ($("#userCreditsValue")) $("#userCreditsValue").textContent = "—";
        if ($("#rechargeModalCredits")) $("#rechargeModalCredits").textContent = "—";
        state.project = null;
        state.messages = [];
        state.documents = [];
        sessionStorage.removeItem(llmConfigKey);
        state.llmConfig = { provider: "openai_compatible", model: "", base_url: "", api_key: "" };
        showAuthGate("已退出登录。");
      }
    });
    state.authSubscription = subscription.data.subscription;
    if (data.session) {
      await startApplication(data.session);
    } else {
      showAuthGate();
    }
  }

  async function submitAuthForm(event) {
    event.preventDefault();
    const feedback = $("#authFeedback");
    if (state.authBusy) return;
    if (state.authStatus !== "ready" || !state.authClient?.auth) {
      feedback.className = "auth-feedback error";
      feedback.textContent = state.authStatus === "loading"
        ? "登录组件正在初始化，请稍候；当前尚未发送注册或登录请求。"
        : "登录服务尚未就绪，请点击“重新连接登录服务”；无需更换邮箱或密码。";
      syncAuthControls();
      return;
    }
    const authClient = state.authClient;
    const email = $("#authEmail").value.trim().toLowerCase();
    const password = $("#authPassword").value;

    if (state.authMode === "signup") {
      const domain = (email.split("@")[1] || "").toLowerCase();
      const allowedDomains = ["qq.com", "foxmail.com", "163.com", "126.com", "sina.com", "gmail.com", "outlook.com", "hotmail.com"];
      const isEdu = domain === "edu.cn" || domain.endsWith(".edu.cn");
      if (!allowedDomains.includes(domain) && !isEdu) {
        feedback.className = "auth-feedback error";
        feedback.textContent = "为保障服务稳定，注册仅支持 QQ邮箱、163/126、高校教育网 (edu.cn)、Gmail、Outlook 等正规邮箱。";
        return;
      }
    }

    if (state.authMode === "signup" && state.turnstileSiteKey) {
      if (!state.turnstileToken) {
        feedback.className = "auth-feedback error";
        feedback.textContent = "请先完成人机安全验证。";
        return;
      }
    }

    state.authBusy = true;
    syncAuthControls();
    feedback.className = "auth-feedback";
    feedback.textContent = state.authMode === "signup" ? "正在创建账号…" : "正在登录…";
    try {
      const signupOptions = {
        emailRedirectTo: window.location.origin,
      };
      if (state.turnstileToken) {
        signupOptions.captchaToken = state.turnstileToken;
      }

      const result = state.authMode === "signup"
        ? await authClient.auth.signUp({
            email,
            password,
            options: signupOptions,
          })
        : await authClient.auth.signInWithPassword({ email, password });
      if (result.error) throw result.error;
      if (result.data.session) {
        await startApplication(result.data.session);
        await loadUserBalance();
      } else if (state.authMode === "signup") {
        feedback.textContent = "账号已创建。请查收邮箱并完成验证后登录。";
        feedback.classList.add("success");
      } else {
        feedback.textContent = "登录成功，正在载入你的项目…";
      }
    } catch (error) {
      const message = error.message || "";
      feedback.textContent = /Cannot read properties|undefined|Failed to fetch|NetworkError|fetch failed/i.test(message)
        ? "无法连接登录服务，请稍后重试或检查网络。"
        : message || "登录失败，请检查邮箱和密码。";
      feedback.classList.add("error");
    } finally {
      if (window.turnstile && state.turnstileWidgetId !== null && state.authMode === "signup") {
        try {
          window.turnstile.reset(state.turnstileWidgetId);
        } catch (_) {}
        state.turnstileToken = "";
      }
      state.authBusy = false;
      syncAuthControls();
    }
  }

  async function signOutCloudUser() {
    if (!state.authClient) return;
    const { error } = await state.authClient.auth.signOut();
    if (error) toast("退出失败：" + error.message, true);
  }

  function renderProjectList(projects, filterKeyword = "") {
    const list = $("#projectList");
    const countBadge = $("#projectCountBadge");
    if (countBadge) countBadge.textContent = state.projectsList.length;
    list.replaceChildren();

    const query = filterKeyword.trim().toLowerCase();
    const filtered = query
      ? projects.filter(p => {
          const title = (p.title || "").toLowerCase();
          const skill = (p.state?.skill_name || "").toLowerCase();
          return title.includes(query) || skill.includes(query);
        })
      : projects;

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

  async function refreshProjects(filterKeyword = "") {
    try {
      const response = await api("/api/projects");
      state.projectsList = response.projects || [];
      renderProjectList(state.projectsList, filterKeyword);
    } catch (e) {
      console.warn("刷新项目列表失败", e);
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
      if (state.project?.id !== projectId) $("#uploadResult").classList.add("hidden");
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
      if (state.llmConfig.provider === "preset") await loadUserBalance();
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
      if ((error.message || "").includes("积分不足") || (error.message || "").includes("402")) {
        openRechargeDialog();
      }
    } finally {
      submit.disabled = false;
    }
  }

  function updateTemplateQuickActions(project) {
    const bar = $("#templateQuickActions");
    const needsAnswer = project?.state?.template_preference === "not_asked";
    bar.classList.toggle("hidden", !needsAnswer);
    renderPrivacyNotice(project);
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
      photo: ["上传真实实验 / 调研照片", "没有照片时 Word 会放“待补充”占位，不会生成假图；负责人证件照可在下方事实面板上传"],
    }[kind];
    $("#uploadTitle").textContent = copy[0];
    $("#uploadHint").textContent = copy[1];
    $("#fileInput").accept = kind === "photo" ? ".png,.jpg,.jpeg,.webp" : ".docx,.pdf,.txt,.md,.png,.jpg,.jpeg,.webp";
  }

  async function uploadFiles(fileList, kind = state.uploadKind, fromChat = false) {
    if (!state.project || !fileList.length) return;
    if (state.uploading) return toast("材料正在上传，请稍候。", true);
    if (fileList.length > 12) return toast("一次最多上传 12 个文件。", true);
    const projectId = state.project.id;
    const form = new FormData();
    for (const file of fileList) form.append("files", file);
    const names = fileList.map((file) => file.name);
    const query = new URLSearchParams({ kind });
    state.uploading = true;
    $("#chooseFileBtn").disabled = true;
    $("#chatAttachBtn").disabled = true;
    const status = $("#uploadResult");
    status.replaceChildren();
    status.textContent = "正在上传并识别材料，请稍候…";
    status.classList.remove("hidden", "error");
    try {
      toast(state.cloudMode ? "正在安全上传并识别材料…" : "正在本机识别文件…");
      const result = state.cloudMode
        ? await uploadFilesToCloud(fileList, kind, projectId)
        : await api(`/api/projects/${projectId}/documents?${query}`, { method: "POST", body: form });
      const failed = (result.documents || []).filter((d) => d.error);
      const uploaded = (result.documents || []).filter((d) => !d.error);
      if (state.project?.id !== projectId) return;
      await loadProject(projectId);
      renderUploadResult(result.documents || []);
      toast(failed.length ? "有文件处理失败，请查看上传结果。" : `上传成功：${uploaded.length} 个文件，可预览并核对文字。`, failed.length > 0);
      const firstDocument = (result.documents || []).find((item) => item.document?.id);
      if (firstDocument) void previewDocument(firstDocument.document, true);
      if (fromChat && uploaded.length) {
        const labels = { source: "项目信息材料", template: "学校申报模板", photo: "实验 / 调研照片" };
        const successfulNames = uploaded.map((item) => item.document?.original_name).filter(Boolean);
        await sendChat(
          undefined,
          `我刚上传了${labels[kind] || "材料"}：${(successfulNames.length ? successfulNames : names).join("、")}。请告诉我下一步怎么处理。`
        );
      }
      if (fromChat && failed.length) {
        appendMessage("assistant", `以下文件未能完成处理：\n${failed.map((item) =>
          `${item.document?.original_name || "文件"}：${item.error}`
        ).join("\n")}\n请查看项目材料区的上传结果后重试。`);
      }
    } catch (error) {
      if (state.project?.id !== projectId) return;
      renderUploadResult(names.map((name) => ({ document: { original_name: name }, error: error.message })));
      toast(error.message, true);
      if (fromChat) appendMessage("assistant", `上传没有完成：${error.message}`);
    } finally {
      state.uploading = false;
      $("#chooseFileBtn").disabled = false;
      $("#chatAttachBtn").disabled = false;
      $("#fileInput").value = "";
      $("#chatFileInput").value = "";
    }
  }

  async function uploadFilesToCloud(fileList, kind, projectId = state.project.id) {
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
      const storagePath = `${state.authSession.user.id}/${projectId}/${documentId}${extension}`;
      const contentType = file.type || mimeByExtension[extension] || "application/octet-stream";
      const { error: uploadError } = await state.authClient.storage
        .from("stardust-project-files")
        .upload(storagePath, file, { contentType, upsert: false });
      if (uploadError) {
        documents.push({ error: uploadError.message, document: { original_name: file.name } });
        continue;
      }
      try {
        const registered = await api(`/api/projects/${projectId}/documents/from-storage`, {
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

  function renderUploadResult(items) {
    const box = $("#uploadResult");
    box.replaceChildren();
    const failed = items.filter((item) => item.error);
    const title = document.createElement("strong");
    title.textContent = items.length
      ? `上传结果：${items.length - failed.length} 个成功，${failed.length} 个处理失败`
      : "未收到上传结果，请重试。";
    box.append(title);
    box.classList.remove("hidden");
    box.classList.toggle("error", failed.length > 0 || !items.length);
    for (const item of items) {
      const row = document.createElement("div");
      row.className = "upload-result-item";
      const label = document.createElement("span");
      const saved = Boolean(item.document?.id);
      label.textContent = `${item.document?.original_name || "文件"} — ${
        item.error ? `${saved ? "已保存，识别失败" : "上传失败"}：${item.error}` : "上传成功"
      }`;
      row.append(label);
      if (saved) {
        const preview = button("预览", "button button-small button-secondary");
        preview.addEventListener("click", () => void previewDocument(item.document));
        row.append(preview);
      }
      box.append(row);
    }
  }

  let documentPreviewVersion = 0;
  let documentPreviewUrl = "";

  function clearDocumentPreview() {
    documentPreviewVersion += 1;
    $("#documentPreviewBody").replaceChildren();
    if (documentPreviewUrl) URL.revokeObjectURL(documentPreviewUrl);
    documentPreviewUrl = "";
  }

  async function fetchDocumentBlob(doc) {
    const headers = new Headers();
    if (state.authSession?.access_token) {
      headers.set("Authorization", `Bearer ${state.authSession.access_token}`);
    }
    // Private files must be fetched with the session JWT, not used as bare img/iframe URLs.
    const response = await fetch(`/api/documents/${encodeURIComponent(doc.id)}/file`, { headers });
    if (!response.ok) {
      throw new Error(response.status === 401
        ? "登录已过期，请重新登录后预览。"
        : `原文件读取失败（HTTP ${response.status}），可查看提取文字。`);
    }
    return response.blob();
  }

  async function previewDocument(doc, justUploaded = false) {
    const dialog = $("#documentPreviewDialog");
    clearDocumentPreview();
    const version = documentPreviewVersion;
    const body = $("#documentPreviewBody");
    const status = $("#documentPreviewStatus");
    const extension = doc.original_name.split(".").pop().toLowerCase();
    $("#documentPreviewTitle").textContent = doc.original_name;
    const failed = doc.extraction_status === "error";
    status.textContent = failed
      ? `原文件已保存，但文字识别失败：${doc.extraction_warning || "请重新上传可复制文字的版本，或手动补充文字。"}`
      : `${justUploaded ? "上传成功 · " : ""}${doc.kind === "template" ? "学校模板" : doc.confirmed ? "材料已入库并建立检索" : "材料已保存，识别文字待核对"}。`;
    $("#reviewDocumentBtn").onclick = () => {
      dialog.close();
      handleTabNavigation("panel-materials");
      const card = $(`[data-document-id="${doc.id}"]`);
      card?.scrollIntoView({ behavior: "smooth", block: "center" });
      $("textarea", card || $("#documentsList"))?.focus();
    };
    $("#downloadDocumentBtn").onclick = async () => {
      try {
        const blob = await fetchDocumentBlob(doc);
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = doc.original_name;
        link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      } catch (error) {
        toast(error.message, true);
      }
    };
    if (!dialog.open) dialog.showModal();
    const text = document.createElement("pre");
    text.className = "document-preview-text";
    text.textContent = doc.extracted_text || "暂无识别文字；可下载原文件查看，或在材料卡片中手动补充。";
    if (!["pdf", "png", "jpg", "jpeg", "webp"].includes(extension)) {
      const note = document.createElement("p");
      note.textContent = extension === "docx"
        ? "Word 文字预览（不保留原版式）。查看完整排版请下载原文件。"
        : "识别文字预览";
      body.append(note, text);
      body.setAttribute("aria-busy", "false");
      return;
    }
    body.textContent = "正在加载原文件预览…";
    body.setAttribute("aria-busy", "true");
    try {
      const blob = await fetchDocumentBlob(doc);
      if (version !== documentPreviewVersion || !dialog.open) return;
      // Use the supported extension's MIME so PDF/image previews work even if the upload MIME was generic.
      const mime = extension === "pdf" ? "application/pdf"
        : `image/${extension === "jpg" ? "jpeg" : extension}`;
      documentPreviewUrl = URL.createObjectURL(new Blob([blob], { type: mime }));
      const media = document.createElement(extension === "pdf" ? "iframe" : "img");
      media.src = documentPreviewUrl;
      if (extension === "pdf") media.title = `PDF 原文件预览：${doc.original_name}`;
      else media.alt = doc.original_name;
      const fallback = document.createElement("p");
      fallback.textContent = "若浏览器无法显示原文件，请使用上方“下载原文件”。下方为识别文字。";
      body.replaceChildren(media, fallback, text);
    } catch (error) {
      if (version !== documentPreviewVersion || !dialog.open) return;
      const warning = document.createElement("p");
      warning.textContent = error.message;
      body.replaceChildren(warning, text);
    } finally {
      if (version === documentPreviewVersion) body.setAttribute("aria-busy", "false");
    }
  }

  function renderDocuments() {
    const list = $("#documentsList");
    list.replaceChildren();
    if (!state.documents.length) return;
    for (const doc of state.documents) {
      const card = document.createElement("div");
      card.className = "document-card";
      card.dataset.documentId = doc.id;
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
      badge.textContent = doc.extraction_status === "error" ? "已保存 · 识别失败"
        : doc.kind === "template" ? "已上传 · 模板" : doc.confirmed ? "已上传 · 已入库" : "已上传 · 待核对";
      top.append(type, name, badge);
      card.append(top);
      if (doc.extraction_warning) {
        const warning = document.createElement("div");
        warning.className = "doc-warning";
        warning.textContent = doc.extraction_warning;
        card.append(warning);
      }
      const text = document.createElement("textarea");
      text.className = "doc-text";
      text.rows = Math.min(7, Math.max(3, Math.ceil((doc.extracted_text || "").length / 95)));
      text.value = doc.extracted_text || "";
      text.placeholder = doc.extraction_status === "error" ? "识别失败，请重新上传或手动补充内容。" : "暂无识别文字";
      text.readOnly = doc.kind === "template" || doc.confirmed;
      text.setAttribute("aria-label", `识别文字：${doc.original_name}`);
      card.append(text);
      const actions = document.createElement("div");
      actions.className = "doc-actions";
      const preview = button("预览文件", "button button-small button-secondary");
      preview.addEventListener("click", () => void previewDocument(doc));
      actions.append(preview);
      if (doc.kind !== "template") {
        const edit = button("修改识别文字", "button button-small button-secondary");
        edit.addEventListener("click", () => {
          text.readOnly = !text.readOnly;
          if (!text.readOnly) {
            text.focus();
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
            actions.insertBefore(save, remove);
            edit.remove();
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
    const commonKeys = [
      "project_name", "problem", "target_user", "method", "foundation",
      "goal", "expected_output", "constraints", "duration", "budget",
      "leader_name", "advisor_name", "team"
    ];
    const keys = [...new Set([...commonKeys, ...Object.keys(facts)])];
    for (const key of keys) {
      if (key.startsWith("skill_") || key.startsWith("template_") || key.startsWith("fact_") || key === "leader_photo") continue;
      const val = facts[key];
      const box = document.createElement("div");
      box.className = `fact-chip ${val ? "" : "missing"} clickable`;
      box.title = val ? "点击展开编辑该字段" : "点击展开编辑并补充该字段";
      const label = document.createElement("small");
      label.textContent = labels[key] || key.replace(/_/g, " ");
      const value = document.createElement("span");
      value.textContent = val || "待补充 ＋";
      box.append(label, value);
      if (factSources[key]) {
        const source = document.createElement("small");
        source.className = "fact-source";
        source.textContent = `依据：“${factSources[key]}”`;
        box.append(source);
      }
      box.addEventListener("click", () => {
        $("#factsEditor").classList.remove("hidden");
        const targetInput = $(`[data-fact="${key}"]`);
        if (targetInput) {
          targetInput.focus();
          targetInput.scrollIntoView({ behavior: "smooth", block: "center" });
        }
      });
      summary.append(box);
      const input = $(`[data-fact="${key}"]`);
      if (input) input.value = val || "";
    }
    const photoId = state.project?.state?.leader_photo || facts.leader_photo;
    const photoBox = document.createElement("div");
    photoBox.className = `fact-chip ${photoId ? "" : "missing"} clickable`;
    photoBox.title = photoId ? "负责人照片已上传，点击展开编辑" : "点击上传负责人照片";
    const photoLabel = document.createElement("small");
    photoLabel.textContent = "负责人照片";
    const photoValue = document.createElement("span");
    photoValue.textContent = photoId ? "已上传 ✓" : "待补充 ＋";
    photoBox.append(photoLabel, photoValue);
    photoBox.addEventListener("click", () => {
      $("#factsEditor").classList.remove("hidden");
      $("#chooseLeaderPhotoBtn")?.focus();
    });
    summary.append(photoBox);
    renderLeaderPhoto();
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

  let leaderPhotoBlobUrl = "";

  async function renderLeaderPhoto() {
    const preview = $("#leaderPhotoPreview");
    const removeBtn = $("#removeLeaderPhotoBtn");
    const chooseBtn = $("#chooseLeaderPhotoBtn");
    if (!preview) return;
    const photoId = state.project?.state?.leader_photo;
    if (!photoId) {
      preview.replaceChildren();
      const placeholder = document.createElement("span");
      placeholder.className = "photo-placeholder-text";
      placeholder.textContent = "暂无照片";
      preview.append(placeholder);
      if (removeBtn) removeBtn.classList.add("hidden");
      if (chooseBtn) chooseBtn.textContent = "上传照片";
      if (leaderPhotoBlobUrl) {
        URL.revokeObjectURL(leaderPhotoBlobUrl);
        leaderPhotoBlobUrl = "";
      }
      return;
    }
    const doc = (state.documents || []).find((d) => d.id === photoId) || { id: photoId };
    try {
      const blob = await fetchDocumentBlob(doc);
      if (leaderPhotoBlobUrl) URL.revokeObjectURL(leaderPhotoBlobUrl);
      leaderPhotoBlobUrl = URL.createObjectURL(blob);
      const img = document.createElement("img");
      img.src = leaderPhotoBlobUrl;
      img.alt = "负责人照片";
      preview.replaceChildren(img);
      if (removeBtn) removeBtn.classList.remove("hidden");
      if (chooseBtn) chooseBtn.textContent = "更换照片";
    } catch {
      preview.replaceChildren();
      const img = document.createElement("img");
      img.src = `/api/documents/${encodeURIComponent(photoId)}/file`;
      img.alt = "负责人照片";
      img.onerror = () => {
        preview.textContent = "已上传";
      };
      preview.append(img);
      if (removeBtn) removeBtn.classList.remove("hidden");
      if (chooseBtn) chooseBtn.textContent = "更换照片";
    }
  }

  async function handleLeaderPhotoUpload(file) {
    if (!file || !state.project?.id) return;
    const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
    if (![".png", ".jpg", ".jpeg", ".webp"].includes(ext)) {
      return toast("照片只支持 PNG、JPG 或 WebP 格式。", true);
    }
    const btn = $("#chooseLeaderPhotoBtn");
    if (btn) btn.disabled = true;
    try {
      toast("正在上传负责人照片…");
      const form = new FormData();
      form.append("file", file);
      await api(`/api/projects/${state.project.id}/leader-photo`, {
        method: "POST",
        body: form,
      });
      await loadProject(state.project.id);
      renderLeaderPhoto();
      renderFacts();
      toast("负责人照片上传成功！");
    } catch (err) {
      toast(`上传失败：${err.message}`, true);
    } finally {
      if (btn) btn.disabled = false;
      const input = $("#leaderPhotoInput");
      if (input) input.value = "";
    }
  }

  async function handleLeaderPhotoDelete() {
    if (!state.project?.id) return;
    if (typeof confirm === "function" && !confirm("确定删除已上传的负责人照片吗？")) return;
    const btn = $("#removeLeaderPhotoBtn");
    if (btn) btn.disabled = true;
    try {
      await api(`/api/projects/${state.project.id}/leader-photo`, { method: "DELETE" });
      await loadProject(state.project.id);
      renderLeaderPhoto();
      renderFacts();
      toast("已删除负责人照片。");
    } catch (err) {
      toast(`删除失败：${err.message}`, true);
    } finally {
      if (btn) btn.disabled = false;
    }
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
      if ((error.message || "").includes("积分不足") || (error.message || "").includes("402")) {
        openRechargeDialog();
      }
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
      if ((error.message || "").includes("积分不足") || (error.message || "").includes("402")) {
        openRechargeDialog();
      }
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
      if ((error.message || "").includes("积分不足") || (error.message || "").includes("402")) {
        openRechargeDialog();
      }
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
      list.textContent = "还没有目录。点击“拟一份目录”或“赛道推荐目录”开始。";
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
      up.disabled = index === 0;
      up.addEventListener("click", () => {
        if (index === 0) return;
        [state.outline[index - 1], state.outline[index]] = [state.outline[index], state.outline[index - 1]];
        renderOutline();
      });
      const down = button("↓", "remove-outline down-outline");
      down.title = "下移";
      down.disabled = index === state.outline.length - 1;
      down.addEventListener("click", () => {
        if (index === state.outline.length - 1) return;
        [state.outline[index + 1], state.outline[index]] = [state.outline[index], state.outline[index + 1]];
        renderOutline();
      });
      const remove = button("×", "remove-outline");
      remove.title = "删除章节";
      remove.addEventListener("click", () => {
        state.outline.splice(index, 1);
        renderOutline();
      });
      row.append(mark, input, up, down, remove);
      list.append(row);
    });
    const add = button("＋ 添加章节", "button button-small button-quiet");
    add.addEventListener("click", () => {
      const newId = `section_${Date.now()}`;
      state.outline.push({ id: newId, title: "新章节" });
      renderOutline();
      const allInputs = $$("#outlineList .outline-row input");
      const last = allInputs[allInputs.length - 1];
      if (last) {
        last.focus();
        last.select();
      }
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

  function updateDraftStats() {
    const badge = $("#draftStatsBadge");
    if (!badge) return;
    const outline = state.outline || [];
    const sections = state.project?.sections || {};
    const totalWords = outline.reduce((sum, s) => sum + countWords(sections[s.id] || ""), 0);
    const completed = outline.filter(s => (sections[s.id] || "").trim().length > 0).length;
    badge.textContent = `${completed}/${outline.length} 章节 · 共 ${totalWords} 字`;
  }

  let allSectionsFolded = false;
  function toggleAllSections() {
    allSectionsFolded = !allSectionsFolded;
    $$(".draft-section-body").forEach(body => {
      body.classList.toggle("folded", allSectionsFolded);
    });
    $$(".fold-toggle-btn").forEach(btn => {
      btn.textContent = allSectionsFolded ? "▶" : "▼";
    });
    const btn = $("#toggleAllSectionsBtn");
    if (btn) btn.textContent = allSectionsFolded ? "展开全部" : "折叠全部";
  }

  async function startBatchGeneration() {
    if (!state.project || !state.outline?.length) {
      toast("请先拟定并确认目录", true);
      return;
    }
    if (state.batchGenerating) return;

    state.batchGenerating = true;
    state.batchAbort = false;

    const wrapper = $("#batchProgressWrapper");
    const fill = $("#batchProgressFill");
    const text = $("#batchProgressText");
    const batchBtn = $("#batchGenerateSectionsBtn");

    if (wrapper) wrapper.classList.remove("hidden");
    if (batchBtn) {
      batchBtn.disabled = true;
      batchBtn.textContent = "批量生成中…";
    }

    const outline = state.outline;
    let completedCount = 0;
    const total = outline.length;

    for (let i = 0; i < total; i++) {
      if (state.batchAbort) {
        toast("已中止批量生成");
        break;
      }
      const section = outline[i];
      if (fill) fill.style.width = `${Math.round(((i + 0.1) / total) * 100)}%`;
      if (text) text.textContent = `正在生成 [${i + 1}/${total}]：${section.title}…`;

      try {
        const result = await api(`/api/projects/${state.project.id}/sections/${section.id}/generate`, { method: "POST" });
        state.project.sections = state.project.sections || {};
        state.project.sections[section.id] = result.content;

        await api(`/api/projects/${state.project.id}/sections/${section.id}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content: result.content }),
        });
        completedCount++;
      } catch (err) {
        console.warn(`生成章节 ${section.title} 失败:`, err);
      }
    }

    if (fill) fill.style.width = "100%";
    if (text) text.textContent = `批量生成结束，共完成 ${completedCount}/${total} 章节。`;
    renderSections();
    updateDraftStats();
    toast(`批量生成完成，共更新 ${completedCount} 个章节。`);

    setTimeout(() => {
      if (wrapper) wrapper.classList.add("hidden");
    }, 2800);

    state.batchGenerating = false;
    state.batchAbort = false;
    if (batchBtn) {
      batchBtn.disabled = false;
      batchBtn.textContent = "⚡ 批量生成所有章节";
    }
  }

  function cancelBatchGeneration() {
    state.batchAbort = true;
    const progressText = $("#batchProgressText");
    if (progressText) progressText.textContent = "已发起取消，正在等待当前章节收尾…";
  }


  function renderReviewCard(wrapper, card) {
    if (!wrapper || !card) return;
    let cardEl = wrapper.querySelector(".agentic-review-card");
    if (!cardEl) {
      cardEl = document.createElement("div");
      cardEl.className = "agentic-review-card";
      wrapper.append(cardEl);
    }
    cardEl.replaceChildren();

    const header = document.createElement("div");
    header.className = "agentic-review-header";

    const scoreTitle = document.createElement("div");
    scoreTitle.className = "agentic-review-score";
    const incomplete = card.review_status === "failed" || !Number.isFinite(card.score);
    scoreTitle.textContent = incomplete
      ? "AI 辅助检查：评审未完成（无分数）"
      : `AI 辅助检查：${card.score} 分 · ${card.grade || ""}（非官方评审）`;

    const badge = document.createElement("span");
    badge.className = `agentic-review-badge ${card.passed && !incomplete ? "" : "warning"}`;
    badge.textContent = incomplete ? "草稿保留 · 待重试评审"
      : `${card.iterations} 轮检查 · ${card.passed ? "通过辅助检查" : "待完善"}`;

    header.append(scoreTitle, badge);
    cardEl.append(header);

    if (Array.isArray(card.user_hints) && card.user_hints.length > 0) {
      for (const hint of card.user_hints) {
        const hintEl = document.createElement("div");
        hintEl.className = "agentic-review-hint";
        hintEl.textContent = hint;
        cardEl.append(hintEl);
      }
    }
  }

  function renderSections() {
    const root = $("#draftSections");
    root.replaceChildren();
    updateDraftStats();
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
      wrapper.id = `draft-sec-${section.id}`;
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

      const initialContent = state.project.sections?.[section.id] || "";
      const wordBadge = document.createElement("span");
      wordBadge.className = "section-word-badge";
      wordBadge.textContent = `${countWords(initialContent)} 字`;

      const statusPill = document.createElement("span");
      statusPill.className = `section-status-pill ${initialContent.trim() ? "saved" : "unsaved"}`;
      statusPill.textContent = initialContent.trim() ? "✓ 已有草稿" : "● 待撰写";

      titleGroup.append(foldToggle, title, wordBadge, statusPill);

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

      // Toolbar for mode switch and quick placeholders
      const toolbar = document.createElement("div");
      toolbar.className = "draft-section-toolbar";

      const leftTools = document.createElement("div");
      leftTools.className = "toolbar-group";
      const editModeBtn = document.createElement("button");
      editModeBtn.type = "button";
      editModeBtn.className = "mode-switch-btn active";
      editModeBtn.textContent = "✏️ 编辑";

      const previewModeBtn = document.createElement("button");
      previewModeBtn.type = "button";
      previewModeBtn.className = "mode-switch-btn";
      previewModeBtn.textContent = "👁️ 预览排版";

      leftTools.append(editModeBtn, previewModeBtn);

      const rightTools = document.createElement("div");
      rightTools.className = "toolbar-group";
      const placeholderBtn = document.createElement("button");
      placeholderBtn.type = "button";
      placeholderBtn.className = "placeholder-btn";
      placeholderBtn.textContent = "＋ 插入【待补充】";
      placeholderBtn.title = "在光标处插入待补充标记";

      rightTools.append(placeholderBtn);
      toolbar.append(leftTools, rightTools);

      const editor = document.createElement("textarea");
      editor.value = initialContent;
      editor.placeholder = "点击“生成草稿”，或直接在这里撰写。缺失具体数据或依据时标注【待补充】。";

      const previewBox = document.createElement("div");
      previewBox.className = "section-preview-render hidden";

      function updatePreview() {
        previewBox.innerHTML = editor.value.trim()
          ? renderMarkdownSafe(editor.value)
          : '<p style="color:var(--text-subtle);font-style:italic;">暂无草稿内容，点击上方“生成草稿”或直接输入。</p>';
      }

      editModeBtn.addEventListener("click", () => {
        editModeBtn.classList.add("active");
        previewModeBtn.classList.remove("active");
        editor.classList.remove("hidden");
        previewBox.classList.add("hidden");
      });

      previewModeBtn.addEventListener("click", () => {
        previewModeBtn.classList.add("active");
        editModeBtn.classList.remove("active");
        updatePreview();
        editor.classList.add("hidden");
        previewBox.classList.remove("hidden");
      });

      placeholderBtn.addEventListener("click", () => {
        const start = editor.selectionStart || 0;
        const end = editor.selectionEnd || 0;
        const text = editor.value;
        const insert = "【待补充：请核实具体数据/依据】";
        editor.value = text.slice(0, start) + insert + text.slice(end);
        editor.focus();
        editor.selectionStart = editor.selectionEnd = start + insert.length;
        editor.dispatchEvent(new Event("input"));
      });

      editor.addEventListener("input", () => {
        const words = countWords(editor.value);
        wordBadge.textContent = `${words} 字`;
        statusPill.className = "section-status-pill unsaved";
        statusPill.textContent = "● 未保存";
        updateDraftStats();
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
        statusPill.className = "section-status-pill generating";
        statusPill.textContent = "✦ 生成中…";
        wrapper.classList.add("generating");
        try {
          let result = await api(`/api/projects/${state.project.id}/sections/${section.id}/generate`, { method: "POST" });
          if (result && result.status === "processing" && result.job_id) {
            statusPill.textContent = "✦ 后台生成中…";
            for (let i = 0; i < 45; i++) {
              await new Promise(r => setTimeout(r, 2000));
              const jobSt = await api(`/api/projects/${state.project.id}/sections/${section.id}/jobs/${result.job_id}`);
              if (jobSt && jobSt.status === "completed") {
                result = jobSt.result || {};
                break;
              }
              if (jobSt && jobSt.status === "failed") {
                throw new Error(jobSt.error_message || "后台生成失败");
              }
              statusPill.textContent = `✦ 生成中(${jobSt.step || "执行中"})…`;
            }
          }

          if (result.conflict_status === "user_edit_preserved") {
            toast(result.notice || "检测到您已编辑该章节，AI最新草稿已安全存入历史版本，未覆盖您的正文。", false);
            statusPill.className = "section-status-pill saved";
            statusPill.textContent = "● 有新备选版本";
            if (result.review_card) {
              renderReviewCard(wrapper, result.review_card);
            }
          } else if (result.content) {
            editor.value = result.content;
            wordBadge.textContent = `${countWords(result.content)} 字`;
            const evidence = (result.evidence || []).map((e) => `${e.source_name} · ${e.source_ref}`).join("；");
            sources.textContent = evidence ? `检索依据：${evidence}` : "未检索到可用材料；请补充事实或保留“待补充”标记。";
            state.project.sections = state.project.sections || {};
            state.project.sections[section.id] = result.content;

            await api(`/api/projects/${state.project.id}/sections/${section.id}`, {
              method: "PUT",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ content: result.content }),
            });

            if (result.review_card) {
              renderReviewCard(wrapper, result.review_card);
            }
            statusPill.className = "section-status-pill saved";
            statusPill.textContent = "✓ 已保存";
            updateDraftStats();
            toast("章节草稿已生成并自动保存。");
          }
        } catch (error) {
          statusPill.className = "section-status-pill unsaved";
          statusPill.textContent = "● 生成失败";
          toast(error.message, true);
          if ((error.message || "").includes("积分不足") || (error.message || "").includes("402")) {
            openRechargeDialog();
          }
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
          statusPill.className = "section-status-pill saved";
          statusPill.textContent = "✓ 已保存";
          updateDraftStats();
          toast(`已保存“${section.title}”。`);
        } catch (error) {
          toast(error.message, true);
        }
      });

      bodyWrapper.append(toolbar, editor, previewBox, sources);
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
      if ((error.message || "").includes("积分不足") || (error.message || "").includes("402")) {
        openRechargeDialog();
      }
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

  async function generateWorkbenchImage() {
    if (!state.project) return toast("请先打开项目", true);
    const prompt = $("#workbenchImagePrompt").value.trim();
    if (prompt.length < 5) return toast("请补充具体的配图描述", true);
    const btn = $("#generateWorkbenchImageBtn");
    btn.disabled = true;
    try {
      const result = await api(`/api/projects/${state.project.id}/images/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt }),
      });
      state.project.diagrams = [...(state.project.diagrams || []), result.diagram];
      state.diagrams = state.project.diagrams;
      renderDiagrams();
      await loadUserBalance();
      toast("配图已生成并保存到项目。");
    } catch (error) {
      toast(error.message, true);
      await loadUserBalance();
      if ((error.message || "").includes("积分不足") || (error.message || "").includes("402")) {
        openRechargeDialog();
      }
    } finally {
      btn.disabled = false;
    }
  }

  function showImageLightbox(src, title = "图表预览") {
    const dialog = $("#imageLightboxDialog");
    const img = $("#lightboxImage");
    const titleEl = $("#lightboxTitle");
    const dl = $("#lightboxDownloadBtn");
    if (!dialog || !img) return;
    img.src = src;
    if (titleEl) titleEl.textContent = title;
    if (dl) {
      dl.href = src;
      dl.download = `${title}.png`;
    }
    dialog.showModal();
  }

  function renderDiagrams() {
    const gallery = $("#diagramGallery");
    gallery.replaceChildren();
    const diagrams = state.diagrams || [];
    if (!diagrams.length) {
      const empty = document.createElement("div");
      empty.className = "empty-diagram-box";
      empty.innerHTML = `<strong>暂未生成路线图或项目配图</strong><p style="margin:4px 0 0;color:var(--text-subtle);">点击上方「请 Agent 提建议」梳理关键节点，或输入提示词生成项目配图，生成后将自动嵌入最终 Word 文档中。</p>`;
      gallery.append(empty);
      return;
    }
    for (const diagram of diagrams) {
      const card = document.createElement("div");
      card.className = "diagram-card";
      const title = document.createElement("h3");
      title.textContent = diagram.title;
      card.append(title);
      const imgUrl = diagram.preview_url || (diagram.preview ? `/api/projects/${state.project.id}/diagrams/${diagram.id}/preview` : null);
      if (imgUrl) {
        const image = document.createElement("img");
        image.src = imgUrl;
        image.alt = diagram.title;
        image.title = "点击查看高清大图";
        image.addEventListener("click", () => showImageLightbox(imgUrl, diagram.title));
        card.append(image);
      }
      const steps = document.createElement("p");
      steps.textContent = (diagram.nodes || []).join(" → ");
      card.append(steps);

      const actionsBar = document.createElement("div");
      actionsBar.className = "diagram-card-actions";

      const edit = button("✏️ 编辑步骤", "button button-small button-secondary");
      edit.addEventListener("click", () => {
        state.editingDiagramId = diagram.id;
        $("#diagramTitle").value = diagram.title;
        $("#diagramNodes").value = (diagram.nodes || []).join("\n");
        $("#diagramEditor").classList.remove("hidden");
        $("#saveDiagramBtn").textContent = "保存图表修改";
        $("#diagramEditor").scrollIntoView({ behavior: "smooth", block: "center" });
      });
      actionsBar.append(edit);

      if (imgUrl) {
        const viewBig = button("🔍 放大", "button button-small button-quiet");
        viewBig.addEventListener("click", () => showImageLightbox(imgUrl, diagram.title));
        actionsBar.append(viewBig);
      }

      const del = document.createElement("button");
      del.type = "button";
      del.className = "diagram-del-btn";
      del.textContent = "🗑️ 删除";
      del.title = "从本项目中移除此图表";
      del.addEventListener("click", async () => {
        if (!confirm(`确定删除图表“${diagram.title}”吗？`)) return;
        try {
          await api(`/api/projects/${state.project.id}/diagrams/${diagram.id}`, { method: "DELETE" });
          state.diagrams = (state.diagrams || []).filter(d => d.id !== diagram.id);
          state.project.diagrams = state.diagrams;
          renderDiagrams();
          toast("图表已删除。");
        } catch (err) {
          toast(err.message, true);
        }
      });
      actionsBar.append(del);

      card.append(actionsBar);
      gallery.append(card);
    }
  }

  function toggleChatMenu() {
    const menu = $("#chatActionMenu");
    menu?.classList.toggle("hidden");
  }

  async function copyFullChatHistory() {
    const messages = state.messages || [];
    if (!messages.length) return toast("当前暂无对话记录", true);
    const text = messages.map(m => `### ${m.role === "user" ? "用户" : "Stardust Agent"}\n\n${m.content}`).join("\n\n---\n\n");
    try {
      await navigator.clipboard.writeText(text);
      toast("已复制完整对话记录到剪贴板");
    } catch {
      toast("复制失败，请重试", true);
    }
  }

  function exportChatAsMarkdown() {
    const messages = state.messages || [];
    if (!messages.length) return toast("当前暂无对话记录", true);
    const text = `# Stardust Agent 对话记录 · ${state.project?.title || "未命名课题"}\n\n` +
      messages.map(m => `### ${m.role === "user" ? "用户" : "Stardust Agent"}\n\n${m.content}`).join("\n\n---\n\n");
    const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${state.project?.title || "课题"}对话记录.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    toast("已导出 Markdown 对话记录文件");
  }

  function clearChatViewDisplay() {
    if (!confirm("确定清空当前对话窗口的显示内容吗？（不会删除服务器上的项目历史）")) return;
    const root = $("#chatMessages");
    root.replaceChildren();
    appendMessage(
      "assistant",
      `窗口已清空。我是 **Stardust Agent**，针对「${state.project?.state?.skill_name || "当前赛道"}」，有什么我可以继续协助你的？`
    );
    toast("窗口已重置");
  }

  function autoResizeChatInput() {
    const input = $("#chatInput");
    if (!input) return;
    input.style.height = "auto";
    input.style.height = `${Math.min(180, Math.max(44, input.scrollHeight))}px`;
  }

  function syncChatControls() {
    $("#sendBtn").disabled = state.chatSending;
    $$("#chatTools button").forEach((button) => { button.disabled = state.chatSending; });
  }

  function appendThinkingMessage() {
    const root = $("#chatMessages");
    const row = document.createElement("div");
    row.className = "message assistant thinking";
    const avatar = document.createElement("div");
    avatar.className = "message-avatar";
    avatar.textContent = "✦";
    const bubble = document.createElement("div");
    bubble.className = "thinking-bubble";
    const status = document.createElement("span");
    status.textContent = "正在等待模型回复，请勿重复发送…";
    const dots = document.createElement("span");
    dots.className = "thinking-dots";
    dots.append(document.createElement("span"), document.createElement("span"), document.createElement("span"));
    bubble.append(status, dots);
    row.append(avatar, bubble);
    root.append(row);
    root.scrollTop = root.scrollHeight;
    const started = Date.now();
    const timer = setInterval(() => {
      const seconds = Math.floor((Date.now() - started) / 1000);
      status.textContent = seconds >= 30
        ? `已等待 ${seconds} 秒，模型响应较慢，请勿重复发送。`
        : `正在等待模型回复，已等待 ${seconds} 秒…`;
    }, 1000);
    return {
      row,
      remove() { clearInterval(timer); row.remove(); },
      setStatus(msg) { clearInterval(timer); status.textContent = msg; },
    };
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

  function appendMessage(role, text, actionNode = null) {
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
      if (actionNode) {
        bubble.append(actionNode);
      }
      const copyBtn = document.createElement("button");
      copyBtn.type = "button";
      copyBtn.className = "bubble-copy-btn";
      copyBtn.textContent = "📋 复制";
      copyBtn.title = "复制此条回答";
      copyBtn.addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(text);
          toast("已复制回答内容");
        } catch {
          toast("复制失败，请手动选取", true);
        }
      });
      row.append(copyBtn);
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
    if (state.chatSending) return toast("上一条请求还未完成，请勿重复发送。", true);
    const projectId = state.project.id;
    state.chatSending = true;
    syncChatControls();
    if (messageOverride === null) {
      input.value = "";
      input.style.height = "auto";
    }
    appendMessage("user", message);
    const pending = appendThinkingMessage();

    // Check if api was replaced by a mock (e.g. in headless unit tests)
    const isMockApi = typeof api === "function" && api !== originalApi;
    if (isMockApi) {
      try {
        const result = await api(`/api/projects/${projectId}/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message }),
        });
        pending.remove();
        if (state.project?.id !== projectId) return;
        if (typeof result.message !== "string" || !result.message.trim()) {
          throw new Error("模型未返回可用正文，请勿连续重试；请先查看积分流水并联系管理员核对。");
        }
        appendMessage("assistant", result.message);
        state.messages.push({ role: "user", content: message }, { role: "assistant", content: result.message });
        if (result.free_chat) {
          state.freeChatsRemaining = Number(result.free_chats_remaining || 0);
          renderFreeChatsIndicator();
          if (state.freeChatsRemaining > 0) {
            toast(`本轮为免费体验对话（剩余 ${state.freeChatsRemaining} 次免费对话）`);
          } else {
            toast("本轮为最后一次免费体验对话，后续调用将使用积分");
          }
        } else if (result.free_chats_remaining !== undefined) {
          state.freeChatsRemaining = Number(result.free_chats_remaining || 0);
          renderFreeChatsIndicator();
        }
        if (result.setup_updated || (result.tool_calls || []).some((name) => ["save_project_fact", "save_section"].includes(name))) {
          await loadProject(state.project.id);
        }
        await refreshProjects();
        if (state.llmConfig.provider === "preset") await loadUserBalance();
      } catch (error) {
        pending.remove();
        if (state.project?.id !== projectId) return;
        await loadProject(projectId);
        const isCreditsErr = (error.message || "").includes("积分不足") || (error.message || "").includes("402");
        if (isCreditsErr) {
          const ctaWrap = document.createElement("div");
          ctaWrap.className = "chat-recharge-cta";
          if (state.cardShopUrl) {
            const shopLink = document.createElement("a");
            shopLink.className = "button button-primary button-small";
            shopLink.href = state.cardShopUrl;
            shopLink.target = "_blank";
            shopLink.rel = "noopener noreferrer";
            shopLink.textContent = "获取卡密 ↗";
            ctaWrap.append(shopLink);
          }
          const openBtn = document.createElement("button");
          openBtn.type = "button";
          openBtn.className = "button button-secondary button-small";
          openBtn.textContent = "输入卡密";
          openBtn.addEventListener("click", () => openRechargeDialog());
          ctaWrap.append(openBtn);
          appendMessage("assistant", `暂时无法完成：${error.message}`, ctaWrap);
          openRechargeDialog();
        } else {
          appendMessage("assistant", `暂时无法完成：${error.message}`);
        }
        if (state.llmConfig.provider === "preset") await loadUserBalance();
      } finally {
        state.chatSending = false;
        syncChatControls();
      }
      return;
    }

    // Real SSE streaming path
    let assistantRow = null;
    let bubble = null;
    let streamedText = "";
    let finalResult = null;

    try {
      const url = `/api/projects/${projectId}/chat?stream=true`;
      const headers = new Headers({
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
      });
      if (state.authSession?.access_token) {
        headers.set("Authorization", `Bearer ${state.authSession.access_token}`);
      }
      const body = {
        message,
        stream: true,
        llm_config: { ...state.llmConfig },
      };

      const response = await fetch(url, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        let errText = "";
        try {
          const errJson = await response.json();
          errText = errJson.detail || errJson.error;
        } catch {
          errText = await response.text();
        }
        throw new Error(errText || `请求失败 (${response.status})`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let sseBuffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        sseBuffer += decoder.decode(value, { stream: true });
        const blocks = sseBuffer.split("\n\n");
        sseBuffer = blocks.pop() || "";
        for (const block of blocks) {
          if (!block.trim()) continue;
          let eventType = "message";
          let eventData = "";
          for (const line of block.split("\n")) {
            if (line.startsWith("event:")) {
              eventType = line.slice(6).trim();
            } else if (line.startsWith("data:")) {
              eventData = line.slice(5).trim();
            }
          }
          if (!eventData) continue;
          const parsed = JSON.parse(eventData);

          if (eventType === "status") {
            if (pending.setStatus && parsed.message) {
              pending.setStatus(parsed.message);
            }
          } else if (eventType === "delta") {
            if (!assistantRow) {
              pending.remove();
              assistantRow = document.createElement("div");
              assistantRow.className = "message assistant";
              const avatar = document.createElement("div");
              avatar.className = "message-avatar";
              avatar.textContent = "✦";
              assistantRow.append(avatar);
              bubble = document.createElement("div");
              bubble.className = "message-bubble";
              assistantRow.append(bubble);
              const root = $("#chatMessages");
              root.append(assistantRow);
            }
            streamedText += parsed.text || "";
            bubble.textContent = streamedText;
            const root = $("#chatMessages");
            root.scrollTop = root.scrollHeight;
          } else if (eventType === "done") {
            finalResult = parsed;
          } else if (eventType === "error") {
            throw new Error(parsed.error || "请求发生错误");
          }
        }
      }

      pending.remove();
      if (state.project?.id !== projectId) return;

      const finalText = finalResult?.message || streamedText;
      if (!finalText.trim()) {
        throw new Error("模型未返回可用正文，请勿连续重试；请先查看积分流水并联系管理员核对。");
      }

      if (assistantRow && bubble) {
        bubble.innerHTML = renderMarkdownSafe(finalText);
        const copyBtn = document.createElement("button");
        copyBtn.type = "button";
        copyBtn.className = "bubble-copy-btn";
        copyBtn.textContent = "📋 复制";
        copyBtn.title = "复制此条回答";
        copyBtn.addEventListener("click", async () => {
          try {
            await navigator.clipboard.writeText(finalText);
            toast("已复制回答内容");
          } catch {
            toast("复制失败，请手动选取", true);
          }
        });
        assistantRow.append(copyBtn);
      } else {
        appendMessage("assistant", finalText);
      }

      state.messages.push({ role: "user", content: message }, { role: "assistant", content: finalText });

      if (finalResult?.free_chat) {
        state.freeChatsRemaining = Number(finalResult.free_chats_remaining || 0);
        renderFreeChatsIndicator();
        if (state.freeChatsRemaining > 0) {
          toast(`本轮为免费体验对话（剩余 ${state.freeChatsRemaining} 次免费对话）`);
        } else {
          toast("本轮为最后一次免费体验对话，后续调用将使用积分");
        }
      } else if (finalResult?.free_chats_remaining !== undefined) {
        state.freeChatsRemaining = Number(finalResult.free_chats_remaining || 0);
        renderFreeChatsIndicator();
      }
      if (finalResult?.setup_updated || (finalResult?.tool_calls || []).some((name) => ["save_project_fact", "save_section"].includes(name))) {
        await loadProject(state.project.id);
      }
      await refreshProjects();
      if (state.llmConfig.provider === "preset") await loadUserBalance();
    } catch (error) {
      pending.remove();
      if (assistantRow && !streamedText.trim()) assistantRow.remove();
      if (state.project?.id !== projectId) return;
      await loadProject(projectId);
      const isCreditsErr = (error.message || "").includes("积分不足") || (error.message || "").includes("402");
      if (isCreditsErr) {
        const ctaWrap = document.createElement("div");
        ctaWrap.className = "chat-recharge-cta";
        if (state.cardShopUrl) {
          const shopLink = document.createElement("a");
          shopLink.className = "button button-primary button-small";
          shopLink.href = state.cardShopUrl;
          shopLink.target = "_blank";
          shopLink.rel = "noopener noreferrer";
          shopLink.textContent = "获取卡密 ↗";
          ctaWrap.append(shopLink);
        }
        const openBtn = document.createElement("button");
        openBtn.type = "button";
        openBtn.className = "button button-secondary button-small";
        openBtn.textContent = "输入卡密";
        openBtn.addEventListener("click", () => openRechargeDialog());
        ctaWrap.append(openBtn);
        appendMessage("assistant", `暂时无法完成：${error.message}`, ctaWrap);
        openRechargeDialog();
      } else {
        appendMessage("assistant", `暂时无法完成：${error.message}`);
      }
      if (state.llmConfig.provider === "preset") await loadUserBalance();
    } finally {
      state.chatSending = false;
      syncChatControls();
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
      if ((error.message || "").includes("积分不足") || (error.message || "").includes("402")) {
        openRechargeDialog();
      }
    } finally {
      buttonNode.disabled = false;
      buttonNode.textContent = "开启模拟评审";
    }
  }

  async function exportDoc() {
    const btn = $("#exportBtn");
    const topBtn = $("#quickExportTopBtn");
    const headingBtn = $("#headingExportBtn");
    [btn, topBtn, headingBtn].forEach(b => {
      if (b) {
        b.disabled = true;
        b.dataset.origText = b.textContent;
        b.textContent = "正在生成…";
      }
    });
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

      // 自动触发浏览器安全下载
      const autoDownload = document.createElement("a");
      autoDownload.href = result.download_url;
      autoDownload.download = link.download;
      document.body.appendChild(autoDownload);
      autoDownload.click();
      document.body.removeChild(autoDownload);

      toast("Word 草稿已生成并开始下载！");
    } catch (error) {
      toast(error.message, true);
      if ((error.message || "").includes("积分不足") || (error.message || "").includes("402")) {
        openRechargeDialog();
      }
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = '生成并下载 Word 申报书 <span>↓</span>';
      }
      if (topBtn) {
        topBtn.disabled = false;
        topBtn.innerHTML = '<span>📥 导出草稿</span>';
      }
      if (headingBtn) {
        headingBtn.disabled = false;
        headingBtn.textContent = '📥 导出 Word';
      }
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
      renderProjectList(state.projectsList, e.target.value);
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
    $("#chooseLeaderPhotoBtn")?.addEventListener("click", () => $("#leaderPhotoInput")?.click());
    $("#leaderPhotoInput")?.addEventListener("change", (e) => {
      if (e.target.files?.[0]) handleLeaderPhotoUpload(e.target.files[0]);
    });
    $("#removeLeaderPhotoBtn")?.addEventListener("click", handleLeaderPhotoDelete);
    $("#proposeFactsBtn").addEventListener("click", proposeFacts);
    $("#paperSearchBtn").addEventListener("click", () => searchSources("paper"));
    $("#officialSearchBtn").addEventListener("click", () => searchSources("official"));
    $("#officialUrlBtn").addEventListener("click", previewOfficialUrl);
    $("#generateOutlineBtn").addEventListener("click", generateOutline);
    $("#resetOutlineBtn")?.addEventListener("click", generateOutline);
    $("#saveOutlineBtn").addEventListener("click", saveOutline);
    $("#batchGenerateSectionsBtn")?.addEventListener("click", startBatchGeneration);
    $("#cancelBatchBtn")?.addEventListener("click", cancelBatchGeneration);
    $("#toggleAllSectionsBtn")?.addEventListener("click", toggleAllSections);
    $("#proposeDiagramBtn").addEventListener("click", proposeDiagram);
    $("#saveDiagramBtn").addEventListener("click", saveDiagram);
    $("#generateWorkbenchImageBtn").addEventListener("click", generateWorkbenchImage);
    $("#pilotFingerprintBtn").addEventListener("click", makePilotFingerprint);
    $("#chatForm").addEventListener("submit", sendChat);
    $("#chatInput").addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        sendChat();
      }
    });
    $("#chatInput").addEventListener("input", autoResizeChatInput);
    $$(".chat-tools button").forEach((button) => button.addEventListener("click", () => {
      $("#chatInput").value = button.dataset.prompt;
      autoResizeChatInput();
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
    $("#clearChatBtn")?.addEventListener("click", (e) => {
      e.stopPropagation();
      toggleChatMenu();
    });
    $("#copyFullChatBtn")?.addEventListener("click", () => {
      toggleChatMenu();
      copyFullChatHistory();
    });
    $("#exportChatMdBtn")?.addEventListener("click", () => {
      toggleChatMenu();
      exportChatAsMarkdown();
    });
    $("#explainChatStorageBtn")?.addEventListener("click", () => {
      toggleChatMenu();
      toast(state.cloudMode ? "对话记录已随项目保存至云端安全空间。" : "对话记录保存在当前本机项目库中。");
    });
    $("#clearChatViewBtn")?.addEventListener("click", () => {
      toggleChatMenu();
      clearChatViewDisplay();
    });
    document.addEventListener("click", (e) => {
      if (!e.target.closest(".chat-menu-container")) {
        $("#chatActionMenu")?.classList.add("hidden");
      }
    });
    $("#closeLightboxBtn")?.addEventListener("click", () => $("#imageLightboxDialog")?.close());
    $("#closeDocumentPreviewBtn").addEventListener("click", () => $("#documentPreviewDialog").close());
    $("#documentPreviewDialog").addEventListener("close", clearDocumentPreview);
    $("#toggleChatBtn")?.addEventListener("click", toggleChatColumn);

    $$(".workspace-tab-btn").forEach(btn => {
      btn.addEventListener("click", () => handleTabNavigation(btn.dataset.target));
    });

    // Dialog backdrop click to close
    $$("dialog").forEach((dlg) => {
      dlg.addEventListener("click", (e) => {
        const rect = dlg.getBoundingClientRect();
        const inDialog = (
          rect.top <= e.clientY && e.clientY <= rect.top + rect.height &&
          rect.left <= e.clientX && e.clientX <= rect.left + rect.width
        );
        if (!inDialog) dlg.close();
      });
    });

    $("#modelSettingsBtn").addEventListener("click", () => {
      syncModelSettingsForm();
      $("#modelSettingsDialog").showModal();
    });
    $("#closeModelSettingsBtn").addEventListener("click", () => $("#modelSettingsDialog").close());
    $$('input[name="llmProvider"]').forEach((input) => input.addEventListener("change", updateModelFields));
    $("#testModelConfigBtn").addEventListener("click", testSelectedLlmConfig);
    $("#saveModelConfigBtn").addEventListener("click", saveSelectedLlmConfig);
    $("#customImageReuseText")?.addEventListener("change", (e) => {
      $("#customImageSeparateFields")?.classList.toggle("hidden", e.target.checked);
    });
    $("#creditsBadgeBtn")?.addEventListener("click", openRechargeDialog);
    $("#openRechargeBtn")?.addEventListener("click", openRechargeDialog);
    $("#sidebarRechargeBtn")?.addEventListener("click", openRechargeDialog);
    $("#closeRechargeBtn")?.addEventListener("click", () => $("#rechargeDialog")?.close());
    $("#usageLogsBtn")?.addEventListener("click", openUsageDialog);
    $("#closeUsageBtn")?.addEventListener("click", () => $("#usageDialog")?.close());
    $("#refreshUsageBtn")?.addEventListener("click", openUsageDialog);
    $("#submitRedeemBtn")?.addEventListener("click", handleRedeemCode);
    $("#helpGuideBtn")?.addEventListener("click", openOnboardingDialog);
    $("#closeOnboardingBtn")?.addEventListener("click", closeOnboardingDialog);
    $("#prevOnboardingBtn")?.addEventListener("click", () => setOnboardingStep(currentOnboardingStep - 1));
    $("#nextOnboardingBtn")?.addEventListener("click", () => setOnboardingStep(currentOnboardingStep + 1));
    $("#finishOnboardingBtn")?.addEventListener("click", closeOnboardingDialog);
    $$(".onboarding-step-tab").forEach((tab) => {
      tab.addEventListener("click", () => setOnboardingStep(parseInt(tab.dataset.step, 10)));
    });
    $("#authForm").addEventListener("submit", submitAuthForm);
    $("#retryAuthBtn").addEventListener("click", () => {
      // No credential resubmission or automatic signup retries.
      if (state.authInitializing || state.authBusy) return;
      if (!window.supabase?.createClient || !state.authConfig) {
        window.location.reload();
      } else {
        void initializeCloudAuth(state.authConfig);
      }
    });
    $("#authModeToggle").addEventListener("click", () => {
      if (state.authStatus !== "ready" || state.authBusy) return;
      state.authMode = state.authMode === "signin" ? "signup" : "signin";
      $("#authTitle").textContent = state.authMode === "signup" ? "创建你的项目空间" : "登录你的项目空间";
      syncAuthControls();
      $("#authModeToggle").textContent = state.authMode === "signup"
        ? "已有账号？返回登录"
        : "还没有账号？创建账号";
      $("#authPassword").autocomplete = state.authMode === "signup" ? "new-password" : "current-password";
      $("#authFeedback").textContent = "";
      updateTurnstileState();
    });
    $("#signOutBtn").addEventListener("click", signOutCloudUser);
  }

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

  async function init() {
    setupResizeHandles();
    bindEvents();
    updateTemplateExplain();
    $("#chatFileInput").accept = chatUploadAccept($("#chatUploadKind").value);
    await loadSkills();
    await loadPresetModelsAndPlans();
    const config = await api("/api/config");
    state.turnstileSiteKey = config.turnstile_site_key || "";
    updateTurnstileState();
    $("#pilotFingerprintBox")?.classList.toggle(
      "hidden", new URLSearchParams(window.location.search).get("pilot") !== "1"
    );
    $("#workbenchImageControls")?.classList.toggle("hidden", !config.preset_enabled);
    state.cardRedemptionEnabled = Boolean(config.card_redemption_enabled);
    state.cardShopUrl = config.card_shop_url || "";
    const redeemButton = $("#submitRedeemBtn");
    if (redeemButton) {
      redeemButton.disabled = !state.cardRedemptionEnabled;
      redeemButton.textContent = state.cardRedemptionEnabled ? "立即兑换" : "代兑暂未开通";
    }
    const shopLink = $("#cardShopLink");
    const shopUnavailable = $("#cardShopUnavailable");
    if (shopLink && state.cardRedemptionEnabled && config.card_shop_url) {
      shopLink.href = config.card_shop_url;
      shopLink.classList.remove("hidden");
      shopUnavailable?.classList.add("hidden");
    }
    if (!config.preset_enabled && state.llmConfig.provider === "preset") {
      storeLlmConfig({ provider: config.cloud_mode ? "openai_compatible" : "ollama",
        model: config.cloud_mode ? "" : "qwen2.5:7b", base_url: "", api_key: "" });
    }
    if (!config.preset_enabled) {
      $("#providerPreset")?.closest(".model-provider-option")?.classList.add("hidden");
      if (state.llmConfig.provider === "preset") updateModelFields();
    }
    await initializeCloudAuth(config);
    // In cloud mode the auth gate initializes the Supabase session first; only
    // then can the server bind the balance request to the verified user ID.
    if (!config.cloud_mode || state.authSession?.access_token) await loadUserBalance();
  }

  document.addEventListener("DOMContentLoaded", () => {
    init().catch((error) => {
      if (state.authStatus !== "ready" && !state.appStarted) {
        state.authStatus = "error";
        showAuthGate("工作台初始化失败，请点击“重新连接登录服务”或刷新页面重试。");
      } else {
        toast(error.message, true);
      }
    });
  });
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && state.authSession?.access_token) void loadUserBalance();
  });
})();

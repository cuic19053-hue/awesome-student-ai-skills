/* =========================================================================
 * Stardust Agent · 设置中心
 * 账户 / 购买与积分 / 模型配置 / 用量明细 / 关于
 * 所有弹窗均可通过 X、遮罩、Esc 关闭
 * ========================================================================= */
(function () {
  "use strict";
  const S = window.S;
  const icon = S.icon;
  const esc = S.esc;

  const TABS = [
    { id: "account", label: "账户", icon: "user" },
    { id: "purchase", label: "购买与积分", icon: "credit-card" },
    { id: "model", label: "模型配置", icon: "cpu" },
    { id: "usage", label: "用量明细", icon: "chart" },
    { id: "about", label: "关于", icon: "info" },
  ];

  const data = {
    config: null,
    balance: null,
    balanceError: null,
    presets: null,
    stats: null,
    logs: [],
    usageProjectId: "",
    usageError: null,
  };

  let view = null; // { ctx, active, el }

  function open(tab) {
    if (view) {
      switchTab(tab || view.active);
      return;
    }
    const active = tab || "account";
    const ctx = S.openModal({
      title: "设置",
      subtitle: "模型、积分与数据都集中在这里",
      size: "lg",
      className: "settings-modal",
      body:
        '<div class="settings-layout">' +
        '<nav class="settings-nav" role="tablist">' +
        TABS.map(function (t) {
          return (
            '<button type="button" role="tab" data-settings-tab="' +
            t.id +
            '" class="' +
            (t.id === active ? "active" : "") +
            '">' +
            icon(t.icon) +
            "<span>" +
            t.label +
            "</span></button>"
          );
        }).join("") +
        "</nav>" +
        '<div class="settings-panel" id="settings-panel" role="tabpanel"></div>' +
        "</div>",
      onMount: function (c) {
        const body = c.el.querySelector(".modal-body");
        if (body) {
          body.style.padding = "0";
          body.style.overflow = "hidden";
        }
        view = { ctx: c, active: active, el: c.el };
        c.el.addEventListener("click", onClick);
        c.el.addEventListener("change", onChange);
        switchTab(active);
        loadAll();
      },
      onClose: function () {
        view = null;
      },
    });
    return ctx;
  }

  function switchTab(tab) {
    if (!view) return;
    if (!TABS.some(function (t) { return t.id === tab; })) tab = "account";
    view.active = tab;
    view.el.querySelectorAll("[data-settings-tab]").forEach(function (btn) {
      btn.classList.toggle("active", btn.getAttribute("data-settings-tab") === tab);
    });
    renderPanel();
    if (tab === "purchase" && !data.balance && !data.balanceError) loadBalance();
    if (tab === "usage" && !data.stats) loadStats();
  }

  function $(sel) {
    return view ? view.el.querySelector(sel) : null;
  }

  function renderPanel() {
    const panel = $("#settings-panel");
    if (!panel) return;
    const tab = view.active;
    if (tab === "account") panel.innerHTML = accountPanel();
    else if (tab === "purchase") panel.innerHTML = purchasePanel();
    else if (tab === "model") panel.innerHTML = modelPanel();
    else if (tab === "usage") panel.innerHTML = usagePanel();
    else panel.innerHTML = aboutPanel();
  }

  /* ---------------------------------------------------------------------
   * 数据加载
   * ------------------------------------------------------------------- */
  async function loadAll() {
    try {
      data.config = await S.api("/api/config");
    } catch (e) {
      data.config = null;
    }
    loadBalance();
    loadStats();
  }

  async function loadBalance() {
    try {
      data.balance = await S.api("/api/user/balance");
      data.balanceError = null;
    } catch (e) {
      data.balance = null;
      data.balanceError = e;
    }
    if (view && view.active === "purchase") renderPanel();
    if (window.App && window.App.syncBalance) window.App.syncBalance();
  }

  async function loadStats() {
    try {
      const result = await S.api("/api/token-stats");
      data.stats = (result && result.stats) || null;
      data.usageError = null;
    } catch (e) {
      data.stats = null;
      data.usageError = e;
    }
    if (view && view.active === "usage") renderPanel();
  }

  async function loadProjectUsage(projectId) {
    data.usageProjectId = projectId || "";
    if (!projectId) {
      loadStats();
      return;
    }
    try {
      const result = await S.api("/api/projects/" + projectId + "/usage?limit=20");
      data.stats = result.stats || null;
      data.logs = result.logs || [];
      data.usageError = null;
    } catch (e) {
      data.usageError = e;
      data.stats = null;
      data.logs = [];
    }
    if (view && view.active === "usage") renderPanel();
  }

  /* ---------------------------------------------------------------------
   * 账户
   * ------------------------------------------------------------------- */
  function accountPanel() {
    const ui = S.getUI();
    const cloud = !!(data.config && data.config.cloud_mode);
    const balance = data.balance;
    const themeMode = S.theme.mode();
    const themeModes = [
      { id: "light", label: "浅色" },
      { id: "dark", label: "深色" },
      { id: "auto", label: "跟随系统" },
    ];
    return (
      '<div class="settings-section">' +
      '<h3 class="settings-section-title">外观</h3>' +
      '<p class="settings-section-desc">主题会立即生效，并记住你的选择。</p>' +
      '<div class="settings-card"><div class="settings-row">' +
      '<div><div class="settings-row-label">界面主题</div>' +
      '<div class="settings-row-desc">浅色适合白天与打印预览，深色适合长时间阅读。</div></div>' +
      '<div class="segmented">' +
      themeModes
        .map(function (m) {
          return (
            '<button type="button" data-act="set-theme" data-mode="' +
            m.id +
            '" class="' +
            (themeMode === m.id ? "active" : "") +
            '">' +
            m.label +
            "</button>"
          );
        })
        .join("") +
      "</div></div></div></div>" +
      '<div class="settings-section">' +
      '<h3 class="settings-section-title">个人资料</h3>' +
      '<p class="settings-section-desc">称呼只保存在当前浏览器，用于界面展示与导出提示，不会上传。</p>' +
      '<div class="settings-card">' +
      '<div class="settings-row">' +
      '<div style="display:flex;align-items:center;gap:12px;min-width:0">' +
      '<div class="avatar avatar-lg">' +
      esc(S.initials(ui.userName)) +
      "</div>" +
      '<div style="min-width:0">' +
      '<div class="settings-row-label">' +
      esc(ui.userName) +
      "</div>" +
      '<div class="settings-row-desc">' +
      (cloud ? "云端模式 · 数据保存在 Supabase" : "本地模式 · 数据保存在本机 .agent-data/") +
      "</div>" +
      "</div>" +
      "</div>" +
      '<button type="button" class="btn btn-sm btn-ghost" data-act="rename">修改称呼</button>' +
      "</div>" +
      "</div>" +
      "</div>" +
      '<div class="settings-section">' +
      '<h3 class="settings-section-title">账号与登录</h3>' +
      '<div class="settings-card">' +
      '<div class="settings-row">' +
      '<div><div class="settings-row-label">' +
      (cloud ? "云端账号" : "本机账号") +
      "</div><div class=\"settings-row-desc\">" +
      (cloud
        ? "已启用 Supabase 登录与积分账本，可跨设备同步项目。"
        : "当前为本地版：无需登录，项目与材料只存在这台电脑上。") +
      "</div></div>" +
      (cloud
        ? '<span class="badge badge-ok">' + icon("check") + "已连接</span>"
        : '<span class="badge">本地模式</span>') +
      "</div>" +
      "</div>" +
      "</div>" +
      '<div class="settings-section">' +
      '<h3 class="settings-section-title">数据管理</h3>' +
      '<p class="settings-section-desc">本地保存的会话记录与项目指令可单独清理，项目文件仍保留在 .agent-data/ 中。</p>' +
      '<div class="settings-card">' +
      '<div class="settings-row">' +
      '<div><div class="settings-row-label">清除本地界面数据</div>' +
      '<div class="settings-row-desc">会话线程、项目指令、欢迎页状态、模型配置</div></div>' +
      '<button type="button" class="btn btn-sm btn-danger" data-act="clear-local">清除</button>' +
      "</div>" +
      "</div>" +
      "</div>" +
      (balance
        ? '<div class="settings-section"><h3 class="settings-section-title">当前积分</h3><div class="settings-card"><div class="settings-row"><div class="settings-row-label">' +
          esc(S.fmtCredits(balance.credits)) +
          ' 积分</div><button type="button" class="btn btn-sm btn-ghost" data-act="goto-purchase">充值 / 兑换</button></div></div></div>'
        : "")
    );
  }

  /* ---------------------------------------------------------------------
   * 购买与积分
   * ------------------------------------------------------------------- */
  function purchasePanel() {
    const cfg = data.config || {};
    const balance = data.balance;
    const local = !!(data.balanceError && (data.balanceError.status === 503 || data.balanceError.status === 404));
    const plans = [
      { price: "0.5", credits: "5", desc: "体验一次完整材料撰写" },
      { price: "1", credits: "10", desc: "常规申报书所需额度" },
    ];
    let balanceHtml;
    if (balance) {
      balanceHtml =
        '<div class="balance-grid">' +
        '<div class="balance-cell"><div class="balance-label">当前积分</div><div class="balance-value">' +
        esc(S.fmtCredits(balance.credits)) +
        "<small>积分</small></div></div>" +
        '<div class="balance-cell muted-card"><div class="balance-label">累计充值</div><div class="balance-value">' +
        esc(S.fmtCredits(balance.total_credited)) +
        "<small>积分</small></div></div>" +
        '<div class="balance-cell muted-card"><div class="balance-label">累计消耗</div><div class="balance-value">' +
        esc(S.fmtCredits(balance.total_consumed)) +
        "<small>积分</small></div></div>" +
        "</div>" +
        (balance.free_chats_remaining > 0
          ? '<div class="settings-row-desc" style="margin-top:8px">剩余免费体验对话：' +
            esc(balance.free_chats_remaining) +
            " 次</div>"
          : "");
    } else {
      balanceHtml =
        '<div class="balance-grid">' +
        '<div class="balance-cell"><div class="balance-label">当前积分</div><div class="balance-value">—</div></div>' +
        '<div class="balance-cell muted-card"><div class="balance-label">计费状态</div><div class="balance-value" style="font-size:14px;line-height:1.4;margin-top:8px">' +
        (local ? "本地模式未接计费" : "暂时不可用") +
        "</div></div>" +
        '<div class="balance-cell muted-card"><div class="balance-label">提示</div><div class="balance-value" style="font-size:14px;line-height:1.4;margin-top:8px">可先用自带 Key</div></div>' +
        "</div>" +
        '<div class="settings-row-desc" style="margin-top:10px">' +
        (local
          ? "本地版未接入充值账本：在「模型配置」里使用 Ollama 或自备 OpenAI 兼容 API 即可继续写作，不扣积分。"
          : "积分账本读取失败，请检查服务配置。") +
        "</div>";
    }

    const shopButton = cfg.card_shop_url
      ? '<a class="btn btn-sm btn-accent" href="' +
        esc(cfg.card_shop_url) +
        '" target="_blank" rel="noopener noreferrer">打开卡密商店</a>'
      : "";

    return (
      '<div class="settings-section">' +
      '<h3 class="settings-section-title">积分余额</h3>' +
      '<p class="settings-section-desc">¥1 = 10 积分；模型调用按官方单价的两倍结算，失败调用会自动退回预留积分。</p>' +
      balanceHtml +
      "</div>" +
      '<div class="settings-section">' +
      '<h3 class="settings-section-title">购买套餐</h3>' +
      '<p class="settings-section-desc">' +
      (cfg.card_redemption_enabled
        ? "购买后获得卡密，在兑换区绑定到当前账号。"
        : "卡密兑换通道尚未开启（需要先在服务端配置 WOPALLY 店铺与账本）。") +
      "</p>" +
      '<div class="plan-list">' +
      plans
        .map(function (p) {
          return (
            '<button type="button" class="plan-card" data-act="buy" data-price="' +
            p.price +
            '">' +
            '<div class="plan-name">' +
            p.credits +
            " 积分</div>" +
            '<div class="plan-price">¥' +
            p.price +
            ' <small>/ 份</small></div>' +
            '<div class="plan-desc">' +
            p.desc +
            "</div></button>"
          );
        })
        .join("") +
      "</div>" +
      (shopButton ? '<div style="margin-top:12px">' + shopButton + "</div>" : "") +
      "</div>" +
      '<div class="settings-section">' +
      '<h3 class="settings-section-title">兑换卡密</h3>' +
      '<p class="settings-section-desc">输入 AGT1 开头的卡密或配对余额码，兑换后积分立即到账。</p>' +
      '<div class="settings-card">' +
      '<div class="fact-add" style="margin-top:0;grid-template-columns:1fr auto">' +
      '<input class="input" id="redeem-code" placeholder="粘贴卡密，例如 AGT1-xxxx-xxxx" autocomplete="off">' +
      '<button type="button" class="btn btn-primary" data-act="redeem">兑换</button>' +
      "</div>" +
      '<div class="settings-row-desc" style="margin-top:10px" id="redeem-note">卡密只在本机提交到服务端核验，不会保存在浏览器。</div>' +
      "</div>" +
      "</div>" +
      (balance && balance.transactions && balance.transactions.length
        ? '<div class="settings-section"><h3 class="settings-section-title">最近积分变动</h3><div class="settings-card" style="padding:6px 0;overflow:hidden">' +
          '<table class="data-table"><thead><tr><th>时间</th><th>类型</th><th>积分</th><th>余额</th></tr></thead><tbody>' +
          balance.transactions
            .slice(0, 10)
            .map(function (t) {
              const kindLabels = {
                payment_credit: "充值",
                chat_usage: "对话消费",
                outline_usage: "大纲消费",
                sections_usage: "章节消费",
                refund: "退回",
                voucher_credit: "卡密兑换",
                adjust: "调整",
              };
              const toCredits = function (value) {
                const micro = Number(value);
                return Number.isFinite(micro) ? S.fmtCredits(micro / 100000) : "—";
              };
              return (
                "<tr><td>" +
                esc(S.fmtTime(t.created_at)) +
                "</td><td>" +
                esc(kindLabels[t.kind] || t.kind || "调整") +
                "</td><td>" +
                esc(toCredits(t.delta_micro_cny)) +
                "</td><td>" +
                esc(toCredits(t.balance_after_micro_cny)) +
                "</td></tr>"
              );
            })
            .join("") +
          "</tbody></table></div></div>"
        : "")
    );
  }

  /* ---------------------------------------------------------------------
   * 模型配置
   * ------------------------------------------------------------------- */
  function modelPanel() {
    const m = S.getModel();
    const cfg = data.config || {};
    const presetReady = !!cfg.preset_enabled;
    const provider = m.provider || "preset";

    function option(id, name, desc, badge) {
      return (
        '<button type="button" class="model-option' +
        (provider === id ? " active" : "") +
        '" data-act="provider" data-provider="' +
        id +
        '">' +
        '<span class="model-radio"></span>' +
        '<span class="model-option-meta">' +
        '<span class="model-option-name">' +
        name +
        (badge || "") +
        "</span>" +
        '<span class="model-option-desc">' +
        desc +
        "</span>" +
        "</span></button>"
      );
    }

    let fields = "";
    if (provider === "ollama") {
      fields =
        '<div class="settings-card">' +
        '<div class="field"><label class="field-label">Ollama 地址</label>' +
        '<input class="input" id="model-base" placeholder="http://127.0.0.1:11434" value="' +
        esc(m.base_url || "") +
        '"><div class="field-hint">默认连接本机 Ollama；不要填写公网地址，项目内容会发送到该主机。</div></div>' +
        '<div class="field"><label class="field-label">模型名称</label>' +
        '<input class="input" id="model-name" placeholder="qwen2.5:7b" value="' +
        esc(m.model || "") +
        '"></div>' +
        "</div>";
    } else if (provider === "openai_compatible") {
      fields =
        '<div class="settings-card">' +
        '<div class="field"><label class="field-label">API Base URL</label>' +
        '<input class="input" id="model-base" placeholder="https://api.example.com/v1" value="' +
        esc(m.base_url || "") +
        '"></div>' +
        '<div class="field"><label class="field-label">模型名称</label>' +
        '<input class="input" id="model-name" placeholder="deepseek-chat" value="' +
        esc(m.model || "") +
        '"></div>' +
        '<div class="field"><label class="field-label">API Key</label>' +
        '<input class="input" id="model-key" type="password" placeholder="sk-..." value="' +
        esc(m.api_key || "") +
        '" autocomplete="off"></div>' +
        '<div class="field-hint">Key 仅保存在当前标签页的 sessionStorage，关闭标签页即失效；每次请求由本机服务转发。</div>' +
        "</div>";
    } else {
      fields =
        '<div class="settings-card">' +
        '<div class="settings-row">' +
        '<div><div class="settings-row-label">平台预设模型</div>' +
        '<div class="settings-row-desc">写作与生图按任务自动路由，按积分结算，无需填写 Key。</div></div>' +
        (presetReady
          ? '<span class="badge badge-ok">' + icon("check") + "可用</span>"
          : '<span class="badge badge-warn">未开通</span>') +
        "</div>" +
        (presetReady
          ? ""
          : '<div class="settings-row-desc" style="margin-top:8px">当前环境未配置平台模型，请改用 Ollama 或自备 API。</div>') +
        "</div>";
    }

    return (
      '<div class="settings-section">' +
      '<h3 class="settings-section-title">推理来源</h3>' +
      '<p class="settings-section-desc">选择对话与写作使用的模型来源。配置只影响当前浏览器标签页。</p>' +
      '<div class="model-options">' +
      option("preset", "平台预设", "开箱即用，按积分计费，无需配置密钥。", "") +
      option("ollama", "本地 Ollama", "完全本机运行，不产生调用费用，需要先启动 Ollama。", "") +
      option("openai_compatible", "自备 OpenAI 兼容 API", "填写自己的 Base URL 与 Key，适合已有中转站或云服务的同学。", "") +
      "</div>" +
      "</div>" +
      '<div class="settings-section">' +
      '<h3 class="settings-section-title">参数</h3>' +
      fields +
      "</div>" +
      '<div class="settings-section">' +
      '<h3 class="settings-section-title">生图模型（可选）</h3>' +
      '<p class="settings-section-desc">用于技术路线图、封面等配图生成；不填则跳过生图功能。</p>' +
      '<div class="settings-card">' +
      '<div class="form-grid">' +
      '<div class="field"><label class="field-label">生图模型</label><input class="input" id="image-model" placeholder="gpt-image-2" value="' +
      esc(m.image_model || "") +
      '"></div>' +
      '<div class="field"><label class="field-label">生图 Base URL</label><input class="input" id="image-base" placeholder="留空则复用文本 API" value="' +
      esc(m.image_base_url || "") +
      '"></div>' +
      '<div class="field form-grid-full"><label class="field-label">生图 API Key</label><input class="input" id="image-key" type="password" placeholder="留空则复用文本 API Key" value="' +
      esc(m.image_api_key || "") +
      '"></div>' +
      "</div>" +
      "</div>" +
      "</div>" +
      '<div class="settings-section">' +
      '<h3 class="settings-section-title">预览选项</h3>' +
      '<div class="settings-card">' +
      '<div class="settings-row">' +
      '<div><div class="settings-row-label">演示模式</div>' +
      '<div class="settings-row-desc">不调用任何模型，用本地示例回复演示界面流程，仅用于前端预览。</div></div>' +
      '<label style="display:inline-flex;align-items:center;gap:8px;font-size:12.5px;color:var(--text-2);cursor:pointer">' +
      '<input type="checkbox" id="demo-mode" ' +
      (m.demo ? "checked" : "") +
      ' style="width:15px;height:15px;accent-color:#8b7cff">开启</label>' +
      "</div>" +
      "</div>" +
      "</div>" +
      '<div class="settings-section" style="display:flex;gap:8px;align-items:center">' +
      '<button type="button" class="btn btn-primary" data-act="save-model">保存配置</button>' +
      '<button type="button" class="btn btn-ghost" data-act="test-model">测试连接</button>' +
      '<span class="settings-row-desc" id="model-test-result" style="margin:0"></span>' +
      "</div>"
    );
  }

  /* ---------------------------------------------------------------------
   * 用量明细
   * ------------------------------------------------------------------- */
  function usagePanel() {
    const stats = data.stats;
    const projects = (window.App && window.App.state && window.App.state.projects) || [];
    const err = data.usageError;
    const cards = stats
      ? '<div class="usage-cards">' +
        '<div class="usage-card"><div class="usage-label">调用次数</div><div class="usage-value">' +
        esc(stats.call_count || 0) +
        "</div></div>" +
        '<div class="usage-card"><div class="usage-label">总 Tokens</div><div class="usage-value">' +
        esc(Number(stats.grand_total_tokens || 0).toLocaleString("en-US")) +
        "</div></div>" +
        '<div class="usage-card"><div class="usage-label">平均延迟</div><div class="usage-value">' +
        esc(Math.round(stats.avg_latency_ms || 0)) +
        "<small> ms</small></div></div>" +
        "</div>"
      : '<div class="empty" style="padding:30px 10px"><div class="empty-icon">' +
        icon("chart") +
        '</div><div class="empty-title">' +
        (err && err.status === 503 ? "积分账本尚未配置" : "暂无用量数据") +
        '</div><div class="empty-desc">' +
        (err && err.status === 503
          ? "本地版未接入计量账本，用量查询需要云端配置。"
          : "完成一次模型调用后，这里会显示 token 消耗与延迟。") +
        "</div></div>";

    const zeroHint =
      stats && !stats.call_count
        ? '<div class="settings-section-desc" style="margin-top:2px">完成一次真实模型调用后，这里会记录 token 消耗、任务类型与延迟。演示模式不产生用量。</div>'
        : "";
    const byTask =
      stats && stats.by_task && stats.by_task.length
        ? '<div class="settings-section"><h3 class="settings-section-title">按任务类型</h3><div class="settings-card" style="padding:6px 0;overflow:hidden"><table class="data-table"><thead><tr><th>任务</th><th>次数</th><th>Tokens</th></tr></thead><tbody>' +
          stats.by_task
            .map(function (row) {
              return (
                "<tr><td>" +
                esc(row.task_type || "—") +
                "</td><td>" +
                esc(row.count || 0) +
                "</td><td>" +
                esc(Number(row.tokens || 0).toLocaleString("en-US")) +
                "</td></tr>"
              );
            })
            .join("") +
          "</tbody></table></div></div>"
        : "";
    const byModel =
      stats && stats.by_model && stats.by_model.length
        ? '<div class="settings-section"><h3 class="settings-section-title">按模型</h3><div class="settings-card" style="padding:6px 0;overflow:hidden"><table class="data-table"><thead><tr><th>模型</th><th>次数</th><th>Tokens</th></tr></thead><tbody>' +
          stats.by_model
            .map(function (row) {
              return (
                "<tr><td>" +
                esc(row.model || "—") +
                "</td><td>" +
                esc(row.count || 0) +
                "</td><td>" +
                esc(Number(row.tokens || 0).toLocaleString("en-US")) +
                "</td></tr>"
              );
            })
            .join("") +
          "</tbody></table></div></div>"
        : "";

    const projectSelect =
      '<div class="settings-section"><h3 class="settings-section-title">按项目查看</h3>' +
      '<p class="settings-section-desc">选择项目可查看该项目近 20 次调用的详细记录。</p>' +
      '<div class="settings-card"><select class="select" id="usage-project">' +
      '<option value="">全部项目</option>' +
      projects
        .map(function (p) {
          return (
            '<option value="' +
            esc(p.id) +
            '"' +
            (data.usageProjectId === p.id ? " selected" : "") +
            ">" +
            esc(S.clean(p.title || "未命名项目")) +
            "</option>"
          );
        })
        .join("") +
      "</select></div></div>";

    const logs =
      data.logs && data.logs.length
        ? '<div class="settings-section"><h3 class="settings-section-title">最近调用</h3><div class="settings-card" style="padding:6px 0;overflow:hidden"><table class="data-table"><thead><tr><th>时间</th><th>任务</th><th>模型</th><th>Tokens</th><th>延迟</th></tr></thead><tbody>' +
          data.logs
            .map(function (row) {
              return (
                "<tr><td>" +
                esc(S.fmtTime(row.created_at)) +
                "</td><td>" +
                esc(row.task_type || "—") +
                "</td><td>" +
                esc(row.model || "—") +
                "</td><td>" +
                esc(Number(row.total_tokens || 0).toLocaleString("en-US")) +
                "</td><td>" +
                esc(row.latency_ms != null ? row.latency_ms + " ms" : "—") +
                "</td></tr>"
              );
            })
            .join("") +
          "</tbody></table></div></div>"
        : "";

    return cards + zeroHint + projectSelect + byTask + byModel + logs;
  }

  /* ---------------------------------------------------------------------
   * 关于
   * ------------------------------------------------------------------- */
  function aboutPanel() {
    return (
      '<div class="settings-section">' +
      '<h3 class="settings-section-title">Stardust Agent</h3>' +
      '<p class="settings-section-desc">大学生申报材料 Agent · 35 个申报赛道 · 逐章协作撰写与 Word 草稿导出。</p>' +
      '<div class="settings-card">' +
      '<div class="settings-row"><span class="settings-row-label">版本</span><span class="settings-row-desc" style="margin:0">前端 v2 · 本地版</span></div>' +
      '<div class="settings-row"><span class="settings-row-label">运行模式</span><span class="settings-row-desc" style="margin:0">' +
      (data.config && data.config.cloud_mode ? "云端（Supabase）" : "本地（FastAPI + SQLite）") +
      "</span></div>" +
      '<div class="settings-row"><span class="settings-row-label">快捷键</span><span class="settings-row-desc" style="margin:0">⌘K 快速跳转 · Esc 关闭弹窗</span></div>' +
      "</div>" +
      "</div>" +
      '<div class="settings-section">' +
      '<h3 class="settings-section-title">使用边界</h3>' +
      '<div class="settings-card">' +
      '<div class="settings-row-desc" style="margin:0;line-height:1.9">' +
      "Agent 生成的所有内容都是草稿：提交前请核对学校通知、数据与引用。未确认的材料不会进入检索；缺少依据之处会标记为“待补充/待验证”。" +
      "</div></div></div>" +
      '<div class="settings-section">' +
      '<h3 class="settings-section-title">链接</h3>' +
      '<div class="settings-card">' +
      '<div class="settings-row"><span class="settings-row-label">项目仓库</span>' +
      '<a class="settings-row-desc" style="margin:0" href="https://github.com/cuic19053-hue/awesome-student-ai-skills" target="_blank" rel="noopener noreferrer">GitHub</a></div>' +
      '<div class="settings-row"><span class="settings-row-label">在线版</span>' +
      '<a class="settings-row-desc" style="margin:0" href="https://agent.stardust.website" target="_blank" rel="noopener noreferrer">agent.stardust.website</a></div>' +
      "</div></div>"
    );
  }

  /* ---------------------------------------------------------------------
   * 事件
   * ------------------------------------------------------------------- */
  function onClick(event) {
    const tabBtn = event.target.closest("[data-settings-tab]");
    if (tabBtn) {
      switchTab(tabBtn.getAttribute("data-settings-tab"));
      return;
    }
    const actEl = event.target.closest("[data-act]");
    if (!actEl) return;
    const act = actEl.getAttribute("data-act");

    if (act === "rename") {
      const ui = S.getUI();
      const ctx = S.openModal({
        title: "修改称呼",
        size: "sm",
        body:
          '<div class="field"><label class="field-label">怎么称呼你</label>' +
          '<input class="input" id="rename-input" data-autofocus maxlength="24" value="' +
          esc(ui.userName) +
          '"></div>',
        footer:
          '<button type="button" class="btn btn-ghost" data-modal-close>取消</button>' +
          '<button type="button" class="btn btn-primary" data-save>保存</button>',
      });
      const save = function () {
        const input = ctx.backdrop.querySelector("#rename-input");
        const name = (input.value || "").trim() || "同学";
        S.setUI({ userName: name });
        if (window.App) {
          window.App.state.ui = S.getUI();
          window.App.refreshShell();
        }
        S.closeModal();
        S.settings.open("account");
        S.toast("称呼已更新", "success");
      };
      ctx.backdrop.querySelector("[data-save]").addEventListener("click", save);
      ctx.backdrop.querySelector("#rename-input").addEventListener("keydown", function (e) {
        if (e.key === "Enter") save();
      });
      return;
    }

    if (act === "clear-local") {
      S.confirm({
        title: "清除本地界面数据？",
        message: "会删除本机保存的会话线程、项目指令、欢迎页状态与模型配置；本地项目和已上传材料不受影响。",
        confirmText: "清除",
        danger: true,
      }).then(function (ok) {
        if (!ok) return;
        S.LS.remove(S.THREADS_KEY);
        S.LS.remove(S.UI_KEY);
        S.SS.remove(S.MODEL_KEY);
        S.toast("本地界面数据已清除", "success");
        if (window.App) {
          window.App.state.ui = S.getUI();
          window.App.refreshShell();
        }
        S.settings.open("account");
      });
      return;
    }

    if (act === "set-theme") {
      const mode = actEl.getAttribute("data-mode") || "auto";
      S.theme.set(mode);
      renderPanel();
      S.toast(mode === "auto" ? "已跟随系统外观" : mode === "dark" ? "已切换到深色外观" : "已切换到浅色外观");
      return;
    }

    if (act === "goto-purchase") {
      switchTab("purchase");
      return;
    }

    if (act === "buy") {
      const shopUrl = data.config && data.config.card_shop_url;
      if (shopUrl) {
        window.open(shopUrl, "_blank", "noopener");
      } else {
        S.toast("当前环境未配置卡密商店（需在服务端设置 WOPALLY_CARD_SHOP_URL）", "error");
      }
      return;
    }

    if (act === "redeem") {
      const input = $("#redeem-code");
      const note = $("#redeem-note");
      const code = (input && input.value ? input.value : "").trim();
      if (!code) {
        S.toast("请先输入卡密", "error");
        if (input) input.focus();
        return;
      }
      actEl.disabled = true;
      actEl.innerHTML = '<span class="spinner"></span> 兑换中';
      S.api("/api/pay/redeem", { method: "POST", body: { code: code } })
        .then(function (result) {
          if (result && result.balance != null) {
            data.balance = Object.assign({}, data.balance || {}, { credits: result.balance });
          }
          actEl.disabled = false;
          actEl.textContent = "兑换";
          if (note) {
            note.textContent =
              result && result.message
                ? result.message
                : "兑换成功，积分已到账。";
            note.style.color = "var(--ok)";
          }
          S.toast("兑换成功", "success");
          loadBalance();
        })
        .catch(function (err) {
          actEl.disabled = false;
          actEl.textContent = "兑换";
          if (note) {
            note.textContent = err.message || "兑换失败";
            note.style.color = "var(--danger)";
          }
          S.toast(err.message || "兑换失败", "error");
        });
      return;
    }

    if (act === "provider") {
      const provider = actEl.getAttribute("data-provider");
      S.setModel({ provider: provider });
      renderPanel();
      return;
    }

    if (act === "save-model") {
      S.setModel(readModelForm());
      S.toast("模型配置已保存（仅当前标签页有效）", "success");
      renderPanel();
      return;
    }

    if (act === "test-model") {
      const resultEl = $("#model-test-result");
      actEl.disabled = true;
      actEl.innerHTML = '<span class="spinner"></span>';
      const payload = readModelForm();
      const body = {
        provider: payload.provider,
        model: payload.model || "",
        base_url: payload.base_url || "",
        api_key: payload.api_key || "",
        image_model: payload.image_model || "",
        image_base_url: payload.image_base_url || "",
        image_api_key: payload.image_api_key || "",
        image_reuse_text: false,
      };
      S.api("/api/model-config/test", { method: "POST", body: body })
        .then(function (res) {
          if (resultEl)
            resultEl.innerHTML =
              '<span class="badge badge-ok">' +
              icon("check") +
              (res && res.message ? esc(res.message) : "连接成功") +
              "</span>";
        })
        .catch(function (err) {
          if (resultEl)
            resultEl.innerHTML = '<span class="badge badge-warn">' + esc(err.message || "连接失败") + "</span>";
        })
        .then(function () {
          actEl.disabled = false;
          actEl.textContent = "测试连接";
        });
      return;
    }
  }

  function readModelForm() {
    const current = S.getModel();
    const providerBtn = view.el.querySelector(".model-option.active");
    const provider = providerBtn ? providerBtn.getAttribute("data-provider") : current.provider;
    const baseEl = $("#model-base");
    const nameEl = $("#model-name");
    const keyEl = $("#model-key");
    const imageModelEl = $("#image-model");
    const imageBaseEl = $("#image-base");
    const imageKeyEl = $("#image-key");
    const demoEl = $("#demo-mode");
    return {
      provider: provider,
      base_url: baseEl ? baseEl.value.trim() : current.base_url,
      model: nameEl ? nameEl.value.trim() : current.model,
      api_key: keyEl ? keyEl.value.trim() : current.api_key,
      image_model: imageModelEl ? imageModelEl.value.trim() : current.image_model,
      image_base_url: imageBaseEl ? imageBaseEl.value.trim() : current.image_base_url,
      image_api_key: imageKeyEl ? imageKeyEl.value.trim() : current.image_api_key,
      demo: demoEl ? demoEl.checked : !!current.demo,
    };
  }

  function onChange(event) {
    const target = event.target;
    if (!target) return;
    if (target.id === "demo-mode") {
      S.setModel({ demo: target.checked });
      S.toast(target.checked ? "已开启演示模式（本地示例回复）" : "已关闭演示模式", "info");
      return;
    }
    if (target.id === "usage-project") {
      loadProjectUsage(target.value);
    }
  }

  window.S.settings = { open: open };
})();

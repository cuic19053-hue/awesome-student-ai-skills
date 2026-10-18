/* =========================================================================
 * Stardust Agent · 应用外壳
 * 欢迎页 / 首页 / 新建项目 / 路由 / 侧边栏
 * ========================================================================= */
(function () {
  "use strict";
  const S = window.S;
  const icon = S.icon;
  const esc = S.esc;

  const state = {
    config: null,
    skills: [],
    projects: [],
    project: null,
    balance: null,
    balanceError: null,
    ui: S.getUI(),
    create: null,
    route: { name: "home" },
    booted: false,
    loading: false,
  };

  const App = (window.App = {
    state: state,
    navigate: navigate,
    reloadCurrent: reloadCurrent,
    refreshShell: refreshShell,
    refreshProjects: refreshProjects,
    syncBalance: syncBalance,
    toggleSidebar: toggleSidebar,
    openSettings: openSettings,
  });

  let mainEl = null;

  /* ---------------------------------------------------------------------
   * 路由
   * ------------------------------------------------------------------- */
  function parseRoute() {
    const raw = location.hash.replace(/^#\/?/, "");
    const parts = raw.split("/").filter(Boolean);
    if (!parts.length) return { name: "home" };
    if (parts[0] === "new") return { name: "create" };
    if (parts[0] === "p" && parts[1]) {
      const projectId = parts[1];
      if (parts[2] === "c" && parts[3]) return { name: "chat", projectId: projectId, threadId: parts[3] };
      return { name: "project", projectId: projectId, tab: parts[2] || "conversations" };
    }
    return { name: "home" };
  }

  function navigate(hash, replace) {
    const target = hash || "#/";
    if (replace) {
      history.replaceState(null, "", target);
      renderRoute();
      return;
    }
    if (location.hash === target) {
      renderRoute();
      return;
    }
    location.hash = target;
  }

  function reloadCurrent() {
    return renderRoute(true);
  }

  /* ---------------------------------------------------------------------
   * 启动
   * ------------------------------------------------------------------- */
  async function boot() {
    S.theme.init();
    if (S.auth) {
      let authState = { cloud: false, signedIn: true };
      try {
        authState = await S.auth.init();
      } catch (e) {}
      if (authState.cloud) {
        S.auth.onGate(showAuthGate);
        S.auth.onSignedIn(function () {
          if (state.booted) {
            window.location.reload();
            return;
          }
          startApp();
        });
        if (!authState.signedIn) {
          showAuthGate(authState.message || "");
          return;
        }
      }
    }
    startApp();
  }

  async function startApp() {
    if (state.booted) return;
    renderShell();
    bindGlobalEvents();
    state.booted = true;
    await loadBootstrap();
    renderRoute();
    if (!state.ui.welcomeSeen) {
      setTimeout(showWelcome, 120);
    }
  }

  let authGateMode = "login";

  function authPageHTML() {
    return (
      '<div class="auth-page" id="auth-page">' +
      '<div class="auth-card">' +
      '<div class="auth-brand">' + icon("sparkles") + "<span>STARDUST</span></div>" +
      '<h1 class="auth-title" id="auth-title">登录 Stardust</h1>' +
      '<p class="auth-sub" id="auth-sub">用邮箱和密码进入你的项目空间</p>' +
      '<form class="auth-form" id="auth-form" novalidate>' +
      '<label class="auth-field"><span class="auth-label">邮箱</span>' +
      '<input class="auth-input" id="auth-email" type="email" autocomplete="email" placeholder="you@example.com" required></label>' +
      '<label class="auth-field"><span class="auth-label">密码</span>' +
      '<input class="auth-input" id="auth-password" type="password" autocomplete="current-password" placeholder="至少 6 位" required minlength="6"></label>' +
      '<div class="auth-error" id="auth-error" role="alert"></div>' +
      '<button class="btn btn-primary auth-submit" id="auth-submit" type="submit">登录</button>' +
      '</form>' +
      '<div class="auth-actions">' +
      '<button class="text-btn" type="button" id="auth-toggle">还没有账号？创建账号</button>' +
      '<button class="text-btn" type="button" id="auth-forgot">忘记密码？</button>' +
      "</div>" +
      '<p class="auth-note">登录状态只保存在这台设备的浏览器里；退出后需要重新登录。</p>' +
      "</div></div>"
    );
  }

  function setAuthFeedback(page, text, ok) {
    const el = page.querySelector("#auth-error");
    if (!el) return;
    el.textContent = text || "";
    el.classList.toggle("ok", !!ok);
  }

  function switchAuthMode(page, mode) {
    authGateMode = mode;
    const signup = mode === "signup";
    page.querySelector("#auth-title").textContent = signup ? "创建 Stardust 账号" : "登录 Stardust";
    page.querySelector("#auth-sub").textContent = signup
      ? "用邮箱注册，注册后直接进入项目空间"
      : "用邮箱和密码进入你的项目空间";
    page.querySelector("#auth-submit").textContent = signup ? "创建账号" : "登录";
    page.querySelector("#auth-toggle").textContent = signup
      ? "已有账号？直接登录"
      : "还没有账号？创建账号";
    page.querySelector("#auth-password").setAttribute(
      "autocomplete",
      signup ? "new-password" : "current-password"
    );
    setAuthFeedback(page, "");
  }

  function bindAuthGate(page) {
    const form = page.querySelector("#auth-form");
    const submit = page.querySelector("#auth-submit");
    const emailInput = page.querySelector("#auth-email");
    const passwordInput = page.querySelector("#auth-password");

    async function doSubmit() {
      const email = (emailInput.value || "").trim();
      const password = passwordInput.value || "";
      if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
        setAuthFeedback(page, "请输入有效的邮箱地址");
        emailInput.focus();
        return;
      }
      if (password.length < 6) {
        setAuthFeedback(page, "密码至少需要 6 位");
        passwordInput.focus();
        return;
      }
      submit.disabled = true;
      submit.textContent = authGateMode === "signup" ? "创建中…" : "登录中…";
      setAuthFeedback(page, "");
      try {
        if (authGateMode === "signup") {
          const result = await S.auth.signUp(email, password);
          if (result && result.needsConfirm) {
            switchAuthMode(page, "login");
            setAuthFeedback(page, "确认邮件已发送，请查收后再登录", true);
            return;
          }
        } else {
          await S.auth.signIn(email, password);
        }
        page.remove();
        document.body.classList.remove("auth-lock");
        S.auth.emitSignedIn();
      } catch (err) {
        setAuthFeedback(page, err.message || "登录失败，请稍后重试");
      } finally {
        submit.disabled = false;
        submit.textContent = authGateMode === "signup" ? "创建账号" : "登录";
      }
    }

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      doSubmit();
    });
    page.querySelector("#auth-toggle").addEventListener("click", function () {
      switchAuthMode(page, authGateMode === "signup" ? "login" : "signup");
      emailInput.focus();
    });
    page.querySelector("#auth-forgot").addEventListener("click", async function () {
      const email = (emailInput.value || "").trim();
      if (!email) {
        setAuthFeedback(page, "先填写邮箱，再发送重置邮件");
        emailInput.focus();
        return;
      }
      try {
        await S.auth.recover(email);
        setAuthFeedback(page, "如果该邮箱已注册，重置邮件会发送到你的邮箱", true);
      } catch (err) {
        setAuthFeedback(page, err.message || "发送失败，请稍后重试");
      }
    });
  }

  function showAuthGate(message) {
    let page = document.getElementById("auth-page");
    if (!page) {
      document.body.insertAdjacentHTML("beforeend", authPageHTML());
      page = document.getElementById("auth-page");
      bindAuthGate(page);
      document.body.classList.add("auth-lock");
    }
    if (message) setAuthFeedback(page, message);
    const email = page.querySelector("#auth-email");
    if (email) setTimeout(function () { email.focus(); }, 80);
  }

  async function loadBootstrap() {
    const tasks = [
      S.api("/api/config").catch(function () {
        return null;
      }),
      S.api("/api/skills").catch(function () {
        return null;
      }),
      S.api("/api/projects").catch(function () {
        return null;
      }),
      S.api("/api/user/balance").catch(function (err) {
        state.balanceError = err;
        return null;
      }),
    ];
    const results = await Promise.all(tasks);
    state.config = results[0];
    state.skills = (results[1] && results[1].skills) || [];
    state.projects = (results[2] && results[2].projects) || [];
    if (results[3]) {
      state.balance = results[3];
      state.balanceError = null;
    }
    state.configError = !results[0];
    state.skillsError = !results[1];
    state.projectsError = !results[2];
    refreshShell();
  }

  /* ---------------------------------------------------------------------
   * 外壳
   * ------------------------------------------------------------------- */
  function renderShell() {
    const app = document.getElementById("app");
    app.innerHTML =
      sidebarHTML() +
      '<div class="app-main" id="main"></div>' +
      '<div class="mobile-scrim" id="mobile-scrim"></div>';
    mainEl = document.getElementById("main");
  }

  function sidebarHTML() {
    const route = state.route;
    const collapsed = !!state.ui.sidebarCollapsed;
    const projects = state.projects || [];
    const projectRows = projects.length
      ? projects
          .map(function (p) {
            const active = route.projectId === p.id;
            return (
              '<div class="side-item' +
              (active ? " active" : "") +
              '" role="button" tabindex="0" data-act="open-project" data-project="' +
              esc(p.id) +
              '">' +
              icon(projectIconOf(p.id)) +
              '<span class="side-item-text">' +
              esc(S.clean(p.title || "未命名项目")) +
              "</span>" +
              '<span class="side-item-del" role="button" tabindex="0" data-act="delete-project" data-project="' +
              esc(p.id) +
              '" title="删除项目">' +
              icon("trash") +
              "</span></div>"
            );
          })
          .join("")
      : '<div class="side-empty">还没有项目。新建一个，开始准备你的第一份材料。</div>';

    const threadItems = [];
    projects.forEach(function (p) {
      S.threads.list(p.id).slice(0, 4).forEach(function (t) {
        threadItems.push({ project: p, thread: t });
      });
    });
    threadItems.sort(function (a, b) {
      return (b.thread.updatedAt || 0) - (a.thread.updatedAt || 0);
    });
    const threadRows = threadItems
      .slice(0, 8)
      .map(function (item) {
        const active = route.name === "chat" && route.threadId === item.thread.id;
        return (
          '<div class="side-item' +
          (active ? " active" : "") +
          '" role="button" tabindex="0" data-act="open-thread" data-project="' +
          esc(item.project.id) +
          '" data-thread="' +
          esc(item.thread.id) +
          '" title="' +
          esc(S.clean(item.thread.title)) +
          '">' +
          icon("message") +
          '<span class="side-item-text">' +
          esc(S.clean(item.thread.title || "新对话")) +
          '</span><span class="side-item-meta">' +
          esc(shortProjectName(item.project.title)) +
          "</span></div>"
        );
      })
      .join("");

    const balance = state.balance;
    const creditText = balance ? S.fmtCredits(balance.credits) : "—";
    const creditSub = balance ? "积分" : "本地模式";

    return (
      '<aside class="sidebar">' +
      '<div class="sidebar-head">' +
      '<div class="brand"><span class="brand-mark">' +
      icon("star") +
      '</span><span class="brand-name">Stardust</span></div>' +
      '<button class="icon-btn sidebar-toggle" type="button" data-act="toggle-sidebar" aria-label="收起侧边栏" title="收起侧边栏">' +
      icon("panel-left") +
      "</button></div>" +
      '<button class="new-chat-btn" type="button" data-act="new-chat" title="新建会话（⌘K 打开快速跳转）">' +
      icon("plus") +
      '<span class="label">新建会话</span>' +
      '<span class="shortcut"><span class="kbd">⌘</span><span class="kbd">K</span></span></button>' +
      '<div class="sidebar-scroll">' +
      '<div class="side-section"><div class="side-label"><span>项目</span></div>' +
      '<div class="side-item" role="button" tabindex="0" data-act="new-project">' +
      icon("plus") +
      '<span class="side-item-text">新建项目</span></div>' +
      projectRows +
      "</div>" +
      '<div class="side-section"><div class="side-label"><span>对话</span></div>' +
      (threadRows || '<div class="side-empty">还没有对话。</div>') +
      "</div></div>" +
      '<div class="sidebar-foot">' +
      '<button class="credit-card" type="button" data-act="open-purchase">' +
      '<span class="credit-card-top">' +
      icon("zap") +
      "<span>积分余额</span></span>" +
      '<span class="credit-card-value">' +
      esc(creditText) +
      "<span>" +
      esc(creditSub) +
      "</span></span></button>" +
      '<div class="user-row">' +
      '<span class="avatar">' +
      esc(S.initials(state.ui.userName)) +
      "</span>" +
      '<span class="user-meta"><span class="user-name">' +
      esc(state.ui.userName) +
      '</span><span class="user-sub">' +
      (state.config && state.config.cloud_mode ? "云端账号" : "本地账号") +
      "</span></span>" +
      '<button class="icon-btn" type="button" data-act="toggle-theme" title="切换外观" aria-label="切换外观">' +
      icon(S.theme.resolved() === "dark" ? "sun" : "moon") +
      "</button>" +
      '<button class="icon-btn" type="button" data-act="open-settings" title="设置" aria-label="设置">' +
      icon("settings") +
      "</button></div></div></aside>"
    );
  }

  function projectIconOf(projectId) {
    return (state.ui.projectIcons && state.ui.projectIcons[projectId]) || "folder";
  }

  function shortProjectName(title) {
    const name = S.clean(title || "");
    return name.length > 6 ? name.slice(0, 6) : name;
  }

  function refreshShell() {
    const sb = document.querySelector(".sidebar");
    if (!sb) return;
    sb.outerHTML = sidebarHTML();
    applySidebarCollapse();
    refreshScrim();
  }

  function applySidebarCollapse() {
    const root = document.getElementById("app");
    if (!root) return;
    root.classList.toggle("sidebar-collapsed", !!state.ui.sidebarCollapsed);
  }

  function toggleSidebar(open) {
    const app = document.getElementById("app");
    const sidebar = document.querySelector(".sidebar");
    if (!app || !sidebar) return;
    if (window.innerWidth <= 860) {
      app.classList.toggle("sidebar-open", open === undefined ? !app.classList.contains("sidebar-open") : !!open);
      refreshScrim();
      return;
    }
    state.ui = S.setUI({ sidebarCollapsed: open === undefined ? !state.ui.sidebarCollapsed : !open });
    applySidebarCollapse();
  }

  function refreshScrim() {
    const scrim = document.getElementById("mobile-scrim");
    const app = document.getElementById("app");
    if (!scrim || !app) return;
    scrim.classList.toggle("is-in", app.classList.contains("sidebar-open"));
  }

  function syncBalance() {
    if (S.settings && state.balance) {
      /* 设置面板已刷新余额，这里只更新侧边栏 */
    }
    refreshShell();
  }

  async function refreshProjects() {
    try {
      const result = await S.api("/api/projects");
      state.projects = (result && result.projects) || [];
    } catch (e) {
      state.projects = state.projects || [];
    }
    refreshShell();
  }

  function openSettings(tab) {
    S.settings.open(tab || "account");
  }

  /* ---------------------------------------------------------------------
   * 全局事件
   * ------------------------------------------------------------------- */
  function bindGlobalEvents() {
    window.addEventListener("hashchange", function () {
      renderRoute();
    });
    window.addEventListener("resize", function () {
      refreshScrim();
    });

    const app = document.getElementById("app");

    window.addEventListener("stardust:theme", function () {
      refreshShell();
    });

    app.addEventListener("keydown", function (event) {
      const target = event.target.closest('[role="button"][data-act]');
      // 只处理侧边栏；项目/对话内容区有各自的键盘委托，避免一次 Enter 触发两次 click。
      if (!target || !target.closest(".sidebar")) return;
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        target.click();
      }
    });

    app.addEventListener("click", function (event) {
      const target = event.target.closest("[data-act]");
      if (!target) return;
      const act = target.getAttribute("data-act");
      const inSidebar = !!target.closest(".sidebar");
      if (act === "toggle-sidebar") {
        toggleSidebar();
        return;
      }
      if (act === "open-sidebar") {
        toggleSidebar(true);
        return;
      }
      if (act === "toggle-theme") {
        S.theme.toggle();
        S.toast(S.theme.resolved() === "dark" ? "已切换到深色外观" : "已切换到浅色外观");
        return;
      }
      if (act === "open-settings" && inSidebar) {
        openSettings("account");
        return;
      }
      if (act === "open-project" && inSidebar) {
        navigate("#/p/" + target.getAttribute("data-project") + "/conversations");
        return;
      }
      if (act === "delete-project" && inSidebar) {
        event.stopPropagation();
        deleteProject(target.getAttribute("data-project"));
        return;
      }
      if (act === "open-thread" && inSidebar) {
        navigate(
          "#/p/" + target.getAttribute("data-project") + "/c/" + target.getAttribute("data-thread")
        );
        return;
      }
      if (act === "new-project" && inSidebar) {
        state.create = newCreateState();
        navigate("#/new");
        return;
      }
      if (act === "new-chat" && inSidebar) {
        startNewChat();
        return;
      }
      if (act === "open-purchase" && inSidebar) {
        openSettings("purchase");
        return;
      }
    });

    const scrim = document.getElementById("mobile-scrim");
    if (scrim) {
      scrim.addEventListener("click", function () {
        toggleSidebar(false);
      });
    }

    document.addEventListener("keydown", function (event) {
      const meta = event.metaKey || event.ctrlKey;
      if (meta && !event.shiftKey && (event.key === "k" || event.key === "K")) {
        event.preventDefault();
        openPalette();
        return;
      }
      if (event.key === "Escape") {
        if (document.querySelector(".modal-backdrop")) return;
        if (window.innerWidth <= 1024) {
          const docPanel = document.querySelector(".doc-panel");
          if (docPanel) {
            docPanel.remove();
            return;
          }
        }
        const app2 = document.getElementById("app");
        if (app2 && app2.classList.contains("sidebar-open")) toggleSidebar(false);
      }
    });
  }

  async function deleteProject(projectId) {
    const project = state.projects.find(function (p) {
      return p.id === projectId;
    });
    const ok = await S.confirm({
      title: "删除项目？",
      message:
        "「" +
        S.clean((project && project.title) || "这个项目") +
        "」的会话、文件与共同记忆都会被删除，且无法恢复。",
      confirmText: "删除",
      danger: true,
    });
    if (!ok) return;
    try {
      await S.api("/api/projects/" + projectId, { method: "DELETE" });
      state.projects = state.projects.filter(function (p) {
        return p.id !== projectId;
      });
      S.toast("项目已删除", "success");
      const route = parseRoute();
      if (route.projectId === projectId) navigate("#/");
      else refreshShell();
    } catch (err) {
      S.toast(err.message || "删除失败", "error");
    }
  }

  /* ---------------------------------------------------------------------
   * 命令面板（⌘K）
   * ------------------------------------------------------------------- */
  let paletteOpen = false;

  function openPalette() {
    if (paletteOpen || document.querySelector(".welcome")) return;
    paletteOpen = true;
    const projects = state.projects || [];
    const threads = [];
    projects.forEach(function (p) {
      S.threads.list(p.id).forEach(function (t) {
        threads.push({ project: p, thread: t });
      });
    });
    threads.sort(function (a, b) {
      return (b.thread.updatedAt || 0) - (a.thread.updatedAt || 0);
    });

    const actions = [
      { kind: "action", icon: "plus", label: "新建会话", sub: "在当前项目里开一条新对话", run: function () { S.closeModal(); startNewChat(); } },
      { kind: "action", icon: "folder-plus", label: "新建项目", sub: "选择赛道并准备材料", run: function () { S.closeModal(); state.create = newCreateState(); navigate("#/new"); } },
      { kind: "action", icon: "home", label: "返回首页", sub: "回到工作台入口", run: function () { S.closeModal(); navigate("#/"); } },
      { kind: "action", icon: "settings", label: "打开设置", sub: "账户、购买、模型与用量", run: function () { S.closeModal(); openSettings("account"); } },
      { kind: "action", icon: "sun", label: "切换浅色 / 深色外观", sub: "立即生效", run: function () { S.closeModal(); S.theme.toggle(); refreshShell(); } },
    ];

    const items = function () {
      const out = actions.map(function (a) {
        return { kind: a.kind, icon: a.icon, label: a.label, sub: a.sub, run: a.run };
      });
      projects.forEach(function (p) {
        out.push({
          kind: "project",
          icon: projectIconOf(p.id),
          label: S.clean(p.title || "未命名项目"),
          sub: "项目 · " + skillNameOf(p),
          run: function () {
            S.closeModal();
            navigate("#/p/" + p.id + "/conversations");
          },
        });
      });
      threads.slice(0, 12).forEach(function (item) {
        out.push({
          kind: "thread",
          icon: "message",
          label: S.clean(item.thread.title || "未命名会话"),
          sub: "会话 · " + S.clean(item.project.title || "未命名项目"),
          run: function () {
            S.closeModal();
            navigate("#/p/" + item.project.id + "/c/" + item.thread.id);
          },
        });
      });
      return out;
    };

    const ctx = S.openModal({
      title: "快速跳转",
      subtitle: "搜索项目或会话，也可以直接执行一个动作",
      size: "md",
      className: "palette-modal",
      body:
        '<div class="palette-search">' +
        icon("search") +
        '<input class="palette-input" id="palette-input" data-autofocus placeholder="搜索项目、会话，或输入动作…" autocomplete="off">' +
        "</div>" +
        '<div class="palette-list" id="palette-list"></div>',
      onClose: function () {
        paletteOpen = false;
      },
      onMount: function (modalCtx) {
        const input = modalCtx.el.querySelector("#palette-input");
        const listEl = modalCtx.el.querySelector("#palette-list");
        const all = items();
        let visible = all;
        let active = 0;

        function run(item) {
          if (!item) return;
          item.run();
        }

        function render() {
          listEl.innerHTML = visible.length
            ? visible
                .map(function (item, index) {
                  return (
                    '<button type="button" class="palette-item' +
                    (index === active ? " active" : "") +
                    '" data-index="' +
                    index +
                    '">' +
                    '<span class="palette-ic">' +
                    icon(item.icon) +
                    "</span>" +
                    '<span class="palette-meta"><span class="palette-label">' +
                    esc(item.label) +
                    '</span><span class="palette-sub">' +
                    esc(item.sub || "") +
                    "</span></span>" +
                    '<span class="palette-kind">' +
                    (item.kind === "action" ? "动作" : item.kind === "project" ? "项目" : "会话") +
                    "</span></button>"
                  );
                })
                .join("")
            : '<div class="palette-empty">没有匹配结果</div>';
          const activeEl = listEl.querySelector(".palette-item.active");
          if (activeEl) activeEl.scrollIntoView({ block: "nearest" });
        }

        input.addEventListener("input", function () {
          const query = input.value.trim().toLowerCase();
          visible = query
            ? all.filter(function (item) {
                return (
                  item.label.toLowerCase().indexOf(query) >= 0 ||
                  (item.sub || "").toLowerCase().indexOf(query) >= 0
                );
              })
            : all;
          active = 0;
          render();
        });

        input.addEventListener("keydown", function (e) {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            active = Math.min(active + 1, visible.length - 1);
            render();
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            active = Math.max(active - 1, 0);
            render();
          } else if (e.key === "Enter") {
            e.preventDefault();
            run(visible[active]);
          }
        });

        listEl.addEventListener("click", function (e) {
          const btn = e.target.closest("[data-index]");
          if (btn) run(visible[Number(btn.getAttribute("data-index"))]);
        });

        render();
      },
    });
  }

  function startNewChat() {
    const route = parseRoute();
    if (route.projectId) {
      const thread = S.threads.create(route.projectId);
      navigate("#/p/" + route.projectId + "/c/" + thread.id);
      return;
    }
    if (mainEl) {
      const homeRoot = mainEl.firstElementChild;
    const input = mainEl.querySelector("#home-input");
      if (input) {
        input.focus();
        return;
      }
    }
    navigate("#/");
  }

  /* ---------------------------------------------------------------------
   * 路由渲染
   * ------------------------------------------------------------------- */
  async function renderRoute() {
    if (!mainEl) return;
    const route = parseRoute();
    state.route = route;
    refreshShell();

    S.viewTransition(function () {
      if (route.name === "create") {
        renderCreate();
        return;
      }
      if (route.name === "project" && route.projectId) {
        document.title = "项目 · Stardust";
        S.views.project(mainEl, route.projectId, route.tab);
        return;
      }
      if (route.name === "chat" && route.projectId && route.threadId) {
        document.title = "对话 · Stardust";
        S.views.chat(mainEl, route.projectId, route.threadId);
        return;
      }
      renderHome();
    });
  }

  /* ---------------------------------------------------------------------
   * 欢迎页
   * ------------------------------------------------------------------- */
  function showWelcome() {
    if (document.querySelector(".welcome")) return;
    const el = document.createElement("div");
    el.className = "welcome";
    el.innerHTML =
      '<div class="welcome-inner">' +
      '<nav class="welcome-nav">' +
      '<div class="welcome-brand"><span class="brand-mark">' +
      icon("star") +
      "</span><span>Stardust Agent</span></div>" +
      '<div class="welcome-nav-actions">' +
      '<button class="btn btn-sm btn-ghost" type="button" data-welcome-skip>跳过介绍</button>' +
      "</div></nav>" +
      '<section class="welcome-hero">' +
      '<span class="welcome-eyebrow">' +
      icon("sparkles") +
      " 大学生申报材料 Agent</span>" +
      '<h1 class="welcome-title">把申报材料交给 Agent，<br><em>把时间留给创造。</em></h1>' +
      '<p class="welcome-sub">从大创、挑战杯到国家奖学金，35 个申报赛道。<br>先确认事实与材料，再逐章协作撰写，最后导出排好版的 Word 草稿。</p>' +
      '<div class="welcome-actions">' +
      '<button class="btn btn-primary" type="button" data-welcome-start>' +
      icon("arrow-right") +
      " 开始使用</button>" +
      '<button class="btn btn-ghost" type="button" data-welcome-browse>先看看工作台</button>' +
      "</div>" +
      '<div class="welcome-note">材料默认只保存在这台电脑上；未确认的内容不会进入检索。</div>' +
      "</section>" +
      '<section class="welcome-features">' +
      '<div class="welcome-feature"><h3>' +
      icon("grid") +
      "每个赛道，都有自己的写法</h3><p>35 个申报赛道对应真实的评审标准与材料要求，不会把大创写成奖学金，也不会把社会实践写成竞赛总结。</p></div>" +
      '<div class="welcome-feature"><h3>' +
      icon("chat") +
      "每个数字，都有出处</h3><p>事实先确认再落笔，缺少依据的地方会标注待补充；同一项目的文件与已确认事实贯穿所有对话。</p></div>" +
      '<div class="welcome-feature"><h3>' +
      icon("shield") +
      "写完之后，直接导出</h3><p>导出前自动检查事实缺口、来源标记、占位与数字一致性，确认后生成排好版的 Word 草稿。</p></div>" +
      "</section>" +
      '<footer class="welcome-foot"><span>Stardust Agent · 本地优先版</span><span>内容为 AI 生成草稿，提交前请人工核对</span></footer>' +
      "</div>";

    document.body.appendChild(el);
    document.body.classList.add("modal-open");
    const dismiss = function (goCreate) {
      S.setUI({ welcomeSeen: true });
      state.ui = S.getUI();
      el.remove();
      document.body.classList.remove("modal-open");
      if (goCreate === "create" || (!state.projects.length && goCreate !== "browse")) {
        state.create = newCreateState();
        navigate("#/new");
      } else if (goCreate === "browse") {
        if (!state.projects.length) {
          state.create = newCreateState();
          navigate("#/new");
        } else {
          navigate("#/");
        }
      }
    };
    el.querySelector("[data-welcome-start]").addEventListener("click", function () {
      dismiss("create");
    });
    el.querySelector("[data-welcome-skip]").addEventListener("click", function () {
      dismiss(state.projects.length ? "browse" : "create");
    });
    el.querySelector("[data-welcome-browse]").addEventListener("click", function () {
      dismiss("browse");
    });
  }

  /* ---------------------------------------------------------------------
   * 首页
   * ------------------------------------------------------------------- */
  function renderHome() {
    document.title = "Stardust · 大学生申报材料 Agent";
    const quick = quickActions();
    const projects = state.projects || [];
    const recent = projects.length
      ? '<div class="home-recent"><div class="home-recent-title">最近项目</div><div class="recent-grid">' +
        projects
          .slice(0, 4)
          .map(function (p) {
            return (
              '<button class="recent-card" type="button" data-act="open-recent" data-project="' +
              esc(p.id) +
              '">' +
              '<span class="recent-icon">' +
              icon(projectIconOf(p.id)) +
              "</span>" +
              '<span class="recent-meta"><span class="recent-name">' +
              esc(S.clean(p.title || "未命名项目")) +
              '</span><span class="recent-sub">' +
              esc(skillNameOf(p)) +
              " · " +
              esc(S.fmtTime(p.updated_at)) +
              "</span></span></button>"
            );
          })
          .join("") +
        "</div></div>"
      : "";

    mainEl.innerHTML =
      '<div class="view">' +
      '<button class="icon-btn mobile-only mobile-sidebar-btn" type="button" data-act="open-sidebar" aria-label="打开侧边栏">' +
      icon("menu") +
      "</button>" +
      '<div class="scroll-area"><div class="home-inner">' +
      '<div class="home-hero">' +
      '<h1 class="home-wordmark">STARDUST</h1>' +
      '<p class="home-sub">从赛道判断到逐章成稿，把一个想法写成可提交的材料</p>' +
      "</div>" +
      ((state.projectsError || state.skillsError)
        ? '<div class="home-alert">' +
          icon("alert") +
          "<span>项目或赛道列表没能加载，可能是本地服务暂时不可用。</span>" +
          '<button class="btn btn-sm btn-ghost" type="button" data-act="retry-bootstrap">重试</button></div>'
        : "") +
      '<div class="composer">' +
      '<div class="composer-box">' +
      '<textarea class="composer-input" id="home-input" rows="1" placeholder="描述你要准备的材料，例如：我要申报国家级大创项目"></textarea>' +
      '<div class="composer-bar">' +
      '<button class="composer-tool" type="button" data-act="home-upload">' +
      icon("paperclip") +
      "<span>添加材料</span></button>" +
      '<button class="composer-tool" type="button" data-act="open-settings">' +
      icon("cpu") +
      "<span>" +
      esc(modelLabel()) +
      "</span></button>" +
      '<span class="spacer"></span>' +
      '<button class="send-btn" type="button" data-act="home-send" disabled aria-label="发送">' +
      icon("arrow-up") +
      "</button></div></div></div>" +
      '<div class="home-quick">' +
      quick
        .map(function (q) {
          return (
            '<button class="chip" type="button" data-act="quick" data-prompt="' +
            esc(q.prompt) +
            '" data-skill="' +
            esc(q.skillId || "") +
            '">' +
            icon(q.icon) +
            esc(q.label) +
            "</button>"
          );
        })
        .join("") +
      "</div>" +
      recent +
      "</div></div></div>";

    const input = mainEl.querySelector("#home-input");
    const sendBtn = mainEl.querySelector('[data-act="home-send"]');
    const syncSend = function () {
      if (sendBtn) sendBtn.disabled = !(input && input.value.trim());
    };
    if (input) {
      input.addEventListener("input", function () {
        syncSend();
        input.style.height = "auto";
        input.style.height = Math.min(220, input.scrollHeight) + "px";
      });
      input.addEventListener("keydown", function (e) {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          submitHome();
        }
      });
    }

    function submitHome() {
      const text = (input ? input.value : "").trim();
      if (!text) return;
      goCreateFromText(text);
    }

    S.on(homeRoot, "click", "[data-act]", function (event, target) {
      const act = target.getAttribute("data-act");
      if (act === "home-send") {
        submitHome();
        return;
      }
      if (act === "quick") {
        const prompt = target.getAttribute("data-prompt") || "";
        const skillId = target.getAttribute("data-skill") || "";
        state.create = newCreateState({ request: prompt, skillId: skillId });
        navigate("#/new");
        return;
      }
      if (act === "open-recent") {
        navigate("#/p/" + target.getAttribute("data-project") + "/conversations");
        return;
      }
      if (act === "home-upload") {
        state.create = newCreateState();
        navigate("#/new");
        S.toast("先创建项目，再把材料放进来", "info");
        return;
      }
      if (act === "retry-bootstrap") {
        loadBootstrap().then(function () {
          renderRoute();
          S.toast("已重新加载", "success");
        });
        return;
      }
      if (act === "open-settings") {
        openSettings("model");
        return;
      }
    });
  }

  function quickActions() {
    const skills = state.skills || [];
    function findByName(name) {
      return skills.find(function (s) {
        return (s.name || "").indexOf(name) >= 0;
      });
    }
    const defs = [
      { label: "国家励志奖学金", icon: "award", prompt: "我要申请国家励志奖学金，请帮我准备申报材料", match: "励志奖学金" },
      { label: "大创项目申报", icon: "flask", prompt: "我要申报大学生创新创业训练计划项目", match: "大创" },
      { label: "科研立项", icon: "target", prompt: "我需要准备科研立项申报书", match: "科研" },
      { label: "学科竞赛", icon: "trophy", prompt: "帮我整理学科竞赛申报材料", match: "竞赛" },
    ];
    return defs.map(function (d) {
      const skill = findByName(d.match);
      return { label: d.label, icon: d.icon, prompt: d.prompt, skillId: skill ? skill.id : "" };
    });
  }

  function skillNameOf(project) {
    const st = project.state || {};
    return S.clean(st.skill_name || st.skill_id || "申报项目");
  }

  function modelLabel() {
    const m = S.getModel();
    if (m.provider === "ollama") return "Ollama";
    if (m.provider === "openai_compatible") return "自备 API";
    return "平台预设";
  }

  async function goCreateFromText(text) {
    state.create = newCreateState({ request: text });
    const sendBtn = mainEl.querySelector('[data-act="home-send"]');
    if (sendBtn) sendBtn.disabled = true;
    try {
      const result = await S.api("/api/route", { method: "POST", body: { query: text } });
      if (result && result.selected) {
        state.create.skillId = result.selected.id;
        navigate("#/new");
        return;
      }
      const candidates = (result && result.candidates) || [];
      if (candidates.length) {
        showCandidateModal(candidates, (result && result.message) || "请选择最符合的赛道");
      } else {
        S.toast((result && result.message) || "没能匹配赛道，请手动选择", "info");
        navigate("#/new");
      }
    } catch (err) {
      S.toast("赛道匹配失败，请在下一步手动选择", "error");
      navigate("#/new");
    } finally {
      if (sendBtn) sendBtn.disabled = false;
    }
  }

  function showCandidateModal(candidates, message) {
    const ctx = S.openModal({
      title: "确认申报赛道",
      subtitle: message || "找到几个可能的赛道，请选择最符合的一项",
      size: "md",
      body:
        '<div class="model-options">' +
        candidates
          .map(function (c, i) {
            return (
              '<button type="button" class="model-option" data-candidate="' +
              i +
              '"><span class="model-radio"></span><span class="model-option-meta">' +
              '<span class="model-option-name">' +
              esc(S.clean(c.name)) +
              "</span>" +
              '<span class="model-option-desc">' +
              esc(S.clean(c.description || "").slice(0, 90)) +
              "</span></span></button>"
            );
          })
          .join("") +
        "</div>",
      footer: '<button class="btn btn-ghost" data-modal-close>手动选择</button>',
      onClose: function () {
        navigate("#/new");
      },
    });
    ctx.el.querySelectorAll("[data-candidate]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        const item = candidates[Number(btn.getAttribute("data-candidate"))];
        if (item && state.create) state.create.skillId = item.id;
        S.closeModal();
        navigate("#/new");
      });
    });
  }

  /* ---------------------------------------------------------------------
   * 新建项目
   * ------------------------------------------------------------------- */
  function newCreateState(init) {
    return Object.assign(
      {
        step: 1,
        name: "",
        icon: "star",
        popup: false,
        skillId: "",
        level: "",
        discipline: "",
        school: "",
        template: "",
        request: "",
        category: "all",
        search: "",
        submitting: false,
      },
      init || {}
    );
  }

  function renderCreate() {
    if (!state.create) state.create = newCreateState();
    document.title = "新建项目 · Stardust";
    const c = state.create;
    const steps =
      '<div class="create-steps">' +
      '<span class="step-dot' +
      (c.step === 1 ? " active" : " done") +
      '"><span class="num">1</span>图标与名称</span>' +
      '<span class="step-sep"></span>' +
      '<span class="step-dot' +
      (c.step === 2 ? " active" : "") +
      '"><span class="num">2</span>准备申报材料</span></div>';

    const body = c.step === 1 ? createStepOne(c) : createStepTwo(c);
    mainEl.innerHTML =
      '<div class="view">' +
      '<button class="icon-btn mobile-only mobile-sidebar-btn" type="button" data-act="open-sidebar" aria-label="打开侧边栏">' +
      icon("menu") +
      "</button>" +
      '<div class="scroll-area create-scroll"><div class="create-inner">' +
      '<div class="create-head"><h1 class="create-title">新建项目</h1><p class="create-sub">先选赛道，再准备材料</p></div>' +
      steps +
      body +
      "</div></div></div>";

    bindCreateEvents();
    if (state.create && state.create.step === 2) {
      requestAnimationFrame(function () {
        const picked = mainEl.querySelector(".skill-option.active");
        if (picked) picked.scrollIntoView({ block: "center" });
      });
    }
  }

  function createStepOne(c) {
    const presets = ["star", "flask", "trophy", "graduation-cap", "book-open", "target"];
    const strip = presets
      .map(function (name) {
        return (
          '<button type="button" class="icon-tile' +
          (c.icon === name ? " active" : "") +
          '" data-act="pick-icon" data-icon="' +
          name +
          '" aria-label="选择图标">' +
          icon(name) +
          "</button>"
        );
      })
      .join("");
    const pop = c.popup
      ? '<div class="icon-pop">' +
        S.iconChoices
          .map(function (name) {
            return (
              '<button type="button" class="icon-pop-item' +
              (c.icon === name ? " active" : "") +
              '" data-act="pick-icon" data-icon="' +
              name +
              '">' +
              icon(name) +
              "</button>"
            );
          })
          .join("") +
        "</div>"
      : "";
    return (
      '<div class="icon-strip">' +
      strip +
      '<button type="button" class="icon-tile icon-tile-add' +
      (c.popup ? " active" : "") +
      '" data-act="toggle-icon-pop" aria-label="更多图标">' +
      icon("plus") +
      "</button></div>" +
      pop +
      '<div class="create-name-wrap">' +
      '<input class="create-name" id="create-name" maxlength="60" placeholder="取个名字" value="' +
      esc(c.name) +
      '"></div>' +
      '<div class="create-name-hint">名字可以随时修改，例如「大创·智能校园助手」</div>' +
      '<div class="create-actions">' +
      '<button class="btn btn-ghost" type="button" data-act="cancel-create">取消</button>' +
      '<button class="btn btn-primary" type="button" data-act="next-step">下一步' +
      icon("arrow-right") +
      "</button></div>"
    );
  }

  function createStepTwo(c) {
    const categories = [
      { id: "all", label: "全部" },
      { id: "research", label: "科研立项" },
      { id: "scholarship", label: "奖学金" },
      { id: "competition", label: "竞赛" },
      { id: "practice", label: "社会实践" },
      { id: "honor", label: "荣誉" },
      { id: "political", label: "党团" },
    ];
    const query = (c.search || "").trim().toLowerCase();
    const skills = (state.skills || []).filter(function (s) {
      if (c.category !== "all" && s.category !== c.category) return false;
      if (!query) return true;
      return (
        String(s.name || "").toLowerCase().indexOf(query) >= 0 ||
        String(s.description || "").toLowerCase().indexOf(query) >= 0
      );
    });

    const skillOptions = skills.length
      ? skills
          .map(function (s) {
            return (
              '<button type="button" class="skill-option' +
              (c.skillId === s.id ? " active" : "") +
              '" data-act="pick-skill" data-skill="' +
              esc(s.id) +
              '">' +
              icon(categoryIcon(s.category)) +
              '<span class="skill-option-meta"><span class="skill-option-name">' +
              esc(S.clean(s.name)) +
              '</span><span class="skill-option-desc">' +
              esc(S.clean(s.description || "").slice(0, 60)) +
              "</span></span></button>"
            );
          })
          .join("")
      : '<div class="empty" style="padding:24px 0;grid-column:1/-1"><div class="empty-desc">没有匹配的赛道，换个关键词试试。</div></div>';

    return (
      '<div class="form-card">' +
      '<div class="form-section"><div class="form-section-head"><div class="form-section-title">申报赛道</div><div class="form-section-desc">决定写作规范与评审要点</div></div>' +
      (function () {
        const picked = (state.skills || []).find(function (s) {
          return s.id === c.skillId;
        });
        return (
          '<div class="selected-skill' +
          (picked ? "" : " is-empty") +
          '">' +
          (picked
            ? icon(categoryIcon(picked.category)) +
              '<span class="selected-skill-name">' +
              esc(S.clean(picked.name)) +
              '</span><span class="badge badge-accent">已选</span>'
            : icon("info") +
              "<span>还没选赛道。不选的话默认按「大创·创新训练」准备，创建后也可以再调整。</span>") +
          "</div>"
        );
      })() +
      '<div class="field" style="margin-bottom:10px">' +
      '<input class="input" id="skill-search" placeholder="搜索赛道，例如：大创、奖学金、竞赛" value="' +
      esc(c.search) +
      '"></div>' +
      '<div class="segmented" style="margin-bottom:12px">' +
      categories
        .map(function (cat) {
          return (
            '<button type="button" data-act="pick-category" data-category="' +
            cat.id +
            '" class="' +
            (c.category === cat.id ? "active" : "") +
            '">' +
            cat.label +
            "</button>"
          );
        })
        .join("") +
      "</div>" +
      '<div class="skill-select">' +
      skillOptions +
      "</div></div>" +
      '<div class="form-section"><div class="form-section-head"><div class="form-section-title">基本信息</div><div class="form-section-desc">可以之后再补充</div></div>' +
      '<div class="form-grid">' +
      '<div class="field form-grid-full"><label class="field-label">项目名称</label><input class="input" id="create-title" maxlength="60" value="' +
      esc(c.name) +
      '" placeholder="例如：智能校园助手"></div>' +
      '<div class="field"><label class="field-label">申报级别</label><select class="select" id="create-level">' +
      ["", "国家级", "省级", "校级"]
        .map(function (l) {
          return '<option value="' + l + '"' + (c.level === l ? " selected" : "") + ">" + (l || "暂不确定") + "</option>";
        })
        .join("") +
      "</select></div>" +
      '<div class="field"><label class="field-label">学科 / 专业</label><input class="input" id="create-discipline" maxlength="40" value="' +
      esc(c.discipline) +
      '" placeholder="例如：计算机科学与技术"></div>' +
      '<div class="field form-grid-full"><label class="field-label">学校</label><input class="input" id="create-school" maxlength="60" value="' +
      esc(c.school) +
      '" placeholder="例如：XX大学"></div>' +
      "</div></div>" +
      '<div class="form-section"><div class="form-section-head"><div class="form-section-title">准备申报材料</div><div class="form-section-desc">先告诉我们你手头的情况</div></div>' +
      '<div class="field"><label class="field-label">有学校下发的申报模板吗</label><div class="segmented">' +
      [
        { id: "has", label: "有模板" },
        { id: "none", label: "没有，用通用结构" },
        { id: "", label: "稍后再说" },
      ]
        .map(function (t) {
          return (
            '<button type="button" data-act="pick-template" data-template="' +
            t.id +
            '" class="' +
            (c.template === t.id ? "active" : "") +
            '">' +
            t.label +
            "</button>"
          );
        })
        .join("") +
      "</div></div>" +
      '<div class="field"><label class="field-label">你的需求或已有材料</label>' +
      '<textarea class="textarea" id="create-request" placeholder="例如：我要申报国家级大创，方向是校园智能问答；已有导师和 3 人团队，需要一份申报书。" maxlength="2000">' +
      esc(c.request) +
      "</textarea>" +
      '<div class="field-hint">创建后会自动生成一条开场消息；项目里的文件和共同记忆会持续供 Agent 使用。</div></div>' +
      "</div></div>" +
      '<div class="create-actions">' +
      '<button class="btn btn-ghost" type="button" data-act="prev-step">' +
      icon("arrow-left") +
      " 上一步</button>" +
      '<button class="btn btn-primary" type="button" data-act="create-project"' +
      (c.submitting ? " disabled" : "") +
      ">" +
      (c.submitting ? '<span class="spinner"></span>' : icon("plus")) +
      " 创建项目</button></div>"
    );
  }

  function categoryIcon(category) {
    const map = {
      research: "flask",
      scholarship: "award",
      competition: "trophy",
      practice: "users",
      honor: "star",
      political: "flag",
      military: "shield",
      study_abroad: "globe",
      other: "folder",
    };
    return map[category] || "folder";
  }

  function bindCreateEvents() {
    const c = state.create;
    const nameInput = mainEl.querySelector("#create-name");
    if (nameInput) {
      nameInput.addEventListener("input", function () {
        c.name = nameInput.value;
      });
      nameInput.addEventListener("keydown", function (e) {
        if (e.key === "Enter") {
          e.preventDefault();
          goStepTwo();
        }
      });
      setTimeout(function () {
        nameInput.focus();
      }, 80);
    }
    const searchInput = mainEl.querySelector("#skill-search");
    if (searchInput) {
      searchInput.addEventListener("input", S.debounce(function () {
        syncCreateForm();
        c.search = searchInput.value;
        renderCreate();
        const again = mainEl.querySelector("#skill-search");
        if (again) {
          again.focus();
          again.setSelectionRange(again.value.length, again.value.length);
        }
      }, 220));
    }

    const createRoot = mainEl.firstElementChild;
    S.on(createRoot, "click", "[data-act]", function (event, target) {
      const act = target.getAttribute("data-act");
      if (act === "pick-icon") {
        c.icon = target.getAttribute("data-icon");
        c.popup = false;
        renderCreate();
        return;
      }
      if (act === "toggle-icon-pop") {
        c.popup = !c.popup;
        renderCreate();
        return;
      }
      if (act === "cancel-create") {
        state.create = null;
        navigate("#/");
        return;
      }
      if (act === "next-step") {
        goStepTwo();
        return;
      }
      if (act === "prev-step") {
        syncCreateForm();
        c.step = 1;
        renderCreate();
        return;
      }
      if (act === "pick-skill") {
        syncCreateForm();
        c.skillId = target.getAttribute("data-skill");
        renderCreate();
        return;
      }
      if (act === "pick-category") {
        syncCreateForm();
        c.category = target.getAttribute("data-category");
        renderCreate();
        return;
      }
      if (act === "pick-template") {
        syncCreateForm();
        c.template = target.getAttribute("data-template");
        renderCreate();
        return;
      }
      if (act === "create-project") {
        createProject();
        return;
      }
    });
  }

  function syncCreateForm() {
    const c = state.create;
    if (!c) return;
    const title = mainEl.querySelector("#create-title");
    const name = mainEl.querySelector("#create-name");
    const level = mainEl.querySelector("#create-level");
    const discipline = mainEl.querySelector("#create-discipline");
    const school = mainEl.querySelector("#create-school");
    const request = mainEl.querySelector("#create-request");
    const search = mainEl.querySelector("#skill-search");
    if (name) c.name = name.value;
    if (title) c.name = title.value;
    if (level) c.level = level.value;
    if (discipline) c.discipline = discipline.value;
    if (school) c.school = school.value;
    if (request) c.request = request.value;
    if (search) c.search = search.value;
  }

  function goStepTwo() {
    const c = state.create;
    syncCreateForm();
    c.step = 2;
    renderCreate();
  }

  async function createProject() {
    const c = state.create;
    if (!c || c.submitting) return;
    syncCreateForm();
    c.submitting = true;
    renderCreate();
    try {
      const payload = {
        title: (c.name || "").trim(),
        level: c.level || "",
        discipline: (c.discipline || "").trim(),
        school: (c.school || "").trim(),
        skill_id: c.skillId || "",
        initial_request: (c.request || "").trim(),
        has_template: c.template === "has" ? true : c.template === "none" ? false : null,
      };
      const project = await S.api("/api/projects", { method: "POST", body: payload });
      const icons = Object.assign({}, state.ui.projectIcons || {});
      icons[project.id] = c.icon || "star";
      S.setUI({ projectIcons: icons });
      state.ui = S.getUI();
      state.projects.unshift(project);
      state.create = null;
      S.toast("项目已创建", "success");
      navigate("#/p/" + project.id + "/conversations");
    } catch (err) {
      c.submitting = false;
      renderCreate();
      S.toast(err.message || "创建失败", "error");
    }
  }

  /* ---------------------------------------------------------------------
   * 启动
   * ------------------------------------------------------------------- */
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();

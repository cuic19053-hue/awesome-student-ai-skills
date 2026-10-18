/* =========================================================================
 * Stardust Agent · 项目空间与对话
 * 会话 / 文件 / 共同记忆 / 申报书 / 对话 + 文档预览面板
 * ========================================================================= */
(function () {
  "use strict";
  const S = window.S;
  const icon = S.icon;
  const esc = S.esc;

  const FACT_LABELS = {
    project_name: "项目名称",
    level: "申报级别",
    discipline: "学科 / 专业",
    school: "学校",
    budget: "预算",
    problem: "要解决的问题",
    target_user: "服务对象 / 应用场景",
    method: "拟采用的方法",
    foundation: "现有基础 / 可用资源",
    team: "团队构成",
    advisor: "指导老师",
    duration: "项目周期",
    outcome: "预期成果",
    innovation: "创新点",
    background: "项目背景",
  };

  const TOOL_LABELS = {
    get_project_state: "读取项目信息",
    get_writing_guidance: "查询写作规范",
    search_project_materials: "检索项目材料",
    save_section: "写入章节",
    save_project_fact: "保存事实",
    validate_project: "校验材料",
    export_docx: "导出 Word",
    simulate_review: "模拟评审",
    search_papers: "检索文献",
    search_official_notices: "检索官方通知",
    propose_diagram: "生成图示建议",
    generate_image: "生成配图",
    read_skill: "读取赛道指南",
    list_projects: "查看项目列表",
    add_text_material: "登记文字材料",
    confirm_project_material: "确认材料",
  };

  let projectHost = null;
  let viewSeq = 0;

  function appState() {
    return (window.App && window.App.state) || { projects: [], project: null };
  }

  /* =====================================================================
   * 会话线程（本地持久化，每个项目独立，可多线程）
   * =================================================================== */
  const threads = {
    _map: null,
    map() {
      if (!this._map) {
        const raw = S.loadThreads();
        this._map = raw && typeof raw === "object" && !Array.isArray(raw) ? raw : {};
        Object.keys(this._map).forEach(function (projectId) {
          const box = this._map[projectId];
          if (!box || typeof box !== "object") {
            this._map[projectId] = { threads: [], active: "" };
            return;
          }
          if (!Array.isArray(box.threads)) box.threads = [];
          if (typeof box.active !== "string") box.active = "";
          box.threads = box.threads.filter(function (t) {
            return t && typeof t === "object" && typeof t.id === "string";
          });
          box.threads.forEach(function (t) {
            if (!Array.isArray(t.messages)) t.messages = [];
          });
        }, this);
      }
      return this._map;
    },
    box(projectId) {
      const map = this.map();
      if (!map[projectId]) map[projectId] = { threads: [], active: "" };
      return map[projectId];
    },
    persist() {
      S.saveThreads(this.map());
    },
    list(projectId) {
      return this.box(projectId).threads.slice().sort(function (a, b) {
        return (b.updatedAt || 0) - (a.updatedAt || 0);
      });
    },
    get(projectId, threadId) {
      return this.box(projectId).threads.find(function (t) {
        return t.id === threadId;
      });
    },
    create(projectId, title) {
      const thread = {
        id: S.uid("t"),
        title: title || "新对话",
        createdAt: Date.now(),
        updatedAt: Date.now(),
        messages: [],
      };
      this.box(projectId).threads.unshift(thread);
      this.box(projectId).active = thread.id;
      this.persist();
      return thread;
    },
    ensure(projectId, seedMessages) {
      const box = this.box(projectId);
      if (box.threads.length) {
        const active = box.threads.find(function (t) {
          return t.id === box.active;
        });
        return active || this.list(projectId)[0];
      }
      const thread = this.create(projectId, "项目对话");
      if (seedMessages && seedMessages.length) {
        thread.messages = seedMessages.map(function (m) {
          return {
            role: m.role === "assistant" ? "assistant" : "user",
            content: S.clean(m.content || ""),
            ts: Date.now(),
          };
        });
        thread.updatedAt = Date.now();
        this.persist();
      }
      return thread;
    },
    remove(projectId, threadId) {
      const box = this.box(projectId);
      box.threads = box.threads.filter(function (t) {
        return t.id !== threadId;
      });
      if (box.active === threadId) box.active = "";
      this.persist();
    },
    rename(projectId, threadId, title) {
      const t = this.get(projectId, threadId);
      if (t) {
        t.title = title || t.title;
        t.updatedAt = Date.now();
        this.persist();
      }
    },
    touch(thread) {
      thread.updatedAt = Date.now();
      this.persist();
    },
  };
  S.threads = threads;

  /* =====================================================================
   * 项目数据
   * =================================================================== */
  async function loadProject(projectId, force) {
    const state = appState();
    const cached = state.projects.find(function (p) {
      return p.id === projectId;
    });
    if (!force && state.project && state.project.id === projectId) return state.project;
    const project = await S.api("/api/projects/" + projectId);
    state.project = project;
    if (cached) Object.assign(cached, project);
    return project;
  }

  function skillLabel(project) {
    const state = project.state || {};
    return S.clean(state.skill_name || state.skill_id || "申报项目");
  }

  /* =====================================================================
   * 项目页
   * =================================================================== */
  async function projectView(container, projectId, tab) {
    const seq = ++viewSeq;
    projectHost = container;
    const currentTab = ["conversations", "files", "memory", "document"].indexOf(tab) >= 0 ? tab : "conversations";
    container.innerHTML = loadingHTML();
    let project;
    try {
      project = await loadProject(projectId, true);
    } catch (err) {
      if (seq !== viewSeq) return;
      container.innerHTML = errorHTML(err);
      bindError(container.firstElementChild);
      return;
    }
    if (seq !== viewSeq) return;
    threads.ensure(projectId, project.messages);
    window.App.refreshShell();
    container.innerHTML = projectShell(project, currentTab);
    const root = container.firstElementChild;
    bindProjectEvents(root, project, currentTab);
    if (currentTab === "files") bindDropZone(root, project);
  }

  function loadingHTML() {
    return (
      '<div class="view" style="padding:24px 26px">' +
      '<div class="skeleton" style="height:24px;width:220px;margin-bottom:18px"></div>' +
      '<div class="skeleton" style="height:120px;margin-bottom:12px"></div>' +
      '<div class="skeleton" style="height:64px"></div></div>'
    );
  }

  function errorHTML(err) {
    return (
      '<div class="view"><div class="empty">' +
      '<div class="empty-icon">' +
      icon("alert") +
      "</div>" +
      '<div class="empty-title">项目打不开</div>' +
      '<div class="empty-desc">' +
      esc(err && err.message ? err.message : "请求失败") +
      "</div>" +
      '<button class="btn btn-ghost" data-act="go-home">返回首页</button>' +
      "</div></div>"
    );
  }

  function bindError(container) {
    S.on(container, "click", '[data-act="go-home"]', function () {
      window.App.navigate("#/");
    });
  }

  function projectShell(project, tab) {
    return (
      '<div class="project-view">' +
      projectHeader(project) +
      projectTabs(project, tab) +
      '<div class="project-body">' +
      '<div class="project-main"><div class="project-content"><div class="project-content-inner">' +
      tabContent(project, tab) +
      "</div></div></div>" +
      projectRail(project, tab) +
      "</div></div>"
    );
  }

  function projectHeader(project) {
    return (
      '<header class="project-header">' +
      '<button class="icon-btn mobile-only" type="button" data-act="open-sidebar" aria-label="打开侧边栏">' +
      icon("menu") +
      "</button>" +
      '<div class="breadcrumb">' +
      '<button class="crumb" type="button" data-act="go-home" title="返回首页">' +
      icon("arrow-left") +
      '<span class="crumb-title">' +
      esc(S.clean(project.title || "未命名项目")) +
      "</span></button>" +
      '<span class="badge">' +
      esc(skillLabel(project)) +
      "</span>" +
      "</div>" +
      '<div class="header-actions">' +
      '<button class="btn btn-sm btn-ghost" type="button" data-act="export">' +
      icon("download") +
      "<span>导出 Word</span></button>" +
      '<button class="icon-btn" type="button" data-act="project-settings" title="项目设置" aria-label="项目设置">' +
      icon("settings") +
      "</button>" +
      "</div>" +
      "</header>"
    );
  }

  function projectTabs(project, tab) {
    const docCount = project.documents ? project.documents.length : 0;
    const threadCount = threads.list(project.id).length;
    const tabs = [
      { id: "conversations", label: "会话", icon: "chat", count: threadCount },
      { id: "files", label: "文件", icon: "file", count: docCount },
      { id: "memory", label: "共同记忆", icon: "book-open", count: 0 },
      { id: "document", label: "申报书", icon: "list", count: project.outline ? project.outline.length : 0 },
    ];
    return (
      '<nav class="project-tabs">' +
      tabs
        .map(function (t) {
          return (
            '<button type="button" class="project-tab' +
            (t.id === tab ? " active" : "") +
            '" data-act="tab" data-tab="' +
            t.id +
            '">' +
            icon(t.icon) +
            "<span>" +
            t.label +
            "</span>" +
            (t.count ? '<span class="count">' + t.count + "</span>" : "") +
            "</button>"
          );
        })
        .join("") +
      "</nav>"
    );
  }

  function tabContent(project, tab) {
    if (tab === "files") return filesContent(project);
    if (tab === "memory") return memoryContent(project);
    if (tab === "document") return documentContent(project);
    return conversationsContent(project);
  }

  /* ------------------------------ 会话 ------------------------------ */
  function conversationsContent(project) {
    const list = threads.list(project.id);
    const rows = list.length
      ? list
          .map(function (t) {
            const last = t.messages[t.messages.length - 1];
            return (
              '<button class="conv-row" type="button" data-act="open-thread" data-thread="' +
              esc(t.id) +
              '">' +
              '<span class="conv-icon">' +
              icon("message") +
              "</span>" +
              '<span class="conv-meta">' +
              '<span class="conv-title">' +
              esc(S.clean(t.title || "新对话")) +
              "</span>" +
              '<span class="conv-preview">' +
              esc(last ? S.clean(last.content).slice(0, 80) : "还没有消息") +
              "</span></span>" +
              '<span class="conv-side">' +
              '<span class="conv-time">' +
              esc(S.fmtTime(t.updatedAt)) +
              "</span>" +
              '<span class="conv-del" role="button" tabindex="0" data-act="del-thread" data-thread="' +
              esc(t.id) +
              '" title="删除会话">' +
              icon("trash") +
              "</span></span></button>"
            );
          })
          .join("")
      : emptyHTML("message", "还没有对话", "为这个项目开启一次独立会话：文件与共同记忆会自动带进上下文，但对话各自独立。") +
        '<div style="text-align:center"><button class="btn btn-primary" data-act="new-thread">' +
        icon("plus") +
        " 新建对话</button></div>";

    return (
      guideCardHTML(project) +
      '<div class="section-head"><div><div class="section-title">' +
      icon("message") +
      "会话</div><div class=\"section-desc\">每个项目可以有多条独立会话，共享同一份文件与共同记忆。</div></div>" +
      (list.length ? '<button class="btn btn-sm btn-primary" data-act="new-thread">' + icon("plus") + " 新建对话</button>" : "") +
      "</div>" +
      '<div class="conv-list">' +
      rows +
      "</div>"
    );
  }

  /* ------------------------------ 文件 ------------------------------ */
  function filesContent(project) {
    const docs = project.documents || [];
    const rows = docs
      .map(function (doc) {
        const kindLabel = doc.kind === "template" ? "学校模板" : doc.kind === "photo" ? "照片" : "来源材料";
        let status;
        if (doc.confirmed) status = '<span class="badge badge-ok">' + icon("check") + "已确认</span>";
        else if (doc.extraction_status === "error")
          status = '<span class="badge badge-warn">提取失败</span>';
        else status = '<span class="badge badge-warn">待确认</span>';
        return (
          '<div class="file-row" data-act="view-doc" data-doc="' + esc(doc.id) + '" role="button" tabindex="0">' +
          '<span class="file-ico">' +
          icon(doc.kind === "photo" ? "image" : doc.kind === "template" ? "file-check" : "file") +
          "</span>" +
          '<span class="file-meta">' +
          '<span class="file-name">' +
          esc(S.clean(doc.original_name)) +
          "</span>" +
          '<span class="file-sub"><span>' +
          kindLabel +
          "</span><span>" +
          esc(S.fmtTime(doc.created_at)) +
          "</span>" +
          (doc.extraction_warning ? "<span>" + esc(S.clean(doc.extraction_warning).slice(0, 40)) + "</span>" : "") +
          "</span></span>" +
          status +
          '<span class="file-actions">' +
          '<button class="btn btn-sm btn-ghost" data-act="view-doc" data-doc="' +
          esc(doc.id) +
          '">' +
          (doc.confirmed ? "查看文本" : "查看 / 确认") +
          "</button>" +
          '<button class="icon-btn" data-act="open-doc" data-doc="' +
          esc(doc.id) +
          '" title="打开文件">' +
          icon("external-link") +
          "</button>" +
          '<button class="icon-btn" data-act="del-doc" data-doc="' +
          esc(doc.id) +
          '" title="删除">' +
          icon("trash") +
          "</button>" +
          "</span></div>"
        );
      })
      .join("");

    const templatePreference = (project.state || {}).template_preference || "not_asked";
    const templateHint =
      templatePreference === "has_template"
        ? "这个项目选择了使用学校模板，请上传或确认模板后再生成正文。"
        : templatePreference === "generic"
        ? "这个项目使用通用结构；提交前请核对学校通知中的格式要求。"
        : "还没确认是否有学校模板，可以在对话里告诉 Agent，或直接上传模板。";

    return (
      '<div class="section-head"><div><div class="section-title">' +
      icon("file") +
      "文件</div><div class=\"section-desc\">未确认的材料不会进入检索；模板会自动用于排版。</div></div>" +
      '<div style="display:flex;gap:6px"><button class="btn btn-sm btn-ghost" data-act="upload-template">' +
      icon("upload") +
      " 上传模板</button>" +
      '<button class="btn btn-sm btn-primary" data-act="upload-source">' +
      icon("plus") +
      " 上传材料</button></div></div>" +
      '<div class="file-toolbar"><span class="small muted">' +
      esc(templateHint) +
      "</span></div>" +
      (docs.length
        ? '<div class="file-list">' + rows + "</div>"
        : '<div class="upload-zone" data-act="upload-source">' +
          icon("upload") +
          '<span class="upload-zone-title">拖拽文件到这里，或点击上传</span>' +
          '<span class="upload-zone-sub">支持 PDF / Word / TXT / 图片，单文件不超过 20MB</span></div>') +
      (docs.length
        ? '<div style="margin-top:14px"><div class="upload-zone" data-act="upload-source">' +
          icon("upload") +
          '<span class="upload-zone-title">继续添加材料</span>' +
          '<span class="upload-zone-sub">也可以把学校通知、已有草稿粘贴到对话里</span></div></div>'
        : "")
    );
  }

  /* ---------------------------- 共同记忆 ---------------------------- */
  function memoryContent(project) {
    const state = project.state || {};
    const facts = state.confirmed_facts || {};
    const sources = state.fact_sources || {};
    const keys = Object.keys(facts);
    const rows = keys.length
      ? keys
          .map(function (key) {
            const label = FACT_LABELS[key] || key;
            return (
              '<div class="fact-row">' +
              '<div class="fact-key">' +
              esc(label) +
              "</div>" +
              '<div><div class="fact-value">' +
              esc(S.clean(facts[key])) +
              "</div>" +
              (sources[key]
                ? '<div class="fact-source">来源：' + esc(S.clean(sources[key]).slice(0, 80)) + "</div>"
                : "") +
              "</div></div>"
            );
          })
          .join("")
      : "";

    const ui = S.getUI();
    const instructions = (ui.projectInstructions && ui.projectInstructions[project.id]) || "";
    const info = [
      { label: "申报赛道", value: skillLabel(project) },
      { label: "申报级别", value: project.level || facts.level || "未填写" },
      { label: "学科 / 专业", value: project.discipline || facts.discipline || "未填写" },
      { label: "学校", value: project.school || facts.school || "未填写" },
    ];

    const factOptions = Object.keys(FACT_LABELS)
      .map(function (key) {
        return '<option value="' + key + '">' + esc(FACT_LABELS[key]) + "</option>";
      })
      .join("");

    return (
      '<div class="section-head"><div><div class="section-title">' +
      icon("book-open") +
      "共同记忆</div><div class=\"section-desc\">这里的事实会进入每次对话与写作的上下文；未确认的信息不会被当成事实。</div></div>" +
      '<button class="btn btn-sm btn-ghost" data-act="project-settings">' +
      icon("edit") +
      " 编辑基本信息</button></div>" +
      '<div class="fact-table" style="margin-bottom:16px">' +
      info
        .map(function (item) {
          return (
            '<div class="fact-row"><div class="fact-key">' +
            esc(item.label) +
            '</div><div class="fact-value">' +
            esc(S.clean(item.value)) +
            "</div></div>"
          );
        })
        .join("") +
      "</div>" +
      '<div class="section-title" style="margin:20px 0 8px">' +
      icon("pin") +
      "已确认事实</div>" +
      (facts.length || keys.length
        ? '<div class="fact-table">' + rows + "</div>"
        : '<div class="fact-table"><div class="fact-row"><div class="fact-key">还没有事实</div><div class="fact-value muted">在对话中确认，或在这里手动补充</div></div></div>') +
      '<div class="fact-add">' +
      '<select class="input select" id="fact-key">' +
      factOptions +
      "</select>" +
      '<input class="input" id="fact-value" placeholder="填写内容，例如：国家级">' +
      '<button class="btn btn-ghost" data-act="add-fact">' +
      icon("plus") +
      " 添加</button>" +
      "</div>" +
      '<div class="field-hint" style="margin-top:6px">手动添加的事实会标记来源为“学生在网页中手动确认”。</div>' +
      '<div class="section-title" style="margin:26px 0 8px">' +
      icon("command") +
      "项目指令</div>" +
      '<div class="settings-section-desc" style="margin-bottom:8px">写给 Agent 的长期偏好，例如称呼、语气、需要反复提醒的评审要求。只保存在本机。</div>' +
      '<div class="instructions-box"><textarea class="textarea" id="project-instructions" placeholder="例如：请用正式、克制的书面语；每章控制在 800 字以内；涉及数据必须标注来源。">' +
      esc(instructions) +
      '</textarea><div class="instructions-foot"><button class="btn btn-sm btn-ghost" data-act="save-instructions">' +
      icon("check") +
      " 保存指令</button></div></div>"
    );
  }

  /* ----------------------------- 申报书 ----------------------------- */
  function documentContent(project) {
    const outline = project.outline || [];
    const sections = project.sections || {};
    const rows = outline.length
      ? outline
          .map(function (item, index) {
            const id = item.id || "";
            const content = sections[id] || "";
            return (
              '<div class="outline-row" data-act="open-section" data-id="' + esc(id) + '" role="button" tabindex="0" title="查看或编辑这一章">' +
              '<span class="outline-index">' +
              String(index + 1).padStart(2, "0") +
              "</span>" +
              '<span class="outline-name">' +
              esc(S.clean(item.title || id || "未命名章节")) +
              "</span>" +
              '<span class="outline-status">' +
              (String(content).trim()
                ? '<span class="badge badge-ok">已生成</span>'
                : '<span class="badge">待生成</span>') +
              "</span></div>"
            );
          })
          .join("")
      : emptyHTML("list", "还没有大纲", "先让 Agent 生成申报书目录，再逐章撰写。生成大纲需要可用的模型配置。");

    return (
      '<div class="section-head"><div><div class="section-title">' +
      icon("list") +
      "申报书</div><div class=\"section-desc\">导出的是草稿：提交前请人工核对通知、数据与引用。</div></div>" +
      '<div style="display:flex;gap:6px">' +
      '<button class="btn btn-sm btn-ghost" data-act="validate">' +
      icon("shield") +
      " 导出前检查</button>" +
      '<button class="btn btn-sm btn-ghost" data-act="generate-outline">' +
      icon("sparkles") +
      " 生成大纲</button>" +
      '<button class="btn btn-sm btn-primary" data-act="export">' +
      icon("download") +
      " 导出 Word</button></div></div>" +
      (outline.length ? '<div class="outline-list">' + rows + "</div>" : rows) +
      (outline.length ? '<div class="field-hint" style="margin-top:10px">点击任意章节可以查看、编辑或让 Agent 生成本章。</div>' : "") +
      '<div class="settings-section-desc" style="margin-top:16px">' +
      "当前赛道：" +
      esc(skillLabel(project)) +
      (project.state && project.state.template_preference === "has_template" ? " · 使用学校模板" : " · 通用结构") +
      "</div>"
    );
  }

  /* ------------------------------ 右栏 ------------------------------ */
  function projectRail(project, tab) {
    const state = project.state || {};
    const facts = state.confirmed_facts || {};
    const ui = S.getUI();
    const instructions = (ui.projectInstructions && ui.projectInstructions[project.id]) || "";
    const docs = project.documents || [];
    const railDocs = docs.slice(0, 5);
    return (
      '<aside class="project-rail">' +
      '<div class="rail-block"><div class="rail-title">' +
      icon("folder") +
      "项目信息</div>" +
      '<div class="rail-text">' +
      esc(skillLabel(project)) +
      "\n" +
      (project.level ? esc(S.clean(project.level)) + " · " : "") +
      (project.discipline ? esc(S.clean(project.discipline)) + "\n" : "") +
      (project.school ? esc(S.clean(project.school)) : "") +
      "</div></div>" +
      '<div class="rail-block"><div class="rail-title">' +
      icon("command") +
      "指令</div>" +
      (instructions
        ? '<div class="rail-text">' + esc(instructions.slice(0, 220)) + "</div>"
        : '<div class="rail-empty">还没有项目指令。在「共同记忆」里写下长期偏好，后续每次对话都会带上。</div>') +
      "</div>" +
      '<div class="rail-block"><div class="rail-title">' +
      icon("file") +
      "文件</div>" +
      (railDocs.length
        ? '<div class="rail-files">' +
          railDocs
            .map(function (doc) {
              return (
                '<button class="rail-file" data-act="open-doc" data-doc="' +
                esc(doc.id) +
                '">' +
                icon("file") +
                '<span class="rail-file-name">' +
                esc(S.clean(doc.original_name)) +
                "</span></button>"
              );
            })
            .join("") +
          "</div>"
        : '<div class="rail-empty">还没有上传文件。学校模板、通知与已有草稿都可以放进来。</div>') +
      "</div>" +
      '<div class="rail-block"><div class="rail-title">' +
      icon("pin") +
      "记忆</div>" +
      (Object.keys(facts).length
        ? '<div class="rail-text">' +
          Object.keys(facts)
            .slice(0, 6)
            .map(function (key) {
              return esc(FACT_LABELS[key] || key) + "：" + esc(S.clean(String(facts[key])).slice(0, 30));
            })
            .join("\n") +
          "</div>"
        : '<div class="rail-empty">还没有已确认事实。</div>') +
      "</div>" +
      "</aside>"
    );
  }

  function emptyHTML(iconName, title, desc) {
    return (
      '<div class="empty"><div class="empty-icon">' +
      icon(iconName) +
      '</div><div class="empty-title">' +
      esc(title) +
      '</div><div class="empty-desc">' +
      esc(desc) +
      "</div></div>"
    );
  }

  function guideCardHTML(project) {
    const docs = project.documents || [];
    const facts = (project.state || {}).confirmed_facts || {};
    const outline = project.outline || [];
    const steps = [
      { id: "files", done: docs.length > 0, icon: "file", title: "放入学校模板或已有材料", desc: "模板决定排版，材料决定依据" },
      { id: "memory", done: Object.keys(facts).length > 1, icon: "book-open", title: "确认关键事实", desc: "级别、学科、要解决的问题与方法" },
      { id: "document", done: outline.length > 0, icon: "list", title: "生成申报书大纲", desc: "先有章节结构，再逐章撰写" },
    ];
    const doneCount = steps.filter(function (s) { return s.done; }).length;
    if (doneCount === steps.length) return "";
    return (
      '<div class="guide-card">' +
      '<div class="guide-head"><div><div class="guide-title">开始准备这份材料</div>' +
      '<div class="guide-desc">按顺序完成三步，就能导出第一版草稿</div></div>' +
      '<span class="guide-progress">' + doneCount + " / " + steps.length + "</span></div>" +
      '<div class="guide-steps">' +
      steps
        .map(function (step, index) {
          return (
            '<button class="guide-step' + (step.done ? " done" : "") +
            '" type="button" data-act="guide-' + step.id + '">' +
            '<span class="guide-num">' + (step.done ? icon("check") : String(index + 1)) + "</span>" +
            '<span class="guide-meta"><span class="guide-step-title">' + esc(step.title) +
            '</span><span class="guide-step-desc">' + esc(step.desc) + "</span></span>" +
            icon("chevron-right", "guide-arrow") +
            "</button>"
          );
        })
        .join("") +
      "</div></div>"
    );
  }

  function openDocumentModal(project, documentId, root) {
    const doc = (project.documents || []).find(function (d) { return d.id === documentId; });
    if (!doc) return;
    const kindLabel = doc.kind === "template" ? "学校模板" : doc.kind === "photo" ? "照片" : "来源材料";
    const original = doc.extracted_text || "";
    const failed = doc.extraction_status === "error";
    const isTemplate = doc.kind === "template";
    const ctx = S.openModal({
      title: S.clean(doc.original_name),
      subtitle: kindLabel + (doc.confirmed ? " · 已确认" : " · 待确认") + (failed ? " · 提取失败" : ""),
      size: "lg",
      body:
        (failed
          ? '<div class="home-alert">' + icon("alert") + "<span>这份文件没能提取出文字，可以重新上传可复制文字的版本。</span></div>"
          : "") +
        '<div class="field"><label class="field-label">提取文本' + (isTemplate ? "（模板只用于排版）" : "（可以直接修改）") + "</label>" +
        '<textarea class="textarea doc-textarea" id="doc-text" spellcheck="false"' + (isTemplate ? " readonly" : "") + ' placeholder="没有提取到文字，可以手动粘贴材料内容">' +
        esc(original) +
        "</textarea>" +
        '<div class="field-hint">' + (isTemplate ? "模板不进入事实检索；如需修改排版，请下载后调整再重新上传。" : "确认后这份材料才会进入检索；修改后的文本会覆盖原提取结果。") + "</div></div>" +
        (doc.extraction_warning
          ? '<div class="field-hint" style="margin-top:6px">' + esc(S.clean(doc.extraction_warning)) + "</div>"
          : ""),
      footer:
        '<span class="spacer"></span>' +
        '<button class="btn btn-ghost" type="button" data-open-file>下载原文件</button>' +
        '<button class="btn btn-ghost" type="button" data-modal-close>关闭</button>' +
        (isTemplate
          ? ""
          : '<button class="btn btn-primary" type="button" data-confirm>' +
            (doc.confirmed ? "保存修改" : "确认无误") +
            "</button>"),
      onMount: function (c) {
        c.el.querySelector("[data-open-file]").addEventListener("click", function () {
          window.open("/api/documents/" + doc.id + "/file", "_blank", "noopener");
        });
        const confirmBtn = c.el.querySelector("[data-confirm]");
        if (!confirmBtn) return;
        confirmBtn.addEventListener("click", function () {
          const text = c.el.querySelector("#doc-text").value;
          const body = { confirmed: true };
          if (text !== original) body.corrected_text = text;
          const btn = c.el.querySelector("[data-confirm]");
          btn.disabled = true;
          btn.innerHTML = '<span class="spinner"></span>';
          S.api("/api/documents/" + doc.id + "/confirm", { method: "PATCH", body: body })
            .then(function () {
              S.closeModal();
              S.toast("已确认，材料可以进入检索", "success");
              return refreshProjectView(root, project.id, "files");
            })
            .catch(function (err) {
              btn.disabled = false;
              btn.textContent = doc.confirmed ? "保存修改" : "确认无误";
              S.toast(err.message || "保存失败", "error");
            });
        });
      },
    });
    return ctx;
  }

  function reviewCardHTML(card) {
    if (!card || typeof card !== "object") return "";
    const score = Number(card.score);
    const hasScore = Number.isFinite(score);
    const incomplete = card.review_status === "failed" || !hasScore;
    const grade = S.clean(String(card.grade || ""));
    const iterations = Number(card.iterations) || 1;
    const scoreText = incomplete
      ? "AI 辅助检查：评审未完成（无分数）"
      : "AI 辅助检查 " + S.fmtCredits(score) + " 分" + (grade ? " · " + grade : "") + "（非官方评审）";
    const badge = incomplete
      ? "草稿保留 · 待重试评审"
      : (iterations > 1 ? "经 " + iterations + " 轮检查" : (card.passed ? "通过辅助检查" : "待完善"));
    const hints = (Array.isArray(card.user_hints) ? card.user_hints : [])
      .map(function (hint) { return S.clean(String(hint || "")); })
      .filter(Boolean)
      .slice(0, 4);
    return (
      '<div class="review-card' + (card.passed && !incomplete ? "" : " warn") + '">' +
      '<div class="review-head"><span class="review-score">' + esc(scoreText) + '</span><span class="review-badge' + (card.passed && !incomplete ? "" : " warn") + '">' + esc(badge) + "</span></div>" +
      (hints.length
        ? hints.map(function (hint) {
            return '<div class="review-hint">' + icon("sparkles") + "<span>" + esc(hint) + "</span></div>";
          }).join("")
        : "") +
      "</div>"
    );
  }

  function renderReviewCard(modalEl, card) {
    const existing = modalEl.querySelector(".review-card");
    if (existing) existing.remove();
    if (!card) return;
    const field = modalEl.querySelector("#section-text");
    if (!field) return;
    const wrap = field.closest(".field") || field.parentElement;
    if (wrap) wrap.insertAdjacentHTML("afterend", reviewCardHTML(card));
  }

  function openSectionModal(project, sectionId, root) {
    const outline = project.outline || [];
    const item = outline.find(function (i) { return (i.id || "") === sectionId; });
    const title = item ? item.title || sectionId : sectionId;
    const content = (project.sections || {})[sectionId] || "";
    const ctx = S.openModal({
      title: S.clean(title),
      subtitle: "章节草稿 · 保存后会用于 Word 导出",
      size: "lg",
      body:
        '<div class="field"><label class="field-label">章节内容</label>' +
        '<textarea class="textarea section-textarea" id="section-text" spellcheck="false" placeholder="这一章还没有内容。可以先自己写，或让 Agent 基于已确认事实生成草稿。">' +
        esc(content) +
        "</textarea>" +
        '<div class="field-hint">生成的内容是草稿；缺少依据的地方会标为待补充。</div></div>',
      footer:
        '<span class="spacer"></span>' +
        '<button class="btn btn-ghost" type="button" data-modal-close>关闭</button>' +
        '<button class="btn btn-ghost" type="button" data-generate>' + icon("sparkles") + " 生成本章</button>" +
        '<button class="btn btn-primary" type="button" data-save>保存章节</button>',
      onMount: function (c) {
        const area = c.el.querySelector("#section-text");
        const saveBtn = c.el.querySelector("[data-save]");
        const genBtn = c.el.querySelector("[data-generate]");
        saveBtn.addEventListener("click", function () {
          saveBtn.disabled = true;
          saveBtn.innerHTML = '<span class="spinner"></span>';
          S.api("/api/projects/" + project.id + "/sections/" + sectionId, {
            method: "PUT",
            body: { content: area.value },
          })
            .then(function () {
              S.closeModal();
              S.toast("章节已保存", "success");
              return refreshProjectView(root, project.id, "document");
            })
            .catch(function (err) {
              saveBtn.disabled = false;
              saveBtn.textContent = "保存章节";
              S.toast(err.message || "保存失败", "error");
            });
        });
        genBtn.addEventListener("click", async function () {
          genBtn.disabled = true;
          genBtn.innerHTML = '<span class="spinner"></span> 生成中';
          try {
            await confirmOutline(project, project.outline || []);
            const result = await S.api("/api/projects/" + project.id + "/sections/" + sectionId + "/generate", {
              method: "POST",
              body: { llm_config: modelPayload() },
              timeout: 600000,
            });
            if (result && result.content) {
              area.value = result.content;
              renderReviewCard(c.el, result.review_card);
              S.toast("已生成本章草稿，确认后可保存", "success");
              refreshProjectView(root, project.id, "document");
            } else {
              S.toast("生成结果为空", "error");
            }
          } catch (err) {
            showModelError(err, "生成本章");
          } finally {
            genBtn.disabled = false;
            genBtn.innerHTML = icon("sparkles") + " 生成本章";
          }
        });
      },
    });
    return ctx;
  }

  function openChatMenu(project) {
    const thread = chatCtx && chatCtx.thread;
    if (!thread) return;
    const ctx = S.openModal({
      title: "会话操作",
      subtitle: "当前会话只保存在这台电脑上",
      size: "sm",
      body:
        '<div class="menu-list">' +
        '<button class="menu-item" type="button" data-do="rename">' + icon("edit") + "重命名会话</button>" +
        '<button class="menu-item" type="button" data-do="project">' + icon("folder") + "返回项目</button>" +
        '<button class="menu-item danger" type="button" data-do="delete">' + icon("trash") + "删除会话</button>" +
        "</div>",
    });
    ctx.el.querySelector("[data-do='project']").addEventListener("click", function () {
      S.closeModal();
      window.App.navigate("#/p/" + project.id + "/conversations");
    });
    ctx.el.querySelector("[data-do='rename']").addEventListener("click", function () {
      S.closeModal();
      const rename = S.openModal({
        title: "重命名会话",
        size: "sm",
        body:
          '<div class="field"><label class="field-label">会话名称</label>' +
          '<input class="input" id="thread-name" maxlength="40" data-autofocus value="' + esc(S.clean(thread.title || "")) + '"></div>',
        footer:
          '<button class="btn btn-ghost" type="button" data-modal-close>取消</button>' +
          '<button class="btn btn-primary" type="button" data-ok>保存</button>',
      });
      const save = function () {
        const value = rename.el.querySelector("#thread-name").value.trim() || "新对话";
        threads.rename(project.id, thread.id, value);
        const titleEl = document.getElementById("chat-title");
        if (titleEl) titleEl.textContent = value;
        S.closeModal();
        window.App.refreshShell();
        S.toast("会话名称已更新", "success");
      };
      rename.el.querySelector("[data-ok]").addEventListener("click", save);
      rename.el.querySelector("#thread-name").addEventListener("keydown", function (e) {
        if (e.key === "Enter") save();
      });
    });
    ctx.el.querySelector("[data-do='delete']").addEventListener("click", function () {
      S.closeModal();
      S.confirm({
        title: "删除这条会话？",
        message: "会话记录只保存在本机，删除后无法恢复；项目文件与共同记忆不受影响。",
        confirmText: "删除",
        danger: true,
      }).then(function (ok) {
        if (!ok) return;
        threads.remove(project.id, thread.id);
        window.App.refreshShell();
        window.App.navigate("#/p/" + project.id + "/conversations");
      });
    });
  }

  /* =====================================================================
   * 项目页事件
   * =================================================================== */
  function bindProjectEvents(container, project, tab) {
    S.on(container, "keydown", '[role="button"][data-act]', function (event, target) {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        target.click();
      }
    });
    S.on(container, "click", "[data-act]", function (event, target) {
      const act = target.getAttribute("data-act");
      if (act === "tab") {
        window.App.navigate("#/p/" + project.id + "/" + target.getAttribute("data-tab"));
        return;
      }
      if (act === "go-home") {
        window.App.navigate("#/");
        return;
      }
      if (act === "open-sidebar") {
        window.App.toggleSidebar(true);
        return;
      }
      if (act === "new-thread") {
        const thread = threads.create(project.id);
        window.App.navigate("#/p/" + project.id + "/c/" + thread.id);
        return;
      }
      if (act === "open-thread") {
        const threadId = target.getAttribute("data-thread");
        window.App.navigate("#/p/" + project.id + "/c/" + threadId);
        return;
      }
      if (act === "del-thread") {
        event.stopPropagation();
        const threadId = target.getAttribute("data-thread");
        S.confirm({
          title: "删除这条会话？",
          message: "会话记录只保存在本机，删除后无法恢复；项目文件与共同记忆不受影响。",
          confirmText: "删除",
          danger: true,
        }).then(function (ok) {
          if (!ok) return;
          threads.remove(project.id, threadId);
          projectView(container, project.id, tab);
          window.App.refreshShell();
        });
        return;
      }
      if (act === "upload-source") {
        pickFiles("source", project, container, tab);
        return;
      }
      if (act === "upload-template") {
        pickFiles("template", project, container, tab);
        return;
      }
      if (act === "open-doc") {
        event.stopPropagation();
        window.open("/api/documents/" + target.getAttribute("data-doc") + "/file", "_blank", "noopener");
        return;
      }
      if (act === "view-doc") {
        openDocumentModal(project, target.getAttribute("data-doc"), container);
        return;
      }
      if (act === "open-section") {
        openSectionModal(project, target.getAttribute("data-id"), container);
        return;
      }
      if (act === "guide-files") {
        window.App.navigate("#/p/" + project.id + "/files");
        return;
      }
      if (act === "guide-memory") {
        window.App.navigate("#/p/" + project.id + "/memory");
        return;
      }
      if (act === "guide-document") {
        window.App.navigate("#/p/" + project.id + "/document");
        return;
      }
      if (act === "del-doc") {
        deleteDocument(project, target.getAttribute("data-doc"), container, tab);
        return;
      }
      if (act === "add-fact") {
        addFact(project, container);
        return;
      }
      if (act === "save-instructions") {
        saveInstructions(project.id);
        return;
      }
      if (act === "project-settings") {
        openProjectSettings(project);
        return;
      }
      if (act === "export") {
        exportProject(project);
        return;
      }
      if (act === "validate") {
        validateProject(project);
        return;
      }
      if (act === "generate-outline") {
        generateOutline(project, container);
        return;
      }
    });
  }

  function pickFiles(kind, project, container, tab) {
    const input = document.createElement("input");
    input.type = "file";
    input.multiple = true;
    input.accept = ".pdf,.doc,.docx,.txt,.md,.png,.jpg,.jpeg,.webp";
    input.addEventListener("change", function () {
      if (!input.files || !input.files.length) return;
      uploadFiles(project, kind, input.files, container, tab);
      input.value = "";
    });
    input.click();
  }

  async function uploadFiles(project, kind, files, container, tab) {
    const form = new FormData();
    for (let i = 0; i < files.length; i++) form.append("files", files[i]);
    S.toast("正在上传并提取文字…");
    try {
      const result = await S.api("/api/projects/" + project.id + "/documents?kind=" + kind, {
        method: "POST",
        body: form,
      });
      const docs = (result && result.documents) || [];
      const needs = docs.some(function (d) {
        return d.needs_confirmation;
      });
      S.toast(needs ? "已提取文字，请核对后确认" : "文件已上传", "success");
      const chatRoot =
        chatCtx && chatCtx.container && chatCtx.container.isConnected &&
        chatCtx.container.classList.contains("chat-view")
          ? chatCtx.container
          : null;
      if (chatRoot) {
        const fresh = await loadProject(project.id, true);
        Object.assign(project, fresh);
        if (chatRoot.querySelector(".doc-panel")) renderDocPanelBody(chatRoot, project, "files");
      } else {
        await refreshProjectView(container, project.id, tab || "files");
      }
    } catch (err) {
      S.toast(err.message || "上传失败", "error");
    }
  }

  function deleteDocument(project, documentId, container, tab) {
    S.confirm({
      title: "删除这份材料？",
      message: "删除后它不会再参与检索，也无法恢复。",
      confirmText: "删除",
      danger: true,
    }).then(async function (ok) {
      if (!ok) return;
      try {
        await S.api("/api/documents/" + documentId, { method: "DELETE" });
        S.toast("已删除", "success");
        await refreshProjectView(container, project.id, tab || "files");
      } catch (err) {
        S.toast(err.message || "删除失败", "error");
      }
    });
  }

  async function addFact(project, container) {
    const keyEl = container.querySelector("#fact-key");
    const valueEl = container.querySelector("#fact-value");
    const key = keyEl ? keyEl.value : "";
    const value = valueEl ? valueEl.value.trim() : "";
    if (!value) {
      S.toast("请填写事实内容", "error");
      if (valueEl) valueEl.focus();
      return;
    }
    try {
      await S.api("/api/projects/" + project.id + "/facts", {
        method: "PUT",
        body: { [key]: value },
      });
      S.toast("已加入共同记忆", "success");
      await refreshProjectView(container, project.id, "memory");
    } catch (err) {
      S.toast(err.message || "保存失败", "error");
    }
  }

  function saveInstructions(projectId) {
    const el = document.getElementById("project-instructions");
    const text = el ? el.value.trim() : "";
    const ui = S.getUI();
    const map = Object.assign({}, ui.projectInstructions || {});
    if (text) map[projectId] = text;
    else delete map[projectId];
    S.setUI({ projectInstructions: map });
    S.toast("项目指令已保存", "success");
  }

  async function refreshProjectView(container, projectId, tab) {
    const expected = viewSeq;
    const project = await loadProject(projectId, true);
    if (expected !== viewSeq) return;
    const host = projectHost || container;
    if (!host || !host.isConnected) return;
    host.innerHTML = projectShell(project, tab);
    const root = host.firstElementChild;
    bindProjectEvents(root, project, tab);
    if (tab === "files") bindDropZone(root, project);
    window.App.refreshShell();
  }

  function bindDropZone(container, project) {
    container.querySelectorAll(".upload-zone").forEach(function (zone) {
      ["dragenter", "dragover"].forEach(function (type) {
        zone.addEventListener(type, function (e) {
          e.preventDefault();
          zone.classList.add("is-drag");
        });
      });
      ["dragleave", "drop"].forEach(function (type) {
        zone.addEventListener(type, function (e) {
          e.preventDefault();
          zone.classList.remove("is-drag");
        });
      });
      zone.addEventListener("drop", function (e) {
        if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length) {
          uploadFiles(project, "source", e.dataTransfer.files, container, "files");
        }
      });
    });
  }

  /* =====================================================================
   * 项目设置 / 导出 / 校验 / 大纲
   * =================================================================== */
  function openProjectSettings(project) {
    const state = project.state || {};
    const levels = [
      { value: "", label: "未填写" },
      { value: "国家级", label: "国家级" },
      { value: "省级", label: "省级" },
      { value: "校级", label: "校级" },
    ];
    if (project.level && !levels.some(function (l) { return l.value === project.level; })) {
      levels.push({ value: project.level, label: project.level });
    }
    const ctx = S.openModal({
      title: "项目设置",
      subtitle: "修改名称与基本信息，或删除这个项目",
      size: "md",
      body:
        '<div class="form-grid">' +
        '<div class="field form-grid-full"><label class="field-label">项目名称</label><input class="input" id="ps-title" maxlength="160" value="' +
        esc(S.clean(project.title || "")) +
        '"></div>' +
        '<div class="field"><label class="field-label">申报级别</label><select class="select" id="ps-level">' +
        levels
          .map(function (l) {
            return '<option value="' + l.value + '"' + ((project.level || "") === l.value ? " selected" : "") + ">" + l.label + "</option>";
          })
          .join("") +
        "</select></div>" +
        '<div class="field"><label class="field-label">学科 / 专业</label><input class="input" id="ps-discipline" maxlength="100" value="' +
        esc(S.clean(project.discipline || "")) +
        '"></div>' +
        '<div class="field form-grid-full"><label class="field-label">学校</label><input class="input" id="ps-school" maxlength="120" value="' +
        esc(S.clean(project.school || "")) +
        '"></div>' +
        '<div class="field form-grid-full"><div class="field-hint">当前赛道：' +
        esc(skillLabel(project)) +
        "；赛道由创建时选择，暂不支持更换。</div></div>" +
        "</div>",
      footer:
        '<button class="btn btn-sm btn-danger" data-del-project>删除项目</button><span class="spacer"></span>' +
        '<button class="btn btn-ghost" data-modal-close>取消</button>' +
        '<button class="btn btn-primary" data-save>保存</button>',
    });
    ctx.backdrop.querySelector("[data-save]").addEventListener("click", async function () {
      const title = ctx.backdrop.querySelector("#ps-title").value.trim();
      const level = ctx.backdrop.querySelector("#ps-level").value;
      const discipline = ctx.backdrop.querySelector("#ps-discipline").value.trim();
      const school = ctx.backdrop.querySelector("#ps-school").value.trim();
      try {
        await S.api("/api/projects/" + project.id, {
          method: "PATCH",
          body: { title: title || project.title, level: level || "", discipline: discipline, school: school },
        });
        S.closeModal();
        S.toast("项目信息已更新", "success");
        await window.App.reloadCurrent();
      } catch (err) {
        S.toast(err.message || "保存失败", "error");
      }
    });
    ctx.backdrop.querySelector("[data-del-project]").addEventListener("click", function () {
      S.confirm({
        title: "删除这个项目？",
        message: "项目、会话、文件与共同记忆都会删除，且无法恢复。",
        confirmText: "删除",
        danger: true,
      }).then(async function (ok) {
        if (!ok) return;
        try {
          await S.api("/api/projects/" + project.id, { method: "DELETE" });
          S.closeModal();
          S.toast("项目已删除", "success");
          await window.App.refreshProjects();
          window.App.navigate("#/");
        } catch (err) {
          S.toast(err.message || "删除失败", "error");
        }
      });
    });
  }

  async function exportProject(project) {
    S.toast("正在生成 Word 草稿…");
    try {
      const result = await S.api("/api/projects/" + project.id + "/export", { method: "POST" });
      const validation = result.validation || null;
      S.openModal({
        title: "Word 草稿已生成",
        size: "md",
        body:
          '<div class="doc-paper" style="min-height:auto;padding:18px 20px;background:#f7f7f5;box-shadow:none">' +
          '<div style="font-size:13px;line-height:1.9;color:#2b2b2e">' +
          "草稿已按当前项目内容生成，共 " +
          esc(result.section_count || (project.outline || []).length) +
          " 个章节。导出的是草稿，正式提交前请核对学校通知与事实来源。" +
          "</div></div>" +
          (validation && validation.consistency_warnings && validation.consistency_warnings.length
            ? '<div class="check-list">' +
              validation.consistency_warnings
                .slice(0, 4)
                .map(function (w) {
                  return '<div class="check-row warn">' + icon("alert") + "<span>" + esc(w) + "</span></div>";
                })
                .join("") +
              "</div>"
            : ""),
        footer:
          '<button class="btn btn-ghost" data-modal-close>稍后</button>' +
          '<button class="btn btn-primary" data-download>' +
          icon("download") +
          " 下载 Word</button>",
        onMount: function (ctx) {
          ctx.backdrop.querySelector("[data-download]").addEventListener("click", function () {
            S.downloadUrl("/api/projects/" + project.id + "/download", "申报书草稿.docx");
            S.closeModal();
          });
        },
      });
    } catch (err) {
      S.toast(err.message || "导出失败", "error");
    }
  }

  async function validateProject(project) {
    try {
      const v = await S.api("/api/projects/" + project.id + "/validate", { method: "POST" });
      S.openModal({
        title: "导出前检查",
        subtitle: v.validation_scope || "",
        size: "md",
        body:
          '<div class="check-list" style="margin-top:0">' +
          checkRow(v.passed ? "ok" : "warn", v.passed ? "基础检查通过" : "还有需要补充的项目") +
          ((v.missing_facts || []).length
            ? v.missing_facts
                .map(function (f) {
                  return checkRow("warn", "缺少事实：" + (f.label || f.field));
                })
                .join("")
            : "") +
          ((v.unconfirmed_documents || []).length
            ? v.unconfirmed_documents
                .map(function (name) {
                  return checkRow("warn", "材料待确认：" + name);
                })
                .join("")
            : "") +
          ((v.missing_sections || []).length
            ? v.missing_sections
                .map(function (name) {
                  return checkRow("warn", "章节未生成：" + name);
                })
                .join("")
            : "") +
          ((v.consistency_warnings || [])
            .map(function (w) {
              return checkRow("warn", w);
            })
            .join("")) +
          ((v.low_confidence_ocr || [])
            .map(function (item) {
              return checkRow("warn", "识别置信度偏低：" + item.name);
            })
            .join("")) +
          "</div>" +
          (v.draft_notice
            ? '<div class="settings-section-desc" style="margin-top:14px">' + esc(v.draft_notice) + "</div>"
            : ""),
        footer:
          '<button class="btn btn-ghost" data-modal-close>关闭</button>' +
          '<button class="btn btn-primary" data-export>继续导出</button>',
        onMount: function (ctx) {
          ctx.backdrop.querySelector("[data-export]").addEventListener("click", function () {
            S.closeModal();
            exportProject(project);
          });
        },
      });
    } catch (err) {
      S.toast(err.message || "检查失败", "error");
    }
  }

  function checkRow(kind, text) {
    return (
      '<div class="check-row ' +
      kind +
      '">' +
      icon(kind === "ok" ? "check-circle" : "alert") +
      "<span>" +
      esc(S.clean(text)) +
      "</span></div>"
    );
  }

  async function confirmOutline(project, outline) {
    if (!outline || !outline.length) return false;
    await S.api("/api/projects/" + project.id + "/outline", {
      method: "PUT",
      body: { outline: outline.map(function (item) { return { id: item.id, title: item.title }; }) },
    });
    if (!project.state) project.state = {};
    project.state.outline_confirmed = true;
    return true;
  }

  async function generateOutline(project, container) {
    S.toast("正在生成大纲…");
    try {
      const result = await S.api("/api/projects/" + project.id + "/outline/generate", {
        method: "POST",
        body: { llm_config: modelPayload() },
        timeout: 600000,
      });
      if (result && result.outline && result.outline.length) {
        project.outline = result.outline;
        await confirmOutline(project, result.outline);
        S.toast(result.warning ? "已生成可编辑的通用目录" : "大纲已生成", "success");
        await refreshProjectView(container, project.id, "document");
      } else {
        S.toast("大纲生成结果为空", "error");
      }
    } catch (err) {
      showModelError(err, "生成大纲");
    }
  }

  function showModelError(err, action) {
    if (err && (err.status === 402 || err.status === 503 || err.status === 502 || err.status === 0)) {
      S.openModal({
        title: action + "失败",
        size: "sm",
        body:
          '<div class="msg-error" style="margin-top:0">' +
          icon("alert") +
          '<div class="msg-error-body">' +
          esc(err.message || "模型服务不可用") +
          '<div class="msg-error-actions">' +
          '<button class="btn btn-sm btn-primary" data-open-settings>打开设置</button>' +
          "</div></div></div>",
        footer: '<button class="btn btn-ghost" data-modal-close>关闭</button>',
        onMount: function (ctx) {
          ctx.backdrop.querySelector("[data-open-settings]").addEventListener("click", function () {
            S.closeModal();
            if (window.App) window.App.openSettings("model");
          });
        },
      });
    } else {
      S.toast(err.message || (action + "失败"), "error");
    }
  }

  /* =====================================================================
   * 对话
   * =================================================================== */
  let chatCtx = null;

  async function chatView(container, projectId, threadId) {
    const seq = ++viewSeq;
    container.innerHTML = loadingHTML();
    let project;
    try {
      project = await loadProject(projectId, true);
    } catch (err) {
      if (seq !== viewSeq) return;
      container.innerHTML = errorHTML(err);
      bindError(container.firstElementChild);
      return;
    }
    if (seq !== viewSeq) return;
    threads.ensure(projectId, project.messages);
    window.App.refreshShell();
    let thread = threads.get(projectId, threadId);
    if (!thread) {
      thread = threads.list(projectId)[0] || threads.create(projectId);
      window.App.navigate("#/p/" + projectId + "/c/" + thread.id, true);
    }
    const hasPreview = (project.documents || []).length > 0 || (project.outline || []).length > 0;
    const docOpen = window.innerWidth > 1024 && !!hasPreview;
    container.innerHTML = chatShell(project, thread, docOpen);
    const root = container.querySelector(".chat-view");
    bindChatEvents(root, project, thread, docOpen);
    scrollChatToBottom();
  }

  function chatShell(project, thread, docOpen) {
    const messages = thread.messages || [];
    return (
      '<div class="chat-view">' +
      '<div class="chat-main">' +
      chatHead(project, thread) +
      '<div class="chat-scroll" id="chat-scroll">' +
      (messages.length
        ? '<div class="chat-thread" id="chat-thread" role="log" aria-live="polite">' +
          messages
            .map(function (m, i) {
              return messageHTML(m, i);
            })
            .join("") +
          "</div>"
        : '<div class="chat-thread" id="chat-thread" style="height:100%">' + chatEmpty(project) + "</div>") +
      "</div>" +
      '<button class="scroll-bottom hidden" type="button" data-act="scroll-bottom" aria-label="回到底部">' +
      icon("arrow-down") +
      "</button>" +
      chatComposer(project) +
      "</div>" +
      (docOpen ? docPanel(project) : "") +
      "</div>"
    );
  }

  function chatHead(project, thread) {
    return (
      '<header class="chat-head">' +
      '<button class="icon-btn" type="button" data-act="back-project" title="返回项目" aria-label="返回项目">' +
      icon("arrow-left") +
      "</button>" +
      '<button class="icon-btn mobile-only" type="button" data-act="open-sidebar" aria-label="打开侧边栏">' +
      icon("menu") +
      "</button>" +
      '<div class="chat-head-title" id="chat-title">' +
      esc(S.clean(thread.title || "新对话")) +
      "</div>" +
      '<button class="icon-btn" type="button" data-act="toggle-docs" title="文档预览" aria-label="文档预览">' +
      icon("panel-right") +
      "</button>" +
      '<button class="icon-btn" type="button" data-act="chat-settings" title="项目设置" aria-label="项目设置">' +
      icon("settings") +
      "</button>" +
      '<button class="icon-btn" type="button" data-act="chat-menu" title="会话操作" aria-label="会话操作">' +
      icon("more") +
      "</button>" +
      "</header>"
    );
  }

  function chatEmpty(project) {
    const suggestions = suggestionsFor(project);
    return (
      '<div class="chat-empty">' +
      '<div class="chat-empty-mark">' +
      icon("sparkles") +
      "</div>" +
      '<div class="chat-empty-title">开始写这份材料</div>' +
      '<div class="chat-empty-desc">描述目标或先上传材料，确认事实后再动笔。</div>' +
      '<div class="chat-suggestions">' +
      suggestions
        .map(function (s) {
          return '<button class="chip" type="button" data-act="suggest" data-text="' + esc(s) + '">' + esc(s) + "</button>";
        })
        .join("") +
      "</div></div>"
    );
  }

  function suggestionsFor(project) {
    const state = project.state || {};
    const skill = ((window.App && window.App.state.skills) || []).find(function (s) {
      return s.id === state.skill_id;
    });
    const cat = (skill && skill.category) || state.skill_category || "";
    if (cat === "scholarship") return ["先准备哪些材料？", "列出材料清单", "评审关注什么？"];
    if (cat === "competition") return ["材料包含哪些部分？", "整理项目亮点", "评审关注什么？"];
    if (cat === "practice") return ["报告结构是什么？", "整理成报告大纲", "需要哪些证明？"];
    return ["先准备什么材料？", "生成申报书目录", "评审关注什么？"];
  }

  function chatComposer(project) {
    const m = S.getModel();
    const config = (window.App && window.App.state && window.App.state.config) || {};
    const presetUnavailable =
      !m.demo &&
      config.preset_enabled === false &&
      (m.provider || "preset") === "preset" &&
      !m.model;
    return (
      '<div class="chat-composer">' +
      (presetUnavailable
        ? '<div class="chat-banner">' +
          icon("info") +
          "<span>当前环境未开通平台模型，可在设置中改用 Ollama 或自备 API。</span>" +
          '<span class="spacer"></span><button class="text-btn" data-act="open-settings">去设置</button></div>'
        : "") +
      (m.demo
        ? '<div class="chat-banner">' +
          icon("info") +
          "<span>演示模式：回复由本地示例生成，不会调用真实模型。</span>" +
          '<span class="spacer"></span><button class="text-btn" data-act="open-settings">关闭</button></div>'
        : "") +
      '<div class="composer">' +
      '<div class="composer-box">' +
      '<textarea class="composer-input" id="chat-input" rows="1" placeholder="描述你的需求，Enter 发送，Shift+Enter 换行"></textarea>' +
      '<div class="composer-bar">' +
      '<button class="composer-tool" type="button" data-act="attach">' +
      icon("paperclip") +
      "<span>添加材料</span></button>" +
      '<button class="composer-tool" type="button" data-act="open-settings">' +
      icon("cpu") +
      "<span>" +
      esc(m.provider === "ollama" ? "Ollama" : m.provider === "openai_compatible" ? "自备 API" : "平台预设") +
      "</span></button>" +
      '<span class="spacer"></span>' +
      '<button class="send-btn" type="button" data-act="send" disabled aria-label="发送">' +
      icon("arrow-up") +
      "</button>" +
      "</div></div></div>" +
      '<div class="composer-hint">生成内容是草稿，提交前请核对。</div>' +
      "</div>"
    );
  }

  function messageHTML(msg, index) {
    const copyAction =
      typeof index === "number"
        ? '<div class="msg-actions"><button class="text-btn" type="button" data-act="copy-msg" data-index="' +
          index +
          '">' +
          icon("copy") +
          " 复制</button></div>"
        : "";
    if (msg.role === "user") {
      return (
        '<div class="msg msg-user">' +
        '<div class="msg-col"><div class="msg-bubble">' +
        esc(msg.content) +
        '</div><div class="msg-time">' +
        esc(S.fmtTime(msg.ts || msg.created_at)) +
        "</div>" +
        copyAction +
        "</div>" +
        '<div class="msg-avatar">' +
        icon("user") +
        "</div></div>"
      );
    }
    if (msg.error) {
      return (
        '<div class="msg msg-assistant">' +
        '<div class="msg-avatar">' +
        icon("sparkles") +
        "</div>" +
        '<div class="msg-col"><div class="msg-error">' +
        icon("alert") +
        '<div class="msg-error-body">' +
        esc(S.clean(msg.content)) +
        '<div class="msg-error-actions">' +
        '<button class="btn btn-sm btn-ghost" data-act="retry-last">重试</button>' +
        '<button class="btn btn-sm btn-primary" data-act="open-settings">检查模型配置</button>' +
        "</div></div></div></div></div>"
      );
    }
    return (
      '<div class="msg msg-assistant">' +
      '<div class="msg-avatar">' +
      icon("sparkles") +
      "</div>" +
      '<div class="msg-col"><div class="msg-bubble">' +
      S.md(msg.content) +
      "</div>" +
      (msg.tool_calls && msg.tool_calls.length ? toolGroupHTML(msg.tool_calls) : "") +
      '<div class="msg-time">' +
      esc(S.fmtTime(msg.ts)) +
      "</div>" +
      copyAction +
      "</div></div>"
    );
  }

  const WRITE_TOOLS = [
    "save_section",
    "export_docx",
    "save_diagram",
    "generate_image",
    "save_project_fact",
    "propose_diagram",
  ];

  function hasWriteTools(names) {
    return (names || []).some(function (name) {
      return WRITE_TOOLS.indexOf(name) >= 0;
    });
  }

  function toolGroupHTML(names) {
    const chips = names
      .map(function (name) {
        return (
          '<span class="tool-chip">' +
          icon("command") +
          esc(TOOL_LABELS[name] || String(name).replace(/_/g, " ")) +
          "</span>"
        );
      })
      .join("");
    return (
      '<div class="tool-group">' +
      '<button class="tool-group-head" type="button" data-act="toggle-tools">' +
      icon("command") +
      "<span>使用 " +
      names.length +
      " 个工具</span>" +
      icon("chevron-down", "chevron") +
      "</button>" +
      '<div class="tool-group-body">' +
      chips +
      "</div></div>"
    );
  }

  function scrollChatToBottom() {
    const scroller = document.getElementById("chat-scroll");
    if (scroller) scroller.scrollTop = scroller.scrollHeight;
  }

  /* ------------------------------ 文档预览 ------------------------------ */
  const docPanelState = { tab: "outline", selectedSection: "", selectedFile: "", previewText: "", previewTitle: "" };

  function resetDocPanelState() {
    docPanelState.tab = "outline";
    docPanelState.selectedSection = "";
    docPanelState.selectedFile = "";
    docPanelState.previewText = "";
    docPanelState.previewTitle = "";
  }

  function docPanel() {
    return (
      '<aside class="doc-panel" id="doc-panel">' +
      '<div class="doc-panel-head">' +
      icon("panel-right") +
      '<span class="doc-panel-title">文档预览</span>' +
      '<button class="icon-btn" type="button" data-act="toggle-docs" aria-label="收起文档预览">' +
      icon("x") +
      "</button></div>" +
      '<div class="doc-panel-tabs">' +
      '<button class="doc-panel-tab active" data-act="doc-panel-tab" data-tab="outline">大纲</button>' +
      '<button class="doc-panel-tab" data-act="doc-panel-tab" data-tab="files">文件</button>' +
      "</div>" +
      '<div class="doc-panel-body" id="doc-panel-body"></div>' +
      "</aside>"
    );
  }

  function outlineLevel(item) {
    const title = String(item.title || item.id || "");
    const match = title.match(/^(\d+(?:\.\d+)*)/);
    if (match) return match[1].split(".").length;
    return 1;
  }

  function outlinePanelHTML(project) {
    const outline = project.outline || [];
    const sections = project.sections || {};
    const items = outline
      .map(function (item, index) {
        const id = item.id || "";
        const level = outlineLevel(item);
        const hasContent = String(sections[id] || "").trim();
        const active = docPanelState.selectedSection === id ? " active" : "";
        return (
          '<button class="outline-tree-item' +
          (level > 1 ? " nested" : " top-level") +
          active +
          '" type="button" data-act="outline-item" data-id="' +
          esc(id) +
          '">' +
          '<span class="num">' +
          String(index + 1).padStart(2, "0") +
          "</span>" +
          "<span>" +
          esc(S.clean(item.title || id || "未命名章节")) +
          "</span>" +
          (hasContent ? '<span class="badge badge-ok">已写</span>' : '<span class="badge">待写</span>') +
          "</button>"
        );
      })
      .join("");
    return (
      '<div class="doc-panel-tools">' +
      '<button class="text-btn" type="button" data-act="fold-outline">' +
      icon("minus") +
      "折叠全部层级</button>" +
      '<span class="spacer"></span>' +
      '<button class="text-btn" type="button" data-act="generate-outline">' +
      icon("sparkles") +
      "生成大纲</button></div>" +
      (outline.length
        ? '<div class="outline-tree" id="outline-tree">' + items + "</div>"
        : '<div class="doc-preview-empty">' +
          icon("list") +
          "还没有大纲。生成目录后，这里的章节可以逐条预览。</div>") +
      '<div id="paper-slot" style="margin-top:10px">' + paperHTML(project) + "</div>"
    );
  }

  function filesPanelHTML(project) {
    const docs = project.documents || [];
    const rows = docs
      .map(function (doc) {
        const active = docPanelState.selectedFile === doc.id ? " active" : "";
        return (
          '<button class="doc-list-item' +
          active +
          '" type="button" data-act="doc-preview" data-doc="' +
          esc(doc.id) +
          '">' +
          icon("file") +
          "<span>" +
          esc(S.clean(doc.original_name)) +
          "</span></button>"
        );
      })
      .join("");
    return (
      '<div class="doc-panel-tools">' +
      '<button class="text-btn" type="button" data-act="doc-panel-upload">' +
      icon("plus") +
      "添加材料</button>" +
      '<span class="spacer"></span></div>' +
      (docs.length
        ? '<div class="doc-panel-files">' + rows + "</div>"
        : '<div class="doc-preview-empty">' +
          icon("file") +
          "还没有文件。上传学校模板或已有材料后，可以在这里预览。</div>") +
      '<div id="paper-slot" style="margin-top:10px">' + filePaperHTML(project) + "</div>"
    );
  }

  function paperHTML(project) {
    let title = docPanelState.previewTitle;
    let content = docPanelState.previewText;
    if (!content && docPanelState.selectedSection) {
      if (!title) title = docPanelState.selectedSection;
      content = (project.sections || {})[docPanelState.selectedSection] || "";
    }
    if (!content) {
      return (
        '<div class="doc-preview-empty">' +
        icon("file") +
        "选择一章查看草稿，或等 Agent 写入内容后在这里预览。</div>"
      );
    }
    return (
      '<div class="doc-paper"><div class="paper">' +
      '<div class="paper-head">' +
      '<div class="paper-eyebrow">' +
      esc(skillLabel(project)) +
      " · 草稿</div>" +
      '<h2 class="paper-title">' +
      esc(S.clean(title || project.title || "申报书草稿")) +
      "</h2></div>" +
      '<div class="paper-rule"></div>' +
      '<div class="paper-body">' +
      S.md(content) +
      "</div></div></div>"
    );
  }

  function paperTextHTML(text) {
    const lines = String(text || "")
      .split("\n")
      .map(function (line) {
        return line.replace(/^\[[^\]]{1,14}\]\s*/, "").trim();
      })
      .filter(Boolean);
    if (!lines.length) return '<p class="muted">没有可预览的文本。</p>';
    return lines
      .map(function (line) {
        return "<p>" + esc(line) + "</p>";
      })
      .join("");
  }

  function filePaperHTML(project) {
    const doc = (project.documents || []).find(function (d) {
      return d.id === docPanelState.selectedFile;
    });
    if (!doc) {
      return (
        '<div class="doc-preview-empty">' +
        icon("file") +
        "选择文件后在这里预览，支持 PDF 与图片；Word 与文本会显示提取后的内容。</div>"
      );
    }
    const type = String(doc.content_type || "").toLowerCase();
    const name = String(doc.original_name || "").toLowerCase();
    if (type.indexOf("pdf") >= 0 || name.endsWith(".pdf")) {
      return (
        '<div class="doc-paper"><div class="doc-paper-loading" id="pdf-loading">正在载入 PDF…</div>' +
        '<iframe class="doc-paper-frame" id="pdf-frame" style="display:none" title="' +
        esc(S.clean(doc.original_name)) +
        '"></iframe></div>'
      );
    }
    if (type.indexOf("image") >= 0 || /\.(png|jpe?g|webp)$/.test(name)) {
      return (
        '<div class="doc-paper" style="padding:10px"><img src="/api/documents/' +
        esc(doc.id) +
        '/file" alt="' +
        esc(S.clean(doc.original_name)) +
        '" style="width:100%;border-radius:6px;display:block"></div>'
      );
    }
    const text = doc.extracted_text || "";
    return (
      '<div class="doc-paper"><div class="paper">' +
      '<div class="paper-head"><div class="paper-eyebrow">' +
      (doc.kind === "template" ? "学校模板" : "项目材料") +
      "</div><h2 class=\"paper-title\">" +
      esc(S.clean(doc.original_name)) +
      "</h2></div>" +
      '<div class="paper-rule"></div>' +
      '<div class="paper-body">' +
      (text ? paperTextHTML(text) : '<p class="muted">这份文件还没有可预览的文本，可以点击「打开原文件」查看。</p>') +
      "</div></div></div>"
    );
  }

  async function generateOutlineInPanel(root, project) {
    S.toast("正在生成大纲…");
    try {
      const result = await S.api("/api/projects/" + project.id + "/outline/generate", {
        method: "POST",
        body: { llm_config: modelPayload() },
        timeout: 600000,
      });
      if (result && result.outline && result.outline.length) {
        project.outline = result.outline;
        await confirmOutline(project, result.outline);
        renderDocPanelBody(root, project, "outline");
        S.toast(result.warning ? "已生成可编辑的通用目录" : "大纲已生成", "success");
      } else {
        S.toast("大纲生成结果为空", "error");
      }
    } catch (err) {
      showModelError(err, "生成大纲");
    }
  }

  function renderDocPanelBody(root, project, tab) {
    const body = root.querySelector("#doc-panel-body");
    if (!body) return;
    docPanelState.tab = tab || "outline";
    root.querySelectorAll("[data-act='doc-panel-tab']").forEach(function (btn) {
      btn.classList.toggle("active", btn.getAttribute("data-tab") === docPanelState.tab);
    });
    body.innerHTML = docPanelState.tab === "files" ? filesPanelHTML(project) : outlinePanelHTML(project);
    if (docPanelState.tab === "files") {
      const selected = (project.documents || []).find(function (d) {
        return d.id === docPanelState.selectedFile;
      });
      if (selected) loadPdfPreview(root, selected);
    }
  }

  let pdfObjectUrl = null;

  function loadPdfPreview(root, doc) {
    const frame = root.querySelector("#pdf-frame");
    if (!frame) return;
    const loading = root.querySelector("#pdf-loading");
    const type = String(doc.content_type || "").toLowerCase();
    const name = String(doc.original_name || "").toLowerCase();
    const isPdf = type.indexOf("pdf") >= 0 || name.endsWith(".pdf");
    if (!isPdf) return;
    if (pdfObjectUrl) {
      URL.revokeObjectURL(pdfObjectUrl);
      pdfObjectUrl = null;
    }
    fetch("/api/documents/" + doc.id + "/file")
      .then(function (response) {
        if (!response.ok) throw new Error("load failed");
        return response.blob();
      })
      .then(function (blob) {
        pdfObjectUrl = URL.createObjectURL(new Blob([blob], { type: "application/pdf" }));
        frame.src = pdfObjectUrl;
        frame.style.display = "block";
        if (loading) loading.remove();
      })
      .catch(function () {
        if (loading) loading.textContent = "PDF 预览加载失败，可以下载原文件查看。";
      });
  }

  function ensureDocPanel(root, project) {
    let panel = root.querySelector(".doc-panel");
    if (!panel) {
      const chatViewEl = root.classList.contains("chat-view") ? root : root.querySelector(".chat-view");
      if (!chatViewEl) return null;
      chatViewEl.insertAdjacentHTML("beforeend", docPanel(project));
      panel = chatViewEl.querySelector(".doc-panel");
      renderDocPanelBody(root, project, "outline");
    }
    return panel;
  }

  function bindChatEvents(container, project, thread, docOpen) {
    chatCtx = { container: container, project: project, thread: thread, docOpen: docOpen };
    resetDocPanelState();
    if (docOpen) renderDocPanelBody(container, project, "outline");

    const input = container.querySelector("#chat-input");
    const sendBtn = container.querySelector('[data-act="send"]');
    let sending = false;

    function syncSend() {
      if (!sendBtn || sending) return;
      sendBtn.disabled = !(input && input.value.trim());
    }

    function setBusy(busy) {
      sending = busy;
      if (input) input.disabled = busy;
      if (!sendBtn) return;
      sendBtn.disabled = busy || !(input && input.value.trim());
      sendBtn.innerHTML = busy ? '<span class="spinner"></span>' : icon("arrow-up");
    }

    const scroller = container.querySelector("#chat-scroll");
    const jumpBtn = container.querySelector(".scroll-bottom");
    function updateJump() {
      if (!scroller || !jumpBtn) return;
      const gap = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight;
      jumpBtn.classList.toggle("hidden", gap < 240);
    }
    if (scroller) {
      scroller.addEventListener("scroll", updateJump);
      updateJump();
    }
    if (input) {
      if (window.innerWidth > 900) {
        setTimeout(function () {
          try { input.focus({ preventScroll: true }); } catch (e) { input.focus(); }
        }, 120);
      }
      input.addEventListener("input", function () {
        syncSend();
        input.style.height = "auto";
        input.style.height = Math.min(220, input.scrollHeight) + "px";
      });
      input.addEventListener("keydown", function (e) {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          submitChat();
        }
      });
    }

    S.on(container, "keydown", '[role="button"][data-act]', function (event, target) {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        target.click();
      }
    });
    S.on(container, "click", "[data-act]", function (event, target) {
      const act = target.getAttribute("data-act");
      if (act === "back-project") {
        window.App.navigate("#/p/" + project.id + "/conversations");
        return;
      }
      if (act === "open-sidebar") {
        window.App.toggleSidebar(true);
        return;
      }
      if (act === "suggest") {
        if (input) {
          input.value = target.getAttribute("data-text") || "";
          syncSend();
          input.focus();
        }
        return;
      }
      if (act === "send") {
        submitChat();
        return;
      }
      if (act === "toggle-docs") {
        toggleDocPanel(container, project);
        return;
      }
      if (act === "chat-settings") {
        openProjectSettings(project);
        return;
      }
      if (act === "open-settings") {
        window.App.openSettings("model");
        return;
      }
      if (act === "attach") {
        pickFiles("source", project, container, "files");
        return;
      }
      if (act === "chat-menu") {
        openChatMenu(project);
        return;
      }
      if (act === "scroll-bottom") {
        if (scroller) scroller.scrollTo({ top: scroller.scrollHeight, behavior: "smooth" });
        return;
      }
      if (act === "copy-msg") {
        const index = Number(target.getAttribute("data-index"));
        const item = (chatCtx.thread.messages || [])[index];
        if (!item) return;
        S.copyText(S.clean(item.content))
          .then(function () { S.toast("已复制到剪贴板", "success"); })
          .catch(function () { S.toast("复制失败，请手动选择", "error"); });
        return;
      }
      if (act === "toggle-tools") {
        const group = target.closest(".tool-group");
        if (group) group.classList.toggle("open");
        return;
      }
      if (act === "retry-last") {
        if (sending) return;
        const lastUser = (chatCtx.thread.messages || [])
          .slice()
          .reverse()
          .find(function (m) {
            return m.role === "user";
          });
        if (lastUser) submitChat(lastUser.content);
        return;
      }
      if (act === "doc-panel-tab") {
        renderDocPanelBody(container, project, target.getAttribute("data-tab"));
        return;
      }
      if (act === "outline-item") {
        const sectionId = target.getAttribute("data-id");
        const sectionItem = (project.outline || []).find(function (item) {
          return (item.id || "") === sectionId;
        });
        docPanelState.selectedSection = sectionId;
        docPanelState.previewText = "";
        docPanelState.previewTitle = sectionItem ? S.clean(sectionItem.title || sectionId) : sectionId;
        renderDocPanelBody(container, project, "outline");
        return;
      }
      if (act === "fold-outline") {
        const tree = container.querySelector("#outline-tree");
        if (tree) tree.classList.toggle("is-folded");
        return;
      }
      if (act === "generate-outline") {
        generateOutlineInPanel(container, project);
        return;
      }
      if (act === "doc-preview") {
        docPanelState.selectedFile = target.getAttribute("data-doc");
        renderDocPanelBody(container, project, "files");
        return;
      }
      if (act === "doc-panel-upload") {
        pickFiles("source", project, container, "files");
        return;
      }
    });

    async function submitChat(presetText) {
      if (!chatCtx || sending) return;
      const box = container.querySelector("#chat-input");
      const text = (presetText || (box ? box.value : "")).trim();
      if (!text) return;
      const threadRef = chatCtx.thread;
      const userMsg = { role: "user", content: text, ts: Date.now() };
      threadRef.messages.push(userMsg);
      if (threadRef.messages.filter(function (m) { return m.role === "user"; }).length === 1) {
        threadRef.title = text.slice(0, 24);
        const titleEl = container.querySelector("#chat-title");
        if (titleEl) titleEl.textContent = threadRef.title;
      }
      threads.touch(threadRef);
      if (box) {
        box.value = "";
        box.style.height = "auto";
        box.dispatchEvent(new Event("input"));
      }
      const threadEl = container.querySelector("#chat-thread");
      const emptyEl = threadEl ? threadEl.querySelector(".chat-empty") : null;
      if (emptyEl) threadEl.innerHTML = "";
      const nearBottom =
        !scroller || scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 160;
      if (threadEl) threadEl.insertAdjacentHTML("beforeend", messageHTML(userMsg, threadRef.messages.length - 1));
      appendTyping(container);
      if (nearBottom) scrollChatToBottom();
      updateJump();
      setBusy(true);
      try {
        await respond(project, threadRef, text);
      } finally {
        setBusy(false);
        updateJump();
      }
    }

    async function respond(projectRef, threadRef, text) {
      const model = S.getModel();
      try {
        let result;
        if (model.demo) {
          await new Promise(function (resolve) {
            setTimeout(resolve, 700);
          });
          result = {
            message:
              "（演示模式）已经收到你的需求：**" +
              text.slice(0, 60) +
              "**。\n\n真实环境下，这里会按「" +
              skillLabel(projectRef) +
              "」赛道的要求继续追问信息，并在你确认事实之后逐章撰写。\n\n- 演示模式不会调用任何模型\n- 在「设置 → 模型配置」中可以切换回真实模型",
            tool_calls: ["read_skill", "get_project_state", "save_section"],
          };
        } else {
          result = await S.api("/api/projects/" + projectRef.id + "/chat", {
            method: "POST",
            body: { message: text, llm_config: modelPayload() },
            timeout: 300000,
          });
        }
        if (container.isConnected) removeTyping(container);
        const reply = {
          role: "assistant",
          content: String(result && result.message ? result.message : "（没有返回内容）").trim(),
          tool_calls: (result && result.tool_calls) || [],
          ts: Date.now(),
        };
        threadRef.messages.push(reply);
        threads.touch(threadRef);
        if (container.isConnected) {
          const stick =
            !scroller || scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 200;
          appendMessage(container, reply);
          if (stick) scrollChatToBottom();
          updateJump();
        }
        window.App.refreshShell();
        if (container.isConnected && hasWriteTools(reply.tool_calls)) {
          const panel = ensureDocPanel(container, projectRef);
          if (panel) {
            docPanelState.previewText = reply.content;
            docPanelState.previewTitle = "本轮草稿";
            docPanelState.selectedSection = "";
            renderDocPanelBody(container, projectRef, "outline");
          }
        }
      } catch (err) {
        if (container.isConnected) removeTyping(container);
        const errorMsg = {
          role: "assistant",
          error: true,
          content: err.message || "请求失败",
          status: err.status,
          ts: Date.now(),
        };
        threadRef.messages.push(errorMsg);
        threads.touch(threadRef);
        if (container.isConnected) {
          appendMessage(container, errorMsg);
          updateJump();
        }
      }
    }

    function appendMessage(root, msg) {
      const threadEl = root.querySelector("#chat-thread");
      if (!threadEl) return;
      const index = ((chatCtx.thread.messages || []).length || 1) - 1;
      threadEl.insertAdjacentHTML("beforeend", messageHTML(msg, index));
    }
  }

  function modelPayload() {
    const m = S.getModel();
    return {
      provider: m.provider || "preset",
      model: m.model || "",
      base_url: m.base_url || "",
      api_key: m.api_key || "",
      image_model: m.image_model || "",
      image_base_url: m.image_base_url || "",
      image_api_key: m.image_api_key || "",
      image_reuse_text: false,
    };
  }

  function appendTyping(root) {
    const threadEl = root.querySelector("#chat-thread");
    if (!threadEl) return;
    threadEl.insertAdjacentHTML(
      "beforeend",
      '<div class="msg msg-assistant" id="typing-msg"><div class="msg-avatar">' +
        icon("sparkles") +
        '</div><div class="msg-col"><div class="typing"><i></i><i></i><i></i></div></div></div>'
    );
  }

  function removeTyping(root) {
    const el = root.querySelector("#typing-msg");
    if (el) el.remove();
  }

  function toggleDocPanel(container, project) {
    const viewEl =
      container && container.classList && container.classList.contains("chat-view")
        ? container
        : container
        ? container.querySelector(".chat-view")
        : null;
    if (!viewEl) return;
    const existing = viewEl.querySelector(".doc-panel");
    if (existing) {
      existing.remove();
      return;
    }
    viewEl.insertAdjacentHTML("beforeend", docPanel(project));
    renderDocPanelBody(container, project, "outline");
  }

  /* =====================================================================
   * 导出
   * =================================================================== */
  window.S.views = {
    project: projectView,
    chat: chatView,
  };
})();

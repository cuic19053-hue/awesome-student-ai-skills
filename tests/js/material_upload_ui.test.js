const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { resolve } = require("node:path");
const { test } = require("node:test");
const vm = require("node:vm");

class Element {
  constructor(tag = "div") {
    this.tagName = tag;
    this.children = [];
    this.dataset = {};
    this.attributes = {};
    this.listeners = {};
    this.style = {};
    this.open = false;
    this.textContent = "";
    const classes = new Set();
    this.classList = {
      add: (...names) => names.forEach((name) => classes.add(name)),
      remove: (...names) => names.forEach((name) => classes.delete(name)),
      contains: (name) => classes.has(name),
      toggle(name, force) {
        const active = force === undefined ? !classes.has(name) : force;
        if (active) classes.add(name);
        else classes.delete(name);
      },
    };
  }
  append(...children) { this.children.push(...children); }
  appendChild(child) { this.append(child); }
  removeChild(child) { this.children = this.children.filter(c => c !== child); }
  click() { this.clicked = true; return this.listeners.click?.(); }
  replaceChildren(...children) { this.children = children; this.textContent = ""; }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  closest() { return null; }
  remove() { this.removed = true; }
  showModal() { this.open = true; }
  close() { this.open = false; this.listeners.close?.(); }
}

function harness(sharedSession = new Map()) {
  const elements = new Map();
  const revoked = [];
  const created = [];
  const requests = [];
  const timers = new Map();
  let nextTimer = 1;
  let draftAreas = [];
  let factFields = [];
  const document = {
    querySelector(selector) {
      if (!elements.has(selector)) elements.set(selector, new Element());
      return elements.get(selector);
    },
    querySelectorAll: (selector) => selector === ".draft-section textarea" ? draftAreas : selector === "[data-fact]" ? factFields : [],
    createElement: (tag) => new Element(tag),
    addEventListener() {},
    body: new Element("body"),
  };
  const storage = new Map();
  const session = sharedSession;
  const context = vm.createContext({
    document,
    window: { location: { origin: "https://workbench.example.test" } },
    localStorage: { getItem: (k) => storage.get(k) || null, setItem: (k,v) => storage.set(k,v), removeItem: (k) => storage.delete(k) },
    sessionStorage: { getItem: (k) => session.get(k) || null, setItem: (k,v) => session.set(k,v), removeItem: (k) => session.delete(k) },
    Headers,
    AbortController,
    Blob,
    TextEncoder,
    TextDecoder,
    URL: {
      createObjectURL(blob) {
        created.push(blob);
        return `blob:preview-${created.length}`;
      },
      revokeObjectURL: (url) => revoked.push(url),
    },
    fetch: async (url, options) => {
      requests.push({ url, options });
      return { ok: true, blob: async () => new Blob(["test original"]) };
    },
    setTimeout: () => 0,
    clearTimeout() {},
    setInterval(callback) { const id = nextTimer++; timers.set(id, callback); return id; },
    clearInterval(id) { timers.delete(id); },
  });
  const file = resolve(__dirname, "../../server/static/app.js");
  const source = readFileSync(file, "utf8").replace(/\}\)\(\);\s*$/, `
    globalThis.ui = {
      state, renderUploadResult, renderDocuments, previewDocument,
      clearDocumentPreview, fetchDocumentBlob, uploadFiles,
      uploadFilesToCloud, cloudUploadIntent, uploadResumable, setUploadKind, oversizedUploadError,
      renderPrivacyNotice, showModelStatus, updateTemplateQuickActions,
      syncAuthControls, initializeCloudAuth, submitAuthForm,
      readPublicCache, writePublicCache, sameOriginAuthFetch, storeLlmConfig, loadCloudModelConfig, saveSelectedLlmConfig,
      sendChat, syncChatControls, loadProject, deleteCurrentProject, startGeneralChat, selectConversationSkill, configureSkillWorkspace, renderFacts, saveFacts, renderSections, recommendOutline, saveOutline, validate, restoreInterruptedChatMessage, updateRecoveredChatInput, startBatchGeneration, cancelBatchGeneration,
      exportDoc, fetchExportBlob, flushDraftEdits, showChatDrafts, clearExportArtifacts,
      setApi(fn) { api = fn; },
      setLoadProject(fn) { loadProject = fn; },
      setChatRefresh(fn) { refreshProjects = fn; loadUserBalance = fn; },
    };
  })();`);
  vm.runInContext(source, context, { filename: file });
  return {
    ui: context.ui, context, requests, revoked, created, timers, session,
    element: (selector) => document.querySelector(selector),
    setDraftAreas: (areas) => { draftAreas = areas; },
    setFactFields: (fields) => { factFields = fields; },
  };
}

const doc = {
  id: "a".repeat(32),
  original_name: "学校材料.pdf",
  extracted_text: "待学生核对的材料文字",
  extraction_status: "ready",
  kind: "source",
  confirmed: false,
};

test("recommended outline previews without a model and retains saved chapters", async () => {
  const h = harness();
  h.ui.state.project = { id: "project-one", outline: [{ id: "old-summary", title: "项目摘要" },
    { id: "custom", title: "学生自写章节" }], sections: { "old-summary": "原有摘要", custom: "学生原文" } };
  const calls = [];
  h.ui.setApi(async (url, options) => {
    calls.push({ url, options });
    return { outline: [{ id: "abstract", title: "项目摘要" }, { id: "background", title: "选题背景" }], warning: "请核对学校模板。" };
  });
  await h.ui.recommendOutline();
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/projects/project-one/outline/recommend");
  assert.equal(calls[0].options, undefined);
  assert.deepEqual(Array.from(h.ui.state.outline, item => item.id), ["old-summary", "background", "custom"]);
  assert.equal(h.ui.state.project.outline.length, 2, "the saved outline is unchanged until confirmation");
  assert.match(h.element("#outlineWarning").textContent, /已保留含正文的原章节/);
});

test("a recommendation arriving after a project switch cannot replace the new outline", async () => {
  const h = harness();
  h.ui.state.project = { id: "old", outline: [], sections: {} };
  let finish;
  h.ui.setApi(() => new Promise(resolve => { finish = resolve; }));
  const pending = h.ui.recommendOutline();
  await Promise.resolve();
  h.ui.state.project = { id: "new", outline: [], sections: {} };
  h.ui.state.outline = [{ id: "new-section", title: "新项目章节" }];
  finish({ outline: [{ id: "old-section", title: "旧项目推荐" }] });
  await pending;
  assert.equal(h.ui.state.outline[0].id, "new-section");
});

test("confirming an outline updates the current project for subsequent edits", async () => {
  const h = harness();
  h.ui.state.project = { id: "project-one", outline: [], sections: {}, state: {} };
  h.ui.state.outline = [{ id: "abstract", title: "项目摘要" }];
  const calls = [];
  h.ui.setApi(async (url, options) => { calls.push({ url, options }); return { outline: [{ id: "abstract", title: "项目摘要" }] }; });
  await h.ui.saveOutline();
  assert.equal(calls[0].url, "/api/projects/project-one/outline");
  assert.equal(h.ui.state.project.outline[0].id, "abstract");
  assert.equal(h.ui.state.project.sections.abstract, "");
  assert.equal(h.ui.state.project.state.outline_confirmed, true);
});

test("student validation displays the limited scope of the check", async () => {
  const h = harness();
  h.ui.state.project = { id: "project-one" };
  h.ui.setApi(async () => ({ passed: true, validation_scope: "通用内容检查，具体以学校通知和模板为准。", photo_notice: "" }));
  await h.ui.validate();
  const box = h.element("#validationResult");
  assert.ok(box.children.some(child => child.textContent.includes("具体以学校通知和模板为准")));
});

test("national scholarship workspace offers relevant prompts and hides innovation review", () => {
  const h = harness();
  const project = { state: { skill_id: "national-scholarship", skill_category: "scholarship", skill_name: "国家奖学金" } };
  h.ui.configureSkillWorkspace(project);
  const prompts = h.element("#chatTools").children.map(child => child.textContent);
  assert.ok(prompts.some(text => text.includes("学业")));
  assert.ok(prompts.some(text => text.includes("起草申请书")));
  assert.ok(prompts.every(text => !text.includes("家庭经济") && !text.includes("勤工助学")));
  assert.equal(h.element("#innovationReviewRow").classList.contains("hidden"), true);
  assert.ok(!h.element("#exportHint").textContent.includes("实验图"));
  h.ui.state.project = project;
  h.ui.renderFacts();
  const factLabels = h.element("#factsSummary").children.map(child => child.children[0]?.textContent);
  assert.ok(factLabels.includes("所在学院"));
  assert.ok(!factLabels.includes("预算") && !factLabels.includes("负责人照片"));
  h.ui.configureSkillWorkspace({ state: { skill_id: "innovation-research", skill_category: "research" } });
  assert.equal(h.element("#innovationReviewRow").classList.contains("hidden"), false);
});

test("national scholarship keeps personal layout before skill metadata is available", () => {
  const h = harness();
  const project = { state: { skill_id: "national-scholarship" } };
  h.ui.state.project = project;
  h.ui.renderFacts();
  const labels = h.element("#factsSummary").children.map(child => child.children[0]?.textContent);
  assert.ok(labels.includes("所在学院") && !labels.includes("预算"));
});

test("personal award workspaces use student-specific fields and guidance", () => {
  const h = harness();
  for (const [id, category] of [["outstanding-student", "honor"], ["grant-application", "scholarship"], ["university-scholarship", "scholarship"], ["major-transfer", "other"], ["graduate-recommendation", "other"]]) {
    const project = { state: { skill_id: id, skill_category: category } };
    h.ui.state.project = project;
    h.ui.configureSkillWorkspace(project);
    h.ui.renderFacts();
    const labels = h.element("#factsSummary").children.map(child => child.children[0]?.textContent);
    assert.ok(labels.includes("所在学院"));
    assert.ok(!labels.includes("预算") && !labels.includes("项目名称") && !labels.includes("负责人照片"));
    assert.equal(h.element("#panel-materials .panel-heading h2").textContent, "个人参考材料与知识库");
    assert.equal(h.element("#sources-panel .panel-heading h2").textContent, "学校通知与申报依据");
    const prompts = h.element("#chatTools").children.map(child => child.textContent);
    assert.equal(prompts.some(text => text.includes("家庭")), id === "grant-application");
    if (id === "major-transfer") assert.ok(prompts.some(text => text.includes("转专业")));
    if (id === "graduate-recommendation") assert.ok(prompts.some(text => text.includes("个人陈述")));
  }
  h.ui.configureSkillWorkspace({ state: { skill_id: "innovation-research", skill_category: "research" } });
  assert.equal(h.element("#panel-materials .panel-heading h2").textContent, "项目参考材料与知识库");
  assert.equal(h.element("#sources-panel .panel-heading h2").textContent, "学术文献检索与官方立项依据");
});

test("switching from a research project clears hidden editor fields before saving a student application", async () => {
  const h = harness();
  const budget = h.element('[data-fact="budget"]');
  const budgetParent = new Element("label");
  budget.dataset.fact = "budget";
  budget.closest = () => budgetParent;
  const college = h.element('[data-fact="college"]');
  college.dataset.fact = "college";
  college.closest = () => new Element("label");
  h.setFactFields([budget, college]);
  h.ui.state.project = { id: "research", state: { skill_id: "innovation-research", skill_category: "research", confirmed_facts: { budget: "50000 元", college: "原学院" } } };
  h.ui.renderFacts();
  assert.equal(budget.value, "50000 元");
  h.ui.state.project = { id: "award", state: { skill_id: "outstanding-student", skill_category: "honor", confirmed_facts: { college: "新学院" } } };
  h.ui.renderFacts();
  assert.equal(budget.value, "");
  assert.equal(college.value, "新学院");
  assert.equal(budgetParent.classList.contains("hidden"), true);
  const requests = [];
  h.ui.setApi(async (url, options) => { requests.push({ url, options }); return {}; });
  h.ui.setLoadProject(async () => {});
  await h.ui.saveFacts();
  const payload = JSON.parse(requests[0].options.body);
  assert.equal(payload.budget, undefined);
  assert.equal(payload.college, "新学院");
  h.ui.state.project.state.confirmed_facts.budget = "200 元";
  h.ui.renderFacts();
  assert.equal(budgetParent.classList.contains("hidden"), false, "previously saved data remains editable");
  assert.equal(budget.value, "200 元");
});

test("chat-first entry creates a conversation without requiring a Skill", async () => {
  const h = harness();
  const requests = [];
  let loaded = "";
  h.ui.setApi(async (url, options) => {
    requests.push({ url, options });
    return { id: "conversation-one", state: { skill_id: "" } };
  });
  h.ui.setChatRefresh(async () => {});
  h.ui.setLoadProject(async (id) => { loaded = id; });
  h.element("#chatInput").focus = () => {};
  await h.ui.startGeneralChat();
  assert.equal(requests.length, 1);
  assert.equal(requests[0].url, "/api/projects/conversation");
  assert.equal(requests[0].options.method, "POST");
  assert.equal(loaded, "conversation-one");
  assert.equal(h.element("#newChatBtn").disabled, false);
});

test("user can select a Skill for an unrouted conversation", async () => {
  const h = harness();
  h.ui.state.project = { id: "conversation-one", state: { skill_id: "" } };
  h.element("#conversationSkillSelect").value = "national-scholarship";
  let loaded = "";
  const requests = [];
  h.ui.setApi(async (url, options) => { requests.push({ url, options }); return {}; });
  h.ui.setLoadProject(async id => { loaded = id; });
  await h.ui.selectConversationSkill();
  assert.equal(requests[0].url, "/api/projects/conversation-one/skill");
  assert.equal(JSON.parse(requests[0].options.body).skill_id, "national-scholarship");
  assert.equal(loaded, "conversation-one");
  assert.equal(h.element("#conversationSkillApply").disabled, false);
});

function exportingProject(h) {
  h.ui.state.project = { id: "a".repeat(32), material_revision: 2,
    outline: [{ id: "purpose", title: "项目目的" }], sections: { purpose: "已保存正文" },
    state: { skill_name: "测试材料" } };
  h.ui.state.authSession = { access_token: "fake-session-jwt" };
}

test("batch generation stops on project switch without writing into another project", async () => {
  const h = harness(); exportingProject(h);
  const firstProject = h.ui.state.project;
  h.ui.state.outline = [{ id: "one", title: "第一章" }, { id: "two", title: "第二章" }];
  const calls = [];
  let finish;
  h.ui.setApi((url, options) => { calls.push({ url, options }); return new Promise(resolve => { finish = resolve; }); });
  const running = h.ui.startBatchGeneration();
  h.ui.state.project = { id: "second-project", sections: { one: "新项目正文" } };
  finish({ content: "旧项目生成结果" });
  await running;
  assert.equal(calls.length, 1);
  assert.equal(h.ui.state.project.sections.one, "新项目正文");
  assert.equal(firstProject.sections.one, undefined);
  assert.equal(h.ui.state.batchGenerating, false);
});

test("batch stops after an uncertain result rather than generating further chapters", async () => {
  const h = harness(); exportingProject(h);
  h.ui.state.outline = [{ id: "one", title: "第一章" }, { id: "two", title: "第二章" }];
  const calls = [];
  h.ui.setApi(async (url, options) => { calls.push({ url, options }); return { status: "processing", job_id: "job" }; });
  await h.ui.startBatchGeneration();
  assert.equal(calls.length, 1);
  assert.match(h.element("#batchProgressText").textContent, /后台处理/);
  assert.equal(h.ui.state.project.sections.one, undefined);
  assert.equal(h.ui.state.batchGenerating, false);
});

test("batch stops when a draft requires review", async () => {
  const h = harness(); exportingProject(h);
  h.ui.state.outline = [{ id: "one", title: "第一章" }, { id: "two", title: "第二章" }];
  const calls = [];
  h.ui.setApi(async (url, options) => { calls.push({ url, options });
    return { conflict_status: "user_edit_preserved", notice: "请核对草稿" }; });
  await h.ui.startBatchGeneration();
  assert.equal(calls.length, 1);
  assert.match(h.element("#batchProgressText").textContent, /请核对草稿.*停止后续章节/);
});

test("batch cancellation does not send subsequent model requests", async () => {
  const h = harness(); exportingProject(h);
  h.ui.state.outline = [{ id: "one", title: "第一章" }, { id: "two", title: "第二章" }];
  const calls = [];
  let finish;
  h.ui.setApi((url, options) => { calls.push({ url, options }); return new Promise(resolve => { finish = resolve; }); });
  const running = h.ui.startBatchGeneration();
  h.ui.cancelBatchGeneration();
  finish({ content: "后台当前章可能已保存" });
  await running;
  assert.equal(calls.length, 1);
  assert.match(h.element("#batchProgressText").textContent, /停止后续章节/);
});

test("batch preserves a student's edit made while a chapter is generating", async () => {
  const h = harness(); exportingProject(h);
  h.ui.state.outline = [{ id: "purpose", title: "第一章" }, { id: "two", title: "第二章" }];
  const area = new Element("textarea"); area.value = "已保存正文";
  area.closest = () => ({ id: "draft-sec-purpose" });
  h.setDraftAreas([area]);
  const calls = []; let finish;
  h.ui.setApi((url, options) => { calls.push({ url, options }); return new Promise(resolve => { finish = resolve; }); });
  const running = h.ui.startBatchGeneration();
  area.value = "等待期间手写的修改";
  finish({ content: "后台已生成的正文", material_applied: true, material_revision: 5 });
  await running;
  assert.equal(calls.length, 1);
  assert.equal(area.value, "等待期间手写的修改");
  assert.equal(h.ui.state.project.sections.purpose, "后台已生成的正文");
  assert.equal(h.ui.state.project.material_revision, 5);
  assert.match(h.element("#batchProgressText").textContent, /手写编辑已保留/);
});

test("legacy export fetches private file with bearer and links only a blob", async () => {
  const h = harness(); exportingProject(h);
  const calls = [];
  const download = `/api/projects/${h.ui.state.project.id}/download`;
  h.ui.setApi(async (url, options) => {
    calls.push({ url, options });
    return url.endsWith("/chat-drafts") ? { items: [] } : { download_url: download };
  });
  await h.ui.exportDoc();
  assert.equal(calls.filter(c => c.url.endsWith("/export")).length, 1);
  assert.equal(h.requests[0].url, download);
  assert.equal(h.requests[0].options.headers.Authorization, "Bearer fake-session-jwt");
  assert.equal(h.element("#exportResult").children[1].href, "blob:preview-1");
  h.ui.clearExportArtifacts();
  assert.deepEqual(h.revoked, ["blob:preview-1"]);
});

test("sending a new instruction revokes the previous Word download link", async () => {
  const h = harness(); exportingProject(h);
  h.ui.setChatRefresh(async () => {});
  h.ui.setLoadProject(async () => {});
  h.ui.setApi(async (url) => url.endsWith("/chat-drafts") ? { items: [] }
    : url.endsWith("/chat") ? { message: "已收到" }
    : { download_url: `/api/projects/${h.ui.state.project.id}/download` });
  await h.ui.exportDoc();
  assert.equal(h.element("#exportResult").children.length, 2);
  await h.ui.sendChat(null, "这次不要写家庭收入");
  assert.deepEqual(h.revoked, ["blob:preview-1"]);
  assert.equal(h.element("#exportResult").children.length, 0);
});

test("an in-flight old export cannot download after a newer instruction", async () => {
  const h = harness(); exportingProject(h);
  h.ui.setChatRefresh(async () => {});
  h.ui.setLoadProject(async () => {});
  let finishExport;
  h.ui.setApi(async (url) => {
    if (url.endsWith("/chat-drafts")) return { items: [] };
    if (url.endsWith("/chat")) return { message: "已收到" };
    return new Promise(resolve => { finishExport = resolve; });
  });
  const exporting = h.ui.exportDoc();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(typeof finishExport, "function");
  await h.ui.sendChat(null, "这次不要写家庭收入");
  finishExport({ download_url: `/api/projects/${h.ui.state.project.id}/download` });
  await exporting;
  assert.equal(h.created.length, 0);
  assert.equal(h.requests.length, 0);
});

test("download rejects foreign destination without sending the token", async () => {
  const h = harness(); exportingProject(h);
  await assert.rejects(h.ui.fetchExportBlob("https://evil.invalid/collect", h.ui.state.project.id), /当前项目/);
  assert.equal(h.requests.length, 0);
});

test("download failure is not reported as a started download", async () => {
  const h = harness(); exportingProject(h);
  h.ui.setApi(async url => url.endsWith("/chat-drafts") ? { items: [] } : {
    download_url: `/api/projects/${h.ui.state.project.id}/download`,
  });
  h.context.fetch = async () => ({ ok: false, json: async () => ({ detail: "登录过期" }) });
  await h.ui.exportDoc();
  assert.equal(h.element("#toast").textContent, "登录过期");
  assert.equal(h.created.length, 0);
  assert.equal(h.element("#exportBtn").disabled, false);
});

test("export flushes the latest editor text with CAS before submitting", async () => {
  const h = harness(); exportingProject(h);
  const area = new Element("textarea"); area.value = "最新手写正文";
  area.closest = () => ({ id: "draft-sec-purpose" });
  h.setDraftAreas([area]);
  const calls = [];
  h.ui.setApi(async (url, options = {}) => {
    calls.push({ url, options });
    if (url.endsWith("/sections/purpose")) return { material_revision: 4 };
    if (url.endsWith("/chat-drafts")) return { items: [] };
    if (url.endsWith("/export")) return { download_url: `/api/projects/${h.ui.state.project.id}/download` };
    return { ...h.ui.state.project, material_revision: 3 };
  });
  await h.ui.exportDoc();
  const put = calls.find(c => c.options.method === "PUT");
  assert.equal(JSON.parse(put.options.body).content, "最新手写正文");
  assert.equal(JSON.parse(put.options.body).base_content, "已保存正文");
  assert.equal(JSON.parse(put.options.body).expected_revision, 3);
  assert.ok(calls.indexOf(put) < calls.findIndex(c => c.url.endsWith("/export")));
  assert.equal(h.ui.state.project.sections.purpose, "最新手写正文");
});

test("concurrent chapter edit stops export without losing visible input", async () => {
  const h = harness(); exportingProject(h);
  const area = new Element("textarea"); area.value = "我的手写内容";
  area.closest = () => ({ id: "draft-sec-purpose" }); h.setDraftAreas([area]);
  const calls = [];
  h.ui.setApi(async url => {
    calls.push(url);
    return { ...h.ui.state.project, sections: { purpose: "另一页面的内容" } };
  });
  await h.ui.exportDoc();
  assert.equal(calls.length, 1);
  assert.equal(area.value, "我的手写内容");
  assert.match(h.element("#toast").textContent, /未覆盖/);
});

test("chat draft recovery requires explicit selection and never auto-exports", async () => {
  const h = harness(); exportingProject(h);
  const calls = [];
  const preview = { snapshot: "f".repeat(64), notice: "不扣积分", items: [{
    id: "e".repeat(64), title: "<script>不执行</script>", content: "预算为建议，不是事实",
    already_saved: false, conflict: false,
  }] };
  h.ui.setApi(async (url, options) => {
    calls.push({ url, options });
    return url.endsWith("/chat-drafts") ? preview : { notice: "已保存" };
  });
  h.ui.setLoadProject(async () => {});
  await h.ui.showChatDrafts();
  assert.equal(calls.length, 1);
  assert.equal(h.element("#chatDraftDialog").open, true);
  const row = h.element("#chatDraftItems").children[0];
  assert.equal(row.children[0].children[1].textContent, "<script>不执行</script>");
  row.children[2].value = "用户核对后的文字";
  await h.element("#confirmChatDraftsBtn").onclick();
  assert.equal(calls.length, 2);
  const body = JSON.parse(calls[1].options.body);
  assert.equal(body.items[0].content, "用户核对后的文字");
  assert.ok(calls[1].url.endsWith("/chat-drafts/confirm"));
});

test("a newer chat draft replaces existing text only when explicitly selected", async () => {
  const h = harness(); exportingProject(h);
  const calls = [];
  const preview = { snapshot: "f".repeat(64), notice: "选择草稿", items: [{
    id: "e".repeat(64), title: "申请书", content: "新版正文", already_saved: false, conflict: true,
  }] };
  h.ui.setApi(async (url, options) => {
    calls.push({ url, options });
    return url.endsWith("/chat-drafts") ? preview : { notice: "已保存" };
  });
  h.ui.setLoadProject(async () => {});
  await h.ui.showChatDrafts();
  const row = h.element("#chatDraftItems").children[0];
  const checkbox = row.children[0].children[0];
  assert.equal(checkbox.checked, false);
  assert.equal(checkbox.disabled, false);
  assert.match(row.children[1].textContent, /历史版本/);
  checkbox.checked = true;
  await h.element("#confirmChatDraftsBtn").onclick();
  assert.equal(JSON.parse(calls[1].options.body).items[0].replace_existing, true);
});

test("project drafts with unsupported claims are unchecked until the student reviews them", async () => {
  const h = harness(); exportingProject(h);
  const calls = [];
  const preview = { snapshot: "f".repeat(64), notice: "请选择", items: [{
    id: "e".repeat(64), title: "项目简介", content: "市场规模 5000 亿元",
    already_saved: false, conflict: false, requires_review: true, warnings: ["项目数据需要核对。"],
  }] };
  h.ui.setApi(async (url, options) => {
    calls.push({ url, options });
    return url.endsWith("/chat-drafts") ? preview : { notice: "已保存" };
  });
  h.ui.setLoadProject(async () => {});
  await h.ui.showChatDrafts();
  const row = h.element("#chatDraftItems").children[0];
  const checkbox = row.children[0].children[0];
  assert.equal(checkbox.checked, false);
  assert.match(row.children[1].textContent, /核对/);
  await h.element("#confirmChatDraftsBtn").onclick();
  assert.equal(calls.length, 1);
  row.children[2].value = "市场规模待补充。";
  checkbox.checked = true;
  await h.element("#confirmChatDraftsBtn").onclick();
  assert.equal(JSON.parse(calls[1].options.body).items[0].content, "市场规模待补充。");
});

test("section history can be reviewed and placed into the editor without saving automatically", async () => {
  const h = harness(); exportingProject(h);
  h.ui.state.project.sections = { purpose: "当前正文" };
  h.ui.state.outline = [{ id: "purpose", title: "申请书" }];
  const calls = [];
  h.ui.setApi(async (url) => { calls.push(url); return { versions: [{ content: "先前正文" }] }; });
  h.ui.renderSections();
  const section = h.element("#draftSections").children[0];
  const historyButton = section.children[0].children[1].children[3];
  const body = section.children[1];
  body.children[3].classList.add("hidden"); // Harness does not derive classList from className.
  await historyButton.click();
  const editor = body.children[1];
  const versionsBox = body.children[3];
  assert.equal(versionsBox.children[0].children[0].textContent, "先前正文");
  versionsBox.children[0].children[1].click();
  assert.equal(editor.value, "先前正文");
  assert.equal(h.ui.state.project.sections.purpose, "当前正文");
  assert.equal(calls.length, 1);
});

test("a failed section save keeps the persisted state and the student's edit", async () => {
  const h = harness(); exportingProject(h);
  h.ui.state.project.sections = { purpose: "之前保存的正文" };
  h.ui.state.outline = [{ id: "purpose", title: "申请书" }];
  h.ui.setApi(async () => { throw new Error("网络中断"); });
  h.ui.renderSections();
  const section = h.element("#draftSections").children[0];
  const save = section.children[0].children[1].children[2];
  const editor = section.children[1].children[1];
  editor.value = "尚未保存的新正文";
  await save.click();
  assert.equal(h.ui.state.project.sections.purpose, "之前保存的正文");
  assert.equal(editor.value, "尚未保存的新正文");
});

test("section generation saves an existing unsaved edit before calling the model", async () => {
  const h = harness(); exportingProject(h);
  h.ui.state.outline = [{ id: "purpose", title: "申请书" }];
  h.ui.renderSections();
  const section = h.element("#draftSections").children[0];
  const editor = section.children[1].children[1];
  editor.value = "生成前的手写修改";
  editor.closest = () => ({ id: "draft-sec-purpose" });
  h.setDraftAreas([editor]);
  const calls = [];
  h.ui.setApi(async (url, options = {}) => {
    calls.push({ url, options });
    if (url.endsWith("/sections/purpose/generate")) return { content: "新草稿", material_applied: true, material_revision: 4 };
    if (options.method === "PUT") return { material_revision: 3 };
    return { ...h.ui.state.project, material_revision: 2 };
  });
  await section.children[0].children[1].children[1].click();
  const savedAt = calls.findIndex(call => call.options.method === "PUT");
  const generatedAt = calls.findIndex(call => call.url.endsWith("/generate"));
  assert.ok(savedAt >= 0 && savedAt < generatedAt);
  assert.equal(JSON.parse(calls[savedAt].options.body).content, "生成前的手写修改");
});

test("section generation retains edits made during the model request", async () => {
  const h = harness(); exportingProject(h);
  h.ui.state.outline = [{ id: "purpose", title: "申请书" }];
  h.ui.renderSections();
  const section = h.element("#draftSections").children[0];
  const editor = section.children[1].children[1];
  let finish; const calls = [];
  h.ui.setApi((url, options) => { calls.push({ url, options }); return new Promise(resolve => { finish = resolve; }); });
  const running = section.children[0].children[1].children[1].click();
  editor.value = "学生刚写的内容";
  finish({ content: "服务器保存的生成正文", material_applied: true, material_revision: 5 });
  await running;
  assert.equal(editor.value, "学生刚写的内容");
  assert.equal(h.ui.state.project.sections.purpose, "服务器保存的生成正文");
  assert.equal(h.ui.state.project.material_revision, 5);
  assert.equal(calls.length, 1);
  assert.match(h.element("#toast").textContent, /新编辑已保留/);
});

test("section polling that remains active ends with a visible status and never resubmits", async () => {
  const h = harness(); exportingProject(h);
  h.context.setTimeout = (fn, delay) => { if (delay < 15000) fn(); return 1; };
  h.ui.state.outline = [{ id: "purpose", title: "申请书" }];
  h.ui.renderSections();
  const section = h.element("#draftSections").children[0];
  const calls = [];
  h.ui.setApi(async (url, options = {}) => {
    calls.push({ url, options });
    return options.method === "POST" ? { status: "processing", job_id: "job" } : { status: "running" };
  });
  const button = section.children[0].children[1].children[1];
  await button.click();
  assert.equal(calls.filter(call => call.options.method === "POST").length, 1);
  assert.equal(calls.length, 46);
  assert.equal(button.disabled, false);
  assert.match(h.element("#toast").textContent, /仍在后台处理/);
});

test("a silent section request unlocks with uncertain result, without retry", async () => {
  const h = harness(); exportingProject(h);
  const timers = new Map(); let id = 0;
  h.context.setTimeout = (callback, delay) => { timers.set(++id, { callback, delay }); return id; };
  h.context.clearTimeout = key => timers.delete(key);
  h.ui.state.outline = [{ id: "purpose", title: "申请书" }];
  h.ui.renderSections();
  const section = h.element("#draftSections").children[0];
  const button = section.children[0].children[1].children[1];
  let calls = 0;
  h.ui.setApi(() => { calls++; return new Promise(() => {}); });
  const running = button.click();
  const timeout = [...timers.values()].find(item => item.delay === 180000);
  assert.ok(timeout);
  timeout.callback();
  await running;
  assert.equal(calls, 1);
  assert.equal(button.disabled, false);
  assert.match(h.element("#toast").textContent, /可能仍在后台处理/);
  assert.equal(section.children[0].children[0].children[3].textContent, "● 结果待确认");
});

test("version write failure displays the returned draft without applying or regenerating it", async () => {
  const h = harness(); exportingProject(h);
  h.ui.state.project.sections = { purpose: "原正文" };
  h.ui.state.outline = [{ id: "purpose", title: "申请书" }];
  const calls = [];
  h.ui.setApi(async (url, options) => {
    calls.push({ url, options });
    return { conflict_status: "user_edit_preserved", result_save_uncertain: true,
      content: "生成的候选正文", notice: "保存状态不明" };
  });
  h.ui.renderSections();
  const section = h.element("#draftSections").children[0];
  await section.children[0].children[1].children[1].click();
  const body = section.children[1];
  assert.equal(body.children[4].children[0].children[1].textContent, "生成的候选正文");
  assert.equal(h.ui.state.project.sections.purpose, "原正文");
  assert.equal(calls.length, 1);
  body.children[4].children[0].children[3].click();
  assert.equal(body.children[1].value, "生成的候选正文");
  assert.equal(h.ui.state.project.sections.purpose, "原正文");
});

test("an uncertain generated draft stays scoped to its original project", async () => {
  const h = harness(); exportingProject(h);
  const original = h.ui.state.project;
  original.sections = { purpose: "原正文" };
  h.ui.state.outline = [{ id: "purpose", title: "申请书" }];
  let complete;
  h.ui.setApi(() => new Promise(resolve => { complete = resolve; }));
  h.ui.renderSections();
  const first = h.element("#draftSections").children[0];
  const generating = first.children[0].children[1].children[1].click();
  h.ui.state.project = { id: "second", sections: { purpose: "另一个项目" } };
  h.ui.renderSections();
  complete({ conflict_status: "user_edit_preserved", result_save_uncertain: true, content: "项目一私有草稿" });
  await generating;
  assert.equal(h.element("#draftSections").children[0].children[1].children[4].children.length, 0);
  h.ui.state.project = original;
  h.ui.renderSections();
  const pending = h.element("#draftSections").children[0].children[1].children[4];
  assert.equal(pending.children[0].children[1].textContent, "项目一私有草稿");
  assert.equal(original.sections.purpose, "原正文");
});

test("an old account's late draft is not retained after account switch", async () => {
  const h = harness(); exportingProject(h);
  h.ui.state.authSession = { user: { id: "old-account" } };
  h.ui.state.outline = [{ id: "purpose", title: "申请书" }];
  let complete;
  h.ui.setApi(() => new Promise(resolve => { complete = resolve; }));
  h.ui.renderSections();
  const generating = h.element("#draftSections").children[0].children[0].children[1].children[1].click();
  h.ui.state.authSession = { user: { id: "new-account" } };
  complete({ conflict_status: "user_edit_preserved", result_save_uncertain: true, content: "旧账号草稿" });
  await generating;
  h.ui.renderSections();
  assert.equal(h.element("#draftSections").children[0].children[1].children[4].children.length, 0);
});

test("export opens recovery instead of exporting a cover-only document", async () => {
  const h = harness(); exportingProject(h);
  h.ui.state.project.outline = []; h.ui.state.project.sections = {};
  const calls = [];
  h.ui.setApi(async url => {
    calls.push(url);
    return { snapshot: "f".repeat(64), notice: "请确认", items: [{
      id: "e".repeat(64), title: "项目目的", content: "聊天正文", already_saved: false, conflict: false,
    }] };
  });
  await h.ui.exportDoc();
  assert.equal(calls.length, 1);
  assert.equal(h.element("#chatDraftDialog").open, true);
  assert.equal(h.element("#confirmChatDraftsBtn").textContent, "确认保存并继续导出");
});

test("export presents a conflicting chat draft before using saved text", async () => {
  const h = harness(); exportingProject(h);
  const calls = [];
  const pid = h.ui.state.project.id;
  h.ui.setApi(async (url) => {
    calls.push(url);
    if (url.endsWith("/chat-drafts")) return { snapshot: "f".repeat(64), notice: "请确认", items: [{
      id: "e".repeat(64), title: "项目目的", content: "较新的对话草稿", already_saved: false, conflict: true,
    }] };
    if (url.endsWith("/export")) return { download_url: `/api/projects/${pid}/download` };
    throw Error(`unexpected ${url}`);
  });
  await h.ui.exportDoc();
  assert.equal(h.element("#chatDraftDialog").open, true);
  assert.equal(calls.filter(url => url.endsWith("/export")).length, 0);
  const root = h.element("#chatDraftItems");
  assert.equal(root.children[0].children[0].children[0].checked, false);
  const keep = root.children.find(el => el.textContent === "保持已保存正文并继续导出");
  assert.ok(keep);
  await keep.click();
  assert.equal(calls.filter(url => url.endsWith("/chat-drafts")).length, 1);
  assert.equal(calls.filter(url => url.endsWith("/export")).length, 1);
  assert.equal(h.created.length, 1);
});

test("export continues after saving selected drafts without re-prompting for unchecked ones", async () => {
  const h = harness(); exportingProject(h);
  const pid = h.ui.state.project.id;
  const calls = [];
  h.ui.setApi(async (url, options) => {
    calls.push({ url, options });
    if (url.endsWith("/chat-drafts")) return { snapshot: "f".repeat(64), notice: "请确认", items: [
      { id: "e".repeat(64), title: "项目目的", content: "新版目的", already_saved: false, conflict: true },
      { id: "d".repeat(64), title: "研究背景", content: "待审核背景", already_saved: false, conflict: false, requires_review: true },
    ] };
    if (url.endsWith("/chat-drafts/confirm")) return { notice: "已保存" };
    if (url.endsWith("/export")) return { download_url: `/api/projects/${pid}/download` };
    throw Error(`unexpected ${url}`);
  });
  h.ui.setLoadProject(async () => {});
  await h.ui.exportDoc();
  h.element("#chatDraftItems").children[0].children[0].children[0].checked = true;
  await h.element("#confirmChatDraftsBtn").onclick();
  const confirm = calls.find(c => c.url.endsWith("/chat-drafts/confirm"));
  assert.equal(JSON.parse(confirm.options.body).items.length, 1);
  assert.equal(JSON.parse(confirm.options.body).items[0].replace_existing, true);
  assert.equal(calls.filter(c => c.url.endsWith("/chat-drafts")).length, 1);
  assert.equal(calls.filter(c => c.url.endsWith("/export")).length, 1);
  assert.equal(h.element("#chatDraftDialog").open, false);
});

test("persistent results show success, per-file errors, and preview actions", () => {
  const h = harness();
  h.ui.renderUploadResult([
    { document: doc },
    { document: { original_name: "<img onerror=alert(1)>.txt" }, error: "文件过大" },
  ]);
  const box = h.element("#uploadResult");
  assert.equal(box.children[0].textContent, "上传结果：1 个成功，1 个处理失败");
  assert.match(box.children[1].children[0].textContent, /上传成功/);
  assert.equal(box.children[1].children[1].textContent, "预览");
  assert.match(box.children[2].children[0].textContent, /<img onerror=alert\(1\)>.txt — 上传失败：文件过大/);
  assert.equal(box.classList.contains("error"), true);
  assert.equal(box.classList.contains("hidden"), false);
});

test("empty results never claim upload success", () => {
  const h = harness();
  h.ui.renderUploadResult([]);
  assert.match(h.element("#uploadResult").children[0].textContent, /未收到上传结果/);
  assert.equal(h.element("#uploadResult").classList.contains("error"), true);
});

test("all material categories display the upload ceiling, and an oversized selection sends no requests", async () => {
  const h = harness();
  for (const kind of ["source", "template", "photo"]) {
    h.ui.setUploadKind(kind);
    assert.match(h.element("#uploadHint").textContent, /单个文件最大 50 MB/);
  }
  h.ui.state.project = { id: "a".repeat(32) };
  let calls = 0;
  h.ui.setApi(async () => { calls++; });
  await h.ui.uploadFiles([{ name: "too-large.pdf", size: 50_000_001 }]);
  assert.equal(calls, 0);
  assert.equal(h.requests.length, 0);
  assert.match(h.element("#uploadResult").children[1].children[0].textContent, /单个文件最大 50 MB/);
  assert.equal(h.ui.oversizedUploadError([{ name: "exact.pdf", size: 50_000_000 }]), "");
});

function cloudHarness() {
  const h = harness();
  h.context.URL = URL;
  h.context.crypto = require("node:crypto").webcrypto;
  h.ui.state.cloudMode = true;
  h.ui.state.project = { id: "a".repeat(32) };
  h.ui.state.authConfig = { storage_upload_endpoint: "/uploads/resumable", max_upload_bytes: 50_000_000 };
  const session = { user: { id: "owner" }, access_token: "user-jwt" };
  h.ui.state.authSession = session;
  h.ui.state.authClient = { auth: { getSession: async () => ({ data: { session } }) } };
  h.uploads = [];
  h.context.window.tus = { Upload: class {
    constructor(file, options) { this.file = file; this.options = options; h.uploads.push(this); }
    async findPreviousUploads() { return []; }
    async start() {
      this.request = { getURL: () => "/uploads/resumable", setHeader: (k, v) => { this[k] = v; } };
      try {
        await this.options.onBeforeRequest(this.request);
        this.options.onProgress(this.file.size, this.file.size);
        this.options.onSuccess();
      } catch (error) { this.options.onError(error); }
    }
  } };
  h.context.fetch = async () => ({
    ok: true, headers: new Headers({ "Content-Type": "application/json" }),
  });
  return h;
}

test("a >4.5 MB file uses 6 MiB TUS chunks, then small registration and processing requests", async () => {
  const h = cloudHarness();
  const file = new File([new Uint8Array(7 * 1024 * 1024)], "report.pdf", { lastModified: 1 });
  const calls = [];
  h.ui.setApi(async (url, options) => {
    calls.push({ url, options });
    if (url.endsWith("/from-storage")) return { documents: [{ document: { id: "b".repeat(32), original_name: file.name } }] };
    return { documents: [{ document: { id: "b".repeat(32), original_name: file.name, confirmed: true } }] };
  });
  const result = await h.ui.uploadFilesToCloud([file], "source");
  assert.equal(result.documents.length, 1);
  assert.equal(h.uploads[0].options.chunkSize, 6 * 1024 * 1024);
  assert.equal(h.uploads[0].options.uploadDataDuringCreation, false);
  assert.equal(h.uploads[0].Authorization, "Bearer user-jwt");
  assert.equal(JSON.parse(calls[0].options.body).process_now, false);
  assert.ok(calls[0].options.body.length < 1000);
  assert.match(calls[1].url, /\/documents\/b+\/process$/);
});

test("parse timeouts retain the acknowledged document and never delete uploaded bytes", async () => {
  const h = cloudHarness();
  h.ui.setApi(async (url) => {
    if (url.endsWith("/from-storage")) return { documents: [{ document: { id: "b".repeat(32), original_name: "report.pdf" } }] };
    throw new Error("HTTP 504");
  });
  const result = await h.ui.uploadFilesToCloud([new File(["pdf"], "report.pdf")], "source");
  assert.equal(result.documents[0].document.id, "b".repeat(32));
  assert.match(result.documents[0].error, /原文件已保存/);
});

test("registration failure reuses the completed object rather than uploading/deleting it again", async () => {
  const h = cloudHarness();
  const file = new File(["test"], "report.pdf", { lastModified: 3 });
  h.ui.setApi(async () => { throw new Error("HTTP 504"); });
  await h.ui.uploadFilesToCloud([file], "source");
  await h.ui.uploadFilesToCloud([file], "source");
  assert.equal(h.uploads.length, 1);
});

test("resume fingerprint is scoped to user/project/kind and samples file contents", async () => {
  const h = cloudHarness();
  const file = new File(["first"], "report.pdf", { lastModified: 3 });
  const first = await h.ui.cloudUploadIntent(file, "source", "a".repeat(32));
  assert.equal((await h.ui.cloudUploadIntent(file, "source", "a".repeat(32))).documentId, first.documentId);
  assert.notEqual((await h.ui.cloudUploadIntent(file, "template", "a".repeat(32))).documentId, first.documentId);
  assert.notEqual((await h.ui.cloudUploadIntent(new File(["other"], "report.pdf", { lastModified: 3 }), "source", "a".repeat(32))).documentId, first.documentId);
});

test("50 MB ceiling and disabled Worker prevent doomed Vercel uploads before sending bytes", async () => {
  const h = cloudHarness();
  const tooLarge = { name: "huge.pdf", size: 50_000_001 };
  let result = await h.ui.uploadFilesToCloud([tooLarge], "source");
  assert.match(result.documents[0].error, /50 MB/);
  h.ui.state.authConfig.storage_upload_endpoint = "";
  result = await h.ui.uploadFilesToCloud([{ name: "large.pdf", size: 5_000_000 }], "source");
  assert.match(result.documents[0].error, /大文件通道尚未启用/);
  assert.equal(h.uploads.length, 0);
});

test("a poisoned continuation URL cannot receive the user's JWT", async () => {
  const h = cloudHarness();
  const file = new File(["test"], "report.pdf");
  const intent = await h.ui.cloudUploadIntent(file, "source", "a".repeat(32));
  await h.ui.uploadResumable(file, intent, "application/pdf", "/uploads/resumable");
  let sent = false;
  await assert.rejects(h.uploads[0].options.onBeforeRequest({
    getURL: () => "https://evil.test/uploads/resumable/stolen",
    setHeader: () => { sent = true; },
  }), /续传地址无效/);
  assert.equal(sent, false);
});

test("vendored TUS client has a pinned checksum and loads before app.js", () => {
  const vendor = resolve(__dirname, "../../server/static/vendor");
  const lock = JSON.parse(readFileSync(resolve(vendor, "tus-js-client.lock.json"), "utf8"));
  const sha = require("node:crypto").createHash("sha256").update(readFileSync(resolve(vendor, lock.bundle))).digest("hex");
  assert.equal(sha, lock.bundle_sha256);
  const html = readFileSync(resolve(__dirname, "../../server/static/index.html"), "utf8");
  assert.ok(html.indexOf(lock.bundle) < html.indexOf('src="/static/app.js"'));
});

test("PDF preview fetches with JWT and embeds a PDF blob, not a private endpoint", async () => {
  const h = harness();
  h.ui.state.authSession = { access_token: "fake-session-jwt" };
  await h.ui.previewDocument(doc, true);
  assert.equal(h.requests[0].options.headers.get("Authorization"), "Bearer fake-session-jwt");
  assert.match(h.requests[0].url, /\/api\/documents\/a+\/file$/);
  const body = h.element("#documentPreviewBody");
  assert.equal(body.children[0].tagName, "iframe");
  assert.match(body.children[0].src, /^blob:/);
  assert.equal(h.created[0].type, "application/pdf");
  assert.equal(body.children[2].textContent, doc.extracted_text);
  assert.match(h.element("#documentPreviewStatus").textContent, /上传成功.*待核对/);
  assert.equal(body.attributes["aria-busy"], "false");
  assert.equal(h.ui.state.documents.length, 0); // Preview is not confirmation/indexing.
});

test("images uploaded as ordinary materials also have an authenticated image preview", async () => {
  const h = harness();
  await h.ui.previewDocument({ ...doc, original_name: "扫描件.JPG" });
  assert.equal(h.element("#documentPreviewBody").children[0].tagName, "img");
  assert.equal(h.created[0].type, "image/jpeg");
});

test("Word preview clearly labels text-only layout and uses safe textContent", async () => {
  const h = harness();
  await h.ui.previewDocument({
    ...doc, original_name: "模板.docx", extracted_text: "<script>alert(1)</script>",
  });
  const body = h.element("#documentPreviewBody");
  assert.match(body.children[0].textContent, /不保留原版式/);
  assert.equal(body.children[1].textContent, "<script>alert(1)</script>");
  assert.equal(h.requests.length, 0);
});

test("authorization failure falls back to extracted text and does not claim preview loaded", async () => {
  const h = harness();
  h.context.fetch = async () => ({ ok: false, status: 401 });
  await h.ui.previewDocument(doc);
  const body = h.element("#documentPreviewBody");
  assert.match(body.children[0].textContent, /登录已过期/);
  assert.equal(body.children[1].textContent, doc.extracted_text);
  assert.equal(h.created.length, 0);
  assert.equal(body.attributes["aria-busy"], "false");
});

test("recognition failure is distinct from storage failure", async () => {
  const h = harness();
  const broken = { ...doc, original_name: "损坏.docx", extracted_text: "", extraction_status: "error",
    extraction_warning: "无法识别文件" };
  await h.ui.previewDocument(broken, true);
  assert.match(h.element("#documentPreviewStatus").textContent, /已保存.*识别失败/);
  assert.doesNotMatch(h.element("#documentPreviewStatus").textContent, /上传成功/);
  h.ui.renderUploadResult([{ document: broken, error: "无法识别文件" }]);
  assert.match(h.element("#uploadResult").children[1].children[0].textContent, /已保存，识别失败/);
});

test("switching and closing previews revoke blob URLs", async () => {
  const h = harness();
  await h.ui.previewDocument(doc);
  await h.ui.previewDocument({ ...doc, original_name: "文字.txt" });
  assert.deepEqual(h.revoked, ["blob:preview-1"]);
  await h.ui.previewDocument(doc);
  h.ui.clearDocumentPreview();
  assert.deepEqual(h.revoked, ["blob:preview-1", "blob:preview-2"]);
  assert.equal(h.element("#documentPreviewBody").children.length, 0);
});

test("a late file response cannot replace the next document's preview", async () => {
  const h = harness();
  let finish;
  h.context.fetch = () => new Promise((resolve) => { finish = resolve; });
  const pending = h.ui.previewDocument(doc);
  await h.ui.previewDocument({ ...doc, original_name: "另一份.txt", extracted_text: "新的文字" });
  finish({ ok: true, blob: async () => new Blob(["old"]) });
  await pending;
  assert.equal(h.element("#documentPreviewBody").children[1].textContent, "新的文字");
  assert.equal(h.created.length, 0);
});

test("material cards expose preview and explicit uploaded state without unauthenticated images", () => {
  const h = harness();
  h.ui.state.documents = [{ ...doc, kind: "photo" }];
  h.ui.renderDocuments();
  const card = h.element("#documentsList").children[0];
  assert.equal(card.dataset.documentId, doc.id);
  assert.match(card.children[0].children[2].textContent, /已上传 · 待核对/);
  assert.equal(card.children.at(-1).children[0].textContent, "预览文件");
  assert.equal(card.children.some((child) => child.tagName === "img"), false);
});

test("successful upload shows persistent result and automatically opens preview", async () => {
  const h = harness();
  h.context.FormData = FormData;
  h.context.URLSearchParams = URLSearchParams;
  h.ui.state.project = { id: "project-1" };
  const textDoc = { ...doc, original_name: "记录.txt" };
  h.ui.setApi(async () => ({ documents: [{ document: textDoc }] }));
  h.ui.setLoadProject(async () => {});
  await h.ui.uploadFiles([new File(["内容"], "记录.txt")]);
  assert.match(h.element("#uploadResult").children[0].textContent, /1 个成功/);
  assert.equal(h.element("#documentPreviewDialog").open, true);
  assert.match(h.element("#documentPreviewStatus").textContent, /上传成功/);
  assert.equal(h.ui.state.uploading, false);
  assert.equal(h.element("#chooseFileBtn").disabled, false);
  assert.equal(h.element("#fileInput").value, "");
});

test("request failure persists its cause and restores upload controls", async () => {
  const h = harness();
  h.context.FormData = FormData;
  h.context.URLSearchParams = URLSearchParams;
  h.ui.state.project = { id: "project-1" };
  h.ui.setApi(async () => { throw new Error("文件超过 20 MB"); });
  await h.ui.uploadFiles([new File(["内容"], "记录.txt")]);
  assert.match(h.element("#uploadResult").children[1].children[0].textContent, /上传失败：文件超过 20 MB/);
  assert.equal(h.ui.state.uploading, false);
  assert.equal(h.element("#chatAttachBtn").disabled, false);
  assert.equal(h.element("#documentPreviewDialog").open, false);
});

test("registration refuses an uninitialized auth client without reading null.auth", async () => {
  const h = harness();
  h.ui.state.authMode = "signup";
  await h.ui.submitAuthForm({ preventDefault() {} });
  assert.match(h.element("#authFeedback").textContent, /正在初始化.*尚未发送/);
  assert.doesNotMatch(h.element("#authFeedback").textContent, /Cannot read|TypeError/);
  assert.equal(h.element("#authSubmitBtn").disabled, true);
  assert.equal(h.element("#authModeToggle").disabled, true);
});

test("missing SDK shows recovery and cannot enable registration after an error", async () => {
  const h = harness();
  await h.ui.initializeCloudAuth({ cloud_mode: true });
  assert.equal(h.ui.state.authClient, null);
  assert.equal(h.ui.state.authStatus, "error");
  assert.equal(h.element("#retryAuthBtn").classList.contains("hidden"), false);
  assert.equal(h.element("#authSubmitBtn").disabled, true);
  await h.ui.submitAuthForm({ preventDefault() {} });
  assert.match(h.element("#authFeedback").textContent, /尚未就绪.*重新连接/);
  assert.equal(h.element("#authSubmitBtn").disabled, true);
});

test("constructor or session failure leaves auth disabled instead of leaking technical errors", async () => {
  for (const createClient of [
    () => { throw new TypeError("bad client configuration"); },
    () => ({ auth: { getSession: async () => ({ error: new Error("session unavailable") }) } }),
  ]) {
    const h = harness();
    h.context.window.supabase = { createClient };
    await h.ui.initializeCloudAuth({ cloud_mode: true });
    assert.equal(h.ui.state.authClient, null);
    assert.equal(h.ui.state.authStatus, "error");
    assert.equal(h.ui.state.authInitializing, false);
    assert.equal(h.element("#authSubmitBtn").disabled, true);
    assert.match(h.element("#authFeedback").textContent, /无法初始化登录服务/);
  }
});

test("initialization holds submit disabled until session recovery completes", async () => {
  const h = harness();
  let finish;
  let clientsCreated = 0;
  const client = { auth: {
    getSession: () => new Promise((resolve) => { finish = resolve; }),
    onAuthStateChange: () => ({ data: { subscription: { unsubscribe() {} } } }),
  } };
  h.context.window.supabase = { createClient: () => { clientsCreated++; return client; } };
  const config = { cloud_mode: true };
  const initializing = h.ui.initializeCloudAuth(config);
  assert.equal(h.element("#authSubmitBtn").disabled, true);
  assert.equal(h.ui.state.authClient, null);
  await h.ui.initializeCloudAuth(config);
  assert.equal(clientsCreated, 1); // Concurrent retries must not create duplicate clients.
  finish({ data: { session: null }, error: null });
  await initializing;
  assert.equal(h.ui.state.authStatus, "ready");
  assert.equal(h.ui.state.authClient, client);
  assert.equal(h.element("#authSubmitBtn").disabled, false);
  assert.equal(h.element("#authModeToggle").disabled, false);
  assert.equal(h.element("#retryAuthBtn").classList.contains("hidden"), true);
});

test("signup sends one request only after explicit submission and preserves email verification flow", async () => {
  const h = harness();
  const calls = [];
  let finish;
  h.ui.state.authStatus = "ready";
  h.ui.state.authMode = "signup";
  h.ui.state.authClient = { auth: { signUp: (input) => {
    calls.push(input);
    return new Promise((resolve) => { finish = resolve; });
  } } };
  h.element("#authEmail").value = "TEST@GMAIL.COM";
  h.element("#authPassword").value = "fake-password-for-unit-test";
  const submitting = h.ui.submitAuthForm({ preventDefault() {} });
  assert.equal(h.element("#authSubmitBtn").disabled, true);
  assert.equal(h.element("#authModeToggle").disabled, true);
  await h.ui.submitAuthForm({ preventDefault() {} });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].email, "test@gmail.com");
  assert.equal(calls[0].options.emailRedirectTo, "https://workbench.example.test");
  finish({ data: { session: null }, error: null });
  await submitting;
  assert.match(h.element("#authFeedback").textContent, /账号已创建.*验证后登录/);
  assert.equal(h.element("#authSubmitBtn").disabled, false);
  assert.equal(h.ui.state.authBusy, false);
});

test("network failures render actionable text and never automatically retry a signup", async () => {
  const h = harness();
  let requests = 0;
  h.ui.state.authStatus = "ready";
  h.ui.state.authMode = "signup";
  h.ui.state.authClient = { auth: { signUp: async () => {
    requests++;
    throw new TypeError("Failed to fetch");
  } } };
  h.element("#authEmail").value = "test@gmail.com";
  h.element("#authPassword").value = "fake-password-for-unit-test";
  await h.ui.submitAuthForm({ preventDefault() {} });
  assert.match(h.element("#authFeedback").textContent, /无法连接登录服务/);
  assert.equal(requests, 1);
  assert.equal(h.element("#authSubmitBtn").disabled, false);
});

test("vendored Supabase SDK is pinned, checksummed, and served from this origin before app.js", () => {
  const { createHash } = require("node:crypto");
  const vendor = resolve(__dirname, "../../server/static/vendor");
  const lock = JSON.parse(readFileSync(resolve(vendor, "supabase-js.lock.json")));
  assert.equal(lock.version, "2.118.0");
  const bundle = readFileSync(resolve(vendor, lock.bundle));
  assert.equal(createHash("sha256").update(bundle).digest("hex"), lock.bundle_sha256);
  const html = readFileSync(resolve(__dirname, "../../server/static/index.html"), "utf8");
  const sdkScript = `/static/vendor/${lock.bundle}`;
  assert.ok(html.includes(sdkScript));
  assert.ok(html.indexOf(sdkScript) < html.indexOf('/static/app.js'));
  assert.doesNotMatch(html, /https:\/\/cdn\.jsdelivr\.net\/npm\/@supabase/);
  assert.match(html, /id="authSubmitBtn"[^>]*disabled/);
  assert.match(html, /id="retryAuthBtn"/);
  // Evaluate the real bundle without constructing a client, sending credentials,
  // making any network call, or creating an account.
  const storage = new Map();
  const session = new Map();
  const context = vm.createContext({ console, URL, TextEncoder, TextDecoder });
  vm.runInContext(bundle.toString("utf8"), context);
  assert.equal(typeof context.supabase.createClient, "function");
});

test("chat allows only one pending request and clears its timer after a visible answer", async () => {
  const h = harness();
  h.ui.state.project = { id: "project-one" };
  h.ui.setChatRefresh(async () => {});
  let finish;
  let requests = 0;
  h.ui.setApi(async () => {
    requests++;
    return new Promise((resolve) => { finish = resolve; });
  });
  const first = h.ui.sendChat(null, "hello");
  assert.equal(h.ui.state.chatSending, true);
  assert.equal(h.element("#sendBtn").disabled, true);
  assert.equal(h.timers.size, 1);
  await h.ui.sendChat(null, "duplicate");
  assert.equal(requests, 1);
  finish({ message: "有正文的答复" });
  await first;
  assert.equal(h.ui.state.chatSending, false);
  assert.equal(h.element("#sendBtn").disabled, false);
  assert.equal(h.timers.size, 0);
  assert.equal(h.ui.state.messages[1].content, "有正文的答复");
});

test("blank success payload is an explicit error, never a successful empty answer", async () => {
  const h = harness();
  h.ui.state.project = { id: "project-one" };
  h.ui.setChatRefresh(async () => {});
  h.ui.setLoadProject(async () => {});
  h.ui.setApi(async () => ({ message: "" }));
  await h.ui.sendChat(null, "test");
  assert.equal(h.ui.state.messages.length, 0);
  const bubbles = h.element("#chatMessages").children.flatMap((item) => item.children);
  assert.ok(bubbles.some((item) => item.innerHTML?.includes("未返回可用正文")));
  assert.equal(h.ui.state.chatSending, false);
  assert.equal(h.timers.size, 0);
});

test("a late reply does not enter another project's conversation", async () => {
  const h = harness();
  h.ui.state.project = { id: "project-one" };
  h.ui.setChatRefresh(async () => {});
  let finish;
  h.ui.setApi(() => new Promise((resolve) => { finish = resolve; }));
  const pending = h.ui.sendChat(null, "test");
  h.ui.state.project = { id: "project-two" };
  finish({ message: "answer for project one" });
  await pending;
  assert.equal(h.ui.state.messages.length, 0);
  assert.equal(h.timers.size, 0);
  assert.equal(h.ui.state.chatSending, false);
});

test("public cache recovers from corrupt, expired or unavailable storage", () => {
  const h = harness();
  const list = [{ id: "innovation-research", name: "创新训练" }];
  h.ui.writePublicCache("skills", list);
  assert.equal(h.ui.readPublicCache("skills")[0].id, "innovation-research");
  h.context.localStorage.setItem("stardust-public-v1-skills", "{bad-json");
  assert.equal(h.ui.readPublicCache("skills"), null);
  h.context.localStorage.setItem("stardust-public-v1-skills", JSON.stringify({version:1,savedAt:0,data:list}));
  assert.equal(h.ui.readPublicCache("skills"), null);
  h.context.localStorage.getItem = () => { throw Error("denied"); };
  assert.equal(h.ui.readPublicCache("skills"), null);
});

test("all SDK auth and storage operations use same-origin proxy", async () => {
  const h = harness();
  h.context.URL = URL;
  const fetcher = h.ui.sameOriginAuthFetch("https://project.supabase.co");
  await fetcher("https://project.supabase.co/auth/v1/token?grant_type=refresh_token", {method:"POST"});
  await fetcher("https://project.supabase.co/auth/v1/user", {method:"GET"});
  await fetcher("https://project.supabase.co/auth/v1/logout", {method:"POST"});
  assert.equal(h.requests[0].url, "/api/auth/proxy/token?grant_type=refresh_token");
  assert.equal(h.requests[1].url, "/api/auth/proxy/user");
  assert.equal(h.requests[2].url, "/api/auth/proxy/logout");
  await fetcher("https://project.supabase.co/storage/v1/object/stardust-project-files/test");
  assert.equal(h.requests[3].url, "/api/storage/proxy/object/stardust-project-files/test");
});

test("cloud keys are memory-only; cloud deletion and account switch cannot restore stale key", async () => {
  const h = harness();
  h.ui.state.cloudMode = true;
  h.ui.state.authSession = {user:{id:"A"}};
  const key = "cloud-private-key";
  h.ui.storeLlmConfig({provider:"openai_compatible",api_key:key});
  assert.equal(h.context.sessionStorage.getItem("innovation-proposal-agent-llm-config"), null);
  assert.equal(h.context.localStorage.getItem("innovation-proposal-agent-llm-config"), null);
  let finish;
  h.ui.setApi(() => new Promise(resolve => {finish=resolve;}));
  const loading = h.ui.loadCloudModelConfig();
  h.ui.state.authSession = {user:{id:"B"}};
  h.ui.state.llmConfig = {provider:"preset",api_key:""};
  finish({config:{provider:"openai_compatible",api_key:key}});
  await loading;
  assert.equal(h.ui.state.llmConfig.api_key, "");
  h.ui.setApi(async () => ({config:null}));
  await h.ui.loadCloudModelConfig();
  assert.equal(h.ui.state.llmConfig.provider, "preset");
});

test("login initialization no longer awaits the public catalog or pricing", () => {
  const source = readFileSync(resolve(__dirname, "../../server/static/app.js"), "utf8");
  const init = source.slice(source.indexOf("  async function init()"));
  assert.match(init, /void loadSkills\(\)/);
  assert.match(init, /void loadPresetModelsAndPlans\(\)/);
  assert.doesNotMatch(init, /await Promise\.all/);
});

test("failed cloud save preserves previous model and never claims success", async () => {
  const h = harness();
  h.ui.state.cloudMode = true;
  h.ui.state.authSession = {user:{id:"A"}};
  h.ui.state.llmConfig = {provider:"preset",model:"workbench-bundle",api_key:""};
  h.element('input[name="llmProvider"]:checked').value = "openai_compatible";
  for (const [id,value] of Object.entries({customModelBase:"https://api.example.test/v1",customModelName:"model",
    customModelKey:"new-private-key",customImageModel:"",customImageBase:"",customImageKey:""})) {
    h.element("#" + id).value = value;
  }
  h.ui.setApi(async () => { throw Error("upstream down"); });
  await h.ui.saveSelectedLlmConfig();
  assert.equal(h.ui.state.llmConfig.provider, "preset");
  assert.match(h.element("#modelConfigFeedback").textContent, /保存失败/);
  assert.equal(h.element("#saveModelConfigBtn").disabled, false);
  const calls = [];
  h.ui.setApi(async (url,opts) => {calls.push({url,opts});return {saved:true};});
  await h.ui.saveSelectedLlmConfig();
  assert.equal(calls[0].url, "/api/user/llm-config");
  assert.equal(h.ui.state.llmConfig.api_key, "new-private-key");
  assert.equal(h.context.sessionStorage.getItem("innovation-proposal-agent-llm-config"), null);
});

test("SSE chat cannot bill the default model while cloud BYOK restore is pending or failed", async () => {
  const h = harness();
  h.ui.state.cloudMode = true;
  h.ui.state.project = {id:"project-A"};
  h.element("#chatInput").value = "不要提前扣费";
  for (const status of ["loading", "error"]) {
    h.ui.state.modelConfigSyncStatus = status;
    await h.ui.sendChat({preventDefault(){}});
    assert.equal(h.requests.length, 0);
    assert.equal(h.element("#chatInput").value, "不要提前扣费");
  }
});

function realChatStream(h, text) {
  h.ui.state.project = { id: "project-one" };
  h.ui.setChatRefresh(async () => {});
  h.ui.setLoadProject(async () => {});
  let read = false;
  let cancelled = 0;
  h.context.fetch = async () => ({
    ok: true,
    body: { getReader: () => ({
      read: async () => {
        if (read) return { done: true };
        read = true;
        return { done: false, value: new TextEncoder().encode(text) };
      },
      cancel: async () => { cancelled++; },
      releaseLock() {},
    }) },
  });
  return () => cancelled;
}

test("real SSE EOF without a done event never turns partial output into success", async () => {
  const h = harness();
  const cancelled = realChatStream(h, 'event: delta\ndata: {"text":"不完整的半句"}\n\n');
  await h.ui.sendChat(null, "测试");
  assert.equal(h.ui.state.messages.length, 0);
  const bubbles = h.element("#chatMessages").children.flatMap((item) => item.children);
  assert.ok(bubbles.some((item) => item.innerHTML?.includes("未完成")));
  assert.equal(h.ui.state.chatSending, false);
  assert.equal(h.timers.size, 0);
  assert.equal(cancelled(), 1);
});

test("real SSE done event is required and keeps the complete server response", async () => {
  const h = harness();
  const cancelled = realChatStream(h,
    'event: delta\ndata: {"text":"部分"}\n\n' +
    'event: done\ndata: {"message":"完整回复","tool_calls":[]}\n\n');
  await h.ui.sendChat(null, "测试");
  assert.equal(h.ui.state.messages[1].content, "完整回复");
  assert.equal(h.ui.state.chatSending, false);
  assert.equal(cancelled(), 1);
});

test("a tool call clears provisional streamed text before the final reply", async () => {
  const h = harness();
  realChatStream(h,
    'event: delta\ndata: {"text":"正在查询"}\n\n' +
    'event: reset\ndata: {}\n\n' +
    'event: status\ndata: {"message":"正在检索"}\n\n' +
    'event: delta\ndata: {"text":"最终答复"}\n\n' +
    'event: done\ndata: {"message":"最终答复","tool_calls":[]}\n\n');
  await h.ui.sendChat(null, "测试");
  assert.equal(h.ui.state.messages[1].content, "最终答复");
  const rows = h.element("#chatMessages").children;
  assert.ok(rows.some((row) => row.removed && row.children.some((child) => child.textContent === "正在查询")));
  assert.ok(rows.some((row) => !row.removed && row.children.some((child) => child.innerHTML?.includes("最终答复"))));
});

test("switching projects during real SSE cancels the reader and clears the wait timer", async () => {
  const h = harness();
  h.ui.state.project = { id: "project-one" };
  h.ui.setChatRefresh(async () => {});
  h.ui.setLoadProject(async () => {});
  let cancelled = false;
  h.context.fetch = async () => ({ ok: true, body: { getReader: () => ({
    read: async () => {
      h.ui.state.project = { id: "project-two" };
      return { done: false, value: new TextEncoder().encode('event: delta\ndata: {"text":"old"}\n\n') };
    },
    cancel: async () => { cancelled = true; },
    releaseLock() {},
  }) } });
  await h.ui.sendChat(null, "测试");
  assert.equal(h.ui.state.messages.length, 0);
  assert.equal(h.timers.size, 0);
  assert.equal(h.ui.state.chatSending, false);
  assert.equal(cancelled, true);
});

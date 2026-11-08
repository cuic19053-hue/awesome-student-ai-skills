const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { resolve } = require("node:path");
const { test } = require("node:test");
const vm = require("node:vm");

function harness(statuses, switchProject = false, onFetch = () => {}, { stallPoll = false } = {}) {
  const calls = [], downloads = [], fetches = [], notices = [], revoked = [];
  let pollPending = false, draftAreas = [];
  const state = { project: { id: "a".repeat(32) }, authSession: { access_token: "fake-user-jwt" } };
  const host = { state, toast: text => notices.push(text), api: async (url, options = {}) => {
    calls.push({ url, options });
    if (options.method === "POST") return { id: "b".repeat(32) };
    if (stallPoll) { pollPending = true; return new Promise(() => {}); }
    if (switchProject) state.project = { id: "c".repeat(32) };
    return statuses.length > 1 ? statuses.shift() : statuses[0];
  } };
  const context = vm.createContext({
    window: {}, console, Blob, crypto: { randomUUID: () => "one-export-only" },
    setTimeout: (callback, delay) => { if (delay < 15000 || pollPending) callback(); return 1; }, clearTimeout() {},
    document: { querySelectorAll: () => draftAreas, body: { append() {} },
      createElement: () => ({ click() { downloads.push({ href: this.href, name: this.download }); }, remove() {} }) },
    fetch: async (url, options) => {
      fetches.push({ url, options });
      onFetch();
      return { ok: true, blob: async () => new Blob(["synthetic Word"]) };
    },
    URL: { createObjectURL: () => "blob:private-word", revokeObjectURL(url) { revoked.push(url); } },
  });
  const source = readFileSync(resolve(__dirname, "../../server/static/material.js"), "utf8")
    .replace("window.MaterialPilot =", `
      globalThis.init = config => { host = config; projectId = config.state.project.id;
        data = { context: { revision: 4 } }; refresh = async () => {}; };
      window.MaterialPilot =`);
  vm.runInContext(source, context);
  context.init(host);
  return { export: isCurrent => context.window.MaterialPilot.exportDocument({}, isCurrent),
    flushEdits: () => context.window.MaterialPilot.flushEdits(),
    setDraftAreas: areas => { draftAreas = areas; }, host,
    invalidate: () => context.window.MaterialPilot.invalidateArtifacts(), calls, downloads, fetches, notices, revoked };
}

test("material export waits for its one durable job then downloads with JWT", async () => {
  const h = harness([{ status: "running", step: "saving_artifacts" }, { status: "completed" }]);
  await h.export();
  assert.equal(h.calls.filter(c => c.options.method === "POST").length, 1);
  assert.equal(h.calls.filter(c => c.options.method === "GET").length, 2);
  assert.equal(h.downloads.length, 1);
  assert.equal(h.downloads[0].href, "blob:private-word");
  assert.equal(h.fetches[0].options.headers.Authorization, "Bearer fake-user-jwt");
  assert.match(h.notices.at(-1), /已生成并下载/);
});

test("failed material export never downloads or resubmits", async () => {
  const h = harness([{ status: "failed", step: "saving_artifacts", error: "文件保存失败" }]);
  await assert.rejects(h.export(), /文件保存失败/);
  assert.equal(h.calls.filter(c => c.options.method === "POST").length, 1);
  assert.equal(h.downloads.length, 0);
  assert.equal(h.fetches.length, 0);
});

test("observing a slow task never creates another job or claims success", async () => {
  const h = harness([{ status: "running", step: "rendering_pages" }]);
  await h.export();
  assert.equal(h.calls.filter(c => c.options.method === "POST").length, 1);
  assert.equal(h.calls.length, 81);
  assert.equal(h.downloads.length, 0);
  assert.match(h.notices.at(-1), /仍在后台/);
});

test("a project switch while polling cannot download the previous project", async () => {
  const h = harness([{ status: "completed" }], true);
  await h.export();
  assert.equal(h.downloads.length, 0);
  assert.equal(h.fetches.length, 0);
});

test("a newer instruction during a worker download prevents the stale file from opening", async () => {
  let current = true;
  const h = harness([{ status: "completed" }], false, () => { current = false; });
  await h.export(() => current);
  assert.equal(h.calls.filter(c => c.options.method === "POST").length, 1);
  assert.equal(h.fetches.length, 1);
  assert.equal(h.downloads.length, 0);
  assert.deepEqual(h.revoked, ["blob:private-word"]);
});

test("revoking worker artifacts interrupts an in-flight file fetch", async () => {
  let invalidate;
  const h = harness([{ status: "completed" }], false, () => invalidate());
  invalidate = () => h.invalidate();
  await assert.rejects(h.export(), /项目内容已更新/);
  assert.equal(h.downloads.length, 0);
});

test("a stalled export status stops waiting without submitting another job", async () => {
  const h = harness([], false, () => {}, { stallPoll: true });
  await assert.rejects(h.export(), /文件可能仍在后台生成/);
  assert.equal(h.calls.filter(c => c.options.method === "POST").length, 1);
  assert.equal(h.calls.filter(c => c.options.method === "GET").length, 1);
  assert.equal(h.downloads.length, 0);
});

test("saving before export does not silently mark later keystrokes as saved", async () => {
  const h = harness([{ status: "completed" }]);
  h.host.state.project.sections = { intro: "已保存正文" };
  h.host.state.project.material_revision = 2;
  const area = { value: "本次发送的正文", closest: () => ({ id: "draft-sec-intro" }) };
  h.setDraftAreas([area]);
  let finish;
  h.host.api = () => new Promise(resolve => { finish = resolve; });
  const saving = h.flushEdits();
  area.value = "发送期间输入的新文字";
  finish({ material_revision: 3 });
  await assert.rejects(saving, /保存期间正文又有修改/);
  assert.equal(h.host.state.project.sections.intro, "本次发送的正文");
  assert.equal(area.value, "发送期间输入的新文字");
});

test("a late save cannot put the previous project's text into the current project", async () => {
  const h = harness([{ status: "completed" }]);
  h.host.state.project.sections = { intro: "原项目正文" };
  h.host.state.project.material_revision = 2;
  h.setDraftAreas([{ value: "原项目的新文字", closest: () => ({ id: "draft-sec-intro" }) }]);
  let finish;
  h.host.api = () => new Promise(resolve => { finish = resolve; });
  const saving = h.flushEdits();
  h.host.state.project = { id: "c".repeat(32), sections: { intro: "另一个项目正文" } };
  finish({ material_revision: 3 });
  await assert.rejects(saving, /项目已切换/);
  assert.equal(h.host.state.project.sections.intro, "另一个项目正文");
});

const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { resolve } = require("node:path");
const { test } = require("node:test");
const vm = require("node:vm");

function harness(statuses, switchProject = false) {
  const calls = [], downloads = [], fetches = [], notices = [];
  const state = { project: { id: "a".repeat(32) }, authSession: { access_token: "fake-user-jwt" } };
  const host = { state, toast: text => notices.push(text), api: async (url, options = {}) => {
    calls.push({ url, options });
    if (options.method === "POST") return { id: "b".repeat(32) };
    if (switchProject) state.project = { id: "c".repeat(32) };
    return statuses.length > 1 ? statuses.shift() : statuses[0];
  } };
  const context = vm.createContext({
    window: {}, console, Blob, crypto: { randomUUID: () => "one-export-only" },
    setTimeout: callback => callback(),
    document: { querySelectorAll: () => [], body: { append() {} },
      createElement: () => ({ click() { downloads.push({ href: this.href, name: this.download }); }, remove() {} }) },
    fetch: async (url, options) => {
      fetches.push({ url, options });
      return { ok: true, blob: async () => new Blob(["synthetic Word"]) };
    },
    URL: { createObjectURL: () => "blob:private-word", revokeObjectURL() {} },
  });
  const source = readFileSync(resolve(__dirname, "../../server/static/material.js"), "utf8")
    .replace("window.MaterialPilot =", `
      globalThis.init = config => { host = config; projectId = config.state.project.id;
        data = { context: { revision: 4 } }; refresh = async () => {}; };
      window.MaterialPilot =`);
  vm.runInContext(source, context);
  context.init(host);
  return { export: () => context.window.MaterialPilot.exportDocument(), calls, downloads, fetches, notices };
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

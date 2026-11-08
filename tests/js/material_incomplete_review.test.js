const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { resolve } = require("node:path");
const { test } = require("node:test");
const vm = require("node:vm");

test("a silent job submission ends observation and does not submit a second task", async () => {
  const calls = [], timers = new Map(); let timerId = 0;
  const state = { project: { id: "project", material_revision: 2, sections: {} }, llmConfig: {} };
  const host = { state, toast() {}, api: (url, options = {}) => {
    calls.push({ url, method: options.method }); return new Promise(() => {});
  } };
  const context = vm.createContext({ window: {}, console, confirm: () => true,
    crypto: { randomUUID: () => "once" },
    setTimeout: (fn, delay) => { timers.set(++timerId, { fn, delay }); return timerId; },
    clearTimeout: id => timers.delete(id), document: { querySelectorAll: () => [] } });
  const source = readFileSync(resolve(__dirname, "../../server/static/material.js"), "utf8")
    .replace("window.MaterialPilot =", `
      globalThis.init = config => { host = config; projectId = config.state.project.id;
        data = { context: { revision: 2 }, worker_ready: true }; refresh = async () => {}; };
      window.MaterialPilot =`);
  vm.runInContext(source, context); context.init(host);
  const running = context.window.MaterialPilot.section("chapter", null);
  await new Promise(resolve => setImmediate(resolve));
  const timeout = [...timers.values()].find(entry => entry.delay === 30000);
  assert.ok(timeout);
  timeout.fn();
  await assert.rejects(running, /任务可能已经开始/);
  assert.equal(calls.length, 1);
});

test("switching projects while loading material state cannot submit to another project", async () => {
  const calls = [];
  const state = { project: { id: "first", material_revision: 2, sections: {} }, llmConfig: {} };
  const host = { state, toast() {}, api: async (...args) => { calls.push(args); return {}; } };
  const context = vm.createContext({ window: {}, console, confirm: () => true,
    crypto: { randomUUID: () => "once" }, setTimeout: () => 1, clearTimeout() {},
    document: { querySelectorAll: () => [] } });
  const source = readFileSync(resolve(__dirname, "../../server/static/material.js"), "utf8")
    .replace("window.MaterialPilot =", `
      globalThis.init = config => { host = config; projectId = config.state.project.id;
        data = { context: { revision: 2 }, worker_ready: true };
        refresh = () => new Promise(resolve => { globalThis.finish = resolve; }); };
      window.MaterialPilot =`);
  vm.runInContext(source, context); context.init(host);
  const running = context.window.MaterialPilot.section("chapter", null);
  state.project = { id: "second", material_revision: 2, sections: {} };
  context.finish();
  await assert.rejects(running, /项目已切换/);
  assert.equal(calls.length, 0);
});

test("an incomplete section review remains in its single task without auto-apply", async () => {
  const calls = [];
  const state = { project: { id: "project", material_revision: 2, sections: { chapter: "原文" } }, llmConfig: {} };
  const host = { state, toast() {}, api: async (url, options = {}) => {
    calls.push({ url, method: options.method });
    if (options.method === "POST") return { id: "job" };
    return { status: "completed", result: { status: "review_failed", content: "可查看的备选草稿" } };
  } };
  const context = vm.createContext({ window: {}, console, confirm: () => true,
    crypto: { randomUUID: () => "once" }, setTimeout: (fn, delay) => { if (delay < 15000) fn(); return 1; }, clearTimeout() {},
    document: { querySelectorAll: () => [] } });
  const source = readFileSync(resolve(__dirname, "../../server/static/material.js"), "utf8")
    .replace("window.MaterialPilot =", `
      globalThis.init = config => { host = config; projectId = config.state.project.id;
        data = { context: { revision: 2 }, worker_ready: true }; refresh = async () => {}; };
      window.MaterialPilot =`);
  vm.runInContext(source, context);
  context.init(host);
  const result = await context.window.MaterialPilot.section("chapter", null);
  assert.equal(result.review_incomplete, true);
  assert.equal(result.content, "可查看的备选草稿");
  assert.equal(state.project.sections.chapter, "原文");
  assert.equal(calls.filter(call => call.method === "POST").length, 1);
  assert.ok(!calls.some(call => call.url.endsWith("/apply")));
});

test("explicitly choosing the saved task draft sends the required confirmation", async () => {
  class Element {
    constructor() { this.children = []; this.classList = { toggle() {} }; }
    append(...children) { this.children.push(...children); }
    replaceChildren(...children) { this.children = children; }
  }
  const calls = [];
  const state = { project: { id: "project", material: { enabled: true }, material_revision: 2, sections: {} }, outline: [] };
  const host = { state, toast() {}, reload: async () => {}, api: async (url, options = {}) => {
    calls.push({ url, ...options });
    return { applied: true };
  } };
  const context = vm.createContext({ window: {}, console, URL: { revokeObjectURL() {} },
    document: { createElement: () => new Element(), querySelectorAll: () => [] } });
  const source = readFileSync(resolve(__dirname, "../../server/static/material.js"), "utf8")
    .replace("window.MaterialPilot =", `
      globalThis.show = config => { host = config; projectId = config.state.project.id; root = document.createElement('div');
        data = { worker_ready: true, context: { revision: 2, stale: {}, sources: [], requirements: { priority: [], conflicts: [] } },
          requirements: [], plans: [], jobs: [{ id: 'job', kind: 'section', status: 'completed',
            result: { status: 'review_failed', content: '待查看草稿' } }] };
        refresh = async () => {}; draw(); return root; };
      window.MaterialPilot =`);
  vm.runInContext(source, context);
  const root = context.show(host);
  function find(node, text) {
    if (node.textContent === text) return node;
    for (const child of node.children || []) { const found = find(child, text); if (found) return found; }
  }
  const button = find(root, "使用此草稿");
  assert.ok(button);
  await button.onclick();
  assert.equal(calls.length, 1);
  assert.ok(calls[0].url.endsWith("/jobs/job/apply"));
  assert.equal(JSON.parse(calls[0].body).use_unreviewed_draft, true);
});

test("uncorroborated personal numbers remain in the task and prompt the student to check", async () => {
  const calls = [];
  const state = { project: { id: "project", material_revision: 2, sections: { chapter: "原文" } }, llmConfig: {} };
  const host = { state, toast() {}, api: async (url, options = {}) => {
    calls.push({ url, method: options.method });
    if (options.method === "POST") return { id: "job" };
    return { status: "completed", result: { status: "passed", review_incomplete: true,
      grounding_issues: ["绩点满分制"], content: "我的绩点3.8，满分4.0。" } };
  } };
  const context = vm.createContext({ window: {}, console, confirm: () => true,
    crypto: { randomUUID: () => "once" }, setTimeout: (fn, delay) => { if (delay < 15000) fn(); return 1; }, clearTimeout() {},
    document: { querySelectorAll: () => [] } });
  const source = readFileSync(resolve(__dirname, "../../server/static/material.js"), "utf8")
    .replace("window.MaterialPilot =", `
      globalThis.init = config => { host = config; projectId = config.state.project.id;
        data = { context: { revision: 2 }, worker_ready: true }; refresh = async () => {}; };
      window.MaterialPilot =`);
  vm.runInContext(source, context);
  context.init(host);
  const result = await context.window.MaterialPilot.section("chapter", null);
  assert.match(result.notice, /个人数字需要你核对/);
  assert.equal(state.project.sections.chapter, "原文");
  assert.ok(!calls.some(call => call.url.endsWith("/apply")));
});

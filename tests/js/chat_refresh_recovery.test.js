const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { resolve, dirname } = require("node:path");
const { test } = require("node:test");
const vm = require("node:vm");

// Exercise the same app harness in distinct page instances sharing one tab's
// sessionStorage, just as a real refresh does.
const harnessFile = resolve(__dirname, "material_upload_ui.test.js");
const harnessSource = readFileSync(harnessFile, "utf8");
const harnessEnd = harnessSource.indexOf("\nconst doc = {");
assert.ok(harnessEnd > 0);
const context = vm.createContext({ require, __dirname: dirname(harnessFile), Headers, AbortController, Blob, TextEncoder, TextDecoder, URL });
vm.runInContext(harnessSource.slice(0, harnessEnd) + "\nglobalThis.makeHarness = harness;", context);
const key = "stardust-chat-recovery-v1";

function inputFor(h, value = "") {
  const input = h.element("#chatInput");
  input.style = {};
  input.scrollHeight = 44;
  input.value = value;
  return input;
}

function completedReader() {
  const encoded = new TextEncoder().encode('event: done\ndata: {"message":"已完成","tool_calls":[]}\n\n');
  let first = true;
  return { async read() { if (first) { first = false; return { done: false, value: encoded }; } return { done: true }; },
    async cancel() {}, releaseLock() {} };
}

test("a refresh after a disconnect restores the draft without another request", async () => {
  const session = new Map();
  const first = context.makeHarness(session);
  first.ui.state.project = { id: "project-one" };
  first.ui.setChatRefresh(async () => {});
  first.ui.setLoadProject(async () => {});
  inputFor(first, "学生希望保留的材料");
  first.context.fetch = async () => { throw new TypeError("disconnected"); };
  await first.ui.sendChat(null);
  assert.ok(session.get(key).includes("学生希望保留的材料"));

  const refreshed = context.makeHarness(session);
  refreshed.ui.state.project = { id: "project-one" };
  let requests = 0;
  refreshed.context.fetch = async () => { requests++; throw new Error("unexpected"); };
  const input = inputFor(refreshed);
  refreshed.ui.restoreInterruptedChatMessage("project-one");
  assert.equal(input.value, "学生希望保留的材料");
  assert.equal(requests, 0);
  assert.ok(session.has(key), "restoring the input must not erase it before the next successful send");

  const refreshedAgain = context.makeHarness(session);
  refreshedAgain.ui.state.project = { id: "project-one" };
  const againInput = inputFor(refreshedAgain);
  refreshedAgain.ui.restoreInterruptedChatMessage("project-one");
  assert.equal(againInput.value, "学生希望保留的材料");
});

test("edits to a recovered draft survive refresh and success clears it", async () => {
  const session = new Map();
  const first = context.makeHarness(session);
  first.ui.state.project = { id: "project-one" };
  first.ui.setChatRefresh(async () => {});
  first.ui.setLoadProject(async () => {});
  inputFor(first, "原始内容");
  first.context.fetch = async () => { throw new TypeError("disconnected"); };
  await first.ui.sendChat(null);
  const second = context.makeHarness(session);
  second.ui.state.project = { id: "project-one" };
  const input = inputFor(second);
  second.ui.restoreInterruptedChatMessage("project-one");
  input.value = "修改后内容";
  second.ui.updateRecoveredChatInput();
  const third = context.makeHarness(session);
  third.ui.state.project = { id: "project-one" };
  third.ui.setChatRefresh(async () => {});
  third.ui.setLoadProject(async () => {});
  const latest = inputFor(third);
  third.ui.restoreInterruptedChatMessage("project-one");
  assert.equal(latest.value, "修改后内容");
  third.context.fetch = async () => ({ ok: true, body: { getReader: completedReader } });
  await third.ui.sendChat(null);
  assert.equal(session.has(key), false);
});

test("refresh while a request is still pending does not lose input or issue another request", async () => {
  const session = new Map();
  const first = context.makeHarness(session);
  first.ui.state.project = { id: "project-one" };
  first.ui.setChatRefresh(async () => {});
  first.ui.setLoadProject(async () => {});
  inputFor(first, "长段申请内容");
  let finish;
  first.context.fetch = () => new Promise(resolve => { finish = resolve; });
  const pending = first.ui.sendChat(null);
  assert.ok(session.has(key));
  const refreshed = context.makeHarness(session);
  refreshed.ui.state.project = { id: "project-one" };
  let calls = 0;
  refreshed.context.fetch = async () => { calls++; throw new Error("unexpected"); };
  const input = inputFor(refreshed);
  refreshed.ui.restoreInterruptedChatMessage("project-one");
  assert.equal(input.value, "长段申请内容");
  assert.equal(calls, 0);
  finish({ ok: true, body: { getReader: completedReader } });
  await pending;
});

test("an unsent draft survives refresh and does not replace a pending request", async () => {
  const session = new Map();
  const first = context.makeHarness(session);
  first.ui.state.project = { id: "project-one" };
  first.ui.setChatRefresh(async () => {});
  first.ui.setLoadProject(async () => {});
  const input = inputFor(first, "已经发送的第一段");
  first.ui.updateRecoveredChatInput();
  let finish;
  first.context.fetch = () => new Promise(resolve => { finish = resolve; });
  const pending = first.ui.sendChat(null);
  input.value = "尚未发送的第二段";
  first.ui.updateRecoveredChatInput();
  const saved = JSON.parse(session.get(key));
  assert.deepEqual(saved.projects[0][1], ["已经发送的第一段", "尚未发送的第二段"]);
  const refreshed = context.makeHarness(session);
  refreshed.ui.state.project = { id: "project-one" };
  const restored = inputFor(refreshed);
  refreshed.ui.restoreInterruptedChatMessage("project-one");
  assert.equal(restored.value, "已经发送的第一段");
  const children = refreshed.element("#chatMessages").children.flatMap(row => row.children);
  assert.ok(children.some(item => item.textContent === "尚未发送的第二段"));
  finish({ ok: true, body: { getReader: completedReader } });
  await pending;
});

test("a different signed-in account cannot restore the previous account's draft", async () => {
  const session = new Map();
  const first = context.makeHarness(session);
  first.ui.state.cloudMode = true;
  first.ui.state.authSession = { user: { id: "account-A" }, access_token: "private-token" };
  first.ui.state.project = { id: "project-one" };
  first.ui.setChatRefresh(async () => {});
  first.ui.setLoadProject(async () => {});
  inputFor(first, "账号 A 的申请材料");
  first.context.fetch = async () => { throw new TypeError("disconnected"); };
  await first.ui.sendChat(null);
  assert.ok(session.get(key).includes("账号 A 的申请材料"));
  assert.ok(!session.get(key).includes("private-token"));
  const second = context.makeHarness(session);
  second.ui.state.cloudMode = true;
  second.ui.state.authSession = { user: { id: "account-B" } };
  second.ui.state.project = { id: "project-one" };
  const input = inputFor(second);
  second.ui.restoreInterruptedChatMessage("project-one");
  assert.equal(input.value, "");
  assert.equal(session.has(key), false);
});

test("blocked sessionStorage leaves ordinary in-memory recovery usable", async () => {
  const h = context.makeHarness();
  h.ui.state.project = { id: "project-one" };
  h.ui.setChatRefresh(async () => {});
  h.ui.setLoadProject(async () => {});
  h.context.sessionStorage.getItem = () => { throw new Error("blocked"); };
  h.context.sessionStorage.setItem = () => { throw new Error("blocked"); };
  h.context.sessionStorage.removeItem = () => { throw new Error("blocked"); };
  const input = inputFor(h, "需要保留的输入");
  h.context.fetch = async () => { throw new TypeError("disconnected"); };
  await h.ui.sendChat(null);
  assert.equal(input.value, "需要保留的输入");
});

test("switching projects keeps the input with the original project", async () => {
  const h = context.makeHarness();
  h.ui.state.project = { id: "project-one", state: {}, sections: {}, outline: [] };
  const input = inputFor(h, "第一个项目的未发送草稿");
  h.ui.setApi(async url => ({ id: url.split("/").at(-1), state: {}, sections: {}, outline: [], messages: [] }));
  await h.ui.loadProject("project-two");
  assert.equal(h.ui.state.project.id, "project-two");
  assert.equal(input.value, "");
  await h.ui.loadProject("project-one");
  assert.equal(h.ui.state.project.id, "project-one");
  assert.equal(input.value, "第一个项目的未发送草稿");
});

test("deleting a project clears its restored draft and the current input", async () => {
  const session = new Map();
  const h = context.makeHarness(session);
  h.ui.state.project = { id: "project-one", title: "测试材料" };
  h.ui.setChatRefresh(async () => {});
  h.ui.setLoadProject(async () => {});
  const input = inputFor(h, "待删除项目的内容");
  h.context.fetch = async () => { throw new TypeError("disconnected"); };
  await h.ui.sendChat(null);
  assert.ok(session.has(key));
  h.context.confirm = () => true;
  h.ui.setApi(async () => ({}));
  await h.ui.deleteCurrentProject();
  assert.equal(input.value, "");
  assert.equal(session.has(key), false);
});

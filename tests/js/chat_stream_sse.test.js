const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { resolve, dirname } = require("node:path");
const { test } = require("node:test");
const vm = require("node:vm");

const source = readFileSync(resolve(__dirname, "../../server/static/app.js"), "utf8");
const begin = source.indexOf("  async function readChatEvents(");
const end = source.indexOf("  async function refreshChatAfterError(", begin);
assert.ok(begin >= 0 && end > begin, "chat SSE reader must be present");
const readChatEvents = vm.runInNewContext(
  `(${source.slice(begin, end).trim()})`, { TextDecoder, JSON },
);

// Reuse the existing app DOM harness without executing its unrelated tests.
const harnessFile = resolve(__dirname, "material_upload_ui.test.js");
const harnessSource = readFileSync(harnessFile, "utf8");
const harnessEnd = harnessSource.indexOf("\nconst doc = {");
assert.ok(harnessEnd > 0);
const harnessContext = vm.createContext({
  require, __dirname: dirname(harnessFile), Headers, AbortController, Blob, TextEncoder, TextDecoder, URL,
});
vm.runInContext(harnessSource.slice(0, harnessEnd) + "\nglobalThis.makeHarness = harness;", harnessContext);

function byteReader(text, { failAfterChunks = false } = {}) {
  const bytes = new TextEncoder().encode(text);
  let offset = 0;
  return {
    async read() {
      if (offset < bytes.length) return { done: false, value: bytes.slice(offset, ++offset) };
      if (failAfterChunks) throw new Error("read after terminal event");
      return { done: true };
    },
  };
}

test("CRLF frames and UTF-8 data split across bytes survive streaming", async () => {
  const events = [];
  const stream = ': keepalive\r\nevent: delta\r\ndata: {"text":"中文"}\r\n\r\n' +
    'event: done\r\ndata: {"message":\r\ndata: "完成"}\r\n\r\n';
  await readChatEvents(byteReader(stream, { failAfterChunks: true }), (type, payload) => {
    events.push([type, JSON.parse(JSON.stringify(payload))]);
  });
  assert.deepEqual(events, [["delta", { text: "中文" }], ["done", { message: "完成" }]]);
});

test("an incomplete terminal frame cannot be treated as a completed reply", async () => {
  const events = [];
  await readChatEvents(byteReader('event: done\ndata: {"message":"未完成"}\n'),
    (type, payload) => events.push([type, payload]));
  assert.deepEqual(events, []);
});

test("a completed terminal frame stops before later network failures", async () => {
  const events = [];
  await readChatEvents(byteReader('event: done\ndata: {"message":"完成"}\n\n', { failAfterChunks: true }),
    (type, payload) => events.push([type, payload.message]));
  assert.deepEqual(events, [["done", "完成"]]);
});

test("switching projects stops event delivery immediately", async () => {
  const events = [];
  await readChatEvents(byteReader('event: done\ndata: {"message":"旧项目"}\n\n'),
    (type) => events.push(type), () => false);
  assert.deepEqual(events, []);
});

test("the chat UI accepts CRLF completion even when the next read would fail", async () => {
  const h = harnessContext.makeHarness();
  h.ui.state.project = { id: "project-one" };
  h.ui.setChatRefresh(async () => {});
  h.ui.setLoadProject(async () => {});
  const reader = byteReader('event: delta\r\ndata: {"text":"你好"}\r\n\r\n' +
    'event: done\r\ndata: {"message":"完整答复","tool_calls":[]}\r\n\r\n', { failAfterChunks: true });
  reader.cancel = async () => {};
  reader.releaseLock = () => {};
  h.context.fetch = async () => ({ ok: true, body: { getReader: () => reader } });
  await h.ui.sendChat(null, "测试");
  assert.equal(h.ui.state.messages[1].content, "完整答复");
});

test("network errors warn that billing may be uncertain and never retry automatically", async () => {
  const h = harnessContext.makeHarness();
  h.ui.state.project = { id: "project-one" };
  h.ui.setChatRefresh(async () => {});
  h.ui.setLoadProject(async () => {});
  let requests = 0;
  h.context.fetch = async () => { requests++; throw new TypeError("connection lost"); };
  await h.ui.sendChat(null, "测试");
  const bubbles = h.element("#chatMessages").children.flatMap((row) => row.children);
  assert.ok(bubbles.some((item) => item.innerHTML?.includes("计费状态尚未确认")));
  assert.equal(requests, 1);
});

test("an interrupted send restores the student's input without resending it", async () => {
  const h = harnessContext.makeHarness();
  h.ui.state.project = { id: "project-one" };
  h.ui.setChatRefresh(async () => {});
  h.ui.setLoadProject(async () => h.element("#chatMessages").replaceChildren());
  const input = h.element("#chatInput");
  input.style = {};
  input.scrollHeight = 44;
  input.value = "一段需要保留的申报资料";
  let requests = 0;
  h.context.fetch = async () => { requests++; throw new TypeError("connection lost"); };
  await h.ui.sendChat(null);
  assert.equal(input.value, "一段需要保留的申报资料");
  assert.equal(requests, 1);
  const bubbles = h.element("#chatMessages").children.flatMap(row => row.children);
  assert.ok(bubbles.some(item => item.innerHTML?.includes("计费状态尚未确认")));
});

test("a silent connection times out, restores input and never resends", async () => {
  const h = harnessContext.makeHarness();
  h.ui.state.project = { id: "project-one" };
  h.ui.setChatRefresh(async () => {});
  h.ui.setLoadProject(async () => { throw new Error("server unavailable"); });
  const timers = new Map(); let id = 0;
  h.context.setTimeout = (callback, delay) => { timers.set(++id, { callback, delay }); return id; };
  h.context.clearTimeout = key => timers.delete(key);
  let requests = 0;
  h.context.fetch = async (_url, options) => {
    requests++;
    return await new Promise((_, reject) => options.signal.addEventListener("abort", () => reject(new Error("aborted"))));
  };
  const input = h.element("#chatInput");
  input.value = "需要保留的项目材料";
  const running = h.ui.sendChat(null);
  const timeout = [...timers.values()].find(item => item.delay === 180000);
  assert.ok(timeout);
  timeout.callback();
  await running;
  assert.equal(requests, 1);
  assert.equal(input.value, "需要保留的项目材料");
  assert.equal(h.ui.state.chatSending, false);
  const bubbles = h.element("#chatMessages").children.flatMap(row => row.children);
  assert.ok(bubbles.some(item => item.innerHTML?.includes("计费状态尚未确认")));
});

test("a stalled recovery refresh does not keep the chat locked", async () => {
  const h = harnessContext.makeHarness();
  h.ui.state.project = { id: "project-one" };
  h.ui.setChatRefresh(async () => {});
  h.ui.setLoadProject(() => new Promise(() => {}));
  const timers = new Map(); let id = 0;
  h.context.setTimeout = (callback, delay) => { timers.set(++id, { callback, delay }); return id; };
  h.context.clearTimeout = key => timers.delete(key);
  h.context.fetch = async () => { throw new Error("network lost"); };
  const input = h.element("#chatInput"); input.value = "申报要求";
  const running = h.ui.sendChat(null);
  await new Promise(resolve => setImmediate(resolve));
  const timeout = [...timers.values()].find(item => item.delay === 5000);
  assert.ok(timeout);
  timeout.callback();
  await running;
  assert.equal(input.value, "申报要求");
  assert.equal(h.ui.state.chatSending, false);
});

test("a server timeout message keeps the input and never retries", async () => {
  const h = harnessContext.makeHarness();
  h.ui.state.project = { id: "project-one" };
  h.ui.setChatRefresh(async () => {});
  h.ui.setLoadProject(async () => h.element("#chatMessages").replaceChildren());
  const input = h.element("#chatInput");
  input.style = {};
  input.scrollHeight = 44;
  input.value = "这是需要保留的项目简介要求";
  let requests = 0;
  const event = 'event: error\ndata: {"error":"模型响应超时，暂未收到完整回复。请先查看对话结果，再决定是否手动重试；系统不会自动重复发送。"}\n\n';
  h.context.fetch = async () => { requests++; return { ok: true, body: { getReader: () => byteReader(event) } }; };
  await h.ui.sendChat(null);
  assert.equal(input.value, "这是需要保留的项目简介要求");
  assert.equal(requests, 1);
  const bubbles = h.element("#chatMessages").children.flatMap(row => row.children);
  assert.ok(bubbles.some(item => item.innerHTML?.includes("模型响应超时")));
  assert.ok(!bubbles.some(item => item.innerHTML?.includes("timed out")));
});

test("recovery preserves a new message being typed and retains the interrupted text", async () => {
  const h = harnessContext.makeHarness();
  h.ui.state.project = { id: "project-one" };
  h.ui.setChatRefresh(async () => {});
  h.ui.setLoadProject(async () => h.element("#chatMessages").replaceChildren());
  const input = h.element("#chatInput");
  input.style = {};
  input.scrollHeight = 44;
  input.value = "此前的申报资料";
  let rejectRequest;
  h.context.fetch = () => new Promise((_, reject) => { rejectRequest = reject; });
  const send = h.ui.sendChat(null);
  input.value = "我正在补充另一段内容";
  rejectRequest(new TypeError("connection lost"));
  await send;
  assert.equal(input.value, "我正在补充另一段内容");
  const children = h.element("#chatMessages").children.flatMap(row => row.children);
  assert.ok(children.some(item => item.textContent === "此前的申报资料"));
  assert.ok(children.some(item => item.children?.some(button => button.textContent === "复制上次输入")));
});

test("reload and error handling do not display the same recovery twice", async () => {
  const h = harnessContext.makeHarness();
  h.ui.state.project = { id: "project-one" };
  h.ui.setChatRefresh(async () => {});
  h.ui.setLoadProject(async () => {
    h.element("#chatMessages").replaceChildren();
    h.ui.restoreInterruptedChatMessage("project-one");
  });
  const input = h.element("#chatInput");
  input.style = {};
  input.value = "此前的申报资料";
  let rejectRequest;
  h.context.fetch = () => new Promise((_, reject) => { rejectRequest = reject; });
  const send = h.ui.sendChat(null);
  input.value = "正在输入新内容";
  rejectRequest(new TypeError("connection lost"));
  await send;
  const children = h.element("#chatMessages").children.flatMap(row => row.children);
  assert.equal(children.filter(item => item.textContent === "此前的申报资料").length, 1);
});

test("two interrupted sends do not overwrite each other's recoverable text", async () => {
  const h = harnessContext.makeHarness();
  h.ui.state.project = { id: "project-one" };
  h.ui.setChatRefresh(async () => {});
  h.ui.setLoadProject(async () => h.element("#chatMessages").replaceChildren());
  const input = h.element("#chatInput");
  input.style = {};
  input.scrollHeight = 44;
  let rejectRequest;
  h.context.fetch = () => new Promise((_, reject) => { rejectRequest = reject; });
  input.value = "第一段";
  const first = h.ui.sendChat(null);
  input.value = "第二段";
  rejectRequest(new TypeError("connection lost"));
  await first;
  const second = h.ui.sendChat(null);
  rejectRequest(new TypeError("connection lost"));
  await second;
  const children = h.element("#chatMessages").children.flatMap(row => row.children);
  assert.equal(input.value, "第一段");
  assert.ok(children.some(item => item.textContent === "第二段"));
});

test("an interrupted message remains scoped to its original project", async () => {
  const h = harnessContext.makeHarness();
  h.ui.state.project = { id: "first" };
  h.ui.setChatRefresh(async () => {});
  const input = h.element("#chatInput");
  input.style = {};
  input.scrollHeight = 44;
  input.value = "只属于第一个项目的内容";
  let rejectRequest;
  h.context.fetch = () => new Promise((_, reject) => { rejectRequest = reject; });
  const send = h.ui.sendChat(null);
  h.ui.state.project = { id: "second" };
  rejectRequest(new TypeError("connection lost"));
  await send;
  h.ui.restoreInterruptedChatMessage("second");
  assert.equal(input.value, "");
  h.ui.state.project = { id: "first" };
  h.ui.restoreInterruptedChatMessage("first");
  assert.equal(input.value, "只属于第一个项目的内容");
});

test("switching accounts clears recovered input and cannot restore previous account's text", async () => {
  const h = harnessContext.makeHarness();
  let authCallback;
  h.context.window.supabase = { createClient: () => ({ auth: {
    getSession: async () => ({ data: { session: null }, error: null }),
    onAuthStateChange: callback => {
      authCallback = callback;
      return { data: { subscription: { unsubscribe() {} } } };
    },
  } }) };
  await h.ui.initializeCloudAuth({ cloud_mode: true });
  h.ui.state.authSession = { user: { id: "account-A" } };
  h.ui.state.appStarted = true;
  h.ui.state.project = { id: "first" };
  h.ui.setChatRefresh(async () => {});
  h.ui.setLoadProject(async () => h.element("#chatMessages").replaceChildren());
  const input = h.element("#chatInput");
  input.style = {};
  input.scrollHeight = 44;
  input.value = "账号 A 的个人材料";
  let rejectRequest;
  h.context.fetch = () => new Promise((_, reject) => { rejectRequest = reject; });
  const send = h.ui.sendChat(null);
  input.value = "账号 A 的新输入";
  rejectRequest(new TypeError("connection lost"));
  await send;
  authCallback("SIGNED_IN", { user: { id: "account-B" } });
  assert.equal(input.value, "");
  assert.equal(h.element("#chatMessages").children.length, 0);
  assert.equal(h.ui.state.project, null);
  h.ui.state.project = { id: "first" };
  h.ui.restoreInterruptedChatMessage("first");
  assert.equal(input.value, "");
});

test("a late error after account switch does not restore the old account's input", async () => {
  const h = harnessContext.makeHarness();
  h.ui.state.project = { id: "first" };
  h.ui.state.authSession = { user: { id: "account-A" } };
  h.ui.setChatRefresh(async () => {});
  h.ui.setLoadProject(async () => {});
  const input = h.element("#chatInput");
  input.style = {};
  input.value = "账号 A 的个人材料";
  let rejectRequest;
  h.context.fetch = () => new Promise((_, reject) => { rejectRequest = reject; });
  const send = h.ui.sendChat(null);
  h.ui.state.authSession = { user: { id: "account-B" } };
  rejectRequest(new TypeError("connection lost"));
  await send;
  h.ui.restoreInterruptedChatMessage("first");
  assert.equal(input.value, "");
});

test("signing out clears recovered and pending input", async () => {
  const h = harnessContext.makeHarness();
  let authCallback;
  h.context.window.supabase = { createClient: () => ({ auth: {
    getSession: async () => ({ data: { session: null }, error: null }),
    onAuthStateChange: callback => {
      authCallback = callback;
      return { data: { subscription: { unsubscribe() {} } } };
    },
  } }) };
  await h.ui.initializeCloudAuth({ cloud_mode: true });
  h.ui.state.authSession = { user: { id: "account-A" } };
  h.ui.state.appStarted = true;
  h.ui.state.project = { id: "first" };
  h.ui.setChatRefresh(async () => {});
  h.ui.setLoadProject(async () => h.element("#chatMessages").replaceChildren());
  const input = h.element("#chatInput");
  input.style = {};
  input.scrollHeight = 44;
  input.value = "需要保护的个人材料";
  let rejectRequest;
  h.context.fetch = () => new Promise((_, reject) => { rejectRequest = reject; });
  const send = h.ui.sendChat(null);
  input.value = "正在填写的新内容";
  rejectRequest(new TypeError("connection lost"));
  await send;
  authCallback("SIGNED_OUT", null);
  assert.equal(input.value, "");
  assert.equal(h.element("#chatMessages").children.length, 0);
  h.ui.state.project = { id: "first" };
  h.ui.restoreInterruptedChatMessage("first");
  assert.equal(input.value, "");
});

test("a request started before logout cannot restore input after the same account signs in again", async () => {
  const h = harnessContext.makeHarness();
  let authCallback;
  h.context.window.supabase = { createClient: () => ({ auth: {
    getSession: async () => ({ data: { session: null }, error: null }),
    onAuthStateChange: callback => {
      authCallback = callback;
      return { data: { subscription: { unsubscribe() {} } } };
    },
  } }) };
  await h.ui.initializeCloudAuth({ cloud_mode: true });
  h.ui.state.authSession = { user: { id: "account-A" } };
  h.ui.state.appStarted = true;
  h.ui.state.project = { id: "first" };
  h.ui.setChatRefresh(async () => {});
  h.ui.setLoadProject(async () => {});
  const input = h.element("#chatInput");
  input.style = {};
  input.value = "退出前的个人材料";
  let rejectRequest;
  h.context.fetch = () => new Promise((_, reject) => { rejectRequest = reject; });
  const send = h.ui.sendChat(null);
  authCallback("SIGNED_OUT", null);
  authCallback("SIGNED_IN", { user: { id: "account-A" } });
  h.ui.state.project = { id: "first" };
  rejectRequest(new TypeError("connection lost"));
  await send;
  h.ui.restoreInterruptedChatMessage("first");
  assert.equal(input.value, "");
});

test("a slow project response cannot replace the project selected later", async () => {
  const h = harnessContext.makeHarness();
  let finishFirst;
  h.ui.setApi((url) => url.endsWith("/first")
    ? new Promise(resolve => { finishFirst = resolve; })
    : Promise.resolve({ id: "second", state: {}, messages: [] }));
  const first = h.ui.loadProject("first");
  await h.ui.loadProject("second");
  finishFirst({ id: "first", state: {}, messages: [] });
  await first;
  assert.equal(h.ui.state.project.id, "second");
});

test("a pending project switch blocks an old chat reply from reopening its project", async () => {
  const h = harnessContext.makeHarness();
  h.ui.state.project = { id: "first" };
  h.ui.setChatRefresh(async () => {});
  let finishChat;
  h.context.fetch = () => new Promise(resolve => { finishChat = resolve; });
  const chat = h.ui.sendChat(null, "测试");
  let finishProject;
  h.ui.setApi(() => new Promise(resolve => { finishProject = resolve; }));
  const switchProject = h.ui.loadProject("second");
  const reader = byteReader('event: done\ndata: {"message":"旧项目回复"}\n\n');
  reader.cancel = async () => {};
  reader.releaseLock = () => {};
  finishChat({ ok: true, body: { getReader: () => reader } });
  await chat;
  finishProject({ id: "second", state: {}, messages: [] });
  await switchProject;
  assert.equal(h.ui.state.project.id, "second");
  assert.equal(h.ui.state.messages.length, 0);
});

test("deleting the previous project does not cancel a pending project switch", async () => {
  const h = harnessContext.makeHarness();
  h.ui.state.project = { id: "first", title: "First" };
  h.ui.setChatRefresh(async () => {});
  h.context.confirm = () => true;
  let finishDelete, finishProject;
  h.ui.setApi((url, options) => options?.method === "DELETE"
    ? new Promise(resolve => { finishDelete = resolve; })
    : new Promise(resolve => { finishProject = resolve; }));
  const deletion = h.ui.deleteCurrentProject();
  const switchProject = h.ui.loadProject("second");
  finishDelete({});
  await deletion;
  assert.equal(h.ui.state.project, null);
  finishProject({ id: "second", state: {}, messages: [] });
  await switchProject;
  assert.equal(h.ui.state.project.id, "second");
});

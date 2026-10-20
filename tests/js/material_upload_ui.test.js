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
  replaceChildren(...children) { this.children = children; this.textContent = ""; }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  closest() { return null; }
  remove() { this.removed = true; }
  showModal() { this.open = true; }
  close() { this.open = false; this.listeners.close?.(); }
}

function harness() {
  const elements = new Map();
  const revoked = [];
  const created = [];
  const requests = [];
  const timers = new Map();
  let nextTimer = 1;
  const document = {
    querySelector(selector) {
      if (!elements.has(selector)) elements.set(selector, new Element());
      return elements.get(selector);
    },
    querySelectorAll: () => [],
    createElement: (tag) => new Element(tag),
    addEventListener() {},
  };
  const storage = new Map();
  const session = new Map();
  const context = vm.createContext({
    document,
    window: { location: { origin: "https://workbench.example.test" } },
    localStorage: { getItem: (k) => storage.get(k) || null, setItem: (k,v) => storage.set(k,v), removeItem: (k) => storage.delete(k) },
    sessionStorage: { getItem: (k) => session.get(k) || null, setItem: (k,v) => session.set(k,v), removeItem: (k) => session.delete(k) },
    Headers,
    Blob,
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
      renderPrivacyNotice, showModelStatus, updateTemplateQuickActions,
      syncAuthControls, initializeCloudAuth, submitAuthForm,
      readPublicCache, writePublicCache, sameOriginAuthFetch, storeLlmConfig, loadCloudModelConfig, saveSelectedLlmConfig,
      sendChat, syncChatControls,
      setApi(fn) { api = fn; },
      setLoadProject(fn) { loadProject = fn; },
      setChatRefresh(fn) { refreshProjects = fn; loadUserBalance = fn; },
    };
  })();`);
  vm.runInContext(source, context, { filename: file });
  return {
    ui: context.ui, context, requests, revoked, created, timers,
    element: (selector) => document.querySelector(selector),
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

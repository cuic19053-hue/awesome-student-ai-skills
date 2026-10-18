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
  showModal() { this.open = true; }
  close() { this.open = false; this.listeners.close?.(); }
}

function harness() {
  const elements = new Map();
  const revoked = [];
  const created = [];
  const requests = [];
  const document = {
    querySelector(selector) {
      if (!elements.has(selector)) elements.set(selector, new Element());
      return elements.get(selector);
    },
    querySelectorAll: () => [],
    createElement: (tag) => new Element(tag),
    addEventListener() {},
  };
  const context = vm.createContext({
    document,
    localStorage: { removeItem() {} },
    sessionStorage: { getItem: () => null },
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
  });
  const file = resolve(__dirname, "../../server/static/app.js");
  const source = readFileSync(file, "utf8").replace(/\}\)\(\);\s*$/, `
    globalThis.ui = {
      state, renderUploadResult, renderDocuments, previewDocument,
      clearDocumentPreview, fetchDocumentBlob, uploadFiles,
      setApi(fn) { api = fn; },
      setLoadProject(fn) { loadProject = fn; },
    };
  })();`);
  vm.runInContext(source, context, { filename: file });
  return {
    ui: context.ui, context, requests, revoked, created,
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

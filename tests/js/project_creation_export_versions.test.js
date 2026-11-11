const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { resolve, dirname } = require("node:path");
const { test } = require("node:test");
const vm = require("node:vm");

const harnessFile = resolve(__dirname, "material_upload_ui.test.js");
const original = readFileSync(harnessFile, "utf8");
const context = vm.createContext({
  require, __dirname: dirname(harnessFile), Headers, AbortController, Blob, TextEncoder, TextDecoder, URL,
});
const setup = original.slice(0, original.indexOf("\nconst doc = {"))
  .replace("exportDoc, fetchExportBlob,", "completeProjectCreation, openUsageDialog, exportDoc, fetchExportBlob,");
vm.runInContext(setup + "\nglobalThis.makeHarness = harness;", context);

function ready() {
  const h = context.makeHarness();
  h.ui.state.project = { id: "a".repeat(32), state: {}, outline: [{ id: "letter", title: "申请书" }],
    sections: { letter: "此前保存的正文" } };
  h.ui.state.outline = h.ui.state.project.outline;
  h.ui.setChatRefresh(async () => {});
  return h;
}

function descendants(node) {
  return [node, ...node.children.flatMap(descendants)];
}

test("candidate creation and new chat share a single in-flight creation", async () => {
  const h = ready();
  const calls = [];
  let rejectRequest;
  h.ui.setApi((url) => { calls.push(url); return new Promise((_, reject) => { rejectRequest = reject; }); });
  const first = h.ui.completeProjectCreation({ skill_id: "challenge-cup" });
  await h.ui.completeProjectCreation({ skill_id: "national-scholarship" });
  await h.ui.startGeneralChat();
  assert.deepEqual(calls, ["/api/projects"]);
  rejectRequest(new Error("网络中断"));
  await first;
  const retry = h.ui.startGeneralChat();
  assert.deepEqual(calls, ["/api/projects", "/api/projects/conversation"]);
  rejectRequest(new Error("网络中断"));
  await retry;
});

test("editing a section revokes the generated download link", async () => {
  const h = ready();
  h.ui.setApi(async (url) => url.endsWith("chat-drafts") ? { items: [] }
    : { download_url: `/api/projects/${h.ui.state.project.id}/download` });
  await h.ui.exportDoc();
  assert.equal(h.element("#exportResult").children.length, 2);
  h.ui.renderSections();
  const editor = descendants(h.element("#draftSections")).find(node => node.tagName === "textarea");
  editor.value = "刚更正的正文";
  editor.listeners.input();
  assert.equal(h.element("#exportResult").children.length, 0);
  assert.ok(h.revoked.includes("blob:preview-1"));
});

test("an edit during export prevents the old response from downloading", async () => {
  const h = ready();
  h.ui.renderSections();
  const editor = descendants(h.element("#draftSections")).find(node => node.tagName === "textarea");
  let resolveExport;
  h.ui.setApi(async (url) => url.endsWith("chat-drafts") ? { items: [] }
    : new Promise(resolve => { resolveExport = resolve; }));
  const exporting = h.ui.exportDoc();
  while (!resolveExport) await Promise.resolve();
  editor.value = "导出期间学生继续输入的文字";
  editor.listeners.input();
  resolveExport({ download_url: `/api/projects/${h.ui.state.project.id}/download` });
  await exporting;
  assert.equal(h.requests.length, 0, "the stale export must not even fetch its Word bytes");
  assert.equal(h.element("#exportResult").children.length, 0);
});

test("usage report treats project and model strings as text", async () => {
  const h = ready();
  const malicious = '<img src=x onerror="alert(1)">';
  h.ui.setApi(async () => ({ stats: { by_model: [{ model: malicious, count: 1, tokens: 5 }] },
    logs: [{ project_title: malicious, model: malicious }] }));
  await h.ui.openUsageDialog();
  const tag = h.element("#usageModelTags").children[0];
  assert.ok(tag.textContent.includes(malicious));
  assert.equal(tag.innerHTML, undefined);
  const cells = h.element("#usageTableBody").children[0].children;
  assert.equal(cells[1].textContent, malicious);
  assert.equal(cells[3].textContent, malicious);
});

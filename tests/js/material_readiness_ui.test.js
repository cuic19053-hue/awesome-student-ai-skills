const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { resolve } = require("node:path");
const { test } = require("node:test");
const vm = require("node:vm");

test("material generation stays on the old chain until its worker is ready", () => {
  const context = vm.createContext({ window: {} });
  const source = readFileSync(resolve(__dirname, "../../server/static/material.js"), "utf8")
    .replace("window.MaterialPilot =", `
      globalThis.configure = (config, id, value) => { host = config; projectId = id; data = value; };
      window.MaterialPilot =`);
  vm.runInContext(source, context);
  const state = { project: { id: "one", material: { enabled: true } } };
  context.configure({ state }, "one", { worker_ready: false });
  assert.equal(context.window.MaterialPilot.active(), false);
  context.configure({ state }, "one", { worker_ready: true });
  assert.equal(context.window.MaterialPilot.active(), true);
  state.project = { id: "two", material: { enabled: true } };
  assert.equal(context.window.MaterialPilot.active(), false);
  state.project = { id: "one", material: { enabled: false } };
  assert.equal(context.window.MaterialPilot.active(), false);
});

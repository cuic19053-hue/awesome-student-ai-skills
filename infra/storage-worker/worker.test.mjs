import test from "node:test";
import assert from "node:assert/strict";
import { handleRequest } from "./worker.mjs";

const env = {
  APP_ORIGIN: "https://agent.example.test",
  SUPABASE_URL: "https://fixed.supabase.co",
  SUPABASE_PUBLISHABLE_KEY: "publishable-only",
  UPLOAD_SESSION_SECRET: "test-secret-that-is-longer-than-32-characters",
  MAX_UPLOAD_BYTES: "50000000",
};
const project = "a".repeat(32), doc = "b".repeat(32);
const object = `alice/${project}/${doc}.pdf`;
const meta = (path = object) => Object.entries({
  bucketName: "stardust-project-files", objectName: path, contentType: "application/pdf",
}).map(([k, v]) => `${k} ${btoa(v)}`).join(",");
function request(path, method = "POST", extra = {}, body) {
  const headers = { Authorization: "Bearer alice-jwt", ...extra };
  return new Request(`${env.APP_ORIGIN}/uploads/${path}`, { method, headers, body });
}
function creation(extra = {}, path = object) {
  return request("resumable", "POST", {
    "Tus-Resumable": "1.0.0", "Upload-Length": String(20 * 1024 * 1024),
    "Upload-Metadata": meta(path), ...extra,
  });
}
function upstream({ user = "alice", projectVisible = true, storage, location } = {}) {
  const calls = [];
  const fetcher = async (url, init) => {
    calls.push({ url, init });
    if (url.endsWith("/auth/v1/user")) return Response.json({ id: user });
    if (url.includes("/rest/v1/projects?")) return Response.json(projectVisible ? [{ id: project }] : []);
    if (storage) return storage(url, init);
    return new Response(null, { status: 201,
      headers: { Location: location || "/storage/v1/upload/resumable/upload-id" } });
  };
  return { fetcher, calls };
}
async function session() {
  const result = await handleRequest(creation(), env, upstream().fetcher);
  assert.equal(result.status, 201);
  return result.headers.get("Location");
}

test("unauthenticated and cross-origin requests never reach Supabase", async () => {
  const u = upstream();
  assert.equal((await handleRequest(request("resumable", "POST", { Authorization: "" }), env, u.fetcher)).status, 401);
  assert.equal((await handleRequest(creation({ Origin: "https://evil.test" }), env, u.fetcher)).status, 403);
  assert.equal(u.calls.length, 0);
});
test("only fixed routes and supported methods are allowed", async () => {
  const u = upstream();
  assert.equal((await handleRequest(request("../api/proxy"), env, u.fetcher)).status, 404);
  assert.equal((await handleRequest(request("resumable", "PUT"), env, u.fetcher)).status, 405);
  assert.equal((await handleRequest(new Request(`${env.APP_ORIGIN}/uploads/resumable?target=https://evil.test`), env, u.fetcher)).status, 400);
  assert.equal(u.calls.length, 0);
});
test("20 MiB upload creates a same-origin signed continuation URL", async () => {
  const u = upstream();
  const res = await handleRequest(creation({ Cookie: "must-not-forward=1" }), env, u.fetcher);
  assert.equal(res.status, 201);
  assert.ok(res.headers.get("Location").startsWith(`${env.APP_ORIGIN}/uploads/resumable/`));
  assert.equal(res.headers.get("Cache-Control"), "private, no-store");
  const call = u.calls.at(-1);
  assert.equal(call.init.headers.get("Cookie"), null);
  assert.equal(call.init.headers.get("Authorization"), "Bearer alice-jwt");
  assert.equal(call.init.headers.get("x-upsert"), "false");
  assert.match(call.init.headers.get("Upload-Metadata"), /contentType YXBwbGljYXRpb24vcGRm/);
});
test("file limit, empty files, invalid metadata and another user's directory are rejected", async () => {
  const u = upstream();
  assert.equal((await handleRequest(creation({ "Upload-Length": "50000001" }), env, u.fetcher)).status, 413);
  assert.equal((await handleRequest(creation({ "Upload-Length": "0" }), env, u.fetcher)).status, 413);
  assert.equal((await handleRequest(creation({ "Upload-Metadata": "bad %%%" }), env, u.fetcher)).status, 400);
  assert.equal((await handleRequest(creation({}, object.replace("alice/", "bob/")), env, u.fetcher)).status, 403);
  assert.equal((await handleRequest(creation({}, object.replace(".pdf", ".exe")), env, u.fetcher)).status, 403);
  assert.ok(u.calls.every(call => call.url.endsWith("/auth/v1/user")));
});
test("a user's own directory does not authorize a different user's project", async () => {
  const u = upstream({ projectVisible: false });
  assert.equal((await handleRequest(creation(), env, u.fetcher)).status, 403);
  assert.equal(u.calls.length, 2);
});
test("upstream redirects and off-origin continuation addresses cannot leak credentials", async () => {
  let u = upstream({ location: "https://evil.test/storage/v1/upload/resumable/stolen" });
  assert.equal((await handleRequest(creation(), env, u.fetcher)).status, 502);
  u = upstream({ storage: () => new Response(null, { status: 302, headers: { Location: "https://evil.test" } }) });
  assert.equal((await handleRequest(creation(), env, u.fetcher)).status, 502);
  assert.ok(u.calls.every(call => call.init.redirect === "manual"));
});
test("a 6 MiB chunk bypasses Vercel and is streamed without buffering", async () => {
  const location = await session();
  const bytes = new Uint8Array(6 * 1024 * 1024).fill(73);
  let received;
  const u = upstream({ storage: async (_url, init) => {
    received = new Uint8Array(await new Response(init.body).arrayBuffer());
    return new Response(null, { status: 204, headers: { "Upload-Offset": String(bytes.length) } });
  } });
  const res = await handleRequest(new Request(location, {
    method: "PATCH", headers: { Authorization: "Bearer alice-jwt", "Content-Type": "application/offset+octet-stream",
      "Content-Length": String(bytes.length), "Upload-Offset": "0" }, body: bytes,
  }), env, u.fetcher);
  assert.equal(res.status, 204);
  assert.deepEqual(received, bytes);
  assert.equal(res.headers.get("Upload-Offset"), String(bytes.length));
  assert.ok(u.calls.at(-1).url.startsWith(`${env.SUPABASE_URL}/storage/v1/upload/resumable/`));
});
test("HEAD recovers the committed offset after a lost response", async () => {
  const location = await session();
  const u = upstream({ storage: () => new Response(null, {
    status: 200, headers: { "Upload-Offset": "6291456", "Upload-Length": "20971520" },
  }) });
  const res = await handleRequest(new Request(location, {
    method: "HEAD", headers: { Authorization: "Bearer alice-jwt" },
  }), env, u.fetcher);
  assert.equal(res.status, 200);
  assert.equal(res.headers.get("Upload-Offset"), "6291456");
  assert.equal(await res.text(), "");
});
test("continuation requires the same user AND a valid signature", async () => {
  const location = await session();
  const u = upstream({ user: "bob" });
  const r = new Request(location, { method: "HEAD", headers: { Authorization: "Bearer bob-jwt" } });
  assert.equal((await handleRequest(r, env, u.fetcher)).status, 403);
  const tampered = location.slice(0, -5) + "xxxxx";
  assert.equal((await handleRequest(new Request(tampered, {
    method: "HEAD", headers: { Authorization: "Bearer alice-jwt" },
  }), env, upstream().fetcher)).status, 403);
});
test("expired sessions and non-6-MiB chunks are rejected", async () => {
  const location = await session();
  const u = upstream();
  const response = await handleRequest(new Request(location, {
    method: "PATCH", headers: { Authorization: "Bearer alice-jwt", "Upload-Offset": "0",
      "Content-Length": "2097152", "Content-Type": "application/offset+octet-stream" },
    body: new Uint8Array(2 * 1024 * 1024),
  }), env, u.fetcher);
  assert.equal(response.status, 400);
  const now = Date.now;
  Date.now = () => now() + 25 * 3600_000;
  try {
    assert.equal((await handleRequest(new Request(location, {
      method: "HEAD", headers: { Authorization: "Bearer alice-jwt" },
    }), env, u.fetcher)).status, 403);
  } finally { Date.now = now; }
});
test("large private downloads are streamed and range headers survive", async () => {
  const u = upstream({ storage: (_url, init) => {
    assert.equal(init.headers.get("Range"), "bytes=0-5");
    return new Response("abcdef", { status: 206, headers: { "Content-Range": "bytes 0-5/20000000" } });
  } });
  const res = await handleRequest(request(`object/${object}`, "GET", { Range: "bytes=0-5" }), env, u.fetcher);
  assert.equal(res.status, 206);
  assert.equal(await res.text(), "abcdef");
  assert.equal(res.headers.get("Content-Range"), "bytes 0-5/20000000");
  assert.equal((await handleRequest(request(`object/${object.replace("alice/", "bob/")}`, "GET"), env, u.fetcher)).status, 403);
});
test("an outage produces a sanitized error rather than leaking upstream details", async () => {
  const res = await handleRequest(creation(), env, async () => { throw new Error("secret-token-and-internal-stack"); });
  assert.equal(res.status, 502);
  assert.doesNotMatch(await res.text(), /secret-token/);
});

for (const size of [5_000_000, 20_000_000, 49_999_999]) {
  test(`${size} byte upload completes intact; a lost chunk response can recover using HEAD`, async () => {
    const original = new Uint8Array(size);
    for (let i = 0; i < size; i++) original[i] = i % 251;
    const output = new Uint8Array(size);
    let offset = 0, lost = false;
    const u = upstream({ storage: async (_url, init) => {
      if (init.method === "POST") return new Response(null, {
        status: 201, headers: { Location: "/storage/v1/upload/resumable/integrity-session" },
      });
      if (init.method === "HEAD") return new Response(null, {
        headers: { "Upload-Offset": String(offset), "Upload-Length": String(size) },
      });
      assert.equal(Number(init.headers.get("Upload-Offset")), offset);
      const data = new Uint8Array(await new Response(init.body).arrayBuffer());
      output.set(data, offset);
      offset += data.length;
      if (size === 20_000_000 && !lost) { lost = true; throw new Error("lost response after commit"); }
      return new Response(null, { status: 204, headers: { "Upload-Offset": String(offset) } });
    } });
    const created = await handleRequest(creation({ "Upload-Length": String(size) }), env, u.fetcher);
    const location = created.headers.get("Location");
    let clientOffset = 0;
    while (clientOffset < size) {
      const body = original.slice(clientOffset, Math.min(clientOffset + 6 * 1024 * 1024, size));
      const res = await handleRequest(new Request(location, {
        method: "PATCH", body, headers: { Authorization: "Bearer alice-jwt",
          "Upload-Offset": String(clientOffset), "Content-Length": String(body.length),
          "Content-Type": "application/offset+octet-stream" },
      }), env, u.fetcher);
      if (res.status === 502) {
        const head = await handleRequest(new Request(location, {
          method: "HEAD", headers: { Authorization: "Bearer alice-jwt" },
        }), env, u.fetcher);
        clientOffset = Number(head.headers.get("Upload-Offset"));
      } else {
        assert.equal(res.status, 204);
        clientOffset = Number(res.headers.get("Upload-Offset"));
      }
    }
    assert.equal(clientOffset, size);
    const hash = async bytes => Buffer.from(await crypto.subtle.digest("SHA-256", bytes)).toString("hex");
    assert.equal(await hash(original), await hash(output));
  });
}

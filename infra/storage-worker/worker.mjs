// Only file traffic is routed here. Never use a service-role key or forward cookies.
const PREFIX = "/uploads/";
const TUS_PATH = "/storage/v1/upload/resumable";
const BUCKET = "stardust-project-files";
const CHUNK_BYTES = 6 * 1024 * 1024;
const MAX_BYTES = 50_000_000;
const OBJECT_RE = /^([a-zA-Z0-9-]+)\/([a-f0-9]{32})\/([a-f0-9]{32})\.(docx|pdf|txt|md|png|jpg|jpeg|webp)$/;
const MIME = {
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  pdf: "application/pdf", txt: "text/plain", md: "text/markdown",
  png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg", webp: "image/webp",
};
const enc = new TextEncoder();
const dec = new TextDecoder("utf-8", { fatal: true });

function failure(status, message) {
  return new Response(JSON.stringify({ message }), {
    status, headers: { "Content-Type": "application/json", "Cache-Control": "private, no-store" },
  });
}

function base64url(bytes) {
  let text = "";
  for (const b of bytes) text += String.fromCharCode(b);
  return btoa(text).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
}

function unbase64url(text) {
  return Uint8Array.from(atob(text.replaceAll("-", "+").replaceAll("_", "/")), c => c.charCodeAt(0));
}

async function signingKey(secret) {
  return crypto.subtle.importKey(
    "raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign", "verify"],
  );
}

async function seal(value, secret) {
  const data = base64url(enc.encode(JSON.stringify(value)));
  const sig = await crypto.subtle.sign("HMAC", await signingKey(secret), enc.encode(data));
  return `${data}.${base64url(new Uint8Array(sig))}`;
}

async function unseal(text, secret) {
  try {
    if (text.length > 6000) return null;
    const [data, sig, extra] = text.split(".");
    if (!data || !sig || extra !== undefined) return null;
    if (!await crypto.subtle.verify(
      "HMAC", await signingKey(secret), unbase64url(sig), enc.encode(data),
    )) return null;
    const value = JSON.parse(dec.decode(unbase64url(data)));
    return value.exp > Date.now() ? value : null;
  } catch { return null; }
}

function metadata(header) {
  try {
    const fields = {};
    if (!header || header.length > 4000) throw new Error();
    for (const item of header.split(",")) {
      const [key, value, extra] = item.trim().split(/\s+/);
      if (!["bucketName", "objectName", "contentType", "cacheControl"].includes(key)
          || !value || extra || Object.hasOwn(fields, key)) throw new Error();
      fields[key] = dec.decode(Uint8Array.from(atob(value), c => c.charCodeAt(0)));
    }
    return fields;
  } catch { throw new Error("上传信息无效"); }
}

function upstreamUrl(value, origin) {
  const url = new URL(value, origin);
  if (url.origin !== origin || !url.pathname.startsWith(`${TUS_PATH}/`)
      || url.username || url.password || url.hash || url.search) throw new Error("续传地址无效");
  return url;
}

async function hasCreationBytes(request) {
  if (Number(request.headers.get("Content-Length") || "0") !== 0) return true;
  if (!request.body) return false;
  // Workers can expose a non-null stream for a browser's zero-byte POST.
  // Check actual bytes, not stream presence, and never buffer an upload.
  const reader = request.body.getReader();
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) return false;
      if (value.byteLength) {
        await reader.cancel();
        return true;
      }
    }
  } finally {
    reader.releaseLock();
  }
}

async function handle(request, env, fetcher) {
  const url = new URL(request.url);
  if (url.origin !== env.APP_ORIGIN || !url.pathname.startsWith(PREFIX))
    return failure(404, "上传地址不存在");
  const origin = request.headers.get("Origin");
  if (origin && origin !== env.APP_ORIGIN) return failure(403, "不允许跨站上传");
  if (url.search) return failure(400, "上传地址无效");
  const method = request.method;
  if (url.pathname === `${PREFIX}health` && method === "GET") {
    if (!env.SUPABASE_PUBLISHABLE_KEY || !env.UPLOAD_SESSION_SECRET
        || env.UPLOAD_SESSION_SECRET.length < 32) return failure(503, "上传服务配置未完成");
    return Response.json({ status: "ok", max_upload_bytes: Math.min(MAX_BYTES, Number(env.MAX_UPLOAD_BYTES) || MAX_BYTES) },
      { headers: { "Cache-Control": "no-store" } });
  }
  const isCreate = url.pathname === `${PREFIX}resumable`;
  const isSession = url.pathname.startsWith(`${PREFIX}resumable/`);
  const isObject = url.pathname.startsWith(`${PREFIX}object/`);
  if (!(isCreate || isSession || isObject)) return failure(404, "上传地址不存在");
  if ((isCreate && !["POST", "OPTIONS"].includes(method))
      || (isSession && !["HEAD", "PATCH", "OPTIONS"].includes(method))
      || (isObject && !["GET", "HEAD", "OPTIONS"].includes(method)))
    return failure(405, "不支持此操作");
  if (method === "OPTIONS") return new Response(null, {
    status: 204, headers: { "Tus-Resumable": "1.0.0", "Tus-Version": "1.0.0",
      "Tus-Extension": "creation", "Cache-Control": "no-store" },
  });
  const auth = request.headers.get("Authorization") || "";
  if (!/^Bearer \S+$/.test(auth)) return failure(401, "请先登录后上传材料");
  const sb = new URL(env.SUPABASE_URL);
  if (sb.protocol !== "https:" || sb.pathname !== "/" || sb.username || sb.password
      || !env.SUPABASE_PUBLISHABLE_KEY || !env.UPLOAD_SESSION_SECRET
      || env.UPLOAD_SESSION_SECRET.length < 32) return failure(503, "上传服务配置未完成");
  const headers = new Headers({ apikey: env.SUPABASE_PUBLISHABLE_KEY, Authorization: auth });
  const authResult = await fetcher(`${sb.origin}/auth/v1/user`, {
    headers, redirect: "manual", signal: AbortSignal.timeout(15000),
  });
  if (!authResult.ok) return failure(authResult.status >= 500 ? 503 : 401, "登录已失效或验证服务暂不可用");
  const user = await authResult.json();
  if (typeof user.id !== "string") return failure(401, "登录状态无效");
  const maxBytes = Math.min(MAX_BYTES, Number(env.MAX_UPLOAD_BYTES) || MAX_BYTES);
  let target;
  let total;
  let path;
  if (isCreate) {
    if (request.headers.get("Tus-Resumable") !== "1.0.0") return failure(412, "不支持的续传协议");
    total = Number(request.headers.get("Upload-Length"));
    if (!Number.isSafeInteger(total) || total <= 0 || total > maxBytes)
      return failure(413, `单个文件最大支持 ${Math.floor(maxBytes / 1_000_000)} MB`);
    // Creation never carries bytes: every PATCH can then be checked independently.
    if (await hasCreationBytes(request))
      return failure(400, "请先创建上传，再发送文件分片");
    const fields = metadata(request.headers.get("Upload-Metadata"));
    const match = OBJECT_RE.exec(fields.objectName || "");
    if (fields.bucketName !== BUCKET || !match || match[1] !== user.id)
      return failure(403, "上传目录不属于当前用户");
    path = fields.objectName;
    // RLS verifies project ownership; a path prefix alone is not enough.
    const project = await fetcher(`${sb.origin}/rest/v1/projects?select=id&id=eq.${match[2]}&limit=1`, {
      headers, redirect: "manual", signal: AbortSignal.timeout(15000),
    });
    if (!project.ok) return failure(503, "暂时无法校验项目权限");
    const rows = await project.json();
    if (!Array.isArray(rows) || rows.length !== 1) return failure(403, "项目不存在或不属于当前用户");
    target = new URL(TUS_PATH, sb.origin);
    headers.set("Tus-Resumable", "1.0.0");
    headers.set("Upload-Length", String(total));
    // Rebuild instead of blindly passing attacker-controlled metadata.
    const safe = { bucketName: BUCKET, objectName: path,
      contentType: MIME[match[4]], cacheControl: "0" };
    headers.set("Upload-Metadata", Object.entries(safe)
      .map(([key, value]) => `${key} ${btoa(value)}`).join(","));
    headers.set("x-upsert", "false");
  } else if (isSession) {
    const session = await unseal(url.pathname.slice(`${PREFIX}resumable/`.length), env.UPLOAD_SESSION_SECRET);
    if (!session || session.uid !== user.id) return failure(403, "续传会话无效、已过期或不属于当前用户");
    if (!Number.isSafeInteger(session.total) || session.total <= 0 || session.total > maxBytes)
      return failure(413, "文件大小超出限制");
    target = upstreamUrl(session.upstream, sb.origin);
    headers.set("Tus-Resumable", "1.0.0");
    if (method === "PATCH") {
      const offset = Number(request.headers.get("Upload-Offset"));
      const length = Number(request.headers.get("Content-Length"));
      if (!request.headers.has("Upload-Offset") || !request.headers.has("Content-Length")
          || !Number.isSafeInteger(offset) || offset < 0 || offset >= session.total
          || length !== Math.min(CHUNK_BYTES, session.total - offset))
        return failure(400, "分片大小或偏移量无效");
      if (request.headers.get("Content-Type") !== "application/offset+octet-stream")
        return failure(415, "分片类型无效");
      headers.set("Upload-Offset", String(offset));
      headers.set("Content-Type", "application/offset+octet-stream");
      headers.set("Content-Length", String(length));
    }
  } else {
    path = url.pathname.slice(`${PREFIX}object/`.length);
    const match = OBJECT_RE.exec(path);
    if (!match || match[1] !== user.id) return failure(403, "无权访问此文件");
    // User JWT is forwarded; Storage RLS is still enforced on reads.
    target = new URL(`/storage/v1/object/${BUCKET}/${path}`, sb.origin);
    if (request.headers.has("Range")) headers.set("Range", request.headers.get("Range"));
  }
  const response = await fetcher(target.href, {
    method, headers,
    body: method === "PATCH" ? request.body : undefined,
    redirect: "manual",
  });
  if (response.status >= 300 && response.status < 400)
    return failure(502, "存储服务返回了异常跳转");
  if (isCreate && response.status === 201) {
    target = upstreamUrl(response.headers.get("Location") || "", sb.origin);
    const token = await seal({
      uid: user.id, total, upstream: target.pathname, exp: Date.now() + 24 * 3600_000,
    }, env.UPLOAD_SESSION_SECRET);
    const result = new Headers({ "Location": `${env.APP_ORIGIN}${PREFIX}resumable/${token}`,
      "Tus-Resumable": "1.0.0", "Cache-Control": "private, no-store" });
    return new Response(null, { status: 201, headers: result });
  }
  const result = new Headers({ "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff" });
  for (const name of ["Content-Type", "Content-Length", "Content-Range", "Accept-Ranges",
    "Upload-Offset", "Upload-Length", "Tus-Resumable", "Retry-After"]) {
    if (response.headers.has(name)) result.set(name, response.headers.get(name));
  }
  if (isObject && method === "GET") result.set("Content-Disposition", "attachment");
  // Streams both ways: never buffer an entire uploaded/downloaded file in a Worker.
  return new Response(method === "HEAD" ? null : response.body, { status: response.status, headers: result });
}

export async function handleRequest(request, env, fetcher = fetch) {
  try { return await handle(request, env, fetcher); }
  catch (error) {
    if (error.message === "上传信息无效") return failure(400, error.message);
    return failure(502, "文件通道暂不可用，请稍后重试");
  }
}

export default { fetch: (request, env) => handleRequest(request, env) };

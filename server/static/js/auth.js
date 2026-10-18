/* 登录（Supabase Auth）——只在云端模式启用；本地模式完全跳过。 */
(function () {
  "use strict";

  const AUTH_KEY = "stardust_auth_v1";
  const auth = {
    config: null,
    cloud: false,
    session: null,
    ready: false,
    gate: null,
    signedInHandler: null,
  };

  function readSession() {
    try {
      const raw = localStorage.getItem(AUTH_KEY);
      const data = raw ? JSON.parse(raw) : null;
      if (data && typeof data.access_token === "string" && data.access_token) return data;
    } catch (e) {}
    return null;
  }

  function saveSession(session) {
    try {
      if (session) localStorage.setItem(AUTH_KEY, JSON.stringify(session));
      else localStorage.removeItem(AUTH_KEY);
    } catch (e) {}
  }

  function normalize(data, previous) {
    if (!data || !data.access_token) return null;
    return {
      access_token: data.access_token,
      refresh_token: data.refresh_token || (previous && previous.refresh_token) || "",
      expires_at: Date.now() + (Number(data.expires_in) || 3600) * 1000,
      user: data.user || (previous && previous.user) || null,
    };
  }

  function baseUrl() {
    return String((auth.config && auth.config.supabase_url) || "").replace(/\/+$/, "");
  }

  function friendly(raw) {
    const text = String(raw || "");
    if (/invalid login credentials/i.test(text)) return "邮箱或密码不正确";
    if (/already registered|already been registered/i.test(text)) return "这个邮箱已注册，直接登录即可";
    if (/password should be at least/i.test(text)) return "密码至少需要 6 位";
    if (/email not confirmed/i.test(text)) return "邮箱还没有验证，请先查收确认邮件";
    if (/rate limit|too many requests/i.test(text)) return "尝试次数过多，请稍后再试";
    if (/invalid email/i.test(text)) return "邮箱格式不正确";
    if (/signups not allowed/i.test(text)) return "当前暂未开放注册";
    return text;
  }

  async function supa(path, options) {
    const opts = options || {};
    const headers = Object.assign(
      {
        apikey: (auth.config && auth.config.supabase_publishable_key) || "",
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      opts.headers || {}
    );
    let res;
    try {
      res = await fetch(baseUrl() + path, {
        method: opts.method || "POST",
        headers: headers,
        body: opts.body ? JSON.stringify(opts.body) : undefined,
      });
    } catch (e) {
      throw new Error("无法连接登录服务，请检查网络后重试");
    }
    const text = await res.text();
    let data = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch (e) {}
    if (!res.ok) {
      const raw =
        (data && (data.msg || data.message || data.error_description || data.error)) || "";
      throw new Error(friendly(raw) || "登录服务暂不可用（HTTP " + res.status + "）");
    }
    return data;
  }

  auth.init = async function () {
    let config = null;
    try {
      const res = await fetch("/api/config", { headers: { Accept: "application/json" } });
      if (res.ok) config = await res.json();
    } catch (e) {}
    auth.config = config || {};
    auth.cloud = !!(auth.config.cloud_mode && auth.config.supabase_url);
    if (!auth.cloud) {
      auth.ready = true;
      return { cloud: false, signedIn: true };
    }
    auth.session = readSession();
    let message = "";
    if (auth.session && auth.session.expires_at && Date.now() > auth.session.expires_at - 60000) {
      try {
        await auth.refresh();
      } catch (e) {
        auth.session = null;
        saveSession(null);
        message = "登录已过期，请重新登录";
      }
    }
    auth.ready = true;
    return { cloud: true, signedIn: !!auth.session, message: message };
  };

  auth.signIn = async function (email, password) {
    const data = await supa("/auth/v1/token?grant_type=password", {
      body: { email: email, password: password },
    });
    const session = normalize(data);
    if (!session) throw new Error("登录失败，请稍后重试");
    auth.session = session;
    saveSession(session);
    return session;
  };

  auth.signUp = async function (email, password) {
    const data = await supa("/auth/v1/signup", { body: { email: email, password: password } });
    const session = normalize(data);
    if (session) {
      auth.session = session;
      saveSession(session);
      return { session: session };
    }
    return { needsConfirm: true, user: data && data.user };
  };

  auth.refresh = async function () {
    if (!auth.session || !auth.session.refresh_token) throw new Error("登录已过期，请重新登录");
    const data = await supa("/auth/v1/token?grant_type=refresh_token", {
      body: { refresh_token: auth.session.refresh_token },
    });
    const session = normalize(data, auth.session);
    if (!session) throw new Error("登录已过期，请重新登录");
    auth.session = session;
    saveSession(session);
    return session;
  };

  auth.recover = async function (email) {
    await supa("/auth/v1/recover", { body: { email: email } });
  };

  auth.logout = async function () {
    const token = auth.token();
    auth.session = null;
    saveSession(null);
    if (token) {
      try {
        await fetch(baseUrl() + "/auth/v1/logout", {
          method: "POST",
          headers: {
            apikey: (auth.config && auth.config.supabase_publishable_key) || "",
            Authorization: "Bearer " + token,
          },
        });
      } catch (e) {}
    }
    if (auth.gate) auth.gate("已退出登录，请重新登录");
  };

  auth.token = function () {
    return (auth.session && auth.session.access_token) || "";
  };

  auth.user = function () {
    return (auth.session && auth.session.user) || null;
  };

  auth.attached = function () {
    return !!(auth.cloud && auth.token());
  };

  auth.needsRefresh = function () {
    return !!(
      auth.session &&
      auth.session.refresh_token &&
      auth.session.expires_at &&
      Date.now() > auth.session.expires_at - 60000
    );
  };

  auth.onGate = function (fn) {
    auth.gate = fn;
  };

  auth.onSignedIn = function (fn) {
    auth.signedInHandler = fn;
  };

  auth.emitSignedIn = function () {
    if (auth.signedInHandler) auth.signedInHandler();
  };

  auth.handleUnauthorized = function () {
    auth.session = null;
    saveSession(null);
    if (auth.gate) auth.gate("登录已过期，请重新登录");
  };

  window.S = window.S || {};
  window.S.auth = auth;
})();

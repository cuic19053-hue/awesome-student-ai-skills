/* =========================================================================
 * Stardust Agent · 核心工具层
 * 图标 / API / 本地存储 / Toast / 弹窗 / Markdown / 格式化
 * 全局命名空间：window.S
 * ========================================================================= */
(function () {
  "use strict";
  const S = (window.S = window.S || {});

  /* ---------------------------------------------------------------------
   * 图标（统一线框风格，禁用 emoji）
   * ------------------------------------------------------------------- */
  const ICONS = {
    star: '<path d="M12 2.6l2.7 6.7 6.7 2.7-6.7 2.7L12 21.4l-2.7-6.7L2.6 12l6.7-2.7z"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    minus: '<path d="M5 12h14"/>',
    chat: '<path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/>',
    message: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    folder: '<path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>',
    "folder-plus": '<path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/><path d="M12 11v6M9 14h6"/>',
    file: '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M9 13h6M9 17h4"/>',
    "file-plus": '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M12 12v6M9 15h6"/>',
    settings: '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/>',
    sliders: '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3"/><path d="M1 14h6M9 8h6M17 16h6"/>',
    user: '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    "credit-card": '<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 10h20"/>',
    wallet: '<path d="M19 7V5a2 2 0 0 0-2-2H5a2 2 0 0 0 0 4h15a1 1 0 0 1 1 1v4h-3a2 2 0 0 0 0 4h3a1 1 0 0 0 1-1v-2"/>',
    chart: '<path d="M3 3v18h18"/><path d="M7 16v-4M12 16V8M17 16v-7"/>',
    cpu: '<rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 2v2M15 2v2M9 20v2M15 20v2M2 9h2M2 15h2M20 9h2M20 15h2"/>',
    key: '<circle cx="7.5" cy="15.5" r="5.5"/><path d="M21 2l-9.6 9.6"/><path d="M15.5 7.5l3 3L22 7l-3-3"/>',
    x: '<path d="M18 6 6 18M6 6l12 12"/>',
    "chevron-down": '<path d="M6 9l6 6 6-6"/>',
    "chevron-right": '<path d="M9 18l6-6-6-6"/>',
    "chevron-left": '<path d="M15 18l-6-6 6-6"/>',
    "arrow-right": '<path d="M5 12h14M12 5l7 7-7 7"/>',
    "arrow-left": '<path d="M19 12H5M12 19l-7-7 7-7"/>',
    "arrow-up": '<path d="M12 19V5M5 12l7-7 7 7"/>',
    "arrow-down": '<path d="M12 5v14M19 12l-7 7-7-7"/>',
    home: '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/>',
    "corner-down-left": '<path d="M20 4v7a4 4 0 0 1-4 4H4"/><path d="M9 10l-5 5 5 5"/>',
    paperclip: '<path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/>',
    search: '<circle cx="11" cy="11" r="8"/><path d="M21 21l-4.3-4.3"/>',
    upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M17 8l-5-5-5 5"/><path d="M12 3v12"/>',
    download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 10l5 5 5-5"/><path d="M12 15V3"/>',
    trash: '<path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M10 11v6M14 11v6"/>',
    check: '<path d="M20 6 9 17l-5-5"/>',
    "check-circle": '<circle cx="12" cy="12" r="9"/><path d="M9 12l2 2 4-4"/>',
    copy: '<rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
    clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    "book-open": '<path d="M12 7v14"/><path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z"/>',
    "panel-left": '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 3v18"/>',
    "panel-right": '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M15 3v18"/>',
    more: '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
    "external-link": '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M21 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5"/>',
    shield: '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/>',
    zap: '<path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z"/>',
    "graduation-cap": '<path d="M21.42 10.92a1 1 0 0 0-.02-1.84L12.83 5.18a2 2 0 0 0-1.66 0L2.6 9.08a1 1 0 0 0 0 1.83l8.57 3.91a2 2 0 0 0 1.66 0z"/><path d="M22 10v6"/><path d="M6 12.5V16a6 3 0 0 0 12 0v-3.5"/>',
    award: '<circle cx="12" cy="8" r="6"/><path d="M15.48 12.89 17 22l-5-3-5 3 1.52-9.11"/>',
    flask: '<path d="M10 2v7.53a2 2 0 0 1-.21.9L4.72 20.55a1 1 0 0 0 .9 1.45h12.76a1 1 0 0 0 .9-1.45l-5.07-10.13a2 2 0 0 1-.21-.9V2"/><path d="M8.5 2h7"/><path d="M7 16h10"/>',
    trophy: '<path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6"/><path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18"/><path d="M4 22h16"/><path d="M10 14.66V17c0 .55-.47.98-.97 1.21C7.85 18.75 7 20.24 7 22"/><path d="M14 14.66V17c0 .55.47.98.97 1.21C16.15 18.75 17 20.24 17 22"/><path d="M18 2H6v7a6 6 0 0 0 12 0V2Z"/>',
    flag: '<path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><path d="M4 22v-7"/>',
    globe: '<circle cx="12" cy="12" r="10"/><path d="M2 12h20"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>',
    image: '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="M21 15l-3.09-3.09a2 2 0 0 0-2.83 0L6 21"/>',
    target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.5"/>',
    "file-check": '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M9 15l2 2 4-4"/>',
    edit: '<path d="M17 3a2.83 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5z"/>',
    refresh: '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
    info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
    alert: '<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
    link: '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
    eye: '<path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/>',
    menu: '<path d="M3 6h18M3 12h18M3 18h18"/>',
    sparkles: '<path d="M9.94 15.5A2 2 0 0 0 8.5 14.06l-6.14-1.58a.5.5 0 0 1 0-.96L8.5 9.94A2 2 0 0 0 9.94 8.5l1.58-6.14a.5.5 0 0 1 .96 0L14.06 8.5A2 2 0 0 0 15.5 9.94l6.14 1.58a.5.5 0 0 1 0 .96L15.5 14.06a2 2 0 0 0-1.44 1.44l-1.58 6.14a.5.5 0 0 1-.96 0z"/>',
    loader: '<path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>',
    send: '<path d="M22 2 11 13"/><path d="M22 2l-7 20-4-9-9-4z"/>',
    inbox: '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
    history: '<path d="M3 3v5h5"/><path d="M3.05 13A9 9 0 1 0 6 5.3L3 8"/><path d="M12 7v5l4 2"/>',
    grid: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    list: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
    pin: '<path d="M12 17v5"/><path d="M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V6h1a2 2 0 0 0 0-4H8a2 2 0 0 0 0 4h1z"/>',
    tag: '<path d="M12.59 2.59A2 2 0 0 0 11.17 2H4a2 2 0 0 0-2 2v7.17a2 2 0 0 0 .59 1.42l8.82 8.82a2 2 0 0 0 2.83 0l7.17-7.17a2 2 0 0 0 0-2.83z"/><circle cx="7" cy="7" r="1.5"/>',
    "log-out": '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5"/><path d="M21 12H9"/>',
    command: '<path d="M18 3a3 3 0 0 0-3 3v12a3 3 0 1 0 3-3H6a3 3 0 1 0 3 3V6a3 3 0 1 0-3 3h12a3 3 0 0 0 3-3Z"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/>',
    moon: '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9z"/>',
    dot: '<circle cx="12" cy="12" r="3"/>',
    inbox2: '<path d="M4 4h16v16H4z"/>',
  };

  const ICON_CHOICES = [
    "star",
    "folder",
    "flask",
    "trophy",
    "award",
    "graduation-cap",
    "book-open",
    "target",
    "zap",
    "shield",
    "globe",
    "users",
  ];

  function icon(name, cls) {
    const body = ICONS[name] || ICONS.dot;
    return (
      '<svg class="i' +
      (cls ? " " + cls : "") +
      '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" ' +
      'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      body +
      "</svg>"
    );
  }

  /* ---------------------------------------------------------------------
   * 基础工具
   * ------------------------------------------------------------------- */
  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  const EMOJI_RE =
    /[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{FE0F}\u{1F1E6}-\u{1F1FF}\u{2B00}-\u{2BFF}\u{2190}-\u{21FF}\u{2700}-\u{27BF}]/gu;

  function clean(text) {
    return String(text == null ? "" : text).replace(EMOJI_RE, "").replace(/\s{2,}/g, " ").trim();
  }

  function uid(prefix) {
    return (prefix || "id") + "_" + Math.random().toString(36).slice(2, 9) + Date.now().toString(36).slice(-4);
  }

  function debounce(fn, wait) {
    let timer = null;
    return function () {
      const args = arguments;
      clearTimeout(timer);
      timer = setTimeout(function () {
        fn.apply(null, args);
      }, wait);
    };
  }

  function initials(name) {
    const text = clean(name || "同学");
    return text.slice(0, 1).toUpperCase();
  }

  function fmtTime(input) {
    if (!input) return "";
    const d = input instanceof Date ? input : new Date(input);
    if (isNaN(d.getTime())) return "";
    const now = new Date();
    const diff = now.getTime() - d.getTime();
    if (diff < 60 * 1000) return "刚刚";
    if (diff < 60 * 60 * 1000) return Math.floor(diff / 60000) + " 分钟前";
    const sameDay = d.toDateString() === now.toDateString();
    const pad = (n) => String(n).padStart(2, "0");
    if (sameDay) return "今天 " + pad(d.getHours()) + ":" + pad(d.getMinutes());
    const yesterday = new Date(now.getTime() - 86400000);
    if (d.toDateString() === yesterday.toDateString()) return "昨天 " + pad(d.getHours()) + ":" + pad(d.getMinutes());
    if (d.getFullYear() === now.getFullYear())
      return pad(d.getMonth() + 1) + "-" + pad(d.getDate());
    return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate());
  }

  function fmtBytes(bytes) {
    const n = Number(bytes) || 0;
    if (n < 1024) return n + " B";
    if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
    return (n / 1024 / 1024).toFixed(1) + " MB";
  }

  function fmtCredits(value) {
    const n = Number(value || 0);
    if (!isFinite(n)) return "0";
    return n % 1 === 0 ? String(n) : n.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
  }

  /* ---------------------------------------------------------------------
   * API
   * ------------------------------------------------------------------- */
  class ApiError extends Error {
    constructor(message, status, detail) {
      super(message);
      this.name = "ApiError";
      this.status = status;
      this.detail = detail;
    }
  }

  async function api(path, options) {
    const opts = options || {};
    const method = opts.method || "GET";
    const headers = Object.assign({ Accept: "application/json" }, opts.headers || {});
    let body = opts.body;
    if (body != null && !(body instanceof FormData) && typeof body !== "string") {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(body);
    }
    if (window.S && S.auth && S.auth.cloud && S.auth.needsRefresh()) {
      try {
        await S.auth.refresh();
      } catch (e) {}
    }
    if (window.S && S.auth && S.auth.attached()) {
      headers.Authorization = "Bearer " + S.auth.token();
    }
    const timeout = opts.timeout || 180000;
    const controller = new AbortController();
    const timer = setTimeout(function () {
      controller.abort();
    }, timeout);
    let res;
    try {
      res = await fetch(path, {
        method: method,
        headers: headers,
        body: body,
        signal: controller.signal,
        credentials: "same-origin",
      });
    } catch (err) {
      clearTimeout(timer);
      if (err && err.name === "AbortError") {
        throw new ApiError("请求超时，请稍后重试", 0, "");
      }
      throw new ApiError("网络连接失败，请检查本地服务是否在运行", 0, "");
    }
    clearTimeout(timer);
    let data = null;
    const text = await res.text();
    if (text) {
      try {
        data = JSON.parse(text);
      } catch (e) {
        data = null;
      }
    }
    if (res.status === 401 && window.S && S.auth && S.auth.cloud) {
      S.auth.handleUnauthorized();
      throw new ApiError("登录已过期，请重新登录", 401, "登录已过期，请重新登录");
    }
    if (!res.ok) {
      let detail = "";
      if (data && typeof data === "object") {
        detail = data.detail || data.message || "";
        if (Array.isArray(detail)) {
          detail = detail
            .map(function (d) {
              return d && d.msg ? d.msg : JSON.stringify(d);
            })
            .join("；");
        }
      }
      throw new ApiError(detail || "请求失败（HTTP " + res.status + "）", res.status, detail);
    }
    return data;
  }

  /* ---------------------------------------------------------------------
   * 本地存储
   * ------------------------------------------------------------------- */
  const LS = {
    get(key, fallback) {
      try {
        const raw = localStorage.getItem(key);
        if (raw == null) return fallback;
        return JSON.parse(raw);
      } catch (e) {
        return fallback;
      }
    },
    set(key, value) {
      try {
        localStorage.setItem(key, JSON.stringify(value));
      } catch (e) {
        /* 隐私模式下静默失败 */
      }
    },
    remove(key) {
      try {
        localStorage.removeItem(key);
      } catch (e) {}
    },
  };

  const SS = {
    get(key, fallback) {
      try {
        const raw = sessionStorage.getItem(key);
        if (raw == null) return fallback;
        return JSON.parse(raw);
      } catch (e) {
        return fallback;
      }
    },
    set(key, value) {
      try {
        sessionStorage.setItem(key, JSON.stringify(value));
      } catch (e) {}
    },
    remove(key) {
      try {
        sessionStorage.removeItem(key);
      } catch (e) {}
    },
  };

  const UI_KEY = "stardust_ui_v1";
  const MODEL_KEY = "stardust_model_v1";
  const THREADS_KEY = "stardust_threads_v1";

  const DEFAULT_UI = {
    welcomeSeen: false,
    sidebarCollapsed: false,
    userName: "同学",
    projectIcons: {},
    projectInstructions: {},
    activeProjectId: "",
  };

  const DEFAULT_MODEL = {
    provider: "preset",
    model: "",
    base_url: "",
    api_key: "",
    image_model: "",
    image_base_url: "",
    image_api_key: "",
    demo: false,
  };

  function getUI() {
    return Object.assign({}, DEFAULT_UI, LS.get(UI_KEY, {}));
  }

  function setUI(patch) {
    const next = Object.assign(getUI(), patch || {});
    LS.set(UI_KEY, next);
    return next;
  }

  function getModel() {
    return Object.assign({}, DEFAULT_MODEL, SS.get(MODEL_KEY, {}));
  }

  function setModel(patch) {
    const next = Object.assign(getModel(), patch || {});
    SS.set(MODEL_KEY, next);
    return next;
  }

  function loadThreads() {
    return LS.get(THREADS_KEY, {});
  }

  function saveThreads(map) {
    LS.set(THREADS_KEY, map);
  }

  /* ---------------------------------------------------------------------
   * Toast
   * ------------------------------------------------------------------- */
  function toast(message, type) {
    const root = document.getElementById("toast-root");
    if (!root) return;
    const el = document.createElement("div");
    const kind = type || "info";
    el.className = "toast toast-" + kind;
    const iconName = kind === "error" ? "alert" : kind === "success" ? "check-circle" : "info";
    el.innerHTML = icon(iconName, "toast-icon") + '<span class="toast-text">' + esc(clean(message)) + "</span>";
    root.appendChild(el);
    requestAnimationFrame(function () {
      el.classList.add("is-in");
    });
    setTimeout(function () {
      el.classList.remove("is-in");
      setTimeout(function () {
        el.remove();
      }, 220);
    }, 3200);
  }

  /* ---------------------------------------------------------------------
   * 弹窗（统一可关闭：X / 遮罩 / Esc）
   * ------------------------------------------------------------------- */
  let activeModal = null;

  function closeModal() {
    if (!activeModal) return;
    const ctx = activeModal;
    activeModal = null;
    document.removeEventListener("keydown", ctx.onKey);
    document.removeEventListener("keyup", ctx.onKeyUp);
    if (ctx.prevFocus && ctx.prevFocus.focus) {
      try {
        ctx.prevFocus.focus();
      } catch (e) {}
    }
    document.body.classList.remove("modal-open");
    ctx.backdrop.classList.remove("is-in");
    setTimeout(function () {
      ctx.backdrop.remove();
    }, 160);
    if (ctx.onClose) ctx.onClose();
  }

  function openModal(opts) {
    const config = Object.assign(
      { title: "", subtitle: "", body: "", footer: "", size: "md", closable: true, className: "", onMount: null, onClose: null },
      opts || {}
    );
    closeModal();
    const root = document.getElementById("modal-root");
    const backdrop = document.createElement("div");
    backdrop.className = "modal-backdrop";
    backdrop.innerHTML =
      '<div class="modal modal-' +
      config.size +
      (config.className ? " " + config.className : "") +
      '" role="dialog" aria-modal="true" aria-label="' +
      esc(config.title) +
      '" tabindex="-1">' +
      '<div class="modal-head">' +
      '<div class="modal-heading"><h2 class="modal-title">' +
      esc(config.title) +
      "</h2>" +
      (config.subtitle ? '<p class="modal-sub">' + esc(config.subtitle) + "</p>" : "") +
      "</div>" +
      (config.closable
        ? '<button class="icon-btn modal-close" type="button" aria-label="关闭" data-modal-close>' + icon("x") + "</button>"
        : "") +
      "</div>" +
      '<div class="modal-body">' +
      config.body +
      "</div>" +
      (config.footer ? '<div class="modal-foot">' + config.footer + "</div>" : "") +
      "</div>";
    root.appendChild(backdrop);
    document.body.classList.add("modal-open");
    requestAnimationFrame(function () {
      backdrop.classList.add("is-in");
    });

    function onKey(e) {
      if (activeModal !== ctx) return;
      if (e.key === "Escape" && config.closable) {
        e.stopPropagation();
        closeModal();
      }
      if (e.key === "Tab") {
        // 简单焦点循环
        const focusables = backdrop.querySelectorAll(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        );
        if (!focusables.length) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }

    backdrop.addEventListener("click", function (e) {
      if (!config.closable) return;
      if (e.target === backdrop) closeModal();
    });
    backdrop.querySelectorAll("[data-modal-close]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        closeModal();
      });
    });

    function onKeyUp(e) {
      if (activeModal !== ctx) return;
      if (e.key === "Escape" && config.closable) {
        closeModal();
      }
    }

    const ctx = {
      backdrop: backdrop,
      onKey: onKey,
      onKeyUp: onKeyUp,
      prevFocus: document.activeElement,
      onClose: config.onClose,
      el: backdrop.querySelector(".modal"),
    };
    activeModal = ctx;
    document.addEventListener("keydown", onKey, true);
    document.addEventListener("keyup", onKeyUp, true);

    if (config.onMount) {
      try {
        config.onMount(ctx);
      } catch (err) {
        console.error("modal onMount error", err);
      }
    }
    const autofocus = backdrop.querySelector("[data-autofocus]");
    if (autofocus) {
      setTimeout(function () {
        autofocus.focus();
      }, 60);
    } else {
      setTimeout(function () {
        if (ctx.el && ctx.el.focus) ctx.el.focus({ preventScroll: true });
      }, 60);
    }
    return ctx;
  }

  function confirmDialog(opts) {
    const config = Object.assign(
      { title: "请确认", message: "", confirmText: "确认", cancelText: "取消", danger: false },
      opts || {}
    );
    return new Promise(function (resolve) {
      let settled = false;
      const done = function (value) {
        if (settled) return;
        settled = true;
        resolve(value);
      };
      const ctx = openModal({
        title: config.title,
        size: "sm",
        body: '<p class="confirm-message">' + esc(config.message) + "</p>",
        footer:
          '<button class="btn btn-ghost" type="button" data-cancel>' +
          esc(config.cancelText) +
          "</button>" +
          '<button class="btn ' +
          (config.danger ? "btn-danger" : "btn-primary") +
          '" type="button" data-confirm>' +
          esc(config.confirmText) +
          "</button>",
        onClose: function () {
          done(false);
        },
      });
      ctx.backdrop.querySelector("[data-cancel]").addEventListener("click", function () {
        done(false);
        closeModal();
      });
      ctx.backdrop.querySelector("[data-confirm]").addEventListener("click", function () {
        done(true);
        closeModal();
      });
    });
  }

  /* ---------------------------------------------------------------------
   * Markdown 轻量渲染（先转义再处理，代码块占位）
   * ------------------------------------------------------------------- */
  function renderInline(text) {
    let out = esc(text);
    out = out.replace(/`([^`\n]+)`/g, function (m, code) {
      return "<code>" + code + "</code>";
    });
    out = out.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
    out = out.replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>");
    out = out.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, function (m, label, url) {
      return '<a href="' + url + '" target="_blank" rel="noopener noreferrer">' + label + "</a>";
    });
    return out;
  }

  function md(text) {
    if (!text) return "";
    const source = String(text).replace(/\r\n/g, "\n");
    const blocks = [];
    let work = source.replace(/```([a-zA-Z0-9_+-]*)\n([\s\S]*?)```/g, function (m, lang, code) {
      const idx = blocks.length;
      blocks.push(
        '<pre class="code-block"><div class="code-head"><span>' +
          esc(lang || "code") +
          '</span><button class="code-copy" type="button" data-copy-code>' +
          icon("copy", "code-copy-icon") +
          "</button></div><code>" +
          esc(code.replace(/\n$/, "")) +
          "</code></pre>"
      );
      return "\u0000BLOCK" + idx + "\u0000";
    });

    const lines = work.split("\n");
    const html = [];
    let paragraph = [];
    let listItems = [];
    let orderedItems = [];

    function flushParagraph() {
      if (!paragraph.length) return;
      html.push("<p>" + renderInline(paragraph.join(" ")) + "</p>");
      paragraph = [];
    }
    function flushList() {
      if (listItems.length) {
        html.push("<ul>" + listItems.map(function (li) {
          return "<li>" + renderInline(li) + "</li>";
        }).join("") + "</ul>");
        listItems = [];
      }
      if (orderedItems.length) {
        html.push("<ol>" + orderedItems.map(function (li) {
          return "<li>" + renderInline(li) + "</li>";
        }).join("") + "</ol>");
        orderedItems = [];
      }
    }

    lines.forEach(function (raw) {
      const placeholder = raw.match(/^\u0000BLOCK(\d+)\u0000$/);
      if (placeholder) {
        flushParagraph();
        flushList();
        html.push(blocks[Number(placeholder[1])] || "");
        return;
      }
      const line = raw.trim();
      if (!line) {
        flushParagraph();
        flushList();
        return;
      }
      if (/^[-*_]{3,}$/.test(line)) {
        flushParagraph();
        flushList();
        html.push("<hr>");
        return;
      }
      const heading = line.match(/^(#{1,4})\s+(.*)$/);
      if (heading) {
        flushParagraph();
        flushList();
        const level = Math.min(heading[1].length + 1, 5);
        html.push("<h" + level + ">" + renderInline(heading[2]) + "</h" + level + ">");
        return;
      }
      const quote = line.match(/^>\s?(.*)$/);
      if (quote) {
        flushParagraph();
        flushList();
        html.push("<blockquote>" + renderInline(quote[1]) + "</blockquote>");
        return;
      }
      const bullet = line.match(/^[-*]\s+(.*)$/);
      if (bullet) {
        flushParagraph();
        if (orderedItems.length) flushList();
        listItems.push(bullet[1]);
        return;
      }
      const ordered = line.match(/^\d+[.)]\s+(.*)$/);
      if (ordered) {
        flushParagraph();
        if (listItems.length) flushList();
        orderedItems.push(ordered[1]);
        return;
      }
      flushList();
      paragraph.push(line);
    });
    flushParagraph();
    flushList();
    return html.join("");
  }

  /* ---------------------------------------------------------------------
   * 事件委托 / 工具
   * ------------------------------------------------------------------- */
  function on(root, type, selector, handler) {
    if (!root) return;
    root.addEventListener(type, function (e) {
      const target = e.target instanceof Element ? e.target.closest(selector) : null;
      if (target && root.contains(target)) handler(e, target);
    });
  }

  function copyText(text) {
    const value = String(text == null ? "" : text);
    const fallback = function () {
      return new Promise(function (resolve, reject) {
        try {
          const el = document.createElement("textarea");
          el.value = value;
          el.style.position = "fixed";
          el.style.opacity = "0";
          document.body.appendChild(el);
          el.select();
          const ok = document.execCommand("copy");
          el.remove();
          if (ok) resolve();
          else reject(new Error("copy failed"));
        } catch (err) {
          reject(err);
        }
      });
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(value).catch(fallback);
    }
    return fallback();
  }

  async function fetchBlob(url) {
    if (window.S && S.auth && S.auth.cloud && S.auth.needsRefresh()) {
      try {
        await S.auth.refresh();
      } catch (e) {}
    }
    const headers = {};
    if (window.S && S.auth && S.auth.attached()) {
      headers.Authorization = "Bearer " + S.auth.token();
    }
    const res = await fetch(url, { headers: headers, credentials: "same-origin" });
    if (res.status === 401 && window.S && S.auth && S.auth.cloud) {
      S.auth.handleUnauthorized();
      throw new Error("登录已过期，请重新登录");
    }
    if (!res.ok) throw new Error("文件加载失败（HTTP " + res.status + "）");
    return res.blob();
  }

  function anchorDownload(url, name) {
    const a = document.createElement("a");
    a.href = url;
    if (name) a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  async function downloadUrl(url, fallbackName) {
    if (window.S && S.auth && S.auth.attached()) {
      try {
        const blob = await fetchBlob(url);
        const objectUrl = URL.createObjectURL(blob);
        anchorDownload(objectUrl, fallbackName);
        setTimeout(function () {
          URL.revokeObjectURL(objectUrl);
        }, 10000);
      } catch (err) {
        if (S.toast) S.toast(err.message || "下载失败", "error");
      }
      return;
    }
    anchorDownload(url, fallbackName);
  }

  /* ---------------------------------------------------------------------
   * 主题（浅色 / 深色 / 跟随系统）
   * ------------------------------------------------------------------- */
  const THEME_KEY = "stardust_theme_v1";

  function resolvedTheme(mode) {
    if (mode === "light" || mode === "dark") return mode;
    try {
      return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
    } catch (e) {
      return "dark";
    }
  }

  function applyTheme(mode) {
    const next = resolvedTheme(mode);
    document.documentElement.dataset.theme = next;
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", next === "dark" ? "#08080a" : "#f4f2ee");
    return next;
  }

  const theme = {
    mode() {
      const saved = LS.get(THEME_KEY, { mode: "auto" });
      return saved.mode || "auto";
    },
    resolved() {
      return resolvedTheme(theme.mode());
    },
    set(mode) {
      LS.set(THEME_KEY, { mode: mode });
      applyTheme(mode);
      window.dispatchEvent(new CustomEvent("stardust:theme", { detail: { mode: mode } }));
      return mode;
    },
    toggle() {
      return theme.set(theme.resolved() === "dark" ? "light" : "dark");
    },
    init() {
      applyTheme(theme.mode());
      try {
        const mq = window.matchMedia("(prefers-color-scheme: dark)");
        const onChange = function () {
          if (theme.mode() === "auto") applyTheme("auto");
        };
        if (mq.addEventListener) mq.addEventListener("change", onChange);
        else if (mq.addListener) mq.addListener(onChange);
      } catch (e) {}
    },
  };

  function prefersReducedMotion() {
    try {
      return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    } catch (e) {
      return false;
    }
  }

  /** 页面切换动画：支持 View Transitions 时用它，否则直接执行。 */
  function viewTransition(run) {
    if (!document.startViewTransition || prefersReducedMotion()) return run();
    try {
      const transition = document.startViewTransition(function () {
        return run();
      });
      // 页面被隐藏或快速连续跳转时，浏览器会中止过渡；这里主动吞掉已知的取消错误。
      [transition.ready, transition.updateCallbackDone, transition.finished].forEach(function (promise) {
        if (promise && typeof promise.catch === "function") promise.catch(function () {});
      });
      return transition;
    } catch (e) {
      return run();
    }
  }

  /* ---------------------------------------------------------------------
   * 导出
   * ------------------------------------------------------------------- */
  S.icon = icon;
  S.icons = ICONS;
  S.iconChoices = ICON_CHOICES;
  S.esc = esc;
  S.clean = clean;
  S.uid = uid;
  S.debounce = debounce;
  S.initials = initials;
  S.fmtTime = fmtTime;
  S.fmtBytes = fmtBytes;
  S.fmtCredits = fmtCredits;
  S.api = api;
  S.ApiError = ApiError;
  S.LS = LS;
  S.SS = SS;
  S.getUI = getUI;
  S.setUI = setUI;
  S.getModel = getModel;
  S.setModel = setModel;
  S.loadThreads = loadThreads;
  S.saveThreads = saveThreads;
  S.toast = toast;
  S.openModal = openModal;
  S.closeModal = closeModal;
  S.confirm = confirmDialog;
  S.md = md;
  S.on = on;
  S.copyText = copyText;
  S.downloadUrl = downloadUrl;
  S.fetchBlob = fetchBlob;
  S.theme = theme;
  S.applyTheme = applyTheme;
  S.viewTransition = viewTransition;
  S.prefersReducedMotion = prefersReducedMotion;
  S.UI_KEY = UI_KEY;
  S.MODEL_KEY = MODEL_KEY;
  S.THREADS_KEY = THREADS_KEY;
})();

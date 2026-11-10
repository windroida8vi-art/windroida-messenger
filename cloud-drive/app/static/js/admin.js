import { animNum, api, askPassword, brandMark, confirmDialog, errToast, fmtBytes, fmtDate, fmtNum, getLang, getTheme, h, icon, openModal, promptDialog, setCsrf,
  setLang, t, toast, toggleTheme } from "./common.js";

const root = document.getElementById("root");
const S = { me: null, tab: "dashboard", info: {} };
const TABS = [["dashboard", "dashboard", "home"], ["users", "users", "users"], ["files", "files", "file"], ["settings", "settings", "settings"], ["audit", "audit", "clock"], ["health", "health", "activity"]];
let box;

async function boot() {
  try { S.info = await api("/config"); } catch { /* ignore */ }
  try { const d = await api("/me"); S.me = d.user; setCsrf(d.csrf); } catch { S.me = null; }
  if (!S.me) { location.href = "/"; return; }
  if (S.me.role !== "admin") { root.replaceChildren(h("div", { class: "auth" }, h("div", { class: "auth-card" }, h("h1", {}, t("no_admin")), h("a", { class: "btn", href: "/" }, t("back_to_app"))))); return; }
  shell(); show(location.hash.slice(1) || "dashboard");
}
window.addEventListener("cd:unauthorized", () => { location.href = "/"; });
window.addEventListener("hashchange", () => show(location.hash.slice(1) || "dashboard"));

function shell() {
  box = h("div", { class: "content" });
  const side = h("aside", { class: "sidebar" }, h("div", { class: "brand" }, brandMark(S.info), h("span", { class: "label" }, (S.info.service_name || "Cloud Drive") + " · " + t("admin"))),
    h("nav", { class: "nav" }, TABS.map(([id, key, ic]) => h("a", { href: "#" + id, class: S.tab === id ? "active" : "" }, icon(ic), h("span", { class: "label" }, t(key))))),
    h("div", { class: "grow" }), h("nav", { class: "nav" }, h("a", { href: "/" }, icon("folder"), h("span", { class: "label" }, t("back_to_app")))));
  const top = h("header", { class: "topbar" }, h("h2", { style: "margin:0;font-size:18px" }, t(S.tab)), h("div", { class: "grow" }), h("span", { class: "muted small" }, S.me.username),
    h("button", { class: "btn ghost iconbtn", onclick: () => { setLang(getLang() === "fa" ? "en" : "fa"); shell(); show(S.tab); } }, icon("globe")),
    h("button", { class: "btn ghost iconbtn", onclick: () => { toggleTheme(); shell(); show(S.tab); } }, icon(getTheme() === "dark" ? "sun" : "moon")));
  root.replaceChildren(h("div", { class: "app", style: "grid-template-columns:230px 1fr" }, side, h("main", { class: "main" }, top, box)));
}
async function show(tab) {
  if (!TABS.some((x) => x[0] === tab)) tab = "dashboard";
  S.tab = tab; shell();
  box.replaceChildren(h("div", { class: "muted" }, "…"));
  try { box.replaceChildren(await ({ dashboard, users, files, settings, audit, health })[tab]()); } catch (e) { errToast(e); }
}
const stat = (label, value, extra) => h("div", { class: "stat" }, h("span", {}, label), h("b", {}, value), extra ? h("span", {}, extra) : null);
const num = (n, f = fmtNum) => animNum(n, f);
const panel = (title, ...kids) => h("div", { class: "panel" }, h("h3", {}, title), ...kids);
function table(heads, rows) {
  return h("div", { class: "tablewrap" }, h("table", { class: "list" }, h("thead", {}, h("tr", {}, heads.map((x) => h("th", {}, x)))), h("tbody", {}, rows.length ? rows : h("tr", {}, h("td", { colspan: heads.length, class: "muted" }, t("none"))))));
}
async function sensitive(method, path, body = {}) {
  const pw = await askPassword(); if (!pw) return false;
  try { await api(path, { method, body: { ...body, confirm_password: pw } }); return true; } catch (e) { errToast(e); return false; }
}

// ---------------------------------------------------------------- charts (inline SVG, no library)
function chart(values, labels, fmt) {
  const NS = "http://www.w3.org/2000/svg", W = 600, H = 170, pad = { l: 8, r: 8, t: 14, b: 22 };
  const el = (n, a) => { const e = document.createElementNS(NS, n); for (const k in a) e.setAttribute(k, a[k]); return e; };
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart", preserveAspectRatio: "none", role: "img" });
  const max = Math.max(1, ...values), n = values.length, x = (i) => pad.l + (i * (W - pad.l - pad.r)) / Math.max(1, n - 1), y = (v) => pad.t + (1 - v / max) * (H - pad.t - pad.b);
  for (const f of [0, 0.5, 1]) svg.append(el("line", { x1: pad.l, x2: W - pad.r, y1: y(max * f), y2: y(max * f), style: "stroke:var(--border);stroke-width:1" }));
  const pts = values.map((v, i) => `${x(i)},${y(v)}`).join(" ");
  const g = el("g", { class: "draw" }); svg.append(g);
  g.append(el("polygon", { points: `${x(0)},${y(0)} ${pts} ${x(n - 1)},${y(0)}`, style: "fill:var(--accent);opacity:.14" }), el("polyline", { points: pts, style: "fill:none;stroke:var(--accent);stroke-width:2.5;stroke-linejoin:round;vector-effect:non-scaling-stroke" }));
  const lab = (txt, ax, anchor) => { const e = el("text", { x: ax, y: H - 6, "text-anchor": anchor, style: "fill:var(--muted);font-size:12px" }); e.textContent = txt; return e; };
  svg.append(lab(labels[0].slice(5), pad.l, "start"), lab(labels[n - 1].slice(5), W - pad.r, "end"));
  const top = el("text", { x: W - pad.r, y: 11, "text-anchor": "end", style: "fill:var(--muted);font-size:12px" }); top.textContent = fmt(max); svg.append(top);
  return svg;
}

// ---------------------------------------------------------------- dashboard
async function dashboard() {
  const s = await api("/admin/stats");
  const cards = h("div", { class: "stats" }, stat(t("total_users"), num(s.users_total)), stat(t("active_users"), num(s.users_active), t("online_now") + ": " + fmtNum(s.users_online)),
    stat(t("total_files"), num(s.files_total), t("suspicious") + ": " + fmtNum(s.suspicious_total)), stat(t("total_bytes"), num(s.bytes_total, fmtBytes)),
    stat(t("disk_free"), num(s.disk_free, fmtBytes), "/ " + fmtBytes(s.disk_total)), stat(t("up24"), num(s.uploads_24h), fmtBytes(s.upload_bytes_24h)), stat(t("down24"), num(s.downloads_24h), fmtBytes(s.download_bytes_24h)));
  const charts = h("div", { class: "charts" }, panel(t("user_growth"), chart(s.user_growth.map((d) => d.total), s.user_growth.map((d) => d.day), fmtNum)),
    panel(t("storage_growth"), chart(s.storage_growth.map((d) => d.bytes), s.storage_growth.map((d) => d.day), fmtBytes)));
  const act = panel(t("recent_activity"), table([t("user"), t("action"), t("detail"), t("time")], s.recent_activity.map((a) => h("tr", {}, h("td", {}, a.username || "—"), h("td", {}, t("a_" + a.action) === "a_" + a.action ? a.action : t("a_" + a.action)), h("td", { class: "muted" }, a.detail), h("td", { class: "muted" }, fmtDate(a.created_at))))));
  const errs = panel(t("recent_errors"), table([t("time"), t("type"), t("detail"), "IP"], s.errors.map((e) => h("tr", {}, h("td", { class: "muted" }, fmtDate(e.created_at)), h("td", {}, h("span", { class: "badge " + (e.level === "error" ? "bad" : "warn") }, e.kind)), h("td", {}, e.message), h("td", { class: "muted", dir: "ltr" }, e.ip || "")))));
  return h("div", {}, cards, charts, act, errs);
}

// ---------------------------------------------------------------- users
async function users() {
  const wrap = h("div", {}), q = h("input", { type: "search", placeholder: t("filter_search"), style: "max-width:260px" });
  const st = h("select", { style: "width:auto" }, [["", "all_status"], ["active", "active"], ["disabled", "disabled"], ["banned", "banned"], ["admin", "admin"]].map(([v, k]) => h("option", { value: v }, t(k))));
  const out = h("div", {});
  async function refresh() {
    const p = new URLSearchParams({ q: q.value, status: st.value }); const d = (await api("/admin/users?" + p)).items;
    out.replaceChildren(table([t("username"), t("role"), t("status"), t("storage"), t("created"), t("last_login"), ""], d.map((u) => {
      const status = u.banned_reason ? ["bad", t("banned")] : u.is_active ? ["ok", t("active")] : ["warn", t("disabled")];
      return h("tr", {}, h("td", {}, h("b", {}, u.username), u.display_name && u.display_name !== u.username ? h("div", { class: "muted small" }, u.display_name) : null),
        h("td", {}, h("span", { class: "badge" + (u.role === "admin" ? " ok" : "") }, u.role === "admin" ? t("admin") : t("user"))),
        h("td", {}, h("span", { class: "badge " + status[0], title: u.banned_reason || "" }, status[1])),
        h("td", {}, fmtBytes(u.used) + " / " + fmtBytes(u.quota_bytes), h("div", { class: "bar" + (u.used / Math.max(1, u.quota_bytes) > 0.9 ? " warn" : ""), style: "width:120px" }, h("i", { style: "width:" + Math.min(100, (u.used / Math.max(1, u.quota_bytes)) * 100) + "%" })), h("span", { class: "muted small" }, fmtNum(u.files) + " " + t("files"))),
        h("td", { class: "muted" }, fmtDate(u.created_at)), h("td", { class: "muted" }, fmtDate(u.last_login)),
        h("td", {}, h("div", { class: "row" },
          h("button", { class: "btn sm", onclick: () => editUser(u, refresh) }, icon("edit"), t("edit")),
          u.banned_reason ? h("button", { class: "btn sm", onclick: async () => { if (await sensitive("POST", "/admin/users/" + u.id + "/unban")) { toast(t("saved")); refresh(); } } }, t("unban"))
            : h("button", { class: "btn sm danger", onclick: () => banUser(u, refresh) }, icon("ban"), t("ban")),
          !u.banned_reason ? h("button", { class: "btn sm", onclick: async () => { if (await sensitive("PATCH", "/admin/users/" + u.id, { is_active: !u.is_active })) { toast(t("saved")); refresh(); } } }, u.is_active ? t("disable") : t("enable")) : null,
          h("button", { class: "btn sm", onclick: async () => { if (await sensitive("POST", "/admin/users/" + u.id + "/revoke-sessions")) toast(t("saved")); } }, t("revoke")))));
    })));
  }
  let timer; q.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => refresh().catch(errToast), 250); }); st.addEventListener("change", () => refresh().catch(errToast));
  wrap.append(h("div", { class: "toolbar" }, q, st), out); await refresh(); return wrap;
}
async function banUser(u, done) {
  const reason = await promptDialog(t("ban") + ": " + u.username, { label: t("reason") }); if (!reason) return;
  if (await sensitive("POST", "/admin/users/" + u.id + "/ban", { reason })) { toast(t("saved")); done(); }
}
function editUser(u, done) {
  const quota = h("input", { type: "number", min: 0, value: Math.round(u.quota_bytes / 1048576) });
  const role = h("select", {}, [["user", t("user")], ["admin", t("admin")]].map(([v, l]) => h("option", { value: v, selected: u.role === v }, l)));
  let m;
  m = openModal([h("h2", {}, u.username), h("label", { class: "field" }, t("quota_mb"), quota), h("label", { class: "field" }, t("role"), role),
    h("div", { class: "actions" }, h("button", { class: "btn", onclick: () => m.close() }, t("cancel")), h("button", { class: "btn primary", onclick: async () => {
      const body = { quota_bytes: Math.round(Number(quota.value) * 1048576) }; if (role.value !== u.role) body.role = role.value;
      m.close(); if (await sensitive("PATCH", "/admin/users/" + u.id, body)) { toast(t("saved")); done(); } } }, t("save")))]);
}

// ---------------------------------------------------------------- files (metadata only)
async function files() {
  const q = h("input", { type: "search", placeholder: t("filter_search"), style: "max-width:260px" }), sus = h("input", { type: "checkbox", id: "sus" });
  const out = h("div", {});
  async function refresh() {
    const p = new URLSearchParams({ q: q.value }); if (sus.checked) p.set("suspicious", "1");
    const d = (await api("/admin/files?" + p)).items;
    out.replaceChildren(table([t("name"), t("owner"), t("size"), t("date"), ""], d.map((f) => h("tr", {}, h("td", {}, f.name, " ", f.suspicious ? h("span", { class: "badge warn" }, t("suspicious")) : null, f.trashed_at ? h("span", { class: "badge" }, t("trash")) : null),
      h("td", {}, f.owner), h("td", { class: "muted" }, fmtBytes(f.size)), h("td", { class: "muted" }, fmtDate(f.created_at)),
      h("td", {}, h("button", { class: "btn sm danger", onclick: async () => { const reason = await promptDialog(t("delete_file_admin"), { label: t("reason") }); if (!reason) return; if (await sensitive("DELETE", "/admin/files/" + f.id, { reason })) { toast(t("deleted")); refresh(); } } }, icon("trash"), t("delete")))))));
  }
  let timer; q.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => refresh().catch(errToast), 250); }); sus.addEventListener("change", () => refresh().catch(errToast));
  const wrap = h("div", {}, h("div", { class: "toolbar" }, q, h("label", { class: "row small", for: "sus" }, sus, t("only_suspicious"))), out); await refresh(); return wrap;
}

// ---------------------------------------------------------------- settings
async function settings() {
  const s = await api("/admin/settings"); const F = {};
  const mk = (key, label, type = "number", val = s[key]) => { F[key] = h("input", { type, value: val, min: 0 }); return h("label", { class: "field" }, label, F[key]); };
  const mb = (n) => Math.round(Number(n) / 1048576);
  const chk = (key, label) => { F[key] = h("input", { type: "checkbox", checked: s[key] === "1" }); return h("label", { class: "row", style: "margin-bottom:12px" }, F[key], label); };
  let logo = s.logo_data; const preview = h("div", { class: "brand-mark" }); const showLogo = () => preview.replaceChildren(logo ? h("img", { src: logo, alt: "" }) : icon("drive")); showLogo();
  const file = h("input", { type: "file", accept: "image/png,image/jpeg,image/webp", onchange: () => { const f = file.files[0]; if (!f) return; if (f.size > 200 * 1024) return toast(t("logo"), true); const r = new FileReader(); r.onload = () => { logo = r.result; showLogo(); }; r.readAsDataURL(f); } });
  const save = async () => {
    const settings = { service_name: F.service_name.value, logo_data: logo, max_upload_bytes: Math.round(F.max_upload_mb.value * 1048576), default_quota_bytes: Math.round(F.default_quota_mb.value * 1048576),
      rate_login_per_min: +F.rate_login_per_min.value, rate_api_per_min: +F.rate_api_per_min.value, rate_public_per_min: +F.rate_public_per_min.value,
      file_retention_days: +F.file_retention_days.value, trash_enabled: F.trash_enabled.checked, trash_retention_days: +F.trash_retention_days.value, registration_open: F.registration_open.checked, incomplete_upload_hours: +F.incomplete_upload_hours.value };
    if (await sensitive("PUT", "/admin/settings", { settings })) toast(t("saved"));
  };
  return h("div", { style: "max-width:640px" }, panel(t("service_name"), mk("service_name", t("service_name"), "text"), h("div", { class: "row", style: "margin-bottom:8px" }, preview, file, h("button", { class: "btn sm", onclick: () => { logo = ""; showLogo(); } }, t("remove_logo"))), h("div", { class: "muted small" }, t("logo"))),
    panel(t("storage"), mk("max_upload_mb", t("max_upload_mb"), "number", mb(s.max_upload_bytes)), mk("default_quota_mb", t("default_quota_mb"), "number", mb(s.default_quota_bytes)), mk("file_retention_days", t("retention_days")), mk("incomplete_upload_hours", t("stale_hours")), chk("trash_enabled", t("trash_enabled")), mk("trash_retention_days", t("trash_days"))),
    panel(getLang() === "fa" ? "امنیت" : "Security", mk("rate_login_per_min", t("rate_login")), mk("rate_api_per_min", t("rate_api")), mk("rate_public_per_min", t("rate_public")), chk("registration_open", t("reg_open"))),
    h("button", { class: "btn primary", onclick: save }, icon("check"), t("save")));
}

// ---------------------------------------------------------------- audit / events / health
async function audit() {
  const [a, e] = await Promise.all([api("/admin/audit"), api("/admin/events")]);
  return h("div", {}, panel(t("audit"), table([t("time"), t("admin"), t("action"), t("detail"), "IP"], a.items.map((r) => h("tr", {}, h("td", { class: "muted" }, fmtDate(r.created_at)), h("td", {}, r.admin || "—"), h("td", {}, h("span", { class: "badge" }, r.action), " ", r.target), h("td", { class: "muted" }, r.detail), h("td", { class: "muted", dir: "ltr" }, r.ip || ""))))),
    panel(t("events"), table([t("time"), t("type"), t("detail"), "IP"], e.items.map((r) => h("tr", {}, h("td", { class: "muted" }, fmtDate(r.created_at)), h("td", {}, h("span", { class: "badge " + (r.level === "error" ? "bad" : r.level === "warning" ? "warn" : "") }, r.kind)), h("td", {}, r.message), h("td", { class: "muted", dir: "ltr" }, r.ip || ""))))));
}
async function health() {
  const d = await api("/admin/health"); const ok = (v) => h("span", { class: "badge " + (v ? "ok" : "bad") }, v ? t("healthy") : t("problem"));
  const up = d.uptime_seconds; const upTxt = Math.floor(up / 3600) + "h " + Math.floor((up % 3600) / 60) + "m";
  return h("div", { class: "stats" }, stat(t("api"), ok(d.api)), stat(t("db"), ok(d.database)), stat(t("storage_ok"), ok(d.storage)), stat(t("disk_free"), fmtBytes(d.disk_free), "/ " + fmtBytes(d.disk_total)), stat(t("uptime"), upTxt), stat(t("pending"), fmtNum(d.pending_uploads)), stat("Python", d.python));
}
boot();

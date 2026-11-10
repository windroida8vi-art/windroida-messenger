import { LS, saveInPage, api, askPassword, brandMark, confirmDialog, errToast, fileIcon, fmtBytes, fmtDate, getCsrf, getLang, getTheme, h, icon,
  kindOf, openModal, popupMenu, promptDialog, setCsrf, setLang, t, toast, toggleTheme } from "./common.js";

const root = document.getElementById("root");
const S = {
  me: null, info: {}, view: "files", folderId: null, items: { folders: [], files: [] }, path: [], q: "", sort: "name", order: "asc",
  layout: LS.get("cd_layout", "grid"), kind: "all", sel: new Set(), collapsed: LS.get("cd_collapsed") === "1", navOpen: false,
  loading: false, shares: [], activity: [], authMode: "login",
};
let els = {};

// ================================================================== routing
function parseHash() {
  const m = location.hash.replace(/^#\/?/, "").split("/");
  const view = ["files", "trash", "shared", "activity", "profile"].includes(m[0]) ? m[0] : "files";
  return { view, folderId: view === "files" && m[1] ? parseInt(m[1], 10) || null : null };
}
function go(view, folderId = null) {
  if (S.q) { S.q = ""; if (els.search) els.search.value = ""; }
  const h2 = "#/" + view + (folderId ? "/" + folderId : "");
  if (location.hash === h2) route(); else location.hash = h2;
}
async function route() {
  if (!S.me) return;
  const r = parseHash();
  S.view = r.view; S.folderId = r.folderId; S.navOpen = false;
  if (S.view !== "files" && S.q) { S.q = ""; if (els.search) els.search.value = ""; }
  renderShell();
  await loadView();
}
window.addEventListener("hashchange", route);
window.addEventListener("cd:unauthorized", () => { if (S.me) { S.me = null; toast(t("session_expired"), true); render(); } });

// ================================================================== boot / auth
async function boot() {
  try { S.info = await api("/config"); } catch { /* offline: login still renders */ }
  try { applyMe(await api("/me")); } catch { S.me = null; }
  render();
}
function applyMe(d) { S.me = d.user; S.usage = d.usage; S.maxUpload = d.max_upload_bytes; S.trashEnabled = d.trash_enabled !== false; S.retention = d.retention_days || 0; S.trashDays = d.trash_days || 0; S.info = { ...S.info, service_name: d.service_name, logo_data: d.logo_data }; setCsrf(d.csrf); }
function render() { if (S.me) { renderShell(); route(); } else renderAuth(); }
function toolbarGlobal() {
  return h("div", { class: "row", style: "justify-content:flex-end;margin-bottom:8px" },
    h("button", { class: "btn ghost iconbtn", title: t("language"), onclick: () => { setLang(getLang() === "fa" ? "en" : "fa"); render(); } }, icon("globe")),
    h("button", { class: "btn ghost iconbtn", title: t("theme"), onclick: () => { toggleTheme(); render(); } }, icon(getTheme() === "dark" ? "sun" : "moon")));
}
function renderAuth() {
  if (S.info && S.info.password_auth === false) {   // folded into Windroida: no form here, the only way in is the Windroida menu link
    const fa = getLang() === "fa";
    root.replaceChildren(h("div", { class: "auth" }, h("div", {}, toolbarGlobal(),
      h("div", { class: "auth-card" }, brandMark(S.info), h("h1", {}, S.info.service_name || t("app_name")),
        h("p", { class: "muted", style: "line-height:2;margin:14px 0 0" }, fa
          ? "برای ورود، تو ویندروید منوی ☰ را باز کن و «فضای ابری» را بزن. ورود با نام کاربری و رمز در اینجا وجود ندارد."
          : "To sign in, open Windroida's ☰ menu and tap “Cloud Drive”. There is no username/password login here.")))));
    return;
  }
  const reg = S.authMode === "register";
  const err = h("div", { class: "err", role: "alert" });
  const u = h("input", { type: "text", autocomplete: "username", required: true, maxlength: 32, dir: "ltr" });
  const p = h("input", { type: "password", autocomplete: reg ? "new-password" : "current-password", required: true, maxlength: 128, dir: "ltr" });
  const em = h("input", { type: "email", autocomplete: "email", dir: "ltr" });
  const btn = h("button", { class: "btn primary", style: "width:100%;justify-content:center", type: "submit" }, reg ? t("register") : t("login"));
  const form = h("form", { onsubmit: async (e) => {
    e.preventDefault(); err.textContent = ""; btn.disabled = true;
    try {
      const body = { username: u.value.trim(), password: p.value }; if (reg && em.value.trim()) body.email = em.value.trim();
      applyMe(await api(reg ? "/register" : "/login", { method: "POST", body }));
      location.hash = "#/files"; render();
    } catch (ex) { err.textContent = ex.message; } finally { btn.disabled = false; }
  } },
    h("label", { class: "field" }, t("username"), u), h("label", { class: "field" }, t("password"), p),
    reg ? [h("div", { class: "muted small", style: "margin:-6px 0 10px" }, t("pw_hint")), h("label", { class: "field" }, t("email"), em)] : null, err, btn);
  const switcher = S.info.registration_open === false && !reg ? null :
    h("button", { class: "btn ghost", style: "width:100%;justify-content:center;margin-top:10px", onclick: () => { S.authMode = reg ? "login" : "register"; renderAuth(); } }, reg ? t("have_account") : t("no_account"));
  root.replaceChildren(h("div", { class: "auth" }, h("div", {}, toolbarGlobal(),
    h("div", { class: "auth-card" }, brandMark(S.info), h("h1", {}, S.info.service_name || t("app_name")), form, switcher))));
  u.focus();
}
async function logout() { try { await api("/logout", { method: "POST" }); } catch { /* ignore */ } S.me = null; location.hash = ""; render(); }

// ================================================================== shell
function navItem(view, ic, label) {
  return h("a", { href: "#/" + view, class: S.view === view ? "active" : "", title: label }, icon(ic), h("span", { class: "label" }, label));
}
function renderShell() {
  const q = S.usage ? Math.min(100, (S.usage.used / Math.max(1, S.usage.quota)) * 100) : 0;
  els.quota = h("div", { class: "quota" });
  const side = h("aside", { class: "sidebar" },
    h("div", { class: "brand" }, brandMark(S.info), h("span", { class: "label" }, S.info.service_name || t("app_name"))),
    h("nav", { class: "nav" }, navItem("files", "folder", t("my_files")), navItem("shared", "link", t("shared")), navItem("trash", "trash", t("trash")),
      navItem("activity", "activity", t("activity")), navItem("profile", "user", t("profile")),
      S.me.role === "admin" ? h("a", { href: "/admin" }, icon("shield"), h("span", { class: "label" }, t("admin_panel"))) : null),
    h("div", { class: "grow" }), els.quota,
    h("nav", { class: "nav" }, h("button", { onclick: logout }, icon("logout"), h("span", { class: "label" }, t("logout")))));
  const search = h("input", { type: "search", placeholder: t("search"), value: S.q, "aria-label": t("search") });
  let timer;
  search.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => { S.q = search.value.trim(); if (S.view !== "files") { location.hash = "#/files"; } else loadView(); }, 250); });
  els.search = search;
  const top = h("header", { class: "topbar" },
    h("button", { class: "btn ghost iconbtn", "aria-label": "menu", onclick: () => { if (innerWidth <= 900) { S.navOpen = !S.navOpen; els.app.classList.toggle("navopen", S.navOpen); } else { S.collapsed = !S.collapsed; LS.set("cd_collapsed", S.collapsed ? "1" : "0"); els.app.classList.toggle("collapsed", S.collapsed); } } }, icon("menu")),
    h("div", { class: "search" }, icon("search"), search), h("div", { class: "grow" }),
    h("span", { class: "muted small hide-sm" }, S.me.display_name || S.me.username),
    h("button", { class: "btn ghost iconbtn", title: t("language"), onclick: () => { setLang(getLang() === "fa" ? "en" : "fa"); render(); } }, icon("globe")),
    h("button", { class: "btn ghost iconbtn", title: t("theme"), onclick: () => { toggleTheme(); render(); } }, icon(getTheme() === "dark" ? "sun" : "moon")));
  els.content = h("div", { class: "content", "data-drop": t("drop_here") });
  els.app = h("div", { class: "app" + (S.collapsed ? " collapsed" : "") + (S.navOpen ? " navopen" : "") }, side,
    h("div", { class: "scrim", onclick: () => { S.navOpen = false; els.app.classList.remove("navopen"); } }),
    h("main", { class: "main" }, top, els.content));
  root.replaceChildren(els.app);
  setupDrop(); renderQuota(q);
  side.addEventListener("click", (e) => { if (e.target.closest("a") && innerWidth <= 900) { els.app.classList.remove("navopen"); } });
}
function renderQuota() {
  if (!els.quota || !S.usage) return;
  const pct = Math.min(100, (S.usage.used / Math.max(1, S.usage.quota)) * 100);
  els.quota.replaceChildren(h("div", {}, t("storage")), h("div", { class: "bar" + (pct > 95 ? " full" : pct > 80 ? " warn" : "") }, h("i", { style: "width:" + pct.toFixed(1) + "%" })),
    h("div", { class: "muted" }, fmtBytes(S.usage.used) + " " + t("used_of") + " " + fmtBytes(S.usage.quota)),
    S.retention ? h("div", { class: "muted small", style: "margin-top:8px" }, t("auto_delete_note").replace("{n}", S.retention.toLocaleString(getLang() === "fa" ? "fa-IR" : "en-US"))) : null);
}
async function refreshUsage() { try { S.usage = await api("/usage"); renderQuota(); } catch { /* ignore */ } }

// ================================================================== data loading
function skeleton() { return h("div", { class: "grid" }, Array.from({ length: 8 }, (_, i) => h("div", { class: "skel card", style: "animation-delay:" + i * 60 + "ms" }))); }
async function loadView() {
  S.sel.clear();
  const sk = setTimeout(() => { if (els.content && (S.view === "files" || S.view === "trash")) els.content.replaceChildren(skeleton()); }, 160);
  try {
    if (S.view === "files" || S.view === "trash") {
      const p = new URLSearchParams({ view: S.view === "trash" ? "trash" : "files", sort: S.sort, order: S.order });
      if (S.view === "files") { if (S.q) p.set("q", S.q); else if (S.folderId) p.set("folder_id", S.folderId); }
      const d = await api("/items?" + p); S.items = d; S.path = d.path || [];
    } else if (S.view === "shared") S.shares = (await api("/shares")).items;
    else if (S.view === "activity") S.activity = (await api("/activity")).items;
  } catch (e) { clearTimeout(sk); if (e.status === 404 && S.folderId) { go("files"); return; } errToast(e); }
  clearTimeout(sk);
  renderContent();
}
const reload = () => loadView().then(refreshUsage);

// ================================================================== content
function entries() {
  const f = S.kind === "all" ? S.items.folders.map((x) => ({ ...x, type: "folder", key: "d:" + x.id })) : [];
  const files = S.items.files.filter((x) => S.kind === "all" || kindOf(x.name) === S.kind).map((x) => ({ ...x, type: "file", key: "f:" + x.id }));
  return [...f, ...files];
}
function renderContent() {
  if (!els.content) return;
  const c = els.content;
  c.className = "content" + (S.sel.size ? " has-sel" : "") + (S.still ? " static" : ""); S.still = false;
  if (S.view === "shared") return c.replaceChildren(sharedView());
  if (S.view === "activity") return c.replaceChildren(activityView());
  if (S.view === "profile") return c.replaceChildren(profileView());
  const list = entries();
  const kids = [toolbar()];
  if (S.view === "files") kids.push(chips());
  if (S.sel.size) kids.push(bulkBar(list));
  if (!list.length) kids.push(h("div", { class: "empty" }, icon(S.view === "trash" ? "trash" : "folder", "lg"),
    h("b", {}, S.view === "trash" ? t("trash_empty") : S.q || S.kind !== "all" ? t("no_results") : t("empty_folder")),
    S.view === "files" && !S.q && S.kind === "all" ? h("span", {}, t("empty_hint")) : null));
  else kids.push(S.layout === "grid" ? gridView(list) : listView(list));
  c.replaceChildren(...kids);
}
function toolbar() {
  const crumbs = h("div", { class: "crumbs" });
  if (S.view === "trash") crumbs.append(h("span", {}, t("trash")), S.trashDays ? h("span", { class: "muted small", style: "font-weight:400;margin-inline-start:10px" }, t("trash_note").replace("{n}", S.trashDays.toLocaleString(getLang() === "fa" ? "fa-IR" : "en-US"))) : null);
  else if (S.q) crumbs.append(h("span", {}, "“" + S.q + "”"));
  else {
    crumbs.append(h("button", { onclick: () => go("files") }, t("my_files")));
    for (const p of S.path) crumbs.append(h("span", { class: "sep" }, "›"), h("button", { onclick: () => go("files", p.id) }, p.name));
  }
  const sort = h("select", { "aria-label": t("sort_by"), style: "width:auto", onchange: (e) => { S.sort = e.target.value; loadView(); } },
    ["name", "date", "size", "type"].map((k) => h("option", { value: k, selected: S.sort === k }, t(k))));
  const order = h("button", { class: "btn iconbtn", title: S.order === "asc" ? t("asc") : t("desc"), onclick: () => { S.order = S.order === "asc" ? "desc" : "asc"; loadView(); } },
    h("span", { style: "font-size:16px" }, S.order === "asc" ? "↑" : "↓"));
  const layout = h("button", { class: "btn iconbtn", title: S.layout === "grid" ? t("list_view") : t("grid_view"), onclick: () => { S.layout = S.layout === "grid" ? "list" : "grid"; LS.set("cd_layout", S.layout); renderContent(); } }, icon(S.layout === "grid" ? "list" : "grid"));
  const actions = S.view === "trash"
    ? [h("button", { class: "btn danger", onclick: emptyTrash }, icon("trash"), t("empty_trash"))]
    : [h("button", { class: "btn", onclick: newFolder }, icon("folder-plus"), h("span", { class: "hide-sm" }, t("new_folder"))),
      h("button", { class: "btn primary", onclick: () => pickFiles() }, icon("upload"), t("upload"))];
  return h("div", { class: "toolbar" }, crumbs, h("div", { class: "grow" }), sort, order, layout, ...actions);
}
function chips() {
  return h("div", { class: "chips" }, ["all", "image", "doc", "media", "archive", "other"].map((k) =>
    h("button", { class: "chip" + (S.kind === k ? " on" : ""), onclick: () => { S.kind = k; renderContent(); } },
      { all: t("all"), image: t("images"), doc: t("docs"), media: t("media"), archive: t("archives"), other: t("other") }[k])));
}
function bulkBar(list) {
  const picked = list.filter((e) => S.sel.has(e.key));
  const btns = S.view === "trash"
    ? [h("button", { class: "btn sm", onclick: () => restoreItems(picked) }, icon("restore"), t("restore")), h("button", { class: "btn sm danger", onclick: () => purgeItems(picked) }, icon("trash"), t("delete_forever"))]
    : [h("button", { class: "btn sm", onclick: () => moveItems(picked) }, icon("move"), t("move")), h("button", { class: "btn sm danger", onclick: () => trashItems(picked) }, icon("trash"), t("delete"))];
  return h("div", { class: "bulk" }, h("b", {}, S.sel.size.toLocaleString(getLang() === "fa" ? "fa-IR" : "en-US") + " " + t("selected")), h("div", { class: "grow" }), ...btns,
    h("button", { class: "btn sm ghost", onclick: () => { S.sel.clear(); renderContent(); } }, icon("x")));
}
function toggleSel(e) { S.sel.has(e.key) ? S.sel.delete(e.key) : S.sel.add(e.key); S.still = true; renderContent(); }
function primary(e) {
  if (S.sel.size) return toggleSel(e);
  if (S.view === "trash") return toggleSel(e);
  if (e.type === "folder") return go("files", e.id);
  if (e.previewable) return previewFile(e);
  return null;
}
function menuFor(e) {
  if (S.view === "trash") return [{ icon: "restore", label: t("restore"), run: () => restoreItems([e]) }, { icon: "trash", label: t("delete_forever"), danger: true, run: () => purgeItems([e]) }];
  return [e.type === "folder" ? { icon: "folder", label: t("open"), run: () => go("files", e.id) } : null,
    e.type === "file" && e.previewable ? { icon: "eye", label: t("preview"), run: () => previewFile(e) } : null,
    e.type === "file" ? { icon: "download", label: t("download"), run: () => downloadFile(e) } : null,
    e.type === "file" ? { icon: "link", label: t("share"), run: () => shareDialog(e) } : null,
    { icon: "edit", label: t("rename"), run: () => renameItem(e) }, { icon: "move", label: t("move"), run: () => moveItems([e]) },
    { icon: "trash", label: t("delete"), danger: true, run: () => trashItems([e]) }];
}
function thumb(e) {
  if (e.type === "folder") return h("div", { class: "thumb" }, icon("folder", "lg"));
  if (e.mime && e.mime.startsWith("image/") && e.previewable && e.size < 15 * 1024 * 1024) return h("div", { class: "thumb k-image" }, h("img", { loading: "lazy", alt: "", src: "/api/files/" + e.id + "/preview", onload: (ev) => ev.target.classList.add("ld"), onerror: (ev) => ev.target.remove() }));
  return h("div", { class: "thumb k-" + (e.mime === "application/pdf" ? "pdf" : kindOf(e.name)) }, icon(fileIcon(e), "lg"));
}
function daysLeft(e) {
  const nf = (n) => n.toLocaleString(getLang() === "fa" ? "fa-IR" : "en-US");
  if (S.view === "trash") {   // trash: days until it is deleted for good
    if (!S.trashDays || !e.trashed_at) return "";
    return " · " + nf(Math.max(0, Math.ceil((new Date(e.trashed_at).getTime() + S.trashDays * 864e5 - Date.now()) / 864e5))) + " " + t("days_left");
  }
  if (!S.retention || e.type !== "file") return "";   // only when an admin enabled global auto-delete
  return " · " + nf(Math.max(0, Math.ceil((new Date(e.created_at).getTime() + S.retention * 864e5 - Date.now()) / 864e5))) + " " + t("days_left");
}
function chk(e) { return h("input", { type: "checkbox", class: "chk", checked: S.sel.has(e.key), "aria-label": e.name, onclick: (ev) => { ev.stopPropagation(); toggleSel(e); } }); }
function moreBtn(e) { return h("button", { class: "btn iconbtn more", "aria-label": "menu", onclick: (ev) => { ev.stopPropagation(); popupMenu(ev.currentTarget, menuFor(e)); } }, icon("more")); }
function gridView(list) {
  return h("div", { class: "grid" }, list.map((e, i) => h("div", { class: "card" + (e.type === "folder" ? " folder" : "") + (S.sel.has(e.key) ? " sel" : ""), tabindex: 0, style: "animation-delay:" + Math.min(i, 20) * 12 + "ms",
    onclick: (ev) => primary(e) || popupMenu(ev.currentTarget, menuFor(e)), oncontextmenu: (ev) => { ev.preventDefault(); popupMenu(ev.currentTarget, menuFor(e)); },
    onkeydown: (ev) => { if (ev.key === "Enter") { primary(e); } } },
    chk(e), moreBtn(e), thumb(e),
    h("div", { class: "meta" }, h("div", { class: "name", title: e.name }, e.name), h("div", { class: "muted small" }, e.type === "folder" ? t("folder") + daysLeft(e) : fmtBytes(e.size) + daysLeft(e) + (e.suspicious ? " ⚠" : ""))))));
}
function listView(list) {
  const all = list.every((e) => S.sel.has(e.key));
  return h("div", { class: "tablewrap" }, h("table", { class: "list" },
    h("thead", {}, h("tr", {}, h("th", { style: "width:36px" }, h("input", { type: "checkbox", checked: all, "aria-label": t("select_all"), onchange: () => { if (all) S.sel.clear(); else list.forEach((e) => S.sel.add(e.key)); renderContent(); } })),
      h("th", {}, t("name")), h("th", { class: "hide-sm" }, t("size")), h("th", { class: "hide-sm" }, t("date")), h("th", {}))),
    h("tbody", {}, list.map((e) => h("tr", { class: "item" + (S.sel.has(e.key) ? " sel" : ""), onclick: (ev) => primary(e) || popupMenu(ev.currentTarget, menuFor(e)) },
      h("td", {}, h("input", { type: "checkbox", checked: S.sel.has(e.key), "aria-label": e.name, onclick: (ev) => { ev.stopPropagation(); toggleSel(e); } })),
      h("td", {}, h("div", { class: "nm" }, icon(e.type === "folder" ? "folder" : fileIcon(e)), e.name, e.suspicious ? h("span", { class: "badge warn" }, "⚠") : null)),
      h("td", { class: "hide-sm muted" }, e.type === "folder" ? "—" : fmtBytes(e.size)), h("td", { class: "hide-sm muted" }, fmtDate(e.created_at)),
      h("td", {}, h("button", { class: "btn ghost iconbtn", "aria-label": "menu", onclick: (ev) => { ev.stopPropagation(); popupMenu(ev.currentTarget, menuFor(e)); } }, icon("more"))))))));
}

// ================================================================== item actions
async function newFolder() {
  const name = await promptDialog(t("new_folder"), { label: t("folder_name") }); if (!name) return;
  try { await api("/folders", { method: "POST", body: { name, parent_id: S.folderId } }); toast(t("folder_created")); reload(); } catch (e) { errToast(e); }
}
async function renameItem(e) {
  const name = await promptDialog(t("rename"), { label: t("name"), value: e.name }); if (!name || name === e.name) return;
  try { await api((e.type === "folder" ? "/folders/" : "/files/") + e.id, { method: "PATCH", body: { name } }); toast(t("renamed")); reload(); } catch (er) { errToast(er); }
}
function bodyOf(list) { return { files: list.filter((e) => e.type === "file").map((e) => e.id), folders: list.filter((e) => e.type === "folder").map((e) => e.id) }; }
async function trashItems(list) {
  if (!S.trashEnabled && !(await confirmDialog(t("confirm_purge"), { danger: true }))) return;
  try { await api("/items/trash", { method: "POST", body: bodyOf(list) }); toast(S.trashEnabled ? t("moved_trash") : t("deleted")); reload(); } catch (e) { errToast(e); }
}
async function restoreItems(list) { try { await api("/items/restore", { method: "POST", body: bodyOf(list) }); toast(t("restored")); reload(); } catch (e) { errToast(e); } }
async function purgeItems(list) {
  if (!(await confirmDialog(t("confirm_purge"), { danger: true, okText: t("delete_forever") }))) return;
  try { await api("/items/purge", { method: "POST", body: bodyOf(list) }); toast(t("deleted")); reload(); } catch (e) { errToast(e); }
}
async function emptyTrash() {
  if (!(await confirmDialog(t("confirm_purge"), { danger: true, okText: t("empty_trash") }))) return;
  try { await api("/items/purge", { method: "POST", body: { all: true } }); toast(t("deleted")); reload(); } catch (e) { errToast(e); }
}
function downloadFile(e) { saveInPage("/api/files/" + e.id + "/download", e.name, e.size); }
function previewFile(e) {
  const url = "/api/files/" + e.id + "/preview";
  const body = e.mime === "application/pdf" ? [h("iframe", { src: url, title: e.name }), h("div", { class: "muted small", style: "margin-top:8px" }, t("preview_fallback") + " ", h("a", { href: url, target: "_blank", rel: "noopener" }, t("open_new_tab")))]
    : h("img", { src: url, alt: e.name });
  let m;
  m = openModal([h("div", { class: "row" }, h("h2", { class: "grow", style: "margin:0;overflow:hidden;text-overflow:ellipsis" }, e.name), h("button", { class: "btn iconbtn ghost", "aria-label": t("close"), onclick: () => m.close() }, icon("x"))),
    h("div", { class: "preview", style: "margin-top:12px" }, body),
    h("div", { class: "actions" }, h("button", { class: "btn", onclick: () => downloadFile(e) }, icon("download"), t("download")), h("button", { class: "btn", onclick: () => { m.close(); shareDialog(e); } }, icon("link"), t("share")))], { wide: true });
}
async function moveItems(list) {
  let tree;
  try { tree = (await api("/folders/tree")).folders; } catch (e) { return errToast(e); }
  const moving = new Set(list.filter((e) => e.type === "folder").map((e) => e.id));
  const banned = new Set(moving); let changed = true;
  while (changed) { changed = false; for (const f of tree) if (!banned.has(f.id) && banned.has(f.parent_id)) { banned.add(f.id); changed = true; } }
  const byParent = new Map(); for (const f of tree) { const k = f.parent_id || 0; if (!byParent.has(k)) byParent.set(k, []); byParent.get(k).push(f); }
  const rows = []; (function walk(pid, depth) { for (const f of byParent.get(pid) || []) { if (!banned.has(f.id)) { rows.push([f, depth]); walk(f.id, depth + 1); } } })(0, 1);
  let m;
  const pick = async (dest) => {
    m.close();
    try { for (const e of list) await api((e.type === "folder" ? "/folders/" : "/files/") + e.id, { method: "PATCH", body: e.type === "folder" ? { parent_id: dest } : { folder_id: dest } }); toast(t("moved")); reload(); } catch (er) { errToast(er); }
  };
  const btn = (label, dest, depth, ic) => h("button", { class: "btn ghost", style: "width:100%;justify-content:flex-start;padding-inline-start:" + (12 + depth * 18) + "px", onclick: () => pick(dest) }, icon(ic), label);
  m = openModal([h("h2", {}, t("move_to")), h("div", { style: "max-height:50vh;overflow:auto" }, btn(t("my_files"), null, 0, "home"), rows.map(([f, d]) => btn(f.name, f.id, d, "folder"))),
    h("div", { class: "actions" }, h("button", { class: "btn", onclick: () => m.close() }, t("cancel")))]);
}
function copyText(text, input) {
  const ok = () => toast(t("copied"));
  if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(text).then(ok, () => { input.select(); document.execCommand("copy"); ok(); });
  else { input.select(); try { document.execCommand("copy"); ok(); } catch { /* user can copy manually */ } }
}
function shareDialog(e) {
  const pw = h("input", { type: "text", autocomplete: "off", dir: "ltr" });
  const ex = h("select", {}, [["", "never"], ["1", "h1"], ["24", "h24"], ["168", "h168"], ["720", "h720"]].map(([v, k]) => h("option", { value: v }, t(k))));
  const out = h("div", {}); let m;
  const create = async () => {
    try {
      const s = await api("/files/" + e.id + "/shares", { method: "POST", body: { password: pw.value || null, expires_hours: ex.value ? parseInt(ex.value, 10) : null } });
      const url = location.origin + s.url; const inp = h("input", { type: "text", readonly: true, value: url, dir: "ltr" });
      out.replaceChildren(h("div", { class: "row", style: "margin-top:12px" }, h("div", { class: "grow" }, inp), h("button", { class: "btn primary", onclick: () => copyText(url, inp) }, icon("copy"), t("copy"))));
      inp.select();
    } catch (er) { errToast(er); }
  };
  m = openModal([h("h2", {}, t("share_title")), h("div", { class: "muted small", style: "margin-bottom:12px" }, e.name),
    h("label", { class: "field" }, t("link_password"), pw), h("label", { class: "field" }, t("expiry"), ex), out,
    h("div", { class: "actions" }, h("button", { class: "btn", onclick: () => m.close() }, t("close")), h("button", { class: "btn primary", onclick: create }, icon("link"), t("create_link")))]);
}

// ================================================================== other views
function sharedView() {
  const rows = S.shares;
  const body = !rows.length ? h("div", { class: "empty" }, icon("link", "lg"), h("b", {}, t("no_links")))
    : h("div", { class: "tablewrap" }, h("table", { class: "list" }, h("thead", {}, h("tr", {}, [t("file"), t("status"), t("expiry"), t("downloads"), ""].map((x) => h("th", {}, x)))),
      h("tbody", {}, rows.map((s) => h("tr", {}, h("td", {}, s.file_name),
        h("td", {}, h("span", { class: "badge " + (!s.active || s.expired ? "bad" : "ok") }, !s.active ? t("inactive") : s.expired ? t("expired") : t("active")), " ", s.has_password ? h("span", { class: "badge" }, t("protected")) : null),
        h("td", { class: "muted" }, s.expires_at ? fmtDate(s.expires_at) : t("never")), h("td", { class: "muted" }, s.downloads),
        h("td", {}, h("div", { class: "row" },
          s.active && !s.expired ? h("button", { class: "btn sm", onclick: () => { const i = h("input", { value: location.origin + s.url }); document.body.append(i); copyText(i.value, i); i.remove(); } }, icon("copy"), t("copy")) : null,
          s.active ? h("button", { class: "btn sm danger", onclick: async () => { try { await api("/shares/" + s.id, { method: "DELETE" }); loadView(); } catch (e) { errToast(e); } } }, icon("ban"), t("disable")) : null)))))));
  return h("div", {}, h("div", { class: "toolbar" }, h("div", { class: "crumbs" }, h("span", {}, t("shared")))), body);
}
function activityView() {
  const body = !S.activity.length ? h("div", { class: "empty" }, icon("activity", "lg"), h("b", {}, t("no_activity")))
    : h("div", { class: "tablewrap" }, h("table", { class: "list" }, h("thead", {}, h("tr", {}, [t("action"), t("detail"), t("size"), t("time")].map((x) => h("th", {}, x)))),
      h("tbody", {}, S.activity.map((a) => h("tr", {}, h("td", {}, t("a_" + a.action) === "a_" + a.action ? a.action : t("a_" + a.action)), h("td", { class: "muted" }, a.detail), h("td", { class: "muted" }, a.bytes ? fmtBytes(a.bytes) : ""), h("td", { class: "muted" }, fmtDate(a.created_at)))))));
  return h("div", {}, h("div", { class: "toolbar" }, h("div", { class: "crumbs" }, h("span", {}, t("activity")))), body);
}
function profileView() {
  const dn = h("input", { type: "text", value: S.me.display_name || "", maxlength: 60 }), em = h("input", { type: "email", value: S.me.email || "", dir: "ltr" });
  const cur = h("input", { type: "password", autocomplete: "current-password", dir: "ltr" }), nw = h("input", { type: "password", autocomplete: "new-password", dir: "ltr" });
  const save = async () => { try { applyMe(await api("/me", { method: "PATCH", body: { display_name: dn.value, email: em.value } })); toast(t("saved")); renderShell(); } catch (e) { errToast(e); } };
  const chpw = async () => { try { await api("/me/password", { method: "POST", body: { current_password: cur.value, new_password: nw.value } }); cur.value = nw.value = ""; toast(t("pw_changed")); } catch (e) { errToast(e); } };
  return h("div", { style: "max-width:560px" }, h("div", { class: "toolbar" }, h("div", { class: "crumbs" }, h("span", {}, t("profile")))),
    h("div", { class: "panel" }, h("h3", {}, t("account")), h("div", { class: "muted small", style: "margin-bottom:12px" }, S.me.username + " · " + (S.me.role === "admin" ? t("admin") : t("user")) + " · " + t("member_since") + " " + fmtDate(S.me.created_at)),
      h("label", { class: "field" }, t("display_name"), dn), h("label", { class: "field" }, t("email"), em), h("button", { class: "btn primary", onclick: save }, t("save"))),
    h("div", { class: "panel" }, h("h3", {}, t("change_password")), h("label", { class: "field" }, t("current_password"), cur), h("label", { class: "field" }, t("new_password"), nw),
      h("div", { class: "muted small", style: "margin-bottom:10px" }, t("pw_hint")), h("button", { class: "btn primary", onclick: chpw }, t("change_password"))));
}

// ================================================================== uploads (chunked, resumable, real progress)
const uploads = []; let upPanel, running = 0;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function pickFiles() { const i = h("input", { type: "file", multiple: true, style: "display:none", onchange: () => { addUploads([...i.files]); i.remove(); } }); document.body.append(i); i.click(); }
function setupDrop() {
  const c = els.content; let depth = 0;
  c.addEventListener("dragenter", (e) => { if (S.view !== "files" || !e.dataTransfer.types.includes("Files")) return; e.preventDefault(); depth++; c.classList.add("drag"); });
  c.addEventListener("dragover", (e) => { if (S.view === "files") e.preventDefault(); });
  c.addEventListener("dragleave", () => { depth = Math.max(0, depth - 1); if (!depth) c.classList.remove("drag"); });
  c.addEventListener("drop", (e) => {
    e.preventDefault(); depth = 0; c.classList.remove("drag"); if (S.view !== "files") return;
    const files = []; let skipped = 0;
    for (const it of e.dataTransfer.items || []) { const en = it.webkitGetAsEntry && it.webkitGetAsEntry(); if (en && en.isDirectory) skipped++; else if (it.kind === "file") files.push(it.getAsFile()); }
    if (skipped) toast(getLang() === "fa" ? "آپلود پوشه پشتیبانی نمی‌شود؛ ابتدا پوشه بسازید و فایل‌ها را آپلود کنید" : "Folder drops are not supported; create a folder and upload its files", true);
    addUploads(files.filter(Boolean));
  });
}
function addUploads(files) {
  for (const f of files) uploads.push({ file: f, folderId: S.folderId, status: "queued", loaded: 0, id: Math.random().toString(36).slice(2) });
  renderUploads(); pump();
}
function pump() {
  while (running < 2) {
    const u = uploads.find((x) => x.status === "queued"); if (!u) break;
    running++; u.status = "active";
    runUpload(u).catch(() => {}).finally(() => { running--; renderUploads(); pump(); });
  }
}
function putChunk(uploadId, idx, blob, u, base) {
  return new Promise((resolve, reject) => {
    const x = new XMLHttpRequest(); u.xhr = x;
    x.open("PUT", "/api/uploads/" + uploadId + "/chunks/" + idx);
    x.setRequestHeader("X-CSRF-Token", getCsrf()); x.setRequestHeader("Content-Type", "application/octet-stream");
    x.upload.onprogress = (e) => { u.loaded = base + e.loaded; renderUploads(); };
    x.onload = () => {
      if (x.status >= 200 && x.status < 300) return resolve();
      const er = new Error("HTTP " + x.status); er.status = x.status;
      try { const d = JSON.parse(x.responseText); er.message = (getLang() === "fa" ? d.message : d.message_en) || er.message; er.code = d.error; } catch { /* non-JSON */ }
      reject(er);
    };
    x.onerror = x.ontimeout = () => { const er = new Error(t("net_error")); er.network = true; reject(er); };
    x.onabort = () => { const er = new Error(t("cancelled")); er.aborted = true; reject(er); };
    x.send(blob);
  });
}
async function runUpload(u, restarted = false) {
  const f = u.file, key = "cd_up:" + S.me.id + ":" + f.name + ":" + f.size + ":" + f.lastModified + ":" + (u.folderId || 0);
  try {
    if (S.maxUpload && f.size > S.maxUpload) throw Object.assign(new Error(getLang() === "fa" ? "حجم فایل از حداکثر مجاز بیشتر است" : "File exceeds the maximum upload size"), { fatal: true });
    let st = null; const saved = LS.get(key);
    if (saved) { try { st = await api("/uploads/" + saved); } catch { LS.del(key); } }   // resume an interrupted upload of the same file
    if (!st) { st = await api("/uploads", { method: "POST", body: { name: f.name, size: f.size, folder_id: u.folderId } }); LS.set(key, st.upload_id); }
    u.uploadId = st.upload_id; const cs = st.chunk_size; let have = new Set(st.received);
    for (let i = 0; i < st.total_chunks; i++) {
      if (have.has(i)) continue;
      const done = [...have].reduce((a, j) => a + Math.min(cs, f.size - j * cs), 0);
      for (let attempt = 0; ; attempt++) {
        if (u.cancelled) throw Object.assign(new Error(t("cancelled")), { aborted: true });
        try { u.loaded = done; await putChunk(st.upload_id, i, f.slice(i * cs, Math.min(f.size, (i + 1) * cs)), u, done); u.status = "active"; break; }
        catch (e) {
          if (e.aborted) throw e;
          const retryable = e.network || e.status >= 500 || e.status === 429 || e.status === 408;
          if (!retryable || attempt >= 10) throw e;
          u.status = "retrying"; renderUploads(); await sleep(Math.min(1000 * 2 ** attempt, 15000));
          try { have = new Set((await api("/uploads/" + st.upload_id)).received); if (have.has(i)) break; } catch (er) { if (er.status === 404) throw er; }
        }
      }
      have.add(i);
    }
    u.loaded = f.size; await api("/uploads/" + st.upload_id + "/complete", { method: "POST" });
    LS.del(key); u.status = "done";
    if (S.view === "files" && !S.q && S.folderId === u.folderId) loadView();
    refreshUsage();
  } catch (e) {
    if (e.status === 404 && !restarted && !e.fatal) { LS.del(key); u.loaded = 0; return runUpload(u, true); }
    if (e.aborted) { u.status = "cancelled"; return; }
    if (e.status && e.status < 500) LS.del(key);
    u.status = "error"; u.error = e.message; throw e;
  }
}
function renderUploads() {
  if (!uploads.length) return;
  if (!upPanel) { upPanel = h("div", { class: "uploads", role: "status" }); document.body.append(upPanel); }
  const active = uploads.filter((u) => u.status === "queued" || u.status === "active" || u.status === "retrying");
  const label = (u) => ({ queued: t("waiting"), retrying: t("retrying"), done: t("upload_done"), error: u.error || t("upload_failed"), cancelled: t("cancelled") }[u.status]);
  upPanel.replaceChildren(
    h("header", {}, icon("upload"), h("span", { class: "grow" }, (active.length ? t("uploading") + " (" + active.length + ")" : t("upload_done"))),
      h("button", { class: "btn iconbtn ghost sm", "aria-label": t("close"), onclick: () => { for (const u of active) { u.cancelled = true; if (u.xhr) u.xhr.abort(); u.status = "cancelled"; } uploads.length = 0; upPanel.remove(); upPanel = null; } }, icon("x"))),
    h("div", { class: "list" }, uploads.slice(-30).map((u) => {
      const pct = u.file.size ? Math.min(100, Math.floor((u.loaded / u.file.size) * 100)) : u.status === "done" ? 100 : 0;
      return h("div", { class: "up" }, h("div", { class: "row" }, h("div", { class: "nm grow", title: u.file.name }, u.file.name),
        u.status === "active" || u.status === "queued" || u.status === "retrying" ? h("button", { class: "btn iconbtn ghost sm", "aria-label": t("cancel"), onclick: () => { u.cancelled = true; if (u.xhr) u.xhr.abort(); u.status = "cancelled"; renderUploads(); } }, icon("x")) : null),
        h("div", { class: "bar" + (u.status === "error" ? " full" : "") }, h("i", { style: "width:" + (u.status === "done" ? 100 : pct) + "%" })),
        h("div", { class: "muted" }, u.status === "active" ? pct.toLocaleString(getLang() === "fa" ? "fa-IR" : "en-US") + "٪ · " + fmtBytes(u.loaded) + " / " + fmtBytes(u.file.size) : label(u)));
    })));
}

boot();

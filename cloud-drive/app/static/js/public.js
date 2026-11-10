import { api, saveInPage, toast, brandMark, fmtBytes, fmtDate, getLang, getTheme, h, icon, setLang, t, toggleTheme } from "./common.js";

const root = document.getElementById("root");
const token = decodeURIComponent(location.pathname.split("/").filter(Boolean).pop() || "");
let info = null, site = {}, problem = null;

async function load() {
  try { site = await api("/config"); } catch { /* ignore */ }
  try { info = await api("/public/" + encodeURIComponent(token)); problem = null; }
  catch (e) { problem = e.status === 410 ? t("link_expired") : e.status === 404 ? t("link_gone") : e.message; }
  render();
}
function top() {
  return h("div", { class: "row", style: "justify-content:flex-end;margin-bottom:8px" },
    h("button", { class: "btn ghost iconbtn", onclick: () => { setLang(getLang() === "fa" ? "en" : "fa"); load(); } }, icon("globe")),
    h("button", { class: "btn ghost iconbtn", onclick: () => { toggleTheme(); render(); } }, icon(getTheme() === "dark" ? "sun" : "moon")));
}
function render() {
  const card = h("div", { class: "auth-card" }, brandMark(site));
  if (problem) card.append(h("h1", {}, "—"), h("p", { class: "muted" }, problem));
  else {
    card.append(h("h1", {}, t("shared_file")));
    if (info.unlocked) card.append(h("div", { class: "row", style: "margin:12px 0" }, icon("file"), h("b", { style: "word-break:break-all" }, info.name)),
      h("div", { class: "muted small" }, fmtBytes(info.size) + (info.expires_at ? " · " + t("expiry") + ": " + fmtDate(info.expires_at) : "")));
    if (info.needs_password && !info.unlocked) {
      const pw = h("input", { type: "password", autocomplete: "off", dir: "ltr" }); const err = h("div", { class: "err", role: "alert" });
      const go = async () => { err.textContent = ""; try { await api("/public/" + encodeURIComponent(token) + "/unlock", { method: "POST", body: { password: pw.value } }); info = await api("/public/" + encodeURIComponent(token)); render(); } catch (e) { err.textContent = e.status === 403 ? t("wrong_password") : e.message; } };
      pw.addEventListener("keydown", (e) => { if (e.key === "Enter") go(); });
      card.append(h("label", { class: "field", style: "margin-top:16px" }, t("enter_password"), pw), err, h("button", { class: "btn primary", style: "width:100%;justify-content:center", onclick: go }, t("unlock")));
    } else {
      const base = "/api/public/" + encodeURIComponent(token) + "/download";
      if (info.previewable && info.mime.startsWith("image/")) card.append(h("div", { class: "preview", style: "margin-top:14px" }, h("img", { src: base + "?inline=1", alt: info.name })));
      card.append(h("a", { class: "btn primary", style: "width:100%;justify-content:center;margin-top:16px;text-decoration:none", href: base, onclick: (ev) => { ev.preventDefault(); saveInPage(base, info.name, info.size); } }, icon("download"), t("download")));
      if (info.previewable && info.mime === "application/pdf") card.append(h("a", { class: "btn", style: "width:100%;justify-content:center;margin-top:8px;text-decoration:none", href: base + "?inline=1", target: "_blank", rel: "noopener" }, icon("eye"), t("open_new_tab")));
    }
  }
  root.replaceChildren(h("div", { class: "auth" }, h("div", {}, top(), card)));
}
load();

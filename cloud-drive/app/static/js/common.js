// Shared helpers: DOM builder, icons, i18n (fa/en), theme, API client, toasts, dialogs. No external libraries.
const NS = "http://www.w3.org/2000/svg";
const ICONS = {
  folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  "folder-plus": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M12 10v6M9 13h6"/>',
  file: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',
  pdf: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h6"/>',
  image: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="1.5"/><path d="M21 16l-5-5-8 8"/>',
  upload: '<path d="M12 16V4"/><path d="M7 9l5-5 5 5"/><path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"/>',
  download: '<path d="M12 4v12"/><path d="M7 11l5 5 5-5"/><path d="M4 20h16"/>',
  link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
  trash: '<path d="M4 7h16"/><path d="M9 7V4h6v3"/><path d="M6 7l1 13h10l1-13"/>',
  restore: '<path d="M4 12a8 8 0 1 0 3-6.2"/><path d="M4 4v5h5"/>',
  edit: '<path d="M4 20h4L19 9l-4-4L4 16z"/>',
  move: '<path d="M5 12h14"/><path d="M13 6l6 6-6 6"/>',
  search: '<circle cx="11" cy="11" r="6"/><path d="M20 20l-4-4"/>',
  grid: '<rect x="4" y="4" width="7" height="7"/><rect x="13" y="4" width="7" height="7"/><rect x="4" y="13" width="7" height="7"/><rect x="13" y="13" width="7" height="7"/>',
  list: '<path d="M8 6h12M8 12h12M8 18h12"/><circle cx="4" cy="6" r="1"/><circle cx="4" cy="12" r="1"/><circle cx="4" cy="18" r="1"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4 12H2M22 12h-2M5 5l1.5 1.5M17.5 17.5L19 19M5 19l1.5-1.5M17.5 6.5L19 5"/>',
  moon: '<path d="M20 14A8 8 0 0 1 10 4a8 8 0 1 0 10 10z"/>',
  globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18"/>',
  menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
  x: '<path d="M6 6l12 12M18 6L6 18"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  check: '<path d="M5 12l5 5 9-10"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
  users: '<circle cx="9" cy="8" r="3.5"/><path d="M2 20a7 7 0 0 1 14 0"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7"/><path d="M18 14a7 7 0 0 1 4 6"/>',
  shield: '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/>',
  activity: '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
  drive: '<rect x="3" y="12" width="18" height="8" rx="2"/><path d="M3 12l3-7h12l3 7"/><circle cx="7" cy="16" r=".8"/>',
  more: '<circle cx="12" cy="5" r="1.2"/><circle cx="12" cy="12" r="1.2"/><circle cx="12" cy="19" r="1.2"/>',
  logout: '<path d="M9 4H5a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h4"/><path d="M16 8l4 4-4 4"/><path d="M20 12H9"/>',
  copy: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
  eye: '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  chevron: '<path d="M15 6l-6 6 6 6"/>',
  settings: '<path d="M4 7h10M18 7h2M4 17h2M10 17h10"/><circle cx="16" cy="7" r="2"/><circle cx="8" cy="17" r="2"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  alert: '<path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18v.5"/>',
  ban: '<circle cx="12" cy="12" r="9"/><path d="M5.6 5.6l12.8 12.8"/>',
  home: '<path d="M4 11l8-7 8 7"/><path d="M6 10v10h12V10"/>',
};
export function icon(name, cls = "") {
  const s = document.createElementNS(NS, "svg");
  s.setAttribute("viewBox", "0 0 24 24");
  s.setAttribute("class", "icon " + cls);
  s.setAttribute("aria-hidden", "true");
  s.innerHTML = ICONS[name] || ICONS.file; // static markup only
  return s;
}

export function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "style") el.style.cssText = v;
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === "value" || k === "checked" || k === "disabled" || k === "selected") el[k] = v;
    else el.setAttribute(k, v === true ? "" : String(v));
  }
  for (const c of kids.flat(Infinity)) if (c != null && c !== false) el.append(c.nodeType ? c : document.createTextNode(String(c)));
  return el;
}

export const LS = {
  get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : v; } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* storage may be blocked */ } },
  del(k) { try { localStorage.removeItem(k); } catch { /* ignore */ } },
};

// ------------------------------------------------------------------ i18n  key: [فارسی, English]
const D = {
  app_name: ["Cloud Drive", "Cloud Drive"], login: ["ورود", "Sign in"], register: ["ثبت‌نام", "Sign up"], logout: ["خروج", "Sign out"],
  username: ["نام کاربری", "Username"], password: ["رمز عبور", "Password"], email: ["ایمیل (اختیاری)", "Email (optional)"],
  display_name: ["نام نمایشی", "Display name"], no_account: ["حساب ندارید؟ ثبت‌نام", "No account? Sign up"], have_account: ["حساب دارید؟ ورود", "Have an account? Sign in"],
  pw_hint: ["حداقل ۱۰ نویسه، شامل حرف و عدد", "At least 10 characters with letters and digits"],
  my_files: ["فایل‌های من", "My files"], shared: ["لینک‌های اشتراک", "Shared links"], trash: ["سطل زباله", "Trash"], activity: ["فعالیت‌ها", "Activity"],
  profile: ["پروفایل", "Profile"], admin_panel: ["پنل مدیریت", "Admin panel"], search: ["جست‌وجو در فایل‌ها…", "Search files…"],
  upload: ["آپلود", "Upload"], new_folder: ["پوشه جدید", "New folder"], folder_name: ["نام پوشه", "Folder name"], name: ["نام", "Name"],
  size: ["حجم", "Size"], date: ["تاریخ", "Date"], type: ["نوع", "Type"], owner: ["مالک", "Owner"], sort_by: ["مرتب‌سازی", "Sort by"],
  asc: ["صعودی", "Ascending"], desc: ["نزولی", "Descending"], all: ["همه", "All"], images: ["تصاویر", "Images"], docs: ["اسناد", "Documents"],
  media: ["رسانه", "Media"], archives: ["فشرده", "Archives"], other: ["سایر", "Other"], folder: ["پوشه", "Folder"],
  download: ["دانلود", "Download"], preview: ["پیش‌نمایش", "Preview"], share: ["اشتراک‌گذاری", "Share"], rename: ["تغییر نام", "Rename"],
  move: ["انتقال", "Move"], delete: ["حذف", "Delete"], restore: ["بازیابی", "Restore"], delete_forever: ["حذف دائمی", "Delete forever"],
  empty_trash: ["خالی کردن سطل", "Empty trash"], cancel: ["انصراف", "Cancel"], ok: ["تأیید", "OK"], save: ["ذخیره", "Save"], close: ["بستن", "Close"],
  create: ["ایجاد", "Create"], open: ["باز کردن", "Open"], root: ["ریشه", "Root"], select_all: ["انتخاب همه", "Select all"],
  empty_folder: ["اینجا هنوز چیزی نیست", "Nothing here yet"], drop_here: ["فایل‌ها را اینجا رها کنید", "Drop files to upload"],
  empty_hint: ["فایل‌ها را بکشید و رها کنید یا روی «آپلود» بزنید", "Drag files here or press Upload"],
  no_results: ["نتیجه‌ای پیدا نشد", "No results"], trash_empty: ["سطل زباله خالی است", "Trash is empty"],
  storage: ["فضای ذخیره‌سازی", "Storage"], used_of: ["استفاده‌شده از", "used of"], selected: ["مورد انتخاب شد", "selected"],
  uploading: ["در حال آپلود", "Uploading"], upload_done: ["آپلود کامل شد", "Upload complete"], upload_failed: ["آپلود ناموفق بود", "Upload failed"],
  retrying: ["قطع شد؛ تلاش مجدد…", "Connection lost; retrying…"], cancelled: ["لغو شد", "Cancelled"], waiting: ["در صف", "Queued"],
  confirm_trash: ["به سطل زباله منتقل شود؟", "Move to trash?"], confirm_purge: ["برای همیشه حذف شود؟ این کار قابل بازگشت نیست.", "Delete forever? This cannot be undone."],
  moved_trash: ["به سطل زباله منتقل شد", "Moved to trash"], restored: ["بازیابی شد", "Restored"], deleted: ["حذف شد", "Deleted"], renamed: ["نام تغییر کرد", "Renamed"], moved: ["منتقل شد", "Moved"],
  folder_created: ["پوشه ساخته شد", "Folder created"], copied: ["لینک کپی شد", "Link copied"], saved: ["ذخیره شد", "Saved"],
  share_title: ["لینک اشتراک‌گذاری", "Share link"], link_password: ["رمز لینک (اختیاری)", "Link password (optional)"],
  expiry: ["انقضا", "Expires"], never: ["بدون انقضا", "Never"], h1: ["۱ ساعت", "1 hour"], h24: ["۱ روز", "1 day"], h168: ["۷ روز", "7 days"], h720: ["۳۰ روز", "30 days"],
  create_link: ["ساخت لینک", "Create link"], copy: ["کپی", "Copy"], disable: ["غیرفعال‌سازی", "Disable"], active: ["فعال", "Active"], inactive: ["غیرفعال", "Disabled"],
  expired: ["منقضی", "Expired"], protected: ["رمزدار", "Protected"], downloads: ["دانلود", "Downloads"], file: ["فایل", "File"],
  no_links: ["هنوز لینکی نساخته‌اید", "No links yet"], move_to: ["انتقال به…", "Move to…"], current: ["(فعلی)", "(current)"],
  language: ["زبان", "Language"], theme: ["تم", "Theme"], collapse: ["جمع کردن", "Collapse"], list_view: ["نمای لیست", "List view"], grid_view: ["نمای کارت", "Grid view"],
  current_password: ["رمز فعلی", "Current password"], new_password: ["رمز جدید", "New password"], change_password: ["تغییر رمز عبور", "Change password"],
  pw_changed: ["رمز عبور تغییر کرد", "Password changed"], account: ["حساب کاربری", "Account"], member_since: ["عضویت از", "Member since"],
  action: ["عملیات", "Action"], detail: ["جزئیات", "Details"], time: ["زمان", "Time"], no_activity: ["فعالیتی ثبت نشده", "No activity yet"],
  a_upload: ["آپلود", "Upload"], a_download: ["دانلود", "Download"], a_login: ["ورود", "Login"], a_register: ["ثبت‌نام", "Registered"], a_trash: ["انتقال به سطل", "Trashed"],
  a_restore: ["بازیابی", "Restored"], a_purge: ["حذف دائمی", "Purged"], a_delete: ["حذف", "Deleted"], a_folder_create: ["ساخت پوشه", "Folder created"], a_folder_update: ["ویرایش پوشه", "Folder edited"],
  a_file_update: ["ویرایش فایل", "File edited"], a_share_create: ["ساخت لینک", "Link created"], a_share_disable: ["غیرفعال‌سازی لینک", "Link disabled"], a_public_download: ["دانلود عمومی", "Public download"],
  a_profile_update: ["ویرایش پروفایل", "Profile updated"], a_password_change: ["تغییر رمز", "Password changed"],
  net_error: ["ارتباط با سرور برقرار نشد", "Cannot reach the server"], session_expired: ["نشست شما پایان یافته؛ دوباره وارد شوید", "Session expired, please sign in again"],
  preview_fallback: ["اگر پیش‌نمایش نمایش داده نشد، در تب جدید باز کنید", "If the preview is blank, open it in a new tab"], open_new_tab: ["باز کردن در تب جدید", "Open in new tab"],
  // admin
  dashboard: ["داشبورد", "Dashboard"], users: ["کاربران", "Users"], files: ["فایل‌ها", "Files"], settings: ["تنظیمات", "Settings"], audit: ["لاگ مدیریتی", "Audit log"],
  health: ["سلامت سیستم", "System health"], total_users: ["کل کاربران", "Total users"], active_users: ["حساب‌های فعال", "Active accounts"], online_now: ["آنلاین", "Online now"],
  total_files: ["تعداد فایل‌ها", "Files"], total_bytes: ["حجم ذخیره‌شده", "Stored data"], disk_free: ["فضای آزاد دیسک", "Free disk"], suspicious: ["فایل مشکوک", "Suspicious files"],
  up24: ["آپلود ۲۴ ساعت", "Uploads (24h)"], down24: ["دانلود ۲۴ ساعت", "Downloads (24h)"], user_growth: ["رشد کاربران (۳۰ روز)", "User growth (30 days)"],
  storage_growth: ["مصرف فضا (۳۰ روز)", "Storage usage (30 days)"], recent_activity: ["فعالیت‌های اخیر", "Recent activity"], recent_errors: ["خطاها و هشدارهای مهم", "Important errors & warnings"],
  none: ["موردی نیست", "None"], status: ["وضعیت", "Status"], quota: ["سهمیه", "Quota"], last_login: ["آخرین ورود", "Last login"], created: ["ایجاد", "Created"],
  role: ["نقش", "Role"], disabled: ["غیرفعال", "Disabled"], banned: ["مسدود", "Banned"], admin: ["مدیر", "Admin"], user: ["کاربر", "User"],
  ban: ["مسدود کردن", "Ban"], unban: ["رفع انسداد", "Unban"], enable: ["فعال‌سازی", "Enable"], revoke: ["ابطال نشست‌ها", "Revoke sessions"], edit: ["ویرایش", "Edit"],
  reason: ["دلیل", "Reason"], quota_mb: ["سهمیه (مگابایت)", "Quota (MB)"], confirm_password: ["رمز عبور خود را برای تأیید وارد کنید", "Enter your password to confirm"],
  confirm: ["تأیید", "Confirm"], all_status: ["همه وضعیت‌ها", "All statuses"], only_suspicious: ["فقط مشکوک‌ها", "Suspicious only"], filter_search: ["جست‌وجو…", "Search…"],
  service_name: ["نام سرویس", "Service name"], logo: ["لوگو (PNG/JPEG/WebP، حداکثر ۲۰۰KB)", "Logo (PNG/JPEG/WebP, max 200KB)"], remove_logo: ["حذف لوگو", "Remove logo"],
  max_upload_mb: ["حداکثر حجم هر فایل (MB، ۰ = نامحدود)", "Max size per file (MB, 0 = unlimited)"], default_quota_mb: ["سهمیه پیش‌فرض (MB)", "Default quota (MB)"], rate_login: ["محدودیت ورود (در دقیقه)", "Login attempts per minute"],
  rate_api: ["محدودیت درخواست API (در دقیقه، ۰ = بدون محدودیت)", "API requests per minute (0 = unlimited)"], rate_public: ["محدودیت لینک عمومی (در دقیقه)", "Public link requests per minute"],
  trash_enabled: ["سطل زباله فعال باشد", "Enable trash"], trash_days: ["نگهداری سطل (روز)", "Trash retention (days)"], reg_open: ["ثبت‌نام باز باشد", "Open registration"],
  stale_hours: ["پاک‌سازی آپلود ناقص (ساعت)", "Clean incomplete uploads after (hours)"], db: ["دیتابیس", "Database"], api: ["API", "API"], storage_ok: ["ذخیره‌سازی", "Storage"],
  uptime: ["مدت اجرا", "Uptime"], pending: ["آپلود در جریان", "Pending uploads"], healthy: ["سالم", "Healthy"], problem: ["مشکل", "Problem"], events: ["رویدادهای امنیتی", "Security events"],
  back_to_app: ["بازگشت به فایل‌ها", "Back to files"], delete_file_admin: ["حذف فایل (دائمی)", "Delete file (permanent)"], no_admin: ["دسترسی مدیر ندارید", "You are not an admin"],
  days_left: ["روز تا حذف", "days left"], auto_delete_note: ["⏳ فایل‌ها {n} روز پس از آپلود خودکار حذف می‌شوند", "⏳ Files are deleted automatically {n} days after upload"],
  trash_note: ["⏳ مواردِ سطل زباله {n} روز بعد برای همیشه حذف می‌شوند", "⏳ Items in the trash are deleted for good after {n} days"],
  retention_days: ["حذف خودکار همه فایل‌ها پس از (روز، ۰ = هرگز)", "File retention (days, 0 = keep forever)"],
  // public
  shared_file: ["فایلی برای شما به اشتراک گذاشته شده", "A file was shared with you"], unlock: ["باز کردن قفل", "Unlock"], link_gone: ["این لینک وجود ندارد یا غیرفعال شده است", "This link does not exist or was disabled"],
  link_expired: ["این لینک منقضی شده است", "This link has expired"], enter_password: ["رمز این لینک را وارد کنید", "Enter the link password"], wrong_password: ["رمز نادرست است", "Wrong password"],
};
let lang = LS.get("cd_lang", "fa");
export const getLang = () => lang;
export const t = (k) => (D[k] ? D[k][lang === "fa" ? 0 : 1] : k);
export function setLang(l) { lang = l; LS.set("cd_lang", l); applyLang(); }
export function applyLang() { document.documentElement.lang = lang; document.documentElement.dir = lang === "fa" ? "rtl" : "ltr"; }
applyLang();

// ------------------------------------------------------------------ theme
export function getTheme() { return LS.get("cd_theme", matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"); }
export function applyTheme() { document.documentElement.dataset.theme = getTheme(); }
export function toggleTheme() {
  const el = document.documentElement; el.classList.add("theming");
  LS.set("cd_theme", getTheme() === "dark" ? "light" : "dark"); applyTheme();
  setTimeout(() => el.classList.remove("theming"), 450);
}
applyTheme();

// ------------------------------------------------------------------ formatting
export function fmtBytes(n) {
  if (n == null) return "";
  const u = lang === "fa" ? ["بایت", "کیلوبایت", "مگابایت", "گیگابایت", "ترابایت"] : ["B", "KB", "MB", "GB", "TB"];
  let i = 0, v = n;
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
  return v.toLocaleString(lang === "fa" ? "fa-IR" : "en-US", { maximumFractionDigits: i ? 1 : 0 }) + " " + u[i];
}
export function fmtDate(iso) {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleString(lang === "fa" ? "fa-IR" : "en-GB", { dateStyle: "medium", timeStyle: "short" }); } catch { return iso; }
}
export const fmtNum = (n) => Number(n).toLocaleString(lang === "fa" ? "fa-IR" : "en-US");
const EXT = {
  image: ["png", "jpg", "jpeg", "gif", "webp", "bmp", "svg", "heic"], doc: ["pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "md", "csv", "odt", "rtf"],
  media: ["mp3", "wav", "flac", "ogg", "mp4", "mkv", "avi", "mov", "webm"], archive: ["zip", "rar", "7z", "tar", "gz"],
};
export function kindOf(name) {
  const e = (name.split(".").pop() || "").toLowerCase();
  for (const [k, l] of Object.entries(EXT)) if (l.includes(e)) return k;
  return "other";
}
export function fileIcon(f) { return f.mime === "application/pdf" ? "pdf" : f.mime && f.mime.startsWith("image/") ? "image" : "file"; }

// ------------------------------------------------------------------ API
let csrf = "";
export const setCsrf = (v) => { csrf = v; };
export const getCsrf = () => csrf;
export async function api(path, { method = "GET", body, signal } = {}) {
  const opts = { method, headers: {}, credentials: "same-origin", signal };
  if (csrf && method !== "GET") opts.headers["X-CSRF-Token"] = csrf;
  if (body !== undefined) { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
  let r;
  try { r = await fetch("/api" + path, opts); } catch (e) { const er = new Error(t("net_error")); er.network = true; throw er; }
  let data = null;
  if ((r.headers.get("content-type") || "").includes("json")) data = await r.json().catch(() => null);
  if (!r.ok) {
    const er = new Error((data && (lang === "fa" ? data.message : data.message_en)) || r.statusText);
    er.status = r.status; er.code = data && data.error; er.data = data;
    if (r.status === 401 && er.code === "unauthorized") window.dispatchEvent(new Event("cd:unauthorized"));
    throw er;
  }
  return data;
}

// ------------------------------------------------------------------ toasts & dialogs
let toastBox;
export function toast(msg, isErr = false) {
  if (!toastBox) { toastBox = h("div", { class: "toasts", role: "status", "aria-live": "polite" }); document.body.append(toastBox); }
  const el = h("div", { class: "toast" + (isErr ? " err" : "") }, msg);
  toastBox.append(el);
  const life = isErr ? 6000 : 3000;
  setTimeout(() => el.classList.add("out"), life - 250); setTimeout(() => el.remove(), life);
}
export const errToast = (e) => toast(e && e.message ? e.message : String(e), true);

export function openModal(content, { wide = false } = {}) {
  const prev = document.activeElement;
  const box = h("div", { class: "modal" + (wide ? " wide" : ""), role: "dialog", "aria-modal": "true" }, content);
  const ov = h("div", { class: "overlay" }, box);
  const close = () => { document.removeEventListener("keydown", onKey); ov.classList.add("closing"); setTimeout(() => ov.remove(), 160); if (prev && prev.focus) prev.focus(); };
  const onKey = (e) => { if (e.key === "Escape") close(); };
  ov.addEventListener("mousedown", (e) => { if (e.target === ov) close(); });
  document.addEventListener("keydown", onKey);
  document.body.append(ov);
  const first = box.querySelector("input,select,textarea,button.primary");
  if (first) first.focus();
  return { close, box };
}

export function confirmDialog(message, { danger = false, okText } = {}) {
  return new Promise((res) => {
    let m;
    const done = (v) => { m.close(); res(v); };
    m = openModal([h("p", { style: "margin-top:0" }, message),
      h("div", { class: "actions" }, h("button", { class: "btn", onclick: () => done(false) }, t("cancel")),
        h("button", { class: "btn primary" + (danger ? " danger fill" : ""), onclick: () => done(true) }, okText || t("ok")))]);
  });
}

export function promptDialog(title, { label, value = "", okText } = {}) {
  return new Promise((res) => {
    let m;
    const input = h("input", { type: "text", value, maxlength: 255 });
    const done = (v) => { m.close(); res(v); };
    const go = () => { const v = input.value.trim(); if (v) done(v); };
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") go(); });
    m = openModal([h("h2", {}, title), h("label", { class: "field" }, label || "", input),
      h("div", { class: "actions" }, h("button", { class: "btn", onclick: () => done(null) }, t("cancel")),
        h("button", { class: "btn primary", onclick: go }, okText || t("ok")))]);
    input.select();
  });
}

export function askPassword() {
  return new Promise((res) => {
    let m;
    const input = h("input", { type: "password", autocomplete: "current-password" });
    const done = (v) => { m.close(); res(v); };
    input.addEventListener("keydown", (e) => { if (e.key === "Enter" && input.value) done(input.value); });
    m = openModal([h("h2", {}, t("confirm")), h("label", { class: "field" }, t("confirm_password"), input),
      h("div", { class: "actions" }, h("button", { class: "btn", onclick: () => done(null) }, t("cancel")),
        h("button", { class: "btn primary", onclick: () => input.value && done(input.value) }, t("confirm")))]);
  });
}

let openMenu;
export function popupMenu(anchor, items) {
  if (openMenu) openMenu.remove();
  const r = anchor.getBoundingClientRect();
  const menu = h("div", { class: "menu", role: "menu" }, items.filter(Boolean).map((it) =>
    h("button", { role: "menuitem", class: it.danger ? "danger" : "", onclick: (e) => { e.stopPropagation(); menu.remove(); openMenu = null; it.run(); } }, icon(it.icon), it.label)));
  document.body.append(menu);
  const w = menu.offsetWidth, hgt = menu.offsetHeight;
  let x = lang === "fa" ? r.left : r.right - w;
  x = Math.max(8, Math.min(x, innerWidth - w - 8));
  let y = r.bottom + 4; if (y + hgt > innerHeight - 8) y = Math.max(8, r.top - hgt - 4);
  menu.style.left = x + "px"; menu.style.top = y + "px";
  openMenu = menu;
  setTimeout(() => document.addEventListener("click", () => { menu.remove(); if (openMenu === menu) openMenu = null; }, { once: true }), 0);
}

export function brandMark(info) {
  return h("div", { class: "brand-mark" }, info && info.logo_data ? h("img", { src: info.logo_data, alt: "" }) : icon("drive"));
}

// animated number (count-up); respects reduced motion
export function animNum(n, fmt = (x) => String(x), ms = 900) {
  const el = h("span", {}, fmt(0));
  if (matchMedia("(prefers-reduced-motion: reduce)").matches || !n) { el.textContent = fmt(n); return el; }
  const t0 = performance.now();
  const step = (now) => { const p = Math.min(1, (now - t0) / ms), e = 1 - Math.pow(1 - p, 3); el.textContent = fmt(Math.round(n * e)); if (p < 1) requestAnimationFrame(step); };
  requestAnimationFrame(step);
  return el;
}
// ripple origin for every .btn
document.addEventListener("pointerdown", (e) => {
  const b = e.target.closest && e.target.closest(".btn"); if (!b) return;
  const r = b.getBoundingClientRect();
  b.style.setProperty("--rx", e.clientX - r.left + "px"); b.style.setProperty("--ry", e.clientY - r.top + "px");
  b.classList.remove("rip"); void b.offsetWidth; b.classList.add("rip");
}, { passive: true });

/* In-page download with a progress box. Chrome pauses ("Waiting for network") a DIRECT download from a site whose certificate is self-signed,
   because its download manager does not share the exception you accepted for the page. The page itself is trusted, so the file is read
   through the page in Range pieces (a dropped connection retries only that piece) and then saved: straight to disk where the browser
   allows it (desktop Chrome/Edge, any size), otherwise through a disk temp file (OPFS, any size), and only if that is missing from memory. Falls back to a plain link only if size is unknown. */
const DLX = { big: 150 * 1048576, chunk: 8 * 1048576, blobMax: 1024 * 1048576 };
/* Disk-backed temp file in the page's private storage (OPFS): the pieces are written there instead of RAM, and the finished file is handed to the
   browser's own download manager as a File. So there is no size limit, and phones/Firefox/Safari (no save-picker) work too. */
async function opfsOpen() {
  try {
    if (!navigator.storage || !navigator.storage.getDirectory) return null;
    const dir = await navigator.storage.getDirectory();
    try { for await (const [n, fh] of dir.entries()) if (n.startsWith("wd-dl-")) { const f = await fh.getFile(); if (Date.now() - f.lastModified > 3600e3) await dir.removeEntry(n).catch(() => {}); } } catch {}
    const nm = "wd-dl-" + Date.now() + "-" + Math.random().toString(36).slice(2, 8);
    const fh = await dir.getFileHandle(nm, { create: true });
    if (!fh.createWritable) { await dir.removeEntry(nm).catch(() => {}); return null; }
    return { dir, nm, fh, w: await fh.createWritable() };
  } catch { return null; }
}
async function dlPiece(url, a, b, onBytes, signal) {
  for (let tries = 0; ; tries++) {
    try {
      const r = await fetch(url, { headers: { Range: "bytes=" + a + "-" + b }, signal, credentials: "same-origin" });
      if (r.status !== 206 && !(r.status === 200 && a === 0)) throw new Error("http " + r.status);
      if (!r.body || !r.body.getReader) return await r.blob();
      const rd = r.body.getReader(), parts = []; let n = 0;
      for (;;) { const { done, value } = await rd.read(); if (done) break; parts.push(value); n += value.length; onBytes(n); }
      return new Blob(parts);
    } catch (e) {
      if (e && e.name === "AbortError") throw e;
      if (tries >= 3) throw e;
      await new Promise((z) => setTimeout(z, 1200 * (tries + 1)));
    }
  }
}
const NATIVE_DL = {};   // downloads done by the Android app itself (it reports progress through window.wdDl)
window.wdDl = (id, got, total, state) => { const c = NATIVE_DL[id]; if (c) c(got, total, state); };
function nativeSave(url, name, size) {
  const id = "n" + Date.now() + Math.random().toString(36).slice(2, 6);
  const bar = h("i"), pct = h("span", { class: "pc" }, "…");
  const box = h("div", { class: "dlbox", role: "status" }, h("div", { class: "dt" }, h("b", {}, name), pct), h("div", { class: "bar" }, bar));
  document.body.append(box);
  let timer = null;
  const arm = (ms) => { clearTimeout(timer); timer = setTimeout(() => { box.remove(); delete NATIVE_DL[id]; }, ms); };
  NATIVE_DL[id] = (got, total, state) => {
    const t = total > 0 ? total : size || 0, p = t > 0 ? Math.min(100, Math.round(got / t * 100)) : 0;
    bar.style.width = (state === 1 ? 100 : p) + "%";
    box.classList.toggle("ok", state === 1);
    pct.textContent = state === 1 ? (lang === "fa" ? "ذخیره شد ✓ (پوشه Download/Windroida)" : "Saved ✓ (Download/Windroida)")
      : state === 2 ? (lang === "fa" ? "ناموفق" : "Failed") : t > 0 ? p + "% · " + fmtBytes(got) + " / " + fmtBytes(t) : fmtBytes(got);
    arm(state === 1 ? 3500 : state === 2 ? 4500 : 90000);
  };
  arm(90000);
  window.WD.saveFileId(id, new URL(url, location.href).href, name);
}
export async function saveInPage(url, name, size) {
  if (window.WD && window.WD.saveFileId) return nativeSave(url, name, size);   // Android app: native download with the pinned certificate
  if (window.WD && window.WD.saveFile) {            // inside the Windroida Android app: the app downloads it natively (pinned certificate + login cookie)
    window.WD.saveFile(new URL(url, location.href).href, name);
    return;
  }
  const plain = () => { const a = h("a", { href: url, download: name }); document.body.append(a); a.click(); a.remove(); };
  if (!size) return plain();
  if (size > DLX.big && !confirm(name + " — " + fmtBytes(size) + "\n" + (lang === "fa" ? "تا تموم نشده این صفحه رو نبند. ادامه بدم؟" : "Keep this page open until it finishes. Continue?"))) return;
  let handle = null;
  if (size > DLX.big && window.showSaveFilePicker) { try { handle = await window.showSaveFilePicker({ suggestedName: name }); } catch (e) { if (e && e.name === "AbortError") return; } }
  let opfs = null;
  if (!handle && size > DLX.big) opfs = await opfsOpen();
  if (!handle && !opfs && size > DLX.blobMax && !confirm(lang === "fa" ? "این مرورگر فایل بزرگ رو تو حافظه نگه می‌داره و ممکنه صفحه بسته بشه؛ با کروم/اج کامپیوتر مطمئن‌تره. ادامه بدم؟" : "This browser keeps big files in memory and the tab may crash; desktop Chrome/Edge is safer. Continue?")) return;
  const ab = new AbortController(), bar = h("i"), pct = h("span", { class: "pc" }, "0%");
  const cancel = h("button", { class: "btn", type: "button", onclick: () => ab.abort() }, lang === "fa" ? "لغو" : "Cancel");
  const box = h("div", { class: "dlbox", role: "status" }, h("div", { class: "dt" }, h("b", {}, name), pct), h("div", { class: "bar" }, bar), cancel);
  document.body.append(box);
  const ui = (got, state) => {
    const p = Math.min(100, Math.round(got / size * 100));
    bar.style.width = (state === 1 ? 100 : p) + "%";
    pct.textContent = state === 1 ? (lang === "fa" ? "ذخیره شد ✓" : "Saved ✓") : p + "% · " + fmtBytes(got) + " / " + fmtBytes(size);
    box.classList.toggle("ok", state === 1);
  };
  let w = null, got = 0, last = 0, gone = false;
  const close = (ms) => setTimeout(() => { gone = true; box.remove(); }, ms);
  try {
    if (handle) w = await handle.createWritable(); else if (opfs) w = opfs.w;
    const parts = [];
    for (let a = 0; a < size; a += DLX.chunk) {
      const b = Math.min(a + DLX.chunk - 1, size - 1), base = got;
      const blob = await dlPiece(url, a, b, (n) => { if (Date.now() - last > 200) { last = Date.now(); ui(base + n, 0); } }, ab.signal);
      if (w) await w.write(blob); else parts.push(blob);
      got += blob.size; ui(got, 0);
    }
    if (w) await w.close();
    if (opfs) {    // finished file is on disk: give it to the browser's download manager, delete the temp copy later
      const u = URL.createObjectURL(await opfs.fh.getFile()), a = h("a", { href: u, download: name });
      document.body.append(a); a.click(); a.remove();
      setTimeout(() => { URL.revokeObjectURL(u); opfs.dir.removeEntry(opfs.nm).catch(() => {}); }, 30 * 60000);
    } else if (!w) {
      const u = URL.createObjectURL(new Blob(parts, { type: "application/octet-stream" })), a = h("a", { href: u, download: name });
      document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(u), 60000);
    }
    ui(size, 1); close(2200);
  } catch (e) {
    try { if (w) await w.abort(); } catch {}
    if (opfs) opfs.dir.removeEntry(opfs.nm).catch(() => {});
    box.remove();
    if (e && e.name === "AbortError") return toast(lang === "fa" ? "دانلود لغو شد" : "Download cancelled");
    toast(lang === "fa" ? "دانلود قطع شد؛ دوباره امتحان کن" : "Download interrupted; try again", true);
  }
}

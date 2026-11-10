# راهنمای توسعه‌ی Windroida (برای برنامه‌نویس یا هوش مصنوعی)

نسخه‌ی این راهنما: مطابق `windroida-v6_37`. اول بخش «قوانین طلایی» و «نقشه‌ی پروژه» رو بخون، بعد برو سراغ دستور کار مربوط به کارت.

---

## ۱. Windroida چیه؟

یک پیام‌رسان شبیه تلگرام که روی سرور شخصی (ویندوز/لینوکس) اجرا می‌شه:

- **سرور پایتون** (بدون فریم‌ورک سنگین): پیام، گروه، کانال، تماس صوتی/تصویری، اتاق تماشا/گوش‌دادن، بازی (شطرنج، مافیا، منچ)، نظرسنجی، ایموجی متحرک.
- **رابط وب** (HTML/CSS/JS ساده، بدون build) که مرورگر و WebView اندروید نشونش می‌دن.
- **اپ اندروید بومی** (Kotlin، با View ‌های کلاسیک، نه Compose) + حالت وب داخل WebView.
- دو سرویس کناری که با ورود یکپارچه (SSO) به پیام‌رسان وصلن:
  - **Ghab (قاب)**: شبیه اینستاگرام (Flask، پورت ۸۰۸۴).
  - **Cloud Drive (فضای ابری)**: شبیه گوگل درایو (Flask).

زبان رابط فارسی و راست‌چینه. پیام‌های خطا هم فارسی‌ان.

---

## ۲. قوانین طلایی (قبل از هر تغییری بخون)

1. **هیچ وابستگی به اینترنت بین‌الملل نباید اضافه بشه.** CDN، فونت گوگل، کتابخونه‌ی آنلاین ممنوع. فونت وزیرمتن و کتابخونه‌ها همراه پروژه‌ان (`web/*.woff`، پوشه‌ی `wheels/`).
2. **گواهی سرور با اثر انگشت (pin) تأیید می‌شه، نه با گواهی‌های سیستم.** هر اتصال HTTPS جدید در اندروید باید از `Trust.pinnedContext(Prefs.pin(ctx))` استفاده کنه.
3. **هر چیزی که کاربر حذف می‌کنه باید از سرور هم پاک بشه** (پیام، فایل، چت، عکس پروفایل).
4. **پیام خطا و متن رابط فارسی باشه.**
5. **حریم خصوصی:** کلید رسانه (`media_key`) و توکن‌ها رو تو لاگ ننویس. هیچ مسیری نباید بدون بررسی عضویت چت فایل بده.
6. **تغییر سرور = تست.** حتماً تست‌های مرتبط (بخش ۹) اجرا بشن.
7. **تغییر در وب و اندروید هر دو لازمه** مگر اینکه صراحتاً فقط یکی خواسته شده. وب مرجعه؛ اپ بومی باید شبیهش رفتار کنه.
8. هیچ کلید یا رمز واقعی تو کد نذار.

---

## ۳. نقشه‌ی پروژه

```
windroida/
├─ start.py / start.bat / start.sh   راه‌انداز: سرور + Ghab + Cloud Drive، پورت‌ها، گواهی (start.bat ویندوز، start.sh لینوکس/مک)
├─ server.py                 هسته‌ی سرور: WebSocket، همه‌ی op_* ها، دیتابیس
├─ webgw.py                  دروازه‌ی HTTP/WebSocket: آپلود، media، avatar، static، notify
├─ common.py                 ثابت‌ها (MAX_UPLOAD...)، مسیرها، دیتابیس، ابزار آپلود/آواتار
├─ rooms.py, games.py,       اتاق تماشا/گوش‌دادن و بازی‌ها
│  chess.py, mafia*.py, mensch*.py
├─ polls.py, groupadmin.py, social.py, webpush.py
├─ datasheet.py              پنل ادمین (دیتاشیت)
├─ client_core.py            کلاینت پایتونی (برای تست‌ها)
├─ web/                      رابط وب
│   ├─ index.html, app.js (~۲۰۰۰ خط)، app.css
│   ├─ room.js, chess.js, mafia.js, mensch*.js, polls.js, stickers.js, temoji.js
│   └─ sw.js, manifest.webmanifest, emoji/ (فایل‌های .tgs)
├─ ghab/                     قاب (Flask): server/, web/, migrations/
├─ cloud-drive/              فضای ابری (Flask): app/, tests/
├─ android/                  اپ اندروید (Gradle)
│   └─ app/src/main/java/ir/windroida/app/
│        ├─ MainActivity.kt      حالت وب (WebView پیام‌رسان)
│        ├─ NativeActivity.kt    حالت بومی: ریشه‌ی همه‌ی صفحه‌ها (stack)
│        ├─ SiteActivity.kt      قاب و فضای ابری داخل اپ (WebView + کش)
│        ├─ WebCache.kt          کش دیسکی ۴۰۰ مگی برای قاب (آفلاین)
│        ├─ PlayerActivity.kt    پخش تمام‌صفحه‌ی ویدیو (ExoPlayer/Media3)
│        ├─ MusicService.kt      سرویس پخش آهنگ (نوتیفیکیشن)
│        ├─ NotifyService.kt, BootReceiver.kt
│        ├─ Trust.kt             Prefs + گواهی pin شده
│        ├─ net/ Api.kt Http.kt Json.kt Model.kt Ws.kt   شبکه
│        └─ ui/  ChatScreen, ListScreen, Bubbles, Media, Music, PlayerSheet,
│                Kit (Theme), Frost (شیشه‌ای)، Wall (پس‌زمینه)، Ghab (قدیمی/غیرفعال) ...
└─ test_*.py                 تست‌ها (پایتون)
```

### پورت‌ها
| سرویس | پورت پیش‌فرض | تنظیم |
|---|---|---|
| سرور اصلی (TCP، اپ بومی) | ۸۷۶۵ | ثابت‌ها بالای `start.py` |
| وب | ۸۰۸۱ | `WEB_PORT` در `start.py` (تو نصب شما ممکنه روی ۸۰۸۷ تنظیم شده باشه) |
| Ghab | ۸۰۸۴ | `WINDROIDA_GHAB_PORT` |
| Cloud Drive | ۸۰۸۲ | `WINDROIDA_DRIVE_PORT` |

### پوشه‌ی داده
`data/` کنار برنامه: دیتابیس SQLite، `uploads/<user>/<chat>/…`، `avatars/`، لاگ‌ها، گواهی. **هیچ‌وقت پاکش نکن.**

---

## ۴. پروتکل سرور

### ۴.۱ WebSocket (`/ws`)
- هر پیام یک JSON: `{"id": n, "op": "send", ...}`.
- سرور جواب می‌ده `{"id": n, "ok": true/false, ...}` و رویدادها رو بدون `id` push می‌کنه: `{"event": "message", "message": {...}}`.
- هر `op` یک متد `op_<name>(self, conn, req)` تو `server.py` ـه. `_dispatch` با `getattr(self, "op_"+op)` پیداش می‌کنه.
- خطای قابل‌نمایش به کاربر: `raise Fail("متن فارسی")`.
- عملیات بدون لاگین (`public`): `register, login, resume, reset_question, reset_password, ping`.
- عضویت چت رو با `self._require_member(db, chat_id, uid)` چک کن.
- برای ارسال رویداد به اعضا: `self.push(self._member_ids(db, chat_id), {...}, exclude=conn)`.

### ۴.۲ HTTP (در `webgw.py`)
مسیر هر درخواست تو تابع اصلی هندلر (حدود خط ۲۰۰ تا ۲۶۰) تعیین می‌شه:

| مسیر | کار |
|---|---|
| `POST /upload?k=KEY&chat_id=&name=&text=&reply_to=` | آپلود فایل (بدنه = خود فایل) |
| `GET /upload-status?k=KEY&rid=` | چند بایت از آپلود نیمه‌کاره رسیده |
| `GET /media/<id>?k=KEY` | فایل پیام، با Range (پخش و seek) |
| `/thumb/…`, `/avatar/…`, `/wall/…`, `/userwall` | بندانگشتی، آواتار، پس‌زمینه |
| `POST /avatar`, `/thumb` | آپلود آواتار و بندانگشتی |
| `POST /notify` | long-poll برای سرویس اعلان اندروید |
| `POST /ghab-share` | فقط از localhost: ارسال لینک پست قاب به چت |
| `/roomaudio/…`, `POST /roomupload` | آهنگ و فیلم اتاق |
| `/static/…`, `/` | فایل‌های وب |

`KEY` = `media_key` که با `op_hello` یا `op_media_key` گرفته می‌شه و موقت و امضاشده‌ست (`check_media_key`).

### ۴.۳ آپلود ادامه‌دار (از v6.34)
کلاینت اندروید یک `rid` تصادفی می‌سازه و با `offset` و `total` می‌فرسته. سرور بخش رسیده رو تو `data/uploads/.tmp/r_<uid>_<rid>` نگه می‌داره (تا ۱ ساعت). بعد از قطع اینترنت، کلاینت `GET /upload-status` می‌زنه، `have` رو می‌گیره و فقط ادامه‌ی فایل رو می‌فرسته. اگر `offset` با `have` نخونه، سرور `409` و `have` درست رو برمی‌گردونه. تست: `test_upload_resume.py`.

### ۴.۴ `op_shared`
فهرست رسانه‌ی چت (`kind`: media / file / voice / audio / link). پارامتر `limit` (پیش‌فرض ۶۰، حداکثر ۶۰۰) و `before_id`. صف آهنگ‌ها (بخش ۸) با `kind=audio&limit=600` ازش استفاده می‌کنه.

---

## ۵. رابط وب (`web/app.js`)

- یک فایل بزرگ، بدون ماژول و بدون build. توابع کمکی: `h(tag, attrs, ...children)` برای ساخت DOM، `call(op, params)` برای ارسال op به سرور (Promise)، `S` برای state سراسری (`S.msgs[chatId]`, `S.chats`, `S.me`).
- پخش‌کننده‌ی مشترک: `VP` (یک `Audio` برای ویس و آهنگ). توابع: `startPlay`, `playToggle`, `stopVoice`, `neighbour`, `playNext`, `loadQueue`, `songList`.
- نوار کوچک پخش: `fillMini` / `paintMini` (کلاس CSS `.mini`، تو `index.html` دو جا: `#mini1`, `#mini2`).
- باز کردن قاب و فضای ابری: `openSso('ghab_token' | 'drive_token')`.
- ورودی‌های hash برای اپ اندروید: `#game=`, `#gcall=`, `#dm=`, `#join=`.
- ظاهر: `app.css` با متغیرهای CSS و حالت تیره/روشن. شیشه‌ای بودن با `backdrop-filter` (حدود خط ۹۴۹).
- بعد از هر تغییر در `app.js`، سینتکس رو چک کن: `node -e "new Function(require('fs').readFileSync('web/app.js','utf8'))"`.

---

## ۶. اپ اندروید

### ۶.۱ معماری
- **دو حالت:** `Prefs.mode(ctx)` = `"native"` یا `"web"`.
  - `native`: `NativeActivity` همه‌ی صفحه‌ها رو با یک stack (`a.push(Screen)`, `a.pop()`) مدیریت می‌کنه. هر صفحه از کلاس `Screen` ارث می‌بره و `view`, `onShow`, `onHide`, `onBack`, `onDestroy` داره.
  - `web`: `MainActivity` فقط یه `WebView` روی وب پیام‌رسانه.
- **UI با کد ساخته می‌شه** (نه XML): `LinearLayout`, `FrameLayout`, کمکی‌های `label()`, `icon()`, `iconButton()`, `rounded()`, `lp()`. رنگ‌ها در `Theme` (فایل `ui/Kit.kt`).
- **شبکه:**
  - `net/Ws.kt` + `net/Api.kt`: اتصال WebSocket، `a.rpc("op", mapOf(...)) { ok, r -> }`.
  - `net/Http.kt`: HTTP با گواهی pin شده: `get`, `download`, `upload`, `uploadResumable`, `multipart`.
  - `net/Model.kt`: `model.chats`, `model.msgs`.
  - `net/Json.kt`: JSON سبک خودمون (extension های `str`, `lng`, `bool`, `map`).
- **قاب و فضای ابری:** صفحه‌ی **وب** داخل `SiteActivity` (نه بومی). `NativeActivity.openGhabWeb(next)` توکن SSO می‌گیره و باز می‌کنه. اگه آفلاین باشه، با پورت ذخیره‌شده از کش باز می‌شه.
- **قاب بومی قدیمی** (`ui/Ghab.kt`: `GhabClient`, `GhabScreen`, ...) هنوز تو پروژه هست ولی هیچ‌جا صدا زده نمی‌شه. می‌شه پاکش کرد (فقط `ui/Ghab.kt` و ارجاع‌های `Ghab*` تو `NativeActivity` رو چک کن).

### ۶.۲ ظاهر شیشه‌ای (glassmorphism)
- `ui/Frost.kt`:
  - `Frost.blur()` بلور سریع روی bitmap کوچک.
  - `FrostDrawable`: بلور پس‌زمینه‌ی اپ + رنگ نیمه‌شفاف + لبه‌ی روشن (برای حباب پیام‌ها).
  - `FrostLinear`: نوار با **بلور زنده** از محتوای پشتش (نوار پایین لیست چت و نوار پخش).
- `Theme.frost()` و `Theme.bubbleBg()` در `Kit.kt`.
- `NativeActivity.dispatchTouchEvent` با `Frost.poke()` باعث می‌شه موقع اسکرول بلور تازه بشه.
- محدودیت: بلور حباب‌ها از پس‌زمینه‌ی اپ ساخته می‌شه، نه از محتوای لیست. موقع اسکرول روی عکس‌های پرجزئیات ممکنه کمی جابه‌جا دیده بشه.

### ۶.۳ پخش آهنگ (اندروید)
- `ui/Music.kt`: `RangeSource` آهنگ رو تکه‌تکه (۲۵۶ کیلوبایتی) با Range می‌گیره و **همزمان با دانلود پخش می‌کنه**؛ بعد از تکمیل تو کش می‌ره.
- `ui/Media.kt`: `VoicePlayer` (صف `queue`، `playQueue`, `replaceQueue`, `next`, `prev`، حالت shuffle و repeat).
- `ui/PlayerSheet.kt`: صفحه‌ی کامل پخش‌کننده. `MusicService.kt`: نوتیفیکیشن و کنترل از بیرون.
- **نوار پخش بالای اپ:** `NativeActivity.buildMini()` / `updateMini()` (حباب شیشه‌ای شناور با خط پیشرفت).
- **صف آهنگ‌ها:** `ChatScreen.playVoice` اول با پیام‌های لودشده شروع می‌کنه و بعد لیست کامل رو با `op_shared(kind=audio, limit=600)` می‌گیره و با `voicePlayer.replaceQueue()` جایگزین می‌کنه (بدون قطع آهنگ فعلی).

### ۶.۴ آپلود (اندروید)
- پیام چت: `ChatScreen.upload()` ← `Http.uploadResumable()`. اگه اینترنت قطع بشه تا ۵ دقیقه صبر می‌کنه (`graceMs`)، با `/upload-status` می‌پرسه چقدر رسیده و ادامه می‌ده. اگه ۲۵ ثانیه هیچ بایتی نره، اتصال رو قطع می‌کنه تا دوباره تلاش بشه.
- آپلود قاب داخل وب انجام می‌شه (`SiteActivity` از انتخاب‌گر فایل سیستم استفاده می‌کنه). ادامه‌ی نیمه‌کاره نداره.

### ۶.۵ کش و آفلاین قاب (`WebCache.kt`)
- از `SiteActivity.shouldInterceptRequest` صدا زده می‌شه. فقط درخواست‌های GET به همون origin رو می‌گیره.
- `/media/`, `/thumb/`, `/avatar/`: اول کش. ویدیو موقع پخش ذخیره می‌شه (`Tee`) و بعد از آن از دیسک با Range پخش می‌شه.
- صفحه و `/api/...`: اول شبکه، اگه نشد آخرین جواب ذخیره‌شده.
- سقف کل کش رسانه: پیش‌فرض ۴۰۰ مگابایت (`WebCache.DEFAULT_MB`، تو تنظیمات قابل تغییر)، قدیمی‌ترین‌ها اول پاک می‌شن.
- `/sso`, `/logout`, `/api/reels/watch` هیچ‌وقت کش نمی‌شن.

### ۶.۶ ساخت APK
1. **Android Studio:** پوشه‌ی `android/` رو باز کن، Build → Build APK.
2. **GitHub Actions:** فایل `.github/workflows/android.yml`.
3. نسخه‌ی SDK: `compileSdk 34`، `minSdk 29`. کتابخونه‌ها: media3 (exoplayer, ui, datasource-okhttp) نسخه‌ی 1.4.1، okhttp 4.12، lottie 6.4، core-ktx، appcompat.
4. امضا: `android/make-keystore.bat` و `keystore.properties.example` (امضای ثابت برای اینکه نصب روی نسخه‌ی قبلی به‌روزرسانی حساب بشه).

---

## ۷. Ghab و Cloud Drive

- هر دو Flask مستقل، دیتابیس جدا (Ghab: SQLite با `ghab/migrations/*.sql`).
- **ورود یکپارچه (SSO):** پیام‌رسان با `op_ghab_token` / `op_drive_token` توکن امضاشده (`username.expiry.nonce.sig`) می‌ده. کلاینت `GET /sso?t=…` رو باز می‌کنه و نشست ساخته می‌شه. توکن یک‌بار مصرفه.
- در `ghab/server/routes/sso.py` پارامتر اختیاری `next` هست (فقط `/p/<id>` یا `/u/<name>`) تا لینک پست یا پروفایل بعد از ورود همون‌جا باز بشه.
- اشتراک‌گذاری پست قاب تو چت: `POST /ghab-share` (فقط localhost، امضاشده).
- تست‌ها: `test_ghab*.py`, `test_drive.py`, `pentest_ghab.py`.

---

## ۸. دستور کار: کارهای رایج

### ۸.۱ اضافه کردن یک قابلیت جدید به پیام‌رسان (فرم کلی)
1. **سرور:** تو `server.py` متد `op_<name>(self, conn, req)` بنویس. ورودی رو اعتبارسنجی کن (`int(...)` با try/except و `Fail("…")`). عضویت چت رو چک کن. اگه رویداد لازمه `self.push(...)`.
2. اگه جدول یا ستون جدید لازمه، تو بخش ساخت/مهاجرت دیتابیس (`common.py` / ابتدای `server.py`) اضافه کن و **مهاجرت امن** بنویس (برای دیتابیس‌های قدیمی).
3. **وب:** تو `app.js` با `call('<name>', {...})` صداش بزن و UI رو با `h(...)` بساز. استایل تو `app.css`.
4. **اندروید:** با `a.rpc("<name>", mapOf(...)) { ok, r -> ... }` صدا بزن. UI تو صفحه‌ی مربوط (`ChatScreen`, `ListScreen`, `Bubbles`, ...).
5. **رویداد push:** وب تو `onEvent` (`app.js`)، اندروید تو `net/Api.kt` / `net/Model.kt` هندل می‌شه.
6. تست بنویس (`test_*.py`، الگو: `test_new.py`).

### ۸.۲ تغییر یک مسیر HTTP یا آپلود
تابع‌های `_upload`, `_media`, `_avatar_post`, ... تو `webgw.py`. سقف‌ها: `common.MAX_UPLOAD` (۲۰۰ مگ)، `MAX_AVATAR`. حتماً `common.disk_ok()` و محدودیت نرخ `_room_hits` رو نگه دار.

### ۸.۳ تغییر ظاهر اندروید
رنگ‌ها: `Theme` تو `ui/Kit.kt`. حباب پیام: `Theme.bubbleBg` و `Bubbles.bubble()`. نوار پایین: `ListScreen.buildTabs()`. پس‌زمینه: `ui/Wall.kt`.

### ۸.۴ تغییر پخش ویدیو (اندروید)
- پخش تمام‌صفحه: `PlayerActivity.kt` (ExoPlayer، از سرور استریم می‌کنه، کپی کش می‌شه).
- ویدیوهای قاب: داخل وب‌ویو پخش می‌شن و با `WebCache` ذخیره می‌شن.

### ۸.۵ پاک کردن کد غیرفعال
`ui/Ghab.kt` (قاب بومی) استفاده نمی‌شه. بعد از پاک کردنش، دنبال `GhabClient`, `a.ghab`, `GhabScreen`, `GhabPostScreen`, `GhabProfileScreen` بگرد و ارجاع‌ها رو بردار. بعد کامپایل رو چک کن.

---

## ۹. تست و بررسی

### ۹.۱ تست‌های پایتون
```
python test_new.py             # session, پخش media با Range، آپلود، تماس
python test_upload_resume.py   # آپلود ادامه‌دار
python test_core.py
python test_ghab.py
python test_security.py
```
هر فایل تست مستقل و با سرور موقت خودش کار می‌کنه و آخرش `N passed, M failed` چاپ می‌کنه. تست‌های `*_ui.py` به `playwright` و chromium نیاز دارن.

### ۹.۲ چک کامپایل Kotlin بدون Android Studio
وقتی SDK نداری (مثلاً محیط هوش مصنوعی)، یه چک تقریبی می‌شه:
1. `kotlinc` رو از GitHub releases بگیر (نسخه‌ی 1.9.x) و یه `android.jar` (مثلاً مخزن `Sable/android-platforms`).
2. اجرا کن:
```
JAVA_OPTS="-Xmx3g -Xss32m" kotlinc -no-stdlib \
  -cp android.jar:kotlinc/lib/kotlin-stdlib.jar \
  -d out $(find android/app/src/main/java -name '*.kt')
```
3. خطاهای مربوط به `androidx`, `media3`, `okhttp3`, `lottie` رو نادیده بگیر (کتابخونه‌ها نیستن). چیزی که مهمه: **هیچ خطای دیگه‌ای تو فایل‌هایی که تغییر دادی نباشه.** (خطای `Ghab.kt` درباره‌ی `Bitmap?` تو `posterOf` قدیمی و بی‌ضرره.)
4. این چک جای بیلد واقعی رو نمی‌گیره؛ بیلد نهایی رو تو Android Studio بزن.

### ۹.۳ دام‌هایی که قبلاً دیده شد
- `@Volatile` روی **متغیر محلی** تو Kotlin خطای کامپایله. از `AtomicLong` / `AtomicBoolean` استفاده کن.
- `IntArray` رو با `loc[0]`, `loc[1]` بخون، نه `loc.x` (برای `getLocationInWindow`).
- کلاس‌های `@UnstableApi` تو Media3 فقط هشدار لینت می‌دن؛ کد قبلی (`PlayerActivity`) هم همین‌طوره.
- `ExoPlayer` و `PlayerView` باید روی thread اصلی ساخته بشن.
- `HttpURLConnection` کوکی نمی‌فرسته مگه خودت هدر `Cookie` بذاری (`WebCache` از `CookieManager` برمی‌داره).
- `shouldInterceptRequest` روی thread پس‌زمینه اجرا می‌شه و باید `Range` رو خودش مدیریت کنه.

---

## ۱۰. تاریخچه‌ی تغییرات این دوره

| نسخه | تغییر |
|---|---|
| 6.34 | آپلود ادامه‌دار (سرور + اندروید)؛ ظاهر شیشه‌ای (Frost)؛ نوار پایین با بلور زنده؛ پخش زنده‌ی ویدیوی قاب بومی؛ پخش خودکار ویدیو داخل پست‌های فید بومی |
| 6.35 | رفع خطای کامپایل `Http.kt` و `Frost.kt`؛ قاب بومی غیرفعال و جایگزین با قاب وب داخل اپ؛ نوار پخش آهنگ به صورت حباب شیشه‌ای شناور (اپ + وب)؛ زمان زنده تو حباب آهنگ |
| 6.36 | `WebCache`: کش ۴۰۰ مگی رسانه و آفلاین برای قاب؛ باز شدن قاب بدون اینترنت |
| 6.37 | صف کامل آهنگ‌ها از سرور (`op_shared limit`) برای جلو و عقب کردن بدون پرش (وب + اندروید) |
| 6.38 | فایل `start.sh` برای لینوکس و مک (مثل `start.bat`)؛ این راهنما داخل زیپ |
| 6.39 | تست امنیتی: اسم فایل آپلودی از کاراکتر کنترلی (CR/LF/NUL) پاک می‌شه؛ آپلود نیمه‌کاره هر کاربر حداکثر ۳ تا و ۳۰ دقیقه نگه داشته می‌شه (جلوی پر شدن دیسک)؛ تست‌های آواتار با حذف واقعی فایل‌ها هماهنگ شد |
| 6.40 | پخش زنده‌ی آهنگ سریع‌تر: `RangeSource` دانلود هر تکه را بیرون از قفل انجام می‌دهد (پخش‌کننده پشت prefetch نمی‌ماند)، تکه‌ها ۱۲۸ کیلوبایت، اتصال دوباره استفاده می‌شود |
| 6.41 | قاب: ویدیوی HEVC / ۱۰بیتی گوشی همیشه به H.264 تبدیل می‌شود (حتی اگر کوچک‌تر نشود)؛ نسخه‌ی اصلی ۱۵ دقیقه (به‌جای ۲ دقیقه) می‌ماند؛ تایم‌اوت خواندن بدنه‌ی آپلود ۶۰ ثانیه |
| 6.42 | کش قاب: پاک‌سازی فایل‌های نیمه‌کاره‌ی مانده، قفل مشترک بین صفحه‌ها، ادعای دانلودِ کهنه بعد از ۵ دقیقه آزاد می‌شود، بدنه‌ی بی‌توضیح پاک می‌شود؛ تو تنظیمات ← حافظه: اندازه، پاک کردن و سقف (۲۰۰ تا ۱۶۰۰ مگ) |
| 6.43 | اندروید: لیست چت‌ها شیشه‌ای (هر ردیف یک کارت شیشه‌ای با بلور پس‌زمینه، نوار بالا و چیپ‌ها نیمه‌شفاف)؛ قاب: استایل شیشه‌ای (انتهای `ghab/web/static/app.css`: پس‌زمینه‌ی رنگی، کارت‌ها، نوار بالا و پایین شناور، شیت‌ها، ورودی‌ها؛ تم روشن هم) |

---

## ۱۱. محدودیت‌ها و کارهای باز

- بیلد کامل اندروید با کتابخونه‌های media3 و okhttp رو تو محیط توسعه‌ی هوش مصنوعی نشد کامپایل کرد؛ بعد از هر تغییر، بیلد واقعی لازمه.
- آپلود تو قاب وب ادامه‌ی نیمه‌کاره نداره.
- کاور آهنگ (عکس آلبوم) تو حباب آهنگ نیست؛ سرور هنوز از ID3 در نمی‌یاره.
- بلور حباب‌ها موقع اسکرول روی پس‌زمینه‌ی عکس ممکنه کمی جابه‌جا دیده بشه.
- `ui/Ghab.kt` کد مرده‌ست.
- آپلود وب (مرورگر) هنوز resume نداره؛ سرور آماده‌ست (`rid/offset/total`) و فقط سمت `app.js` مونده.


---

## ۱۲. نتیجه‌ی آخرین تست امنیتی (v6.39)

حمله‌ی شبیه‌سازی‌شده روی سرور موقت: ۱۱۰ بررسی، ۰ باگ باز. بررسی‌شده‌ها: دسترسی بی‌اجازه به فایل چت دیگران (IDOR)، پیمایش مسیر روی همه‌ی مسیرهای فایل (`..`, کدگذاری دوبل، `\`، NUL)، تزریق هدر از اسم فایل، اجرای HTML آپلودی (باید sandbox/attachment باشه)، `Content-Length` غول‌آسا، Range های خراب، آپلود ادامه‌دار دیگران، همه‌ی `op_*` بدون ورود، `op` های بی‌مجوز روی چت خصوصی، brute force رمز (قفل می‌شه)، فریم خراب، تزریق SQL در ورود، `/ghab-share` از بیرون.

نکات قابل‌دونستن (باگ نیستن):
- قفل حساب بعد از چند رمز اشتباه، مهاجم رو هم می‌تونه باعث بشه صاحب حساب ۵ دقیقه نتونه وارد بشه. (معاوضه‌ی معمول)
- `MainActivity` اندروید `exported` ـه (برای اشتراک‌گذاری). یه برنامه‌ی دیگه روی همون گوشی می‌تونه فقط `#hash` اضافه کنه (همون سرور، نه آدرس دلخواه).
- `usesCleartextTraffic=true` برای حالت http محلیه؛ با https و pin ایمنه.
- تست‌های `test_v13` گاهی به خاطر سقف اتصال همزمان هر IP (`over` تو `server.py`) فلکی‌ان؛ `test_mensch3d` بدون فایل `web/lottie_light.js` شکست می‌خوره (فایل بدون اینترنت دانلود نمی‌شه).


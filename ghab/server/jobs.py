"""کارهای پس‌زمینه با اولویت پایین: فشرده‌سازی ویدیو و ساخت نسخه‌های سبک.

برای هر ویدیو دو نسخه هست تا مرورگر بسته به سرعت اینترنت یکی را انتخاب کند (مثل اینستاگرام):
  main  کیفیت قابل‌قبول: تا ۷۲۰ عمودی / ۹۶۰ افقی، ۳۰ فریم، CRF 30 (حدود ۱ تا ۲ مگابیت) ← جایگزین فایل اصلی
        اگر کدگذاری مجدد کوچک‌تر نشود، فایل اصلی دست‌نخورده می‌ماند. نسخه اصلی آرشیو نمی‌شود (۱۰ دقیقه بعد پاک می‌شود)
  low   تا ۴۸۰ عمودی / ۶۴۰ افقی، ۲۴ فریم، تا ~۰٫۶ مگابیت (ستون posts.low) ← اینترنت ضعیف
برای عکس‌های قدیمی هم نسخه ۷۲۰ پیکسلی (posts.mid) ساخته می‌شود. نسخه low از main ساخته می‌شود.
ffmpeg از بسته imageio-ffmpeg یا PATH پیدا می‌شود؛ اگر نبود همه‌چیز مثل قبل کار می‌کند.
"""
import hashlib
import os
import queue
import re
import shutil
import sqlite3
import subprocess
import threading

from . import config, storage

_q = queue.Queue()
_lock = threading.Lock()
_worker = None
_ff = ''  # '' = هنوز جستجو نشده، None = پیدا نشد
_queued = set()
stats = {'done': 0, 'saved': 0}
KEEP_ORIGINAL_SEC = 900  # نسخه اصلی ۱۵ دقیقه می‌ماند تا کلاینت‌های دارای فید قدیمی ۴۰۴ نگیرند
MIN_LOW_SOURCE = 250 * 1024  # ویدیوهای کوچک‌تر از این نسخه low لازم ندارند
TEST_VP8 = False  # فقط برای تست در مرورگرهایی که H.264 ندارند

PROFILES = {
    'main': dict(port=720, land=960, crf=30, rate=2000, fps=30, ab=80, ac=2, preset='veryfast'),
    'low': dict(port=480, land=640, crf=33, rate=600, fps=24, ab=48, ac=1, preset='veryfast'),
}


def ffmpeg_path():
    global _ff
    if _ff == '':
        _ff = None
        try:
            import imageio_ffmpeg
            _ff = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            _ff = shutil.which('ffmpeg')
            local = os.path.join(config.BASE_DIR, 'ffmpeg.exe')
            if not _ff and os.path.exists(local):
                _ff = local
    return _ff


def enqueue(table, row_id, rel, kind='main'):
    if table not in ('posts', 'stories') or (kind, table, row_id) in _queued:
        return False
    if kind in ('main', 'rend') and (not config.COMPRESS_VIDEO or not ffmpeg_path()):
        return False
    global _worker
    _queued.add((kind, table, row_id))
    with _lock:
        if _worker is None:
            _worker = threading.Thread(target=_loop, daemon=True)
            _worker.start()
    _q.put((kind, table, row_id, rel))
    return True


def status():
    return dict(ffmpeg=bool(ffmpeg_path()) and config.COMPRESS_VIDEO, pending=_q.unfinished_tasks,
                done=stats['done'], saved_mb=round(stats['saved'] / 1048576, 1))


def enqueue_all():
    """هرچه فشرده/سبک نشده به صف می‌رود (ویدیوهای قدیمی، نسخه low، عکس‌های بدون mid). تعداد را برمی‌گرداند."""
    n = 0
    con = sqlite3.connect(config.DB_PATH, timeout=10)
    try:
        for table in ('posts', 'stories'):
            for rid, rel in con.execute(f"select id, file from {table} where kind='video' and optimized=0").fetchall():
                n += enqueue(table, rid, rel, 'main')
        if config.EXTRA_RENDITIONS:
            for rid, rel in con.execute("select id, file from posts where kind='video' and optimized=1 and low is null").fetchall():
                n += enqueue('posts', rid, rel, 'rend')
            for rid, rel in con.execute("select id, file from posts where kind='image' and mid is null").fetchall():
                n += enqueue('posts', rid, rel, 'mid')
    finally:
        con.close()
    return n


def wait():
    _q.join()


def _loop():
    while True:
        job = _q.get()
        try:
            {'main': _job_main, 'rend': _job_rend, 'mid': _job_mid}[job[0]](*job[1:])
        except Exception:
            pass
        finally:
            _q.task_done()


def _run(cmd, timeout):
    kw = {}
    if os.name == 'nt':
        kw['creationflags'] = 0x00004000  # BELOW_NORMAL_PRIORITY_CLASS
    else:
        kw['preexec_fn'] = lambda: os.nice(10)
    subprocess.run(cmd, check=True, capture_output=True, timeout=timeout, **kw)


def _ext():
    return 'webm' if TEST_VP8 else 'mp4'


def _encode(src, dst, prof):
    p = PROFILES[prof]
    vf = f"scale='if(gt(iw,ih),min({p['land']},iw),min({p['port']},iw))':-2,fps={p['fps']}"
    if TEST_VP8:
        codec = ['-c:v', 'libvpx', '-crf', str(p['crf']), '-b:v', f"{p['rate']}k", '-deadline', 'realtime', '-cpu-used', '8',
                 '-c:a', 'libvorbis', '-b:a', f"{p['ab']}k", '-f', 'webm']
    else:
        codec = ['-c:v', 'libx264', '-preset', p['preset'], '-crf', str(p['crf']), '-maxrate', f"{p['rate']}k",
                 '-bufsize', f"{p['rate'] * 2}k", '-pix_fmt', 'yuv420p', '-profile:v', 'main',
                 '-c:a', 'aac', '-b:a', f"{p['ab']}k", '-ac', str(p['ac']), '-movflags', '+faststart', '-f', 'mp4']
    _run([ffmpeg_path(), '-y', '-v', 'error', '-i', src, '-vf', vf, *codec, '-threads', '2', dst], 1800)


def probe_kbps(path):
    """نرخ بیت میانگین فایل (کیلوبیت بر ثانیه) از اندازه و مدت؛ کلاینت با آن نسخه مناسب سرعت اینترنت را برمی‌دارد."""
    ff = ffmpeg_path()
    if not ff or not path or not os.path.exists(path):
        return None
    try:
        r = subprocess.run([ff, '-hide_banner', '-i', path], capture_output=True, text=True, timeout=30)
        m = re.search(r'Duration: (\d+):(\d+):([\d.]+)', r.stderr)
        dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
        return max(int(os.path.getsize(path) * 8 / 1000 / dur), 1) if dur > 0 else None
    except Exception:
        return None


def file_sha(path):
    """sha1 فایل (برای تشخیص آپلود تکراری). فقط خواندن؛ به فایل دست نمی‌زند."""
    try:
        h = hashlib.sha1()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(1 << 20), b''):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def backfill_sha():
    """ویدیوهای قدیمی که اثر انگشت ندارند، یک‌بار hash می‌شوند (فقط ستون sha پر می‌شود)."""
    con = sqlite3.connect(config.DB_PATH, timeout=10)
    try:
        rows = con.execute("select id, file from posts where kind='video' and sha is null").fetchall()
        for rid, rel in rows:
            s = file_sha(storage.abs_path(rel) or '')
            if s:
                con.execute('update posts set sha=? where id=?', (s, rid))
        con.commit()
    finally:
        con.close()


def _db():
    return sqlite3.connect(config.DB_PATH, timeout=10)


def _is_plain_h264(src):
    """True / False if the video is H.264 8-bit 4:2:0 (plays everywhere, also in Android WebView); None if unknown.
    Phone cameras often record HEVC / 10-bit HDR: such files must always be re-encoded, even if the result is not smaller."""
    try:
        r = subprocess.run([ffmpeg_path(), '-hide_banner', '-i', src], capture_output=True, timeout=60, text=True, errors='replace')
        line = next((l for l in r.stderr.splitlines() if 'Video:' in l and 'attached pic' not in l), '')
        if not line:
            return None
        import re as _re
        return ' h264' in line.replace('Video:', ' ') and bool(_re.search(r'yuv420p(?!\d)', line))
    except Exception:
        return None


def _job_main(table, row_id, rel):
    src = storage.abs_path(rel)
    if not src or not os.path.exists(src):
        return
    ff = ffmpeg_path()
    new_rel = rel.rsplit('.', 1)[0] + '_c.' + _ext()
    dst = storage.abs_path(new_rel)
    tmp = dst + '.part'
    src_size = os.path.getsize(src)
    swapped = False
    plain = _is_plain_h264(src)
    must = plain is False                   # HEVC / 10-bit / VP9...: re-encode to H.264 whatever the size
    if src_size > 300 * 1024 or must:
        try:
            _encode(src, tmp, 'main')
            if os.path.getsize(tmp) > 0 and (must or os.path.getsize(tmp) < src_size * 0.95):
                os.replace(tmp, dst)
                swapped = True
        except Exception:
            pass
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
    cur, cur_rel = (dst, new_rel) if swapped else (src, rel)
    poster = None
    if table == 'posts':  # اگر مرورگر تصویر کوچک نفرستاده بود، از اولین فریم ساخته می‌شود
        con = _db()
        try:
            row = con.execute('select poster from posts where id=? and file=?', (row_id, rel)).fetchone()
        finally:
            con.close()
        if row and not row[0]:
            p_rel = rel.rsplit('.', 1)[0] + '_p.jpg'
            try:
                _run([ff, '-y', '-v', 'error', '-ss', '0.5', '-i', cur, '-frames:v', '1', '-vf', 'scale=480:-2',
                      '-q:v', '5', storage.abs_path(p_rel)], 60)
                poster = p_rel
            except Exception:
                pass
    con = _db()
    try:
        if table == 'posts':
            n = con.execute('update posts set file=?, optimized=1, poster=coalesce(poster,?), kbps=? where id=? and file=?',
                            (cur_rel, poster, probe_kbps(cur), row_id, rel)).rowcount
        else:
            n = con.execute('update stories set file=?, optimized=1 where id=? and file=?', (cur_rel, row_id, rel)).rowcount
        con.commit()
    finally:
        con.close()
    if not n:  # در این فاصله پست/استوری حذف شده بود
        storage.rm_file(cur_rel)
        if poster:
            storage.rm_file(poster)
        return
    if swapped:
        stats['done'] += 1
        stats['saved'] += max(src_size - os.path.getsize(cur), 0)
        t = threading.Timer(KEEP_ORIGINAL_SEC, storage.rm_file, [rel])
        t.daemon = True
        t.start()
    if table == 'posts' and config.EXTRA_RENDITIONS:
        enqueue('posts', row_id, cur_rel, 'rend')


def _job_rend(table, row_id, _rel):
    """نسخه low را از روی main می‌سازد؛ فقط وقتی نگه داشته می‌شود که حداقل ۲۰٪ سبک‌تر باشد."""
    con = _db()
    try:
        row = con.execute("select file, low, kbps from posts where id=? and kind='video'", (row_id,)).fetchone()
    finally:
        con.close()
    if not row or (row[1] is not None and row[2] is not None):
        return
    rel = row[0]
    src = storage.abs_path(rel)
    if not src or not os.path.exists(src):
        return
    size = os.path.getsize(src)
    base = rel.rsplit('.', 1)[0]
    base = base[:-2] if base.endswith('_c') else base
    low = '' if row[1] is None else row[1]
    if row[1] is None and size >= MIN_LOW_SOURCE:  # ویدیوی خیلی کوچک نسخه جدا لازم ندارد
        cand = f'{base}_480.{_ext()}'
        dst = storage.abs_path(cand)
        tmp = dst + '.part'
        try:
            _encode(src, tmp, 'low')
            if os.path.getsize(tmp) < size * 0.8:
                os.replace(tmp, dst)
                low = cand
        except Exception:
            pass
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
    con = _db()
    try:
        n = con.execute('update posts set low=coalesce(low, ?), kbps=coalesce(kbps, ?), lkbps=coalesce(lkbps, ?) where id=? and file=?',
                        (low, probe_kbps(src), probe_kbps(storage.abs_path(low)) if low else None, row_id, rel)).rowcount
        con.commit()
    finally:
        con.close()
    if not n and low:
        storage.rm_file(low)


def _job_mid(table, row_id, rel):
    """نسخه ۷۲۰ پیکسلی (و تصویر کوچک ۳۶۰ در صورت نبودن) برای عکس‌های قدیمی. گیف متحرک و فایل خراب: '' یعنی لازم نیست."""
    mid = thumb = ''
    src = storage.abs_path(rel)
    ext = rel.rsplit('.', 1)[-1].lower()
    if storage.Image and src and os.path.exists(src) and ext in ('jpg', 'jpeg', 'png', 'webp'):
        try:
            out = rel.rsplit('.', 1)[0] + '_m.jpg'
            im = storage.Image.open(src)
            im.load()
            small = storage._to_rgb(im)
            storage._save_jpeg(small, storage.abs_path(out), 720, 76)
            mid = out
            th = rel.rsplit('.', 1)[0] + '_t.jpg'
            if not os.path.exists(storage.abs_path(th)):
                storage._save_jpeg(small, storage.abs_path(th), 360, 72)
                thumb = th
        except Exception:
            mid = ''
    con = _db()
    try:
        n = con.execute("update posts set mid=?, poster=coalesce(poster, ?) where id=? and file=? and kind='image' and mid is null",
                        (mid, thumb or None, row_id, rel)).rowcount
        con.commit()
    finally:
        con.close()
    if not n and mid:
        storage.rm_file(mid)

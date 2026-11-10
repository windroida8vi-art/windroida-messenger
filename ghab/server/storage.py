"""ذخیره فایل‌ها: برای هر کاربر یک پوشه  data/users/<username>/{posts,stories,avatar}/
در دیتابیس فقط مسیر نسبی می‌ماند، مثل  ali/posts/3f9c….mp4

بهینه‌سازی موقع آپلود:
  • عکس‌ها: چرخش درست (EXIF)، کوچک‌کردن به حداکثر ۱۴۴۰ پیکسل، JPEG فشرده + تصویر کوچک ۳۶۰ پیکسلی
  • ویدیوها: moov به ابتدای فایل برده می‌شود (faststart) تا فوری شروع به پخش کنند
"""
import os
import shutil
import struct
import uuid

try:
    from PIL import Image, ImageOps
    Image.MAX_IMAGE_PIXELS = 40_000_000  # جلوگیری از «بمب تصویر»
except ImportError:  # بدون Pillow هم کار می‌کند، فقط عکس‌ها بهینه نمی‌شوند
    Image = None

from . import config
from .config import USERS_DIR

IMG = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
VID = {'mp4', 'webm', 'mov'}


def user_dir(username):
    return os.path.join(USERS_DIR, username)


def abs_path(rel):
    if not rel:
        return None
    base = os.path.abspath(USERS_DIR)
    p = os.path.abspath(os.path.join(base, rel))
    return p if p.startswith(base + os.sep) else None  # جلوگیری از خروج از پوشه


def _ext(name):
    return name.rsplit('.', 1)[-1].lower() if name and '.' in name else ''


def kind_of(ext):
    return 'image' if ext in IMG else 'video' if ext in VID else None


def _dir(username, folder):
    d = os.path.join(user_dir(username), folder)
    os.makedirs(d, exist_ok=True)
    return d


def _to_rgb(im):
    im = ImageOps.exif_transpose(im)
    if im.mode in ('RGBA', 'LA', 'P'):
        im = im.convert('RGBA')
        bg = Image.new('RGB', im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[-1])
        return bg
    return im.convert('RGB')


def _save_jpeg(im, path, side, q):
    im = im.copy()
    im.thumbnail((side, side))
    im.save(path, 'JPEG', quality=q, optimize=True, progressive=True)


def save_file(f, username, folder, kinds=('image', 'video'), side=None, thumb=True):
    """برمی‌گرداند (مسیر، نوع، تصویر کوچک، نسخه ۷۲۰) یا None اگر فایل معتبر نبود."""
    ext = _ext(f.filename)
    kind = kind_of(ext)
    if not kind or kind not in kinds:
        return None
    side = side or (1440 if config.EXTRA_RENDITIONS else 1080)  # حالت کم‌حجم: ۱۰۸۰ پیکسل مثل اینستاگرام
    d = _dir(username, folder)
    base = uuid.uuid4().hex
    if kind == 'image' and Image:
        try:
            im = Image.open(f.stream)
            im.load()
            if ext == 'gif' and getattr(im, 'is_animated', False):  # گیف متحرک دست‌نخورده می‌ماند
                f.stream.seek(0)
                f.save(os.path.join(d, base + '.gif'))
                name, small = base + '.gif', _to_rgb(im.convert('RGBA') if im.mode == 'P' else im)
            else:
                small = _to_rgb(im)
                name = base + '.jpg'
                _save_jpeg(small, os.path.join(d, name), side, 82)
            poster = mid = None
            if thumb:
                poster = f'{username}/{folder}/{base}_t.jpg'
                _save_jpeg(small, os.path.join(d, base + '_t.jpg'), 360, 72)
                if config.EXTRA_RENDITIONS and name.endswith('.jpg'):  # نسخه ۷۲۰ پیکسلی برای فید (فقط اگر روشن باشد)
                    mid = f'{username}/{folder}/{base}_m.jpg'
                    _save_jpeg(small, os.path.join(d, base + '_m.jpg'), 720, 76)
            return f'{username}/{folder}/{name}', 'image', poster, mid
        except Exception:
            return None  # فایل عکس واقعی نیست
    name = f'{base}.{ext}'
    path = os.path.join(d, name)
    f.save(path)
    if kind == 'video' and ext in ('mp4', 'mov'):
        faststart(path)
    return f'{username}/{folder}/{name}', kind, None, None


def save_poster(f, username):
    """تصویر کوچکِ اولین فریم ویدیو که مرورگر می‌سازد و همراه آپلود می‌فرستد."""
    if not f or not f.filename or not Image:
        return None
    try:
        im = Image.open(f.stream)
        im.load()
        d = _dir(username, 'posts')
        name = f'{uuid.uuid4().hex}_p.jpg'
        _save_jpeg(_to_rgb(im), os.path.join(d, name), 480, 72)
        return f'{username}/posts/{name}'
    except Exception:
        return None


AUD = {'webm', 'ogg', 'opus', 'mp3', 'm4a', 'wav', 'aac'}


def save_audio(f, username, max_bytes=3 * 1024 * 1024):
    """پیام صوتی (حداکثر ۳ مگابایت)."""
    ext = _ext(f.filename) or 'webm'
    if ext not in AUD:
        return None
    name = f'{uuid.uuid4().hex}.{ext}'
    path = os.path.join(_dir(username, 'dm'), name)
    f.save(path)
    if os.path.getsize(path) > max_bytes:
        os.remove(path)
        return None
    return f'{username}/dm/{name}'


def copy_file(rel, username, folder):
    d = _dir(username, folder)
    name = f'{uuid.uuid4().hex}.{_ext(rel)}'
    shutil.copyfile(abs_path(rel), os.path.join(d, name))
    return f'{username}/{folder}/{name}'


def file_size(rel):
    p = abs_path(rel)
    try:
        return os.path.getsize(p) if p else 0
    except OSError:
        return 0


def rm_file(rel):
    p = abs_path(rel)
    if p:
        try:
            os.remove(p)
        except OSError:
            pass


def cleanup_tmp():
    """فایل‌های نیمه‌کاره (.part) که بعد از قطع ناگهانی برق/برنامه مانده‌اند پاک می‌شوند."""
    for r, _, fs in os.walk(USERS_DIR):
        for f in fs:
            if f.endswith('.part') or f.endswith('.fs'):
                try:
                    os.remove(os.path.join(r, f))
                except OSError:
                    pass


def remove_user_dir(username):
    shutil.rmtree(user_dir(username), ignore_errors=True)


def dir_size(path):
    return sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(path) for f in fs)


# ---------- faststart بدون ffmpeg ----------
_CONTAINERS = {b'moov', b'trak', b'mdia', b'minf', b'stbl'}


def _atoms(f, size):
    out, pos = [], 0
    while pos < size:
        f.seek(pos)
        h = f.read(8)
        if len(h) < 8:
            break
        sz, typ = struct.unpack('>I4s', h)
        if sz == 1:
            sz = struct.unpack('>Q', f.read(8))[0]
        elif sz == 0:
            sz = size - pos
        if sz < 8:
            break
        out.append((typ, pos, sz))
        pos += sz
    return out


def _shift(buf, start, end, shift, lo, hi):
    """offsetهای stco/co64 را که به [lo,hi) اشاره می‌کنند به‌اندازه shift جابه‌جا می‌کند."""
    pos = start
    while pos + 8 <= end:
        sz, typ = struct.unpack('>I4s', buf[pos:pos + 8])
        if sz < 8:
            break
        if typ in _CONTAINERS:
            _shift(buf, pos + 8, pos + sz, shift, lo, hi)
        elif typ in (b'stco', b'co64'):
            n = struct.unpack('>I', buf[pos + 12:pos + 16])[0]
            w, fmt = (4, '>I') if typ == b'stco' else (8, '>Q')
            for i in range(n):
                o = pos + 16 + i * w
                v = struct.unpack(fmt, buf[o:o + w])[0]
                if lo <= v < hi:
                    buf[o:o + w] = struct.pack(fmt, v + shift)
        pos += sz


def faststart(path):
    """اگر moov آخر فایل باشد، به بعد از ftyp منتقل می‌شود. هر خطایی = فایل اصلی دست‌نخورده."""
    tmp = path + '.fs'
    try:
        size = os.path.getsize(path)
        with open(path, 'rb') as f:
            at = _atoms(f, size)
            types = [a[0] for a in at]
            if b'moov' not in types or b'mdat' not in types or types.index(b'moov') < types.index(b'mdat'):
                return False
            if types[0] != b'ftyp':
                return False
            _, mpos, msz = at[types.index(b'moov')]
            if msz > 64 * 1024 * 1024:
                return False
            f.seek(mpos)
            moov = bytearray(f.read(msz))
            ftyp_end = at[0][1] + at[0][2]
            _shift(moov, 8, msz, msz, ftyp_end, mpos)
            with open(tmp, 'wb') as out:
                f.seek(0)
                out.write(f.read(ftyp_end))
                out.write(moov)
                for typ, pos, sz in at[1:]:
                    if typ == b'moov':
                        continue
                    f.seek(pos)
                    left = sz
                    while left:
                        chunk = f.read(min(left, 1 << 20))
                        out.write(chunk)
                        left -= len(chunk)
        os.replace(tmp, path)
        return True
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False

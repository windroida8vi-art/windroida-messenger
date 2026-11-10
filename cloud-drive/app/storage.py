"""Storage service. All disk access for user files goes through this class so an S3 backend
can be added later by implementing the same methods."""
import os
import re
import shutil
import uuid
from pathlib import Path

_STORED_RE = re.compile(r"^[0-9a-f]{32}$")
_ID_RE = re.compile(r"^[0-9a-f]{32}$")

PREVIEW_MIMES = {"image/png", "image/jpeg", "image/gif", "image/webp", "application/pdf"}


def sniff_mime(path):
    """Detect a previewable type from magic bytes (never trust the extension or client MIME)."""
    try:
        with open(path, "rb") as f:
            head = f.read(16)
    except OSError:
        return None
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"GIF87a") or head.startswith(b"GIF89a"):
        return "image/gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    return None


class LocalStorage:
    def __init__(self, root, tmp_root):
        self.root = Path(root).resolve()
        self.tmp_root = Path(tmp_root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.tmp_root.mkdir(parents=True, exist_ok=True)

    # --- final files -------------------------------------------------
    @staticmethod
    def new_name():
        return uuid.uuid4().hex

    def path(self, stored_name):
        if not _STORED_RE.match(stored_name or ""):
            raise ValueError("invalid stored name")
        p = (self.root / stored_name[:2] / stored_name).resolve()
        if self.root not in p.parents:
            raise ValueError("path escape")
        return p

    def delete(self, stored_name):
        try:
            self.path(stored_name).unlink()
        except (FileNotFoundError, ValueError):
            pass

    def free_bytes(self):
        return shutil.disk_usage(self.root).free

    def disk_usage(self):
        return shutil.disk_usage(self.root)

    # --- chunk staging -----------------------------------------------
    def _upload_dir(self, upload_id):
        if not _ID_RE.match(upload_id or ""):
            raise ValueError("invalid upload id")
        return self.tmp_root / upload_id

    def write_chunk(self, upload_id, idx, data):
        d = self._upload_dir(upload_id)
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / ("%d.tmp" % idx)
        tmp.write_bytes(data)
        os.replace(tmp, d / ("%d.part" % idx))

    def assemble(self, upload_id, total_chunks, stored_name):
        d = self._upload_dir(upload_id)
        final = self.path(stored_name)
        final.parent.mkdir(parents=True, exist_ok=True)
        tmp = final.with_name(final.name + ".tmp")
        with open(tmp, "wb") as out:
            for i in range(total_chunks):
                with open(d / ("%d.part" % i), "rb") as f:
                    shutil.copyfileobj(f, out, 1024 * 1024)
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, final)
        return final

    def drop_upload(self, upload_id):
        try:
            shutil.rmtree(self._upload_dir(upload_id), ignore_errors=True)
        except ValueError:
            pass

    def list_upload_dirs(self):
        return [p.name for p in self.tmp_root.iterdir() if p.is_dir()]

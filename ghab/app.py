#!/usr/bin/env python3
"""قاب — اجرای برنامه:  python app.py"""
import os

from server import create_app
from server.config import BEHIND_PROXY, PASSWORD_AUTH, PORT, USERS_DIR, VERSION
from server.httpd import make_context, serve
from server.jobs import ffmpeg_path
from server.tls import custom_cert, ensure_cert, lan_ip

app = create_app()

if __name__ == '__main__':
    ip = lan_ip()
    pub = os.environ.get('GHAB_PUBLIC', '').strip()  # IP یا دامنه عمومی (اختیاری)
    ctx, scheme = None, 'http'
    if not BEHIND_PROXY:
        files = ensure_cert(ip, pub)
        if files:
            ctx, scheme = make_context(*files), 'https'
        else:
            app.config['SESSION_COOKIE_SECURE'] = False
    host = pub or ip
    lines = [f'Ghab v{VERSION} is running:  {scheme}://{ip}:{PORT}']
    if pub:
        lines.append(f'Public:        {scheme}://{pub}:{PORT}')
    lines += [f'User files:    {USERS_DIR}',
              'Video compression: ' + ('ON' if ffmpeg_path() else 'OFF (ffmpeg not found)')]
    if BEHIND_PROXY:
        lines.append('Mode: plain HTTP behind an HTTPS proxy (GHAB_PLAIN=1)')
    elif os.environ.get('GHAB_CERT'):
        lines.append('Certificate: shared with Windroida (same browser warning once)')
    elif custom_cert():
        lines.append('Certificate: your own (data/certs/custom) - no browser warning')
    elif ctx and PASSWORD_AUTH:
        lines.append(f'Browser warning? Open {scheme}://{host}:{PORT}/trust once on each device to install the certificate.')
    print('\n  ' + '\n  '.join(lines) + '\n')
    import time, traceback, faulthandler
    try:
        faulthandler.enable()
    except Exception:
        pass
    _fails = []
    while True:                     # a server error restarts the server in this same process (gives up only after 6 failures in a minute)
        try:
            serve(app, '0.0.0.0', PORT, ctx)
            break
        except KeyboardInterrupt:
            raise
        except SystemExit:
            raise
        except BaseException:
            _t = time.time()
            _fails = [x for x in _fails if x > _t - 60] + [_t]
            print('\n  [Ghab] server error, restarting it in 2 s:\n' + traceback.format_exc(), flush=True)
            if len(_fails) > 6:
                raise
            time.sleep(2)

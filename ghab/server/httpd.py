"""سرور HTTPS مقاوم برای قاب (جایگزین سرور داخلی Flask که زود «قفل» می‌شود).

  • دست‌دادن TLS داخل نخ کارگر و با timeout انجام می‌شود؛ کلاینت نیمه‌کاره کل سرور را قفل نمی‌کند.
  • استخر نخ محدود + صف محدود؛ در شلوغی بیش از حد اتصال اضافه رد می‌شود و سرور زنده می‌ماند.
  • HTTP/1.1 با keep-alive واقعی (سرور داخلی Flask همیشه Connection: close می‌فرستد و هر درخواست یک دست‌دادن
    TLS تازه می‌خواهد؛ روی اینترنت کند این چند صد میلی‌ثانیه برای هر درخواست است).
  • اتصال بیکار بعد از چند ثانیه بسته می‌شود؛ بدنه‌های chunked در درخواست رد می‌شوند (جلوگیری از request smuggling).
"""
import logging
import socket
import socketserver
import ssl
import sys
import threading
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler

from werkzeug.wsgi import FileWrapper

from . import config

log = logging.getLogger('ghab.http')
HANDSHAKE_TIMEOUT = 10   # ثانیه برای تمام‌شدن دست‌دادن TLS
KEEPALIVE_IDLE = 10      # ثانیه انتظار برای درخواست بعدیِ همان اتصال
IO_TIMEOUT = 60          # ثانیه برای هر خواندن/نوشتنِ وسط یک درخواست (کلاینت کند؛ آپلود ویدیو از گوشی گاهی چند ثانیه می‌ایستد)
MAX_DRAIN = 1 << 20      # بدنه ناخوانده‌ی بزرگ‌تر از این: اتصال بسته می‌شود به‌جای خواندن


class _Body:
    """بدنه درخواست با حد و شمارش، تا بعد از اپ بتوانیم باقی‌مانده را خالی کنیم."""

    def __init__(self, rfile, length):
        self.rfile, self.left = rfile, length

    def read(self, n=-1):
        if self.left <= 0:
            return b''
        n = self.left if n is None or n < 0 else min(n, self.left)
        data = self.rfile.read(n)
        self.left -= len(data)
        return data

    def readline(self, n=-1):
        if self.left <= 0:
            return b''
        n = self.left if n is None or n < 0 else min(n, self.left)
        data = self.rfile.readline(n)
        self.left -= len(data)
        return data

    def readlines(self, hint=None):
        out = []
        while True:
            line = self.readline()
            if not line:
                return out
            out.append(line)

    def __iter__(self):
        return iter(self.readline, b'')


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    server_version = 'Ghab'
    sys_version = ''

    def log_message(self, *a):
        pass

    def handle_one_request(self):
        try:
            self.connection.settimeout(KEEPALIVE_IDLE)
            self.raw_requestline = self.rfile.readline(65537)
            if len(self.raw_requestline) > 65536:
                self.requestline = self.request_version = self.command = ''
                self.send_error(HTTPStatus.REQUEST_URI_TOO_LONG)
                return
            if not self.raw_requestline:
                self.close_connection = True
                return
            self.connection.settimeout(IO_TIMEOUT)
            if not self.parse_request():
                return
            self._run()
            self.wfile.flush()
        except (socket.timeout, ssl.SSLError, ConnectionError, OSError):
            self.close_connection = True

    # همه متدها به همان اپ WSGI می‌روند
    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = lambda self: None

    def _error(self, code, msg):
        self.close_connection = True
        self.send_error(code, msg)

    def _environ(self, body, length):
        path, _, query = self.path.partition('?')
        if path.startswith(('http://', 'https://')):
            path = urllib.parse.urlsplit(path).path
        env = {
            'REQUEST_METHOD': self.command,
            'SCRIPT_NAME': '',
            'PATH_INFO': urllib.parse.unquote_to_bytes(path).decode('latin-1'),
            'QUERY_STRING': query,
            'SERVER_NAME': self.server.server_address[0],
            'SERVER_PORT': str(self.server.server_address[1]),
            'SERVER_PROTOCOL': self.request_version,
            'REMOTE_ADDR': self.client_address[0],
            'CONTENT_LENGTH': str(length),
            'wsgi.version': (1, 0),
            'wsgi.url_scheme': 'https' if self.server.tls else 'http',
            'wsgi.input': body,
            'wsgi.errors': sys.stderr,
            'wsgi.multithread': True,
            'wsgi.multiprocess': False,
            'wsgi.run_once': False,
            'wsgi.file_wrapper': FileWrapper,
        }
        if self.headers.get('Content-Type'):
            env['CONTENT_TYPE'] = self.headers['Content-Type']
        for k in self.headers.keys():
            key = k.upper().replace('-', '_')
            if key in ('CONTENT_TYPE', 'CONTENT_LENGTH'):
                continue
            env['HTTP_' + key] = ','.join(self.headers.get_all(k))
        return env

    def _run(self):
        if self.headers.get('Transfer-Encoding'):
            return self._error(HTTPStatus.LENGTH_REQUIRED, 'chunked request bodies are not supported')
        try:
            length = int(self.headers.get('Content-Length') or 0)
            if length < 0:
                raise ValueError
        except ValueError:
            return self._error(HTTPStatus.BAD_REQUEST, 'bad Content-Length')
        body = _Body(self.rfile, length)
        env = self._environ(body, length)
        state = {'sent': False, 'chunked': False, 'head': self.command == 'HEAD', 'resp': None}

        def start_response(status, headers, exc_info=None):
            if exc_info and state['sent']:
                raise exc_info[1].with_traceback(exc_info[2])
            state['resp'] = (status, headers)
            return write

        def send_headers(first=b''):
            status, headers = state['resp']
            code = int(status.split(' ', 1)[0])
            names = {k.lower() for k, _ in headers}
            lines = [f'HTTP/1.1 {status}']
            lines += [f'{k}: {v}' for k, v in headers if k.lower() not in ('connection', 'keep-alive', 'transfer-encoding')]
            if 'content-length' not in names and code not in (204, 304) and code >= 200 and not state['head']:
                if self.request_version == 'HTTP/1.1':
                    state['chunked'] = True
                    lines.append('Transfer-Encoding: chunked')
                else:
                    self.close_connection = True
            if body.left > MAX_DRAIN:
                self.close_connection = True
            lines.append('Connection: close' if self.close_connection else 'Connection: keep-alive')
            lines.append('Date: ' + self.date_time_string())
            lines.append('Server: Ghab')
            state['sent'] = True
            self.wfile.write(('\r\n'.join(lines) + '\r\n\r\n').encode('latin-1') + first)

        def write(data):
            if state['head'] or not data:
                if not state['sent']:
                    send_headers()
                return
            if not state['sent']:
                if state['resp'] is None:
                    raise AssertionError('write() before start_response()')
                names = {k.lower() for k, _ in state['resp'][1]}
                if 'content-length' in names or self.request_version != 'HTTP/1.1':
                    send_headers(data)
                    return
                send_headers()
            if state['chunked']:
                self.wfile.write(b'%x\r\n' % len(data) + data + b'\r\n')
            else:
                self.wfile.write(data)

        result = None
        try:
            result = self.server.app(env, start_response)
            for chunk in result:
                write(chunk)
            if not state['sent']:
                if state['resp'] is None:
                    raise AssertionError('app returned without start_response')
                send_headers()
            if state['chunked']:
                self.wfile.write(b'0\r\n\r\n')
        except (socket.timeout, ssl.SSLError, ConnectionError, OSError):
            self.close_connection = True
            return
        except Exception:
            log.exception('خطای اپ WSGI')
            self.close_connection = True
            if not state['sent']:
                try:
                    self.wfile.write(b'HTTP/1.1 500 Internal Server Error\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
                except OSError:
                    pass
            return
        finally:
            if result is not None and hasattr(result, 'close'):
                try:
                    result.close()
                except Exception:
                    pass
        if body.left > 0:  # بدنه‌ای که اپ نخوانده؛ قبل از درخواست بعدی باید خالی شود
            if body.left > MAX_DRAIN:
                self.close_connection = True
            else:
                try:
                    while body.left > 0 and body.read(65536):
                        pass
                except OSError:
                    self.close_connection = True


class PoolServer(socketserver.TCPServer):
    allow_reuse_address = True
    request_queue_size = 512
    daemon_threads = True

    def __init__(self, addr, app, ctx=None, workers=200):
        self.app, self._ctx, self.tls = app, ctx, ctx is not None
        super().__init__(addr, Handler)
        self._pool = ThreadPoolExecutor(workers, thread_name_prefix='ghab-http')
        self._slots = threading.BoundedSemaphore(workers + 128)

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):  # شلوغی بیش از حد: این اتصال رد می‌شود، سرور زنده می‌ماند
            self.shutdown_request(request)
            return
        self._pool.submit(self._serve, request, client_address)

    def _serve(self, request, client_address):
        try:
            request.settimeout(HANDSHAKE_TIMEOUT)
            if self._ctx is not None:
                request = self._ctx.wrap_socket(request, server_side=True)
            request.settimeout(IO_TIMEOUT)
            self.finish_request(request, client_address)
        except (ssl.SSLError, socket.timeout, ConnectionError, OSError):
            pass
        except Exception:
            log.exception('خطای غیرمنتظره در اتصال')
        finally:
            try:
                self.shutdown_request(request)
            except Exception:
                pass
            self._slots.release()

    def handle_error(self, request, client_address):
        pass


def make_context(crt, key):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(crt, key)
    return ctx


def serve(app, host, port, ctx=None, workers=200):
    PoolServer((host, port), app, ctx, workers).serve_forever()

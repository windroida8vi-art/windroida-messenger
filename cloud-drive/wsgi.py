"""Production entry point: python wsgi.py  (waitress if installed, otherwise Werkzeug's threaded server).

TLS: if CD_SSL_CERT and CD_SSL_KEY point at an existing certificate/key pair (Windroida passes its own
self-signed data/server.crt + data/server.key here when it starts this alongside itself - same cert, same
"Advanced -> Continue" warning the browser already showed once for the messenger), this serves https instead
of plain http. waitress has no built-in TLS, so that case uses Werkzeug's threaded server instead."""
import os
import socket

from app import create_app

app = create_app()


def _ssl_pair():
    crt, key = os.environ.get("CD_SSL_CERT", ""), os.environ.get("CD_SSL_KEY", "")
    if crt and key and os.path.isfile(crt) and os.path.isfile(key):
        return crt, key
    return None


def lan_ips():
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            if not info[4][0].startswith("127."):
                ips.add(info[4][0])
    except OSError:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))  # no packet is sent; only selects the local interface
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    return sorted(ips)


def _tls_server(host, port, crt, key):
    """https server that CANNOT be frozen by a half-open connection.
    Werkzeug's own ssl_context does the TLS handshake in the single accept loop: one client that connects and then says nothing (a browser
    pre-connect, a port scanner, a phone that lost Wi-Fi mid-handshake) blocks every other visitor until the OS gives up - the launcher then
    saw "stopped answering" and killed the whole process. Here the handshake happens in the connection's own thread with a 15 s limit,
    and the number of simultaneous connections is capped, so a flood of silent connections can neither freeze nor exhaust the server."""
    import ssl
    import threading
    from werkzeug.serving import ThreadedWSGIServer

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(crt, key)

    class Srv(ThreadedWSGIServer):
        daemon_threads = True
        request_queue_size = 256

        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self._slots = threading.BoundedSemaphore(int(os.environ.get("CD_MAX_CONN") or 300))

        def process_request(self, request, client_address):
            if not self._slots.acquire(blocking=False):      # too many open connections: refuse this one, stay alive
                self.shutdown_request(request)
                return
            super().process_request(request, client_address)

        def process_request_thread(self, request, client_address):
            try:
                try:
                    request.settimeout(15)                   # handshake limit (also protects against slow-loris on the first bytes)
                    request = ctx.wrap_socket(request, server_side=True)
                    request.settimeout(300)
                except Exception:
                    self.shutdown_request(request)
                    return
                super().process_request_thread(request, client_address)
            finally:
                self._slots.release()

    return Srv(host, port, app)


def _forever(run):
    """Run the server; if it ever raises (a bad request, a socket error, the port still busy after a restart ...) log it and start it
    again in the SAME process after 2 s instead of dying. Only gives up (so the launcher takes over) after 6 failures within a minute."""
    import time, traceback, faulthandler
    try:
        faulthandler.enable()
    except Exception:
        pass
    fails = []
    while True:
        try:
            run()
            return
        except KeyboardInterrupt:
            raise
        except SystemExit:
            raise
        except BaseException:
            t = time.time()
            fails = [x for x in fails if x > t - 60] + [t]
            print("\n  [Cloud Drive] server error, restarting it in 2 s:\n" + traceback.format_exc(), flush=True)
            if len(fails) > 6:
                raise
            time.sleep(2)


if __name__ == "__main__":
    # no per-request console lines (they would also print the one-time SSO token); errors still show
    import logging
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    host, port = app.config["HOST"], app.config["PORT"]
    ssl_pair = _ssl_pair()
    scheme = "https" if ssl_pair else "http"
    print("\n  Cloud Drive is starting on port %d" % port)
    print("  This PC : %s://127.0.0.1:%d" % (scheme, port))
    for ip in lan_ips():
        print("  LAN     : %s://%s:%d" % (scheme, ip, port))
    print()
    if ssl_pair:
        print("  https (certificate shared with Windroida) - using the built-in threaded server (waitress has no TLS)\n")
        # werkzeug prints a generic "development server" notice; here it is a deliberate choice (TLS needs it), so keep the console clean
        import logging
        class _NoDevWarn(logging.Filter):
            def filter(self, rec):
                return "development server" not in rec.getMessage()
        logging.getLogger("werkzeug").addFilter(_NoDevWarn())
        try:
            import flask.cli
            flask.cli.show_server_banner = lambda *a, **k: None
        except Exception:
            pass
        if ssl_pair:
            def _run_tls():
                srv = _tls_server(host, port, ssl_pair[0], ssl_pair[1])
                srv.serve_forever()
            _forever(_run_tls)
        else:
            _forever(lambda: app.run(host=host, port=port, threaded=True, debug=False, use_reloader=False))
    else:
        try:
            from waitress import serve
            _forever(lambda: serve(app, host=host, port=port, threads=48, connection_limit=1000, channel_timeout=300, max_request_body_size=64 * 1024 * 1024,
                  ident="CloudDrive", clear_untrusted_proxy_headers=True))
        except ImportError:
            print("  (waitress not installed - using the built-in threaded server; install requirements.txt for production)\n")
            app.run(host=host, port=port, threaded=True, debug=False, use_reloader=False)

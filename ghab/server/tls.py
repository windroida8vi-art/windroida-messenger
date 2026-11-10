"""آدرس شبکه و گواهی HTTPS.

ارور امنیتی مرورگر («Your connection is not private») چون است که گواهی را هیچ مرجع معتبری امضا نکرده. سه راه:
  1) گواهی واقعی: فایل‌های fullchain.pem و privkey.pem را در data/certs/custom/ بگذار (مثلاً از Let's Encrypt برای دامنه‌ات).
  2) پشت Cloudflare / Cloudflare Tunnel / Caddy با GHAB_PLAIN=1 (خودشان HTTPS معتبر می‌دهند).
  3) پیش‌فرض: یک «مرجع گواهی» (CA) محلی ساخته می‌شود و گواهی سرور را امضا می‌کند. هر دستگاه فقط یک‌بار
     /ca.crt را نصب کند، دیگر هیچ هشداری نمی‌بیند (راهنما در /trust).
"""
import datetime
import ipaddress
import os
import socket
import subprocess

from .config import CERT_DIR

CUSTOM_DIR = os.path.join(CERT_DIR, 'custom')
CA_CERT = os.path.join(CERT_DIR, 'ca.pem')
CA_KEY = os.path.join(CERT_DIR, 'ca.key')


def lan_ip():
    if os.environ.get('HOST_IP'):
        return os.environ['HOST_IP']
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('192.168.1.1', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return '127.0.0.1'


def _san(hosts):
    out = []
    for h in hosts:
        try:
            out.append(('IP', str(ipaddress.ip_address(h))))
        except ValueError:
            out.append(('DNS', h))
    return out


def custom_cert():
    # ویندروید گواهی خودش را به همین سرور هم می‌دهد (GHAB_CERT / GHAB_KEY)
    ec, ek = os.environ.get('GHAB_CERT'), os.environ.get('GHAB_KEY')
    if ec and ek and os.path.exists(ec) and os.path.exists(ek):
        return ec, ek
    crt, key = os.path.join(CUSTOM_DIR, 'fullchain.pem'), os.path.join(CUSTOM_DIR, 'privkey.pem')
    return (crt, key) if os.path.exists(crt) and os.path.exists(key) else None


def _write_key(path, key):
    from cryptography.hazmat.primitives import serialization
    with open(path, 'wb') as f:
        f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                  serialization.NoEncryption()))


def _ensure_ca():
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    if os.path.exists(CA_CERT) and os.path.exists(CA_KEY):
        with open(CA_KEY, 'rb') as f:
            key = serialization.load_pem_private_key(f.read(), None)
        with open(CA_CERT, 'rb') as f:
            return x509.load_pem_x509_certificate(f.read()), key
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Ghab Local CA'),
                      x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'Ghab')])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), True)
            .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True, content_commitment=False,
                                         key_encipherment=False, data_encipherment=False, key_agreement=False,
                                         encipher_only=False, decipher_only=False), True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), False)
            .sign(key, hashes.SHA256()))
    _write_key(CA_KEY, key)
    with open(CA_CERT, 'wb') as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    return cert, key


def _needs_renewal(crt, mark, sig):
    if not (os.path.exists(crt) and os.path.exists(mark)) or open(mark).read() != sig:
        return True
    try:
        from cryptography import x509
        with open(crt, 'rb') as f:
            c = x509.load_pem_x509_certificate(f.read())
        left = c.not_valid_after_utc - datetime.datetime.now(datetime.timezone.utc)
        return left < datetime.timedelta(days=30)
    except Exception:
        return True


def ensure_cert(*extra):
    """(crt, key) برمی‌گرداند. اولویت: گواهی دلخواه → گواهی امضاشده با CA محلی → openssl خودامضا."""
    c = custom_cert()
    if c:
        return c
    hosts = list(dict.fromkeys([h for h in extra if h] + ['127.0.0.1', 'localhost']))
    crt, key, mark = (os.path.join(CERT_DIR, n) for n in ('cert.pem', 'key.pem', 'hosts.txt'))
    sig = ','.join(hosts)
    if not _needs_renewal(crt, mark, sig) and os.path.exists(key):
        return crt, key
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
        ca, ca_key = _ensure_ca()
        k = ec.generate_private_key(ec.SECP256R1())
        now = datetime.datetime.now(datetime.timezone.utc)
        names = [x509.IPAddress(ipaddress.ip_address(v)) if t == 'IP' else x509.DNSName(v) for t, v in _san(hosts)]
        cert = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hosts[0])]))
                .issuer_name(ca.subject).public_key(k.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now - datetime.timedelta(days=1)).not_valid_after(now + datetime.timedelta(days=397))
                .add_extension(x509.SubjectAlternativeName(names), False)
                .add_extension(x509.BasicConstraints(ca=False, path_length=None), True)
                .add_extension(x509.KeyUsage(digital_signature=True, key_encipherment=False, content_commitment=False,
                                             data_encipherment=False, key_agreement=True, key_cert_sign=False, crl_sign=False,
                                             encipher_only=False, decipher_only=False), True)
                .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), False)
                .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), False)
                .add_extension(x509.SubjectKeyIdentifier.from_public_key(k.public_key()), False)
                .sign(ca_key, hashes.SHA256()))
        _write_key(key, k)
        with open(crt, 'wb') as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM) + ca.public_bytes(serialization.Encoding.PEM))
        open(mark, 'w').write(sig)
        return crt, key
    except Exception:
        pass
    try:  # بدون کتابخانه cryptography: گواهی خودامضا با openssl
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', key, '-out', crt,
                        '-days', '397', '-subj', '/CN=' + hosts[0],
                        '-addext', 'subjectAltName=' + ','.join(f'{t}:{v}' for t, v in _san(hosts))],
                       check=True, capture_output=True)
        open(mark, 'w').write(sig)
        return crt, key
    except Exception:
        return None

"""Self-signed certificate for end-to-end TLS through the relay.

The relay pipes bytes and cannot read a TLS stream, so serving HTTPS at the instance gives
end-to-end encryption: the browser/desktop handshakes with the instance, and the relay forwards
ciphertext. The cert is self-signed, so the desktop client pins it with `--tls-ca`; the browser
warns once unless you install the cert.

The SHA-256 fingerprint is what `openpi serve --tls` prints and what a user can compare.
"""

from __future__ import annotations

import datetime
import hashlib
import ipaddress
import os
import socket
import uuid
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

CERT = "server.crt"
KEY = "server.key"


def fingerprint(cert_bytes: bytes) -> str:
    digest = hashlib.sha256(cert_bytes).hexdigest()
    return ":".join(digest[i:i + 2] for i in range(0, len(digest), 2))


def _hosts() -> list[str]:
    names = [socket.gethostname(), socket.gethostname() + ".local"]
    try:
        names.append(socket.gethostbyname(socket.gethostname()))
    except OSError:
        pass
    return list(dict.fromkeys(names))


def ensure_cert(directory: Path) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    cert_path = directory / CERT
    key_path = directory / KEY
    if cert_path.exists() and key_path.exists():
        return cert_path, key_path

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "openpi")])
    hosts = _hosts() + ["127.0.0.1", "::1", "localhost"]
    hosts = list(dict.fromkeys(hosts))
    sans = [x509.DNSName(host) for host in hosts]
    for host in hosts:
        try:
            sans.append(x509.IPAddress(ipaddress.ip_address(host)))
        except ValueError:
            pass
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(int(uuid.uuid4()))
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=3650))
        .add_extension(x509.SubjectAlternativeName(sans), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(key, hashes.SHA256())
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ))
    os.chmod(key_path, 0o600)
    return cert_path, key_path


def server_context(directory: Path) -> tuple[object, Path]:
    cert_path, key_path = ensure_cert(directory)
    import ssl

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
    return context, cert_path

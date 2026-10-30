"""Per-user TLS identity and protocol-v2 pairing proofs.

The desktop displays the public certificate fingerprint and pairing code through
an explicit pairing action. Neither is accepted from the network as trust input.
"""
import base64
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import ipaddress
import json
from pathlib import Path
import re
import secrets
import ssl
import tempfile

from server.config import DEFAULT_CONFIG_DIR, _atomic_write

AUTH_VERSION = b"SPB2"
NONCE_SIZE = 32


def auth_proof(secret, nonce, role):
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", secret) or len(nonce) != NONCE_SIZE:
        raise ValueError("Invalid pairing credentials or challenge")
    if role not in ("client", "server"):
        raise ValueError("Invalid authentication role")
    return AUTH_VERSION + hmac.digest(secret.encode("ascii"),
                                      AUTH_VERSION + role.encode("ascii") + b"\0" + nonce,
                                      "sha256")


@dataclass(frozen=True)
class ServerIdentity:
    certificate: str
    private_key: str = field(repr=False)
    pairing_code: str = field(repr=False)

    @property
    def fingerprint(self):
        return hashlib.sha256(ssl.PEM_cert_to_DER_cert(self.certificate)).hexdigest()

    def server_context(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        # SSLContext requires paths. Temporary key files are owner-only and
        # removed immediately after OpenSSL has loaded them into the context.
        with tempfile.TemporaryDirectory(prefix="spen-tls-") as directory:
            cert, key = Path(directory) / "cert.pem", Path(directory) / "key.pem"
            _atomic_write(cert, self.certificate.encode("ascii"))
            _atomic_write(key, self.private_key.encode("ascii"))
            context.load_cert_chain(cert, key)
        return context

    def client_context(self):
        """Used only by local synthetic tests; Android pins the DER fingerprint."""
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.check_hostname = False
        context.load_verify_locations(cadata=self.certificate)
        return context


def load_identity(directory=None):
    """Create once; never silently replace an invalid identity or trust pin."""
    directory = Path(directory) if directory is not None else DEFAULT_CONFIG_DIR
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / "identity.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("version") != 2:
            raise ValueError("Unsupported pairing identity; restore or explicitly reset pairing")
        identity = ServerIdentity(data["certificate"], data["private_key"], data["pairing_code"])
        auth_proof(identity.pairing_code, b"\0" * NONCE_SIZE, "server")
        identity.server_context()  # Check certificate and private-key consistency.
        return identity
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "S Pen Bridge")])
    now = datetime.now(timezone.utc)
    certificate = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
                   .public_key(key.public_key()).serial_number(x509.random_serial_number())
                   .not_valid_before(now - timedelta(minutes=5))
                   .not_valid_after(now + timedelta(days=3650))
                   .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                   .add_extension(x509.SubjectAlternativeName([
                       x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                       x509.IPAddress(ipaddress.ip_address("::1")),
                   ]), critical=False).sign(key, hashes.SHA256()))
    identity = ServerIdentity(
        certificate.public_bytes(serialization.Encoding.PEM).decode("ascii"),
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                          serialization.NoEncryption()).decode("ascii"),
        base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii"),
    )
    # Exclusive creation handles concurrent GUI/CLI starts without overwriting
    # another process's identity. Readers never see a partially written file.
    import os
    temporary = directory / f".identity-{secrets.token_hex(12)}.json"
    try:
        _atomic_write(temporary, json.dumps(dict(version=2, **identity.__dict__)).encode("utf-8"))
        try:
            os.link(temporary, path)
        except FileExistsError:
            return load_identity(directory)
    finally:
        temporary.unlink(missing_ok=True)
    return identity


def open_paired_connection(host, port, identity, timeout=5):
    """Connect local test tooling using the same TLS/pairing contract as Android."""
    import socket
    from server.protocol import HEADER_SIZE, PKT_HANDSHAKE, pack_packet, unpack_header

    raw = socket.create_connection((host, port), timeout=timeout)
    stream = None
    try:
        stream = identity.client_context().wrap_socket(raw, server_hostname="localhost")
        if not hmac.compare_digest(hashlib.sha256(stream.getpeercert(binary_form=True)).hexdigest(),
                                   identity.fingerprint):
            raise ssl.SSLError("Desktop certificate fingerprint does not match pairing")
        stream.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

        def exact(size):
            result = bytearray()
            while len(result) < size:
                chunk = stream.recv(size - len(result))
                if not chunk:
                    raise ConnectionError("Desktop closed the pairing session")
                result.extend(chunk)
            return bytes(result)

        def handshake_packet():
            parsed = unpack_header(exact(HEADER_SIZE))
            if parsed != (PKT_HANDSHAKE, 0, len(AUTH_VERSION) + NONCE_SIZE):
                raise ValueError("Desktop does not support pairing protocol v2")
            return exact(len(AUTH_VERSION) + NONCE_SIZE)

        challenge = handshake_packet()
        if challenge[:4] != AUTH_VERSION:
            raise ValueError("Desktop pairing version mismatch")
        nonce = challenge[4:]
        stream.sendall(pack_packet(PKT_HANDSHAKE, 0, auth_proof(identity.pairing_code, nonce, "client")))
        if not hmac.compare_digest(handshake_packet(), auth_proof(identity.pairing_code, nonce, "server")):
            raise ValueError("Desktop pairing proof did not match")
        return stream
    except BaseException:
        if stream is not None:
            stream.close()
        raw.close()
        raise

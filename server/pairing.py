"""Bounded, user-approved enrollment and LAN discovery.

Pairing is an explicit, short-lived exception to already-paired authentication.
Commitments fix both ephemeral keys/nonces before either side can adapt its
verification number. The number binds ECDH to the actual desktop certificate.
Credentials leave the desktop only after its user approves the matching number.
"""
import asyncio
from dataclasses import dataclass
import hashlib
import hmac
import json
import secrets
import socket
import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

DISCOVERY_PORT = 40119
PAIRING_MAX_BYTES = 2048
DOMAIN = b"SPEN-PAIR-1\0"


def hex_bytes(value, size=None, maximum=200):
    if not isinstance(value, str) or len(value) % 2 or len(value) > maximum * 2:
        raise ValueError("Invalid pairing field")
    try:
        result = bytes.fromhex(value)
    except ValueError:
        raise ValueError("Invalid pairing field") from None
    if size is not None and len(result) != size:
        raise ValueError("Invalid pairing field length")
    return result


def commitment(role, public_key, nonce):
    if role not in ("client", "server") or len(nonce) != 32:
        raise ValueError("Invalid pairing commitment")
    return hashlib.sha256(DOMAIN + role.encode("ascii") + b"\0" + public_key + nonce).digest()


def public_bytes(key):
    return key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)


def verification_number(shared_secret, fingerprint, client_public, client_nonce, server_public, server_nonce):
    transcript = DOMAIN + hex_bytes(fingerprint, 32) + client_public + client_nonce + server_public + server_nonce
    digest = hmac.digest(shared_secret, transcript, "sha256")
    return f"{int.from_bytes(digest[:4], 'big') % 1_000_000:06d}"


def decode_message(payload):
    if not 1 <= len(payload) <= PAIRING_MAX_BYTES:
        raise ValueError("Pairing message exceeds bounds")
    value = json.loads(payload.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Invalid pairing message")
    return value


def encode_message(value):
    payload = json.dumps(value, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(payload) > PAIRING_MAX_BYTES:
        raise ValueError("Pairing message exceeds bounds")
    return payload


@dataclass(frozen=True)
class PairingRequest:
    token: str
    device_name: str
    address: str
    number: str
    expires_in: float


class PairingManager:
    def __init__(self, identity, port, *, desktop_name=None, lan_address="", on_request=None,
                 on_result=None, window_seconds=120, approval_seconds=60, clock=time.monotonic):
        self.identity, self.port = identity, port
        self.desktop_name = (desktop_name or socket.gethostname())[:80]
        self.lan_address = lan_address
        self.on_request, self.on_result = on_request, on_result
        self.window_seconds, self.approval_seconds, self.clock = window_seconds, approval_seconds, clock
        self.deadline = 0.0
        self.attempts = 0
        self._token = None
        self._decision = None

    @property
    def is_open(self):
        return self.clock() < self.deadline and self.attempts < 5

    def open_window(self):
        self.cancel()
        self.deadline = self.clock() + self.window_seconds
        self.attempts = 0

    def cancel(self):
        self.deadline = 0.0
        if self._decision is not None and not self._decision.done():
            self._decision.set_result(False)
        self._decision = None
        self._token = None

    def decide(self, token, approved):
        if (token == self._token and self._decision is not None and not self._decision.done()
                and self.clock() < self.deadline):
            self._decision.set_result(bool(approved))

    def _notify(self, callback, *values):
        if callback:
            try:
                callback(*values)
            except RuntimeError:
                pass  # A closing Qt receiver must not strand an enrollment.

    async def enroll(self, payload, sequence, address, read, write):
        if not self.is_open or self._token is not None or sequence != 0:
            raise ValueError("Open Pair tablet on the desktop before connecting")
        token = secrets.token_hex(16)
        self._token = token
        self.attempts += 1
        approved = False
        try:
            request = decode_message(payload)
            if request.get("stage") != "request":
                raise ValueError("Invalid pairing request")
            name = request.get("name")
            if not isinstance(name, str) or not 1 <= len(name) <= 80 or any(ord(c) < 32 for c in name):
                raise ValueError("Invalid tablet name")
            client_commit = hex_bytes(request.get("commitment"), 32)
            key = ec.generate_private_key(ec.SECP256R1())
            server_public, server_nonce = public_bytes(key), secrets.token_bytes(32)
            await write(0, encode_message({"stage": "server_commit", "name": self.desktop_name,
                                          "commitment": commitment("server", server_public, server_nonce).hex()}))
            kind, seq, payload = await read(5.0)
            reveal = decode_message(payload)
            from server.protocol import PKT_PAIRING
            if kind != PKT_PAIRING or seq != 1 or reveal.get("stage") != "client_reveal":
                raise ValueError("Invalid pairing reveal")
            client_public = hex_bytes(reveal.get("public_key"), maximum=120)
            client_nonce = hex_bytes(reveal.get("nonce"), 32)
            if not hmac.compare_digest(client_commit, commitment("client", client_public, client_nonce)):
                raise ValueError("Pairing commitment changed")
            peer = serialization.load_der_public_key(client_public)
            if not isinstance(peer, ec.EllipticCurvePublicKey) or not isinstance(peer.curve, ec.SECP256R1):
                raise ValueError("Unsupported pairing key")
            if hmac.compare_digest(client_public, server_public):
                raise ValueError("Reflected pairing key")
            secret = key.exchange(ec.ECDH(), peer)
            number = verification_number(secret, self.identity.fingerprint, client_public, client_nonce,
                                         server_public, server_nonce)
            if token != self._token or self.clock() >= self.deadline:
                raise ValueError("Pairing window expired")
            self._decision = asyncio.get_running_loop().create_future()
            decision = self._decision
            await write(1, encode_message({"stage": "server_reveal", "public_key": server_public.hex(),
                                          "nonce": server_nonce.hex()}))
            timeout = min(self.approval_seconds, self.deadline - self.clock())
            self._notify(self.on_request, PairingRequest(token, name, address, number, timeout))
            disconnected = asyncio.create_task(read(timeout))
            try:
                done, _ = await asyncio.wait((decision, disconnected), timeout=timeout,
                                             return_when=asyncio.FIRST_COMPLETED)
                if disconnected in done:
                    # EOF, invalid data or a new frame all cancel enrollment.
                    disconnected.result()
                    raise ValueError("Unexpected data while awaiting pairing approval")
                if decision not in done:
                    raise asyncio.TimeoutError()
                approved = decision.result()
            finally:
                disconnected.cancel()
                await asyncio.gather(disconnected, return_exceptions=True)
            approved = approved and token == self._token and self.clock() < self.deadline
            response = {"stage": "result", "approved": approved}
            if approved:
                response.update(name=self.desktop_name, fingerprint=self.identity.fingerprint,
                                pairing_code=self.identity.pairing_code, host=self.lan_address, port=self.port)
                self.deadline = 0.0  # One successful enrollment per explicit window.
            await write(2, encode_message(response))
            self._notify(self.on_result, approved, "Tablet paired." if approved else "Pairing was declined.")
        except asyncio.TimeoutError:
            self._notify(self.on_result, False, "Pairing timed out. Find the desktop again.")
            raise
        except (ConnectionError, asyncio.IncompleteReadError):
            self._notify(self.on_result, False, "The tablet cancelled pairing. Find the desktop again.")
            raise
        finally:
            if self._token == token:
                self._token = None
                self._decision = None


class DiscoveryResponder(asyncio.DatagramProtocol):
    def __init__(self, manager):
        self.manager = manager
        self.transport = None
        self._last_reply = {}

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, address):
        if not self.manager.is_open or len(data) > 256:
            return
        now = time.monotonic()
        if now - self._last_reply.get(address[0], -1e9) < .4:
            return
        try:
            request = json.loads(data.decode("utf-8"))
            if (not isinstance(request, dict) or request.get("service") != "spen-bridge"
                    or request.get("version") != 1):
                return
            probe = request.get("probe")
            hex_bytes(probe, 16)
        except (ValueError, TypeError, UnicodeError):
            return
        if len(self._last_reply) >= 128:
            self._last_reply.clear()
        self._last_reply[address[0]] = now
        response = {"service": "spen-bridge", "version": 1, "probe": probe,
                    "name": self.manager.desktop_name, "port": self.manager.port}
        self.transport.sendto(json.dumps(response, separators=(",", ":")).encode("utf-8"), address)

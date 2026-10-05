"""Memory-only launch credentials; no process or provider authority."""
from __future__ import annotations

import re
import hashlib
import hmac
import secrets
import threading


class LocalSessionError(ValueError):
    """Safe local-session failure."""


class LocalSession:
    __slots__ = ("_token", "instance_id", "challenge", "_active", "_lock")

    def __init__(self):
        self._token = secrets.token_hex(32)
        self.instance_id = secrets.token_hex(32)
        self.challenge = secrets.token_hex(32)
        self._active = True
        self._lock = threading.Lock()

    def __repr__(self):
        return "LocalSession(<redacted>)"

    def credential(self):
        with self._lock:
            if not self._active:
                raise LocalSessionError("local session is closed")
            return self._token

    def accepts(self, token):
        with self._lock:
            return bool(self._active and type(token) is str
                        and re.fullmatch(r"[0-9a-f]{64}", token, re.ASCII)
                        and secrets.compare_digest(token, self._token))

    def proof(self, role):
        if role not in {"client", "server"}:
            raise LocalSessionError("invalid local proof role")
        with self._lock:
            if not self._active:
                raise LocalSessionError("local session is closed")
            message = ("ATHENA_LOCAL_HANDSHAKE_V1:" + role + ":" + self.instance_id + ":" + self.challenge).encode("ascii")
            return hmac.new(bytes.fromhex(self._token), message, hashlib.sha256).hexdigest()

    def accepts_handshake(self, proof):
        if type(proof) is not str or not re.fullmatch(r"[0-9a-f]{64}", proof, re.ASCII):
            return False
        try:
            return secrets.compare_digest(proof, self.proof("client"))
        except LocalSessionError:
            return False

    def invalidate(self):
        with self._lock:
            self._active = False
            self._token = ""

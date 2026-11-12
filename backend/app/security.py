"""Пароли (scrypt) и подписанные токены (HMAC-SHA256), только stdlib."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import uuid

from app.config import get_settings


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, dk_hex = stored.split("$")
    except ValueError:
        return False
    dk = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1)
    return hmac.compare_digest(dk.hex(), dk_hex)


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def issue_token(user_id: uuid.UUID) -> str:
    s = get_settings()
    body = _b64(json.dumps({"sub": str(user_id), "exp": int(time.time()) + s.token_ttl_seconds}).encode())
    sig = _b64(hmac.new(s.secret_key.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def read_token(token: str) -> uuid.UUID | None:
    try:
        body, sig = token.split(".")
    except ValueError:
        return None
    expected = _b64(hmac.new(get_settings().secret_key.encode(), body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        return None
    data = json.loads(_unb64(body))
    if data["exp"] < time.time():
        return None
    return uuid.UUID(data["sub"])

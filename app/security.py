from __future__ import annotations
import base64
import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from jose import JWTError, jwt
from passlib.context import CryptContext

from .config import settings

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
ALGORITHM = "HS256"


def hash_password(value: str) -> str:
    return pwd_context.hash(value)


def verify_password(value: str, hashed: str) -> bool:
    return pwd_context.verify(value, hashed)


def create_owner_token(owner_id: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode({"sub": owner_id, "exp": exp}, settings.jwt_secret, algorithm=ALGORITHM)


def create_panel_token(subject: str, kind: str = "owner", extra: dict | None = None) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": subject, "kind": kind, "exp": exp}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)

def decode_panel_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except JWTError:
        return None

def decode_owner_token(token: str) -> str | None:
    payload = decode_panel_token(token)
    return payload.get("sub") if payload and payload.get("kind", "owner") == "owner" else None


def generate_app_credentials() -> tuple[str, str]:
    return "app_" + secrets.token_urlsafe(12), secrets.token_urlsafe(32)


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def verify_secret(secret: str, digest: str) -> bool:
    return secrets.compare_digest(hash_secret(secret), digest)


def generate_signing_keys() -> tuple[str, str]:
    private = Ed25519PrivateKey.generate()
    public = private.public_key()
    private_b64 = base64.b64encode(
        private.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )
    ).decode()
    public_b64 = base64.b64encode(
        public.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    ).decode()
    return private_b64, public_b64


def canonical_json(data: dict) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sign_payload(private_b64: str, payload: dict) -> str:
    key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(private_b64))
    return base64.b64encode(key.sign(canonical_json(payload))).decode()


def verify_signature(public_b64: str, payload: dict, signature_b64: str) -> bool:
    try:
        key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_b64))
        key.verify(base64.b64decode(signature_b64), canonical_json(payload))
        return True
    except Exception:
        return False

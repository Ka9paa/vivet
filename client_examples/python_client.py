"""Minimal Vivet client example with Ed25519 response verification."""
import base64
import json
import platform
import uuid

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

BASE_URL = "http://127.0.0.1:8000"
APP_ID = "PASTE_APP_ID"
APP_SECRET = "PASTE_APP_SECRET"
LICENSE_KEY = "PASTE_LICENSE_KEY"


def canonical_json(data: dict) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def verify(public_key_b64: str, payload: dict, signature_b64: str) -> None:
    key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64))
    key.verify(base64.b64decode(signature_b64), canonical_json(payload))


def hwid() -> str:
    return f"{platform.node()}-{uuid.getnode()}"


with httpx.Client(timeout=10) as client:
    init = client.post(f"{BASE_URL}/api/v1/init", json={"app_id": APP_ID, "app_secret": APP_SECRET})
    init.raise_for_status()
    init_body = init.json()
    public_key = init_body["payload"]["public_key"]
    verify(public_key, init_body["payload"], init_body["signature"])

    auth = client.post(
        f"{BASE_URL}/api/v1/license/auth",
        json={
            "app_id": APP_ID,
            "session_id": init_body["payload"]["session_id"],
            "license_key": LICENSE_KEY,
            "hwid": hwid(),
        },
    )
    body = auth.json()
    verify(public_key, body["payload"], body["signature"])
    print(body["payload"])

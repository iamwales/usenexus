"""
Encryption helpers for OAuth credential storage.

Strategy:
- Data encryption key (DEK) generated per-tenant using AES-256-GCM.
- DEK itself is encrypted by AWS KMS (envelope encryption).
- Encrypted DEK stored alongside the ciphertext.

In local/test environments, a static dev key is used when KMS is unavailable.
"""

from __future__ import annotations

import base64
import json
import os
from typing import Protocol

import boto3
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_DEV_KEY = b"\x00" * 32  # Only used in non-production environments


class KeyProvider(Protocol):
    def generate_data_key(self, key_id: str) -> tuple[bytes, bytes]:
        """Returns (plaintext_key, encrypted_key_blob)."""
        ...

    def decrypt_data_key(self, key_id: str, encrypted_key_blob: bytes) -> bytes:
        """Returns plaintext key."""
        ...


class KMSKeyProvider:
    def __init__(self, region: str = "us-east-1") -> None:
        self._client = boto3.client("kms", region_name=region)

    def generate_data_key(self, key_id: str) -> tuple[bytes, bytes]:
        resp = self._client.generate_data_key(KeyId=key_id, KeySpec="AES_256")
        return resp["Plaintext"], resp["CiphertextBlob"]

    def decrypt_data_key(self, key_id: str, encrypted_key_blob: bytes) -> bytes:
        resp = self._client.decrypt(CiphertextBlob=encrypted_key_blob, KeyId=key_id)
        return resp["Plaintext"]


class DevKeyProvider:
    """Used in local development — no KMS required."""

    def generate_data_key(self, key_id: str) -> tuple[bytes, bytes]:
        return _DEV_KEY, b"dev-encrypted-key"

    def decrypt_data_key(self, key_id: str, encrypted_key_blob: bytes) -> bytes:
        return _DEV_KEY


def _get_key_provider() -> KeyProvider:
    if os.getenv("ENVIRONMENT", "development") == "production":
        return KMSKeyProvider(region=os.getenv("AWS_REGION", "us-east-1"))
    return DevKeyProvider()


def encrypt_token(plaintext: str, kms_key_id: str) -> bytes:
    """
    Encrypt a token string. Returns a self-contained blob:
        JSON { nonce, ciphertext, encrypted_dek }  →  base64
    """
    provider = _get_key_provider()
    dek_plaintext, dek_encrypted = provider.generate_data_key(kms_key_id)

    aesgcm = AESGCM(dek_plaintext)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)

    blob = {
        "nonce": base64.b64encode(nonce).decode(),
        "ciphertext": base64.b64encode(ciphertext).decode(),
        "encrypted_dek": base64.b64encode(dek_encrypted).decode(),
    }
    return base64.b64encode(json.dumps(blob).encode())


def decrypt_token(encrypted_blob: bytes, kms_key_id: str) -> str:
    """Inverse of encrypt_token."""
    provider = _get_key_provider()
    blob = json.loads(base64.b64decode(encrypted_blob))

    nonce = base64.b64decode(blob["nonce"])
    ciphertext = base64.b64decode(blob["ciphertext"])
    dek_encrypted = base64.b64decode(blob["encrypted_dek"])

    dek_plaintext = provider.decrypt_data_key(kms_key_id, dek_encrypted)
    aesgcm = AESGCM(dek_plaintext)
    return aesgcm.decrypt(nonce, ciphertext, None).decode()

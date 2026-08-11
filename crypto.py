"""
AES-256-GCM encryption, one key per file (envelope-style).

pip install cryptography
"""

import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def generate_file_key() -> bytes:
    """32-byte random key, one per uploaded file."""
    return AESGCM.generate_key(bit_length=256)


def encrypt(data: bytes, key: bytes) -> bytes:
    """Returns nonce(12 bytes) + ciphertext(includes 16-byte auth tag)."""
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, data, associated_data=None)
    return nonce + ciphertext


def decrypt(blob: bytes, key: bytes) -> bytes:
    nonce, ciphertext = blob[:12], blob[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, associated_data=None)
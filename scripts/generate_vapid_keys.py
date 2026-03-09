#!/usr/bin/env python
"""
Generate VAPID keys for Web Push notifications.

Usage:
    python scripts/generate_vapid_keys.py

Outputs the keys in .env format. Copy them into your .env file.
Requires: pip install pywebpush
"""

import base64
import sys

try:
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import (
        Encoding, NoEncryption, PrivateFormat, PublicFormat
    )
except ImportError:
    print("ERROR: cryptography package not found.")
    print("Install it with: pip install cryptography")
    sys.exit(1)

# Generate EC key pair (P-256, required for VAPID)
private_key = ec.generate_private_key(ec.SECP256R1())
public_key = private_key.public_key()

# Encode private key as base64url DER (PKCS8)
private_bytes = private_key.private_bytes(
    encoding=Encoding.DER,
    format=PrivateFormat.PKCS8,
    encryption_algorithm=NoEncryption(),
)
private_b64 = base64.urlsafe_b64encode(private_bytes).decode().rstrip("=")

# Encode public key as base64url uncompressed point (65 bytes: 04 || x || y)
# This is the format required by the browser's PushManager.subscribe()
public_bytes = public_key.public_bytes(
    encoding=Encoding.X962,
    format=PublicFormat.UncompressedPoint,
)
public_b64 = base64.urlsafe_b64encode(public_bytes).decode().rstrip("=")

print("# Add these lines to your .env file:")
print(f"VAPID_PRIVATE_KEY={private_b64}")
print(f"VAPID_PUBLIC_KEY={public_b64}")
print(f"VAPID_SUBJECT=mailto:dev@localhost")
print()
print("# Frontend application server key (same as VAPID_PUBLIC_KEY):")
print(f"# VITE_VAPID_PUBLIC_KEY={public_b64}")

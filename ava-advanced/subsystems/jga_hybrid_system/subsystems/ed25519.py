"""Pure-Python Ed25519 (RFC 8032), stdlib only.

Why pure Python here: the gatekeeper is meant to stay zero-dependency
on John's machine, and Python's stdlib has no Ed25519. This module is
a straightforward implementation of the RFC 8032 formulas in affine
coordinates -- chosen for auditability over speed (a scalar
multiplication does modular inverses per addition, so it is slower
than an extended-coordinate implementation, but far easier to check
against the curve equation). It is NOT a hardened, constant-time
production implementation, and it must not be presented as one.
Side-channel resistance, key management, and audited crypto still
need the `cryptography` library (or equivalent) before any
production use. For this prototype, correctness is proven by the
RFC 8032 test vectors in tests/test_ed25519.py.

API:
  generate_keypair() -> (secret_key_32, public_key_32)
  publickey(secret_key_32) -> public_key_32
  sign(secret_key_32, message) -> signature_64
  verify(public_key_32, message, signature_64) -> bool
"""
from __future__ import annotations

import hashlib
import os

# Field prime, group order, curve parameter d (RFC 8032 / RFC 7748).
q = 2 ** 255 - 19
L = 2 ** 252 + 27742317777372353535851937790883648493
d = (-121665 * pow(121666, q - 2, q)) % q
I = pow(2, (q - 1) // 4, q)


def _xrecover(y: int) -> int:
    xx = (y * y - 1) * pow(d * y * y + 1, q - 2, q) % q
    x = pow(xx, (q + 3) // 8, q)
    if (x * x - xx) % q != 0:
        x = (x * I) % q
    if x % 2 != 0:
        x = q - x
    return x


# Base point (affine). Bx is computed from By via _xrecover, not
# transcribed, so a digit typo in the base x cannot silently break
# the whole curve.
By = 46316835694926478169428394003475163141307993866256225615783033603165251855960
Bx = _xrecover(By)
B = (Bx, By)
IDENTITY = (0, 1)


def _edwards(P, Q):
    """Twisted Edwards addition, a = -1:
    x3 = (x1*y2 + x2*y1) / (1 + d*x1*x2*y1*y2)
    y3 = (y1*y2 + x1*x2) / (1 - d*x1*x2*y1*y2)   (since -a = +1)
    """
    if P == IDENTITY:
        return Q
    if Q == IDENTITY:
        return P
    x1, y1 = P
    x2, y2 = Q
    den_x = (1 + d * x1 * x2 * y1 * y2) % q
    den_y = (1 - d * x1 * x2 * y1 * y2) % q
    x3 = (x1 * y2 + x2 * y1) * pow(den_x, q - 2, q) % q
    y3 = (y1 * y2 + x1 * x2) * pow(den_y, q - 2, q) % q
    return (x3, y3)


def _scalarmult(P, e: int):
    result = IDENTITY
    # Double-and-add from the most significant bit down.
    for bit in bin(e)[2:]:
        result = _edwards(result, result)
        if bit == "1":
            result = _edwards(result, P)
    return result


def _encodeint(y: int) -> bytes:
    return y.to_bytes(32, "little")


def _encodepoint(P) -> bytes:
    x, y = P
    bits = (y & ((1 << 255) - 1)) | ((x & 1) << 255)
    return bits.to_bytes(32, "little")


def _decodeint(b: bytes) -> int:
    return int.from_bytes(b, "little")


def _decodepoint(b: bytes) -> tuple | None:
    if len(b) != 32:
        return None
    y = _decodeint(b) & ((1 << 255) - 1)
    sign = (_decodeint(b) >> 255) & 1
    if y >= q:
        return None
    x = _xrecover(y)
    if (x & 1) != sign:
        x = q - x
    return (x, y)


def _clamp(h: bytes) -> int:
    a = bytearray(h[:32])
    a[0] &= 248
    a[31] &= 127
    a[31] |= 64
    return int.from_bytes(a, "little")


def publickey(secret_key: bytes) -> bytes:
    if len(secret_key) != 32:
        raise ValueError("secret key must be 32 bytes")
    h = hashlib.sha512(secret_key).digest()
    a = _clamp(h)
    return _encodepoint(_scalarmult(B, a))


def generate_keypair() -> tuple[bytes, bytes]:
    sk = os.urandom(32)
    return sk, publickey(sk)


def sign(secret_key: bytes, message: bytes) -> bytes:
    h = hashlib.sha512(secret_key).digest()
    a = _clamp(h)
    prefix = h[32:]
    r = int.from_bytes(
        hashlib.sha512(prefix + message).digest(), "little") % L
    R = _scalarmult(B, r)
    R_enc = _encodepoint(R)
    A_enc = publickey(secret_key)
    k = int.from_bytes(
        hashlib.sha512(R_enc + A_enc + message).digest(), "little") % L
    S = (r + k * a) % L
    return R_enc + _encodeint(S)


def verify(public_key: bytes, message: bytes, signature: bytes) -> bool:
    if len(public_key) != 32 or len(signature) != 64:
        return False
    R_enc, S_enc = signature[:32], signature[32:]
    S = _decodeint(S_enc)
    if S >= L:
        return False
    A = _decodepoint(public_key)
    R = _decodepoint(R_enc)
    if A is None or R is None:
        return False
    k = int.from_bytes(
        hashlib.sha512(R_enc + public_key + message).digest(), "little") % L
    # Check S*B == R + k*A
    left = _scalarmult(B, S)
    right = _edwards(R, _scalarmult(A, k))
    return left == right

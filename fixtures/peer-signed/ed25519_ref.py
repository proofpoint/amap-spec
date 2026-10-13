"""Ed25519 (RFC 8032 §5.1), pure Python, for the fixture gate only.

This exists so that `fixtures/validate.py` can check the signed peer-statement
cases with the standard library alone, like the rest of the gate. It is a
transcription of the RFC 8032 §6 reference code. It is slow, and it is NOT
constant-time: never sign with a real key using it. The only keys it is ever
given are the published RFC 8032 §7.1 test keys in `rfc8032-vectors.json`.

Verification policy (peer-origin §5.7): the cofactorless check
[S]B == R + [k]A; S < L; canonical encodings of A and R (y < p, and no
"negative zero" x). A configured public key must also pass `load_public_key`:
canonical, on the curve, and not of small order. RFC 8032 §5.1.7 permits the
cofactored equation too; the two agree on everything an honest signer
produces, and the negative vectors exercise only rules this policy fixes.
"""
from __future__ import annotations

import hashlib

p = 2**255 - 19
L = 2**252 + 27742317777372353535851937790883648493
d = -121665 * pow(121666, p - 2, p) % p
SQRT_M1 = pow(2, (p - 1) // 4, p)


def _sha512_int(b: bytes) -> int:
    return int.from_bytes(hashlib.sha512(b).digest(), "little")


def _add(P, Q):
    A = (P[1] - P[0]) * (Q[1] - Q[0]) % p
    B = (P[1] + P[0]) * (Q[1] + Q[0]) % p
    C = 2 * P[3] * Q[3] * d % p
    D = 2 * P[2] * Q[2] % p
    E, F, G, H = B - A, D - C, D + C, B + A
    return (E * F % p, G * H % p, F * G % p, E * H % p)


def _mul(s: int, P):
    Q = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            Q = _add(Q, P)
        P = _add(P, P)
        s >>= 1
    return Q


def _equal(P, Q) -> bool:
    return (P[0] * Q[2] - Q[0] * P[2]) % p == 0 and (P[1] * Q[2] - Q[1] * P[2]) % p == 0


def _recover_x(y: int, sign: int):
    if y >= p:
        return None
    x2 = (y * y - 1) * pow(d * y * y + 1, p - 2, p)
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (p + 3) // 8, p)
    if (x * x - x2) % p != 0:
        x = x * SQRT_M1 % p
    if (x * x - x2) % p != 0:
        return None
    if (x & 1) != sign:
        x = p - x
    return x


_gy = 4 * pow(5, p - 2, p) % p
_gx = _recover_x(_gy, 0)
G = (_gx, _gy, 1, _gx * _gy % p)


def _compress(P) -> bytes:
    zinv = pow(P[2], p - 2, p)
    x, y = P[0] * zinv % p, P[1] * zinv % p
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _decompress(s: bytes):
    if len(s) != 32:
        return None
    y = int.from_bytes(s, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    if x is None:
        return None
    return (x, y, 1, x * y % p)


def _expand(secret: bytes):
    if len(secret) != 32:
        raise ValueError("Ed25519 secret key must be 32 bytes")
    h = hashlib.sha512(secret).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def public_key(secret: bytes) -> bytes:
    a, _ = _expand(secret)
    return _compress(_mul(a, G))


def sign(secret: bytes, msg: bytes) -> bytes:
    a, prefix = _expand(secret)
    A = _compress(_mul(a, G))
    r = _sha512_int(prefix + msg) % L
    R = _compress(_mul(r, G))
    k = _sha512_int(R + A + msg) % L
    s = (r + k * a) % L
    return R + int.to_bytes(s, 32, "little")


def verify(public: bytes, msg: bytes, signature: bytes) -> bool:
    if len(public) != 32 or len(signature) != 64:
        return False
    A = _decompress(public)
    if A is None:
        return False
    Rs = signature[:32]
    R = _decompress(Rs)
    if R is None:
        return False
    s = int.from_bytes(signature[32:], "little")
    if s >= L:
        return False
    k = _sha512_int(Rs + public + msg) % L
    return _equal(_mul(s, G), _add(R, _mul(k, A)))


IDENTITY = (0, 1, 1, 0)


def load_public_key(public: bytes) -> bytes:
    """Configuration-time check for a peer key: 32 bytes, a canonical
    encoding of a curve point, and not of small order ([8]A != identity).
    Raises ValueError; a receiver refuses to load a configuration that fails."""
    A = _decompress(public)
    if A is None:
        raise ValueError("not a canonical encoding of a curve point")
    if _equal(_mul(8, A), IDENTITY):
        raise ValueError("small-order public key")
    return public

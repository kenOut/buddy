"""Password hashing for per-user Manager Portal accounts (AdminUser) —
a different concern from admin_auth.py's session tokens: this module
turns a plaintext password into something safe to store at rest;
admin_auth.py signs/verifies the session cookie issued after a
successful login. Neither depends on the other.

Standard library only (`hashlib.pbkdf2_hmac`) — no new dependency for
one password-hashing need, same reasoning as P3.1's SMTP provider.
PBKDF2-HMAC-SHA256 with a random 16-byte salt per password and 600,000
iterations (OWASP's 2023 minimum recommendation for PBKDF2-SHA256).

Stored format: `pbkdf2_sha256${iterations}${salt_hex}${hash_hex}` — the
iteration count travels with the hash so a future increase never
invalidates already-stored passwords (each is verified with the count
it was created with).
"""

import hashlib
import hmac
import secrets

_ALGORITHM = "pbkdf2_sha256"
_ITERATIONS = 600_000
_SALT_BYTES = 16


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return f"{_ALGORITHM}${_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Never raises on a malformed `stored` value — returns False
    instead, the same "can't verify, so reject" reasoning
    verify_admin_session_token and verify_employee_session_token both
    already use for a malformed token."""
    try:
        algorithm, iterations_str, salt_hex, digest_hex = stored.split("$", 3)
        if algorithm != _ALGORITHM:
            return False
        iterations = int(iterations_str)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (ValueError, TypeError):
        return False

    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return hmac.compare_digest(actual, expected)

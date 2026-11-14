"""Memory-hard password hashing using the Python standard-library scrypt KDF."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os

from app.core.exceptions import ApplicationError


class PasswordHasher:
    """Hash passwords with scrypt; encoded hashes carry their KDF parameters."""

    _N = 1 << 15
    _R = 8
    _P = 1
    _DKLEN = 32
    _MAXMEM = 64 * 1024 * 1024

    @staticmethod
    def validate_password(password: str) -> None:
        if not isinstance(password, str) or len(password) < 12:
            raise ApplicationError("AUTH_PASSWORD_POLICY", "Password must contain at least 12 characters.")
        if len(password) > 128 or "\x00" in password:
            raise ApplicationError("AUTH_PASSWORD_POLICY", "Password exceeds the allowed length or contains invalid characters.")

    def hash(self, password: str) -> str:
        self.validate_password(password)
        salt = os.urandom(16)
        digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=self._N,
                                r=self._R, p=self._P, dklen=self._DKLEN, maxmem=self._MAXMEM)
        return "$scrypt${}${}${}${}${}".format(
            self._N, self._R, self._P,
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        )

    def verify(self, password: str, encoded: str) -> bool:
        if not isinstance(password, str) or not isinstance(encoded, str):
            return False
        try:
            marker, algorithm, n_text, r_text, p_text, salt_text, digest_text = encoded.split("$")
            if marker or algorithm != "scrypt":
                return False
            n, r, p = int(n_text), int(r_text), int(p_text)
            if n < 1 << 14 or n > 1 << 18 or n & (n - 1) or not 1 <= r <= 16 or not 1 <= p <= 4:
                return False
            salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
            expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
            if len(salt) != 16 or len(expected) != self._DKLEN:
                return False
            actual = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p,
                                    dklen=len(expected), maxmem=self._MAXMEM)
            return hmac.compare_digest(actual, expected)
        except (ValueError, TypeError, UnicodeError, MemoryError):
            return False

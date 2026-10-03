from __future__ import annotations

import hashlib
import secrets
import time
from collections import defaultdict, deque
from typing import Protocol

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_password_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)
_dummy_password_hash = _password_hasher.hash("not-a-real-user-password")


def normalize_email(email: str) -> str:
    return email.strip().casefold()


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    candidate_hash = password_hash or _dummy_password_hash
    try:
        valid = _password_hasher.verify(candidate_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    return bool(valid and password_hash is not None)


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class LoginRateLimiter(Protocol):
    def is_allowed(self, key: str) -> bool: ...

    def record_failure(self, key: str) -> None: ...

    def reset(self, key: str) -> None: ...


class InMemoryLoginRateLimiter:
    """Single-process development guard; use shared infrastructure in production."""

    def __init__(self, attempts: int, window_seconds: int) -> None:
        self._attempts = attempts
        self._window_seconds = window_seconds
        self._failures: dict[str, deque[float]] = defaultdict(deque)

    def _active_failures(self, key: str) -> deque[float]:
        failures = self._failures[key]
        cutoff = time.monotonic() - self._window_seconds
        while failures and failures[0] <= cutoff:
            failures.popleft()
        return failures

    def is_allowed(self, key: str) -> bool:
        return len(self._active_failures(key)) < self._attempts

    def record_failure(self, key: str) -> None:
        self._active_failures(key).append(time.monotonic())

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)

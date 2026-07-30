"""Configuration for the loopback browser application."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from pathlib import Path


def _new_session_secret() -> str:
    return secrets.token_urlsafe(32)


@dataclass(frozen=True, slots=True)
class WebSettings:
    """Explicit browser configuration kept outside the SQLite database."""

    database_path: Path
    session_secret: str = field(default_factory=_new_session_secret)
    allowed_hosts: tuple[str, ...] = ("localhost", "127.0.0.1")
    secure_cookies: bool = False
    session_ttl_seconds: int = 8 * 60 * 60
    session_cookie_name: str = "agentboard_session"

    def __post_init__(self) -> None:
        object.__setattr__(self, "database_path", Path(self.database_path))
        if (
            not isinstance(self.session_secret, str)
            or len(self.session_secret.encode("utf-8")) < 32
        ):
            raise ValueError("session secret must be at least 32 bytes")
        if not self.allowed_hosts or any(not host for host in self.allowed_hosts):
            raise ValueError("allowed hosts must not be empty")
        if self.session_ttl_seconds <= 0:
            raise ValueError("session TTL must be positive")
        if not self.session_cookie_name:
            raise ValueError("session cookie name must not be empty")

"""Configuration for the owner-only browser application."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class WebSettings:
    """Explicit browser configuration kept outside the SQLite database."""

    database_path: Path
    owner_password_hash: str
    session_secret: str
    allowed_hosts: tuple[str, ...] = ("localhost", "127.0.0.1")
    secure_cookies: bool = False
    session_ttl_seconds: int = 8 * 60 * 60
    session_cookie_name: str = "agentboard_session"

    def __post_init__(self) -> None:
        object.__setattr__(self, "database_path", Path(self.database_path))
        if not self.owner_password_hash:
            raise ValueError("owner password hash must not be empty")
        if len(self.session_secret.encode("utf-8")) < 32:
            raise ValueError("session secret must be at least 32 bytes")
        if not self.allowed_hosts or any(not host for host in self.allowed_hosts):
            raise ValueError("allowed hosts must not be empty")
        if self.session_ttl_seconds <= 0:
            raise ValueError("session TTL must be positive")
        if not self.session_cookie_name:
            raise ValueError("session cookie name must not be empty")

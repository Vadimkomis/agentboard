"""Public browser application API."""

from agentboard.web.app import create_app
from agentboard.web.settings import WebSettings

__all__ = ["WebSettings", "create_app"]

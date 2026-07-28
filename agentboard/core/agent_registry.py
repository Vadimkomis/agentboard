"""Load agent definitions from YAML files.

Looks in (in order):
1. Config-specified path (user override / ai-playbook)
2. Bundled defaults: agentboard/agents/defaults/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from typing import Any

yaml: Any = import_module("yaml")


@dataclass
class AgentDefinition:
    name: str
    description: str
    preferred_provider: str = "claude"
    model: str = "claude-sonnet-4-6"
    tools: list[str] = field(default_factory=list)
    system_prompt: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentDefinition:
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            preferred_provider=data.get("preferred_provider", "claude"),
            model=data.get("model", "claude-sonnet-4-6"),
            tools=data.get("tools", []),
            system_prompt=data.get("system_prompt", ""),
        )


_DEFAULTS_DIR = Path(__file__).parent.parent / "agents" / "defaults"


def load_agent_registry(override_path: Path | None = None) -> dict[str, AgentDefinition]:
    """Load all agent YAML definitions, returning a name→AgentDefinition map."""
    registry: dict[str, AgentDefinition] = {}

    # Load bundled defaults first
    _load_from_dir(_DEFAULTS_DIR, registry)

    # Override with user-specified path (ai-playbook or custom)
    if override_path and override_path.is_dir():
        _load_from_dir(override_path, registry)

    return registry


def _load_from_dir(directory: Path, registry: dict[str, AgentDefinition]) -> None:
    for yaml_file in sorted(directory.glob("*.yml")):
        try:
            with open(yaml_file) as f:
                data = yaml.safe_load(f)
            if not data or "name" not in data:
                continue
            agent = AgentDefinition.from_dict(data)
            registry[agent.name] = agent
        except Exception:
            # Skip malformed files
            pass


def get_agent(name: str, override_path: Path | None = None) -> AgentDefinition | None:
    registry = load_agent_registry(override_path)
    return registry.get(name)

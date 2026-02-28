"""Tests for agentboard.core.agent_registry — AgentDefinition and load_agent_registry()."""

from __future__ import annotations

import pytest
import yaml

from agentboard.core.agent_registry import AgentDefinition, load_agent_registry

# ===================================================================
# AgentDefinition.from_dict()
# ===================================================================


class TestAgentDefinitionFromDict:
    def test_minimal_required_fields(self):
        data = {"name": "backend", "description": "API work"}
        agent = AgentDefinition.from_dict(data)
        assert agent.name == "backend"
        assert agent.description == "API work"
        # Defaults
        assert agent.preferred_provider == "claude"
        assert agent.model == "claude-sonnet-4-6"
        assert agent.tools == []
        assert agent.system_prompt == ""

    def test_all_fields_provided(self):
        data = {
            "name": "frontend",
            "description": "UI work",
            "preferred_provider": "codex",
            "model": "gpt-4o",
            "tools": ["read_file", "write_file", "bash"],
            "system_prompt": "You are a frontend engineer.",
        }
        agent = AgentDefinition.from_dict(data)
        assert agent.name == "frontend"
        assert agent.description == "UI work"
        assert agent.preferred_provider == "codex"
        assert agent.model == "gpt-4o"
        assert agent.tools == ["read_file", "write_file", "bash"]
        assert agent.system_prompt == "You are a frontend engineer."

    def test_missing_name_raises_key_error(self):
        data = {"description": "No name here"}
        with pytest.raises(KeyError):
            AgentDefinition.from_dict(data)

    def test_missing_description_defaults_to_empty(self):
        data = {"name": "qa"}
        agent = AgentDefinition.from_dict(data)
        assert agent.description == ""

    def test_extra_keys_ignored(self):
        data = {
            "name": "devops",
            "description": "Infra",
            "extra_field": "should not cause error",
        }
        agent = AgentDefinition.from_dict(data)
        assert agent.name == "devops"
        assert not hasattr(agent, "extra_field")

    def test_empty_tools_list(self):
        data = {"name": "docs", "description": "Docs", "tools": []}
        agent = AgentDefinition.from_dict(data)
        assert agent.tools == []

    def test_tools_with_multiple_entries(self):
        data = {
            "name": "backend",
            "description": "API",
            "tools": ["read_file", "write_file", "bash", "github"],
        }
        agent = AgentDefinition.from_dict(data)
        assert len(agent.tools) == 4
        assert "github" in agent.tools


# ===================================================================
# AgentDefinition dataclass
# ===================================================================


class TestAgentDefinitionDataclass:
    def test_default_construction(self):
        agent = AgentDefinition(name="test", description="Test agent")
        assert agent.preferred_provider == "claude"
        assert agent.model == "claude-sonnet-4-6"
        assert agent.tools == []
        assert agent.system_prompt == ""

    def test_equality(self):
        a = AgentDefinition(name="qa", description="QA")
        b = AgentDefinition(name="qa", description="QA")
        assert a == b

    def test_inequality_different_name(self):
        a = AgentDefinition(name="qa", description="QA")
        b = AgentDefinition(name="backend", description="QA")
        assert a != b


# ===================================================================
# load_agent_registry() — with actual bundled YAML defaults
# ===================================================================


EXPECTED_BUNDLED_AGENTS = {
    "backend",
    "frontend",
    "mobile",
    "devops",
    "qa",
    "fullstack",
    "docs",
    "growth",
    "marketing",
}


class TestLoadAgentRegistryBundled:
    def test_loads_all_bundled_agents(self):
        registry = load_agent_registry()
        assert set(registry.keys()) == EXPECTED_BUNDLED_AGENTS

    def test_all_agents_have_name_and_description(self):
        registry = load_agent_registry()
        for name, agent in registry.items():
            assert agent.name == name
            assert agent.description, f"Agent {name} has empty description"

    def test_backend_agent_details(self):
        registry = load_agent_registry()
        backend = registry["backend"]
        assert backend.name == "backend"
        assert backend.preferred_provider == "claude"
        assert "backend" in backend.description.lower() or "api" in backend.description.lower()
        assert len(backend.tools) > 0
        assert backend.system_prompt != ""

    def test_frontend_agent_details(self):
        registry = load_agent_registry()
        frontend = registry["frontend"]
        assert frontend.name == "frontend"
        assert frontend.preferred_provider == "claude"
        assert len(frontend.tools) > 0

    def test_growth_agent_details(self):
        registry = load_agent_registry()
        growth = registry["growth"]
        assert growth.name == "growth"
        assert "growth" in growth.description.lower() or "gtm" in growth.description.lower()

    def test_marketing_agent_details(self):
        registry = load_agent_registry()
        marketing = registry["marketing"]
        assert marketing.name == "marketing"
        desc = marketing.description.lower()
        assert "launch" in desc or "marketing" in desc

    def test_all_agents_have_system_prompts(self):
        registry = load_agent_registry()
        for name, agent in registry.items():
            assert agent.system_prompt, f"Agent {name} has empty system_prompt"


# ===================================================================
# load_agent_registry() — with override path
# ===================================================================


class TestLoadAgentRegistryOverride:
    def test_override_path_adds_agents(self, tmp_path):
        custom_agent = {
            "name": "custom",
            "description": "Custom agent",
            "preferred_provider": "codex",
            "model": "gpt-4o",
            "tools": ["bash"],
            "system_prompt": "You are custom.",
        }
        (tmp_path / "custom.yml").write_text(yaml.dump(custom_agent))
        registry = load_agent_registry(override_path=tmp_path)
        assert "custom" in registry
        assert registry["custom"].preferred_provider == "codex"
        # Bundled agents still present
        assert "backend" in registry

    def test_override_replaces_bundled_agent(self, tmp_path):
        custom_backend = {
            "name": "backend",
            "description": "My custom backend agent",
            "preferred_provider": "codex",
            "model": "o3",
            "tools": [],
            "system_prompt": "Custom backend prompt.",
        }
        (tmp_path / "backend.yml").write_text(yaml.dump(custom_backend))
        registry = load_agent_registry(override_path=tmp_path)
        assert registry["backend"].description == "My custom backend agent"
        assert registry["backend"].preferred_provider == "codex"
        assert registry["backend"].model == "o3"

    def test_override_nonexistent_dir_is_ignored(self, tmp_path):
        fake_dir = tmp_path / "nonexistent"
        registry = load_agent_registry(override_path=fake_dir)
        # Should still load bundled defaults
        assert set(registry.keys()) == EXPECTED_BUNDLED_AGENTS

    def test_override_with_malformed_yaml_file_skipped(self, tmp_path):
        (tmp_path / "bad.yml").write_text(": : : invalid yaml {{{{")
        registry = load_agent_registry(override_path=tmp_path)
        # Bundled agents still loaded, malformed file silently skipped
        assert "backend" in registry

    def test_override_with_yaml_missing_name_skipped(self, tmp_path):
        (tmp_path / "noname.yml").write_text(yaml.dump({"description": "No name"}))
        registry = load_agent_registry(override_path=tmp_path)
        # Should not crash; agent without name is silently skipped
        assert "backend" in registry

    def test_override_with_empty_yaml_file_skipped(self, tmp_path):
        (tmp_path / "empty.yml").write_text("")
        registry = load_agent_registry(override_path=tmp_path)
        assert set(registry.keys()) == EXPECTED_BUNDLED_AGENTS

    def test_override_none_loads_only_bundled(self):
        registry = load_agent_registry(override_path=None)
        assert set(registry.keys()) == EXPECTED_BUNDLED_AGENTS


# ===================================================================
# load_agent_registry() — edge cases with custom dir only
# ===================================================================


class TestLoadAgentRegistryEdgeCases:
    def test_multiple_agents_in_override_dir(self, tmp_path):
        for name in ["agent_a", "agent_b", "agent_c"]:
            data = {"name": name, "description": f"Agent {name}"}
            (tmp_path / f"{name}.yml").write_text(yaml.dump(data))
        registry = load_agent_registry(override_path=tmp_path)
        # Bundled agents plus 3 custom
        assert "agent_a" in registry
        assert "agent_b" in registry
        assert "agent_c" in registry
        assert "backend" in registry  # Bundled still present

    def test_non_yml_files_ignored(self, tmp_path):
        data = {"name": "txt_agent", "description": "In a .txt file"}
        (tmp_path / "agent.txt").write_text(yaml.dump(data))
        (tmp_path / "agent.json").write_text('{"name": "json_agent"}')
        registry = load_agent_registry(override_path=tmp_path)
        assert "txt_agent" not in registry
        assert "json_agent" not in registry

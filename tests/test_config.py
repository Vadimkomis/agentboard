"""Tests for agentboard.core.config — Config dataclass, load_config(), CLI helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from agentboard.core.config import Config, load_config

# ===================================================================
# Config defaults
# ===================================================================


class TestConfigDefaults:
    def test_default_provider_is_claude(self):
        cfg = Config()
        assert cfg.default_provider == "claude"

    def test_default_claude_cli_path(self):
        cfg = Config()
        assert cfg.claude_cli_path == "claude"

    def test_default_codex_cli_path(self):
        cfg = Config()
        assert cfg.codex_cli_path == "codex"

    def test_default_api_keys_are_none(self):
        cfg = Config()
        assert cfg.anthropic_api_key is None
        assert cfg.openai_api_key is None
        assert cfg.github_token is None

    def test_default_heartbeat_interval(self):
        cfg = Config()
        assert cfg.heartbeat_interval_minutes == 30

    def test_default_archive_after_days(self):
        cfg = Config()
        assert cfg.archive_after_days == 7

    def test_default_workspace_base(self):
        cfg = Config()
        assert cfg.workspace_base == "/tmp/agentboard/workspaces"

    def test_default_db_path_is_none(self):
        cfg = Config()
        assert cfg.db_path is None

    def test_default_agent_config_dir_points_to_bundled_defaults(self):
        cfg = Config()
        assert cfg.agent_config_dir.name == "defaults"
        assert "agents" in str(cfg.agent_config_dir)


# ===================================================================
# Config.__post_init__ — agent_config_dir resolution
# ===================================================================


class TestConfigAgentConfigDir:
    def test_custom_agent_config_path_resolved(self, tmp_path):
        custom = tmp_path / "my_agents"
        custom.mkdir()
        cfg = Config(agent_config_path=str(custom))
        assert cfg.agent_config_dir == custom

    def test_no_agent_config_path_uses_bundled(self):
        cfg = Config()
        assert cfg.agent_config_dir.exists()
        assert cfg.agent_config_dir.is_dir()

    def test_tilde_expansion_in_agent_config_path(self):
        cfg = Config(agent_config_path="~/my_agents")
        assert "~" not in str(cfg.agent_config_dir)
        assert cfg.agent_config_dir == Path("~/my_agents").expanduser()


# ===================================================================
# Config.db_file
# ===================================================================


class TestConfigDbFile:
    def test_default_db_file_in_config_dir(self):
        cfg = Config()
        assert cfg.db_file.name == "agentboard.db"
        assert ".agentboard" in str(cfg.db_file)

    def test_custom_db_path(self, tmp_path):
        db = tmp_path / "custom.db"
        cfg = Config(db_path=str(db))
        assert cfg.db_file == db


# ===================================================================
# Config.workspace_dir
# ===================================================================


class TestConfigWorkspaceDir:
    def test_default_workspace_dir(self):
        cfg = Config()
        assert cfg.workspace_dir == Path("/tmp/agentboard/workspaces")

    def test_custom_workspace_base(self):
        cfg = Config(workspace_base="/var/agentboard/ws")
        assert cfg.workspace_dir == Path("/var/agentboard/ws")


# ===================================================================
# Config.resolve_cli_path()
# ===================================================================


class TestConfigResolveCliPath:
    def test_resolve_claude(self):
        cfg = Config(claude_cli_path="/usr/local/bin/claude")
        assert cfg.resolve_cli_path("claude") == "/usr/local/bin/claude"

    def test_resolve_codex(self):
        cfg = Config(codex_cli_path="/usr/local/bin/codex")
        assert cfg.resolve_cli_path("codex") == "/usr/local/bin/codex"

    def test_unknown_provider_raises_value_error(self):
        cfg = Config()
        with pytest.raises(ValueError, match="Unknown provider"):
            cfg.resolve_cli_path("gpt")

    def test_resolve_defaults(self):
        cfg = Config()
        assert cfg.resolve_cli_path("claude") == "claude"
        assert cfg.resolve_cli_path("codex") == "codex"


# ===================================================================
# Config.cli_available()
# ===================================================================


class TestConfigCliAvailable:
    @patch("agentboard.core.config.shutil.which", return_value="/usr/local/bin/claude")
    def test_claude_available(self, mock_which):
        cfg = Config()
        assert cfg.cli_available("claude") is True
        mock_which.assert_called_once_with("claude")

    @patch("agentboard.core.config.shutil.which", return_value=None)
    def test_claude_not_available(self, mock_which):
        cfg = Config()
        assert cfg.cli_available("claude") is False

    @patch("agentboard.core.config.shutil.which", return_value="/usr/local/bin/codex")
    def test_codex_available(self, mock_which):
        cfg = Config()
        assert cfg.cli_available("codex") is True
        mock_which.assert_called_once_with("codex")

    @patch("agentboard.core.config.shutil.which", return_value=None)
    def test_codex_not_available(self, mock_which):
        cfg = Config()
        assert cfg.cli_available("codex") is False

    def test_unknown_provider_raises_in_cli_available(self):
        cfg = Config()
        with pytest.raises(ValueError, match="Unknown provider"):
            cfg.cli_available("gpt4")


# ===================================================================
# load_config() — YAML parsing
# ===================================================================


class TestLoadConfig:
    def test_nonexistent_file_returns_defaults(self, tmp_path):
        cfg = load_config(tmp_path / "does_not_exist.yml")
        assert cfg.default_provider == "claude"
        assert cfg.heartbeat_interval_minutes == 30

    def test_empty_yaml_returns_defaults(self, tmp_path):
        config_file = tmp_path / "config.yml"
        config_file.write_text("")
        cfg = load_config(config_file)
        assert cfg.default_provider == "claude"

    def test_partial_yaml_overrides_only_specified_fields(self, tmp_path):
        config_file = tmp_path / "config.yml"
        data = {"heartbeat_interval_minutes": 10, "default_provider": "codex"}
        config_file.write_text(yaml.dump(data))
        cfg = load_config(config_file)
        assert cfg.heartbeat_interval_minutes == 10
        assert cfg.default_provider == "codex"
        # Unspecified fields keep defaults
        assert cfg.claude_cli_path == "claude"

    def test_full_yaml_loads_all_fields(self, tmp_path):
        config_file = tmp_path / "config.yml"
        data = {
            "default_provider": "codex",
            "claude_cli_path": "/opt/claude",
            "codex_cli_path": "/opt/codex",
            "anthropic_api_key": "sk-ant-123",
            "openai_api_key": "sk-oai-456",
            "github_token": "ghp_abc",
            "heartbeat_interval_minutes": 15,
            "archive_after_days": 14,
            "workspace_base": "/data/ws",
            "db_path": "/data/my.db",
        }
        config_file.write_text(yaml.dump(data))
        cfg = load_config(config_file)
        assert cfg.default_provider == "codex"
        assert cfg.claude_cli_path == "/opt/claude"
        assert cfg.codex_cli_path == "/opt/codex"
        assert cfg.anthropic_api_key == "sk-ant-123"
        assert cfg.openai_api_key == "sk-oai-456"
        assert cfg.github_token == "ghp_abc"
        assert cfg.heartbeat_interval_minutes == 15
        assert cfg.archive_after_days == 14
        assert cfg.workspace_base == "/data/ws"
        assert cfg.db_path == "/data/my.db"

    def test_unknown_keys_are_ignored(self, tmp_path):
        config_file = tmp_path / "config.yml"
        data = {
            "default_provider": "claude",
            "unknown_field_xyz": "should be ignored",
            "another_unknown": 42,
        }
        config_file.write_text(yaml.dump(data))
        cfg = load_config(config_file)
        assert cfg.default_provider == "claude"
        assert not hasattr(cfg, "unknown_field_xyz")

    def test_yaml_with_null_values(self, tmp_path):
        config_file = tmp_path / "config.yml"
        data = {
            "default_provider": "claude",
            "anthropic_api_key": None,
            "github_token": None,
        }
        config_file.write_text(yaml.dump(data))
        cfg = load_config(config_file)
        assert cfg.anthropic_api_key is None
        assert cfg.github_token is None

    def test_agent_config_path_from_yaml(self, tmp_path):
        config_file = tmp_path / "config.yml"
        agents_dir = tmp_path / "custom_agents"
        agents_dir.mkdir()
        data = {"agent_config_path": str(agents_dir)}
        config_file.write_text(yaml.dump(data))
        cfg = load_config(config_file)
        assert cfg.agent_config_dir == agents_dir


# ===================================================================
# load_config() default path (no argument)
# ===================================================================


class TestLoadConfigDefaultPath:
    @patch("agentboard.core.config.CONFIG_PATH")
    def test_default_path_used_when_none_passed(self, mock_path, tmp_path):
        mock_path.exists.return_value = False
        # Should return defaults since file doesn't exist
        cfg = load_config(None)
        assert cfg.default_provider == "claude"

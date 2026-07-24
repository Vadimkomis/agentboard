"""Targeted edge cases for small core helpers and model representations."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from agentboard.agents.pm_agent import _parse_json_response
from agentboard.core import config
from agentboard.core.agent_registry import get_agent
from agentboard.core.models import (
    Execution,
    GrowthMessage,
    MessageRole,
    Runtime,
    Story,
    StoryMessage,
    StoryStatus,
    Ticket,
    TicketStatus,
)
from agentboard.llm import ClaudeCLIClient, CodexCLIClient, LLMClient


def test_config_singleton_set_and_lazy_load():
    configured = config.Config(default_provider="codex")
    config.set_config(configured)
    assert config.get_config() is configured

    config._config = None
    loaded = config.Config(default_provider="claude")
    with patch("agentboard.core.config.load_config", return_value=loaded) as loader:
        assert config.get_config() is loaded
        loader.assert_called_once_with()


def test_config_directory_and_example_copy(tmp_path, monkeypatch):
    config_dir = tmp_path / "home"
    example = tmp_path / "example.yml"
    example.write_text("default_provider: codex\n")
    target = config_dir / "config.yml"
    monkeypatch.setattr(config, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config, "EXAMPLE_CONFIG_PATH", example)

    assert config.write_example_config(target) == target
    assert target.read_text() == example.read_text()

    target.write_text("keep: existing\n")
    assert config.write_example_config(target) == target
    assert target.read_text() == "keep: existing\n"


def test_write_example_config_handles_missing_example(tmp_path, monkeypatch):
    target = tmp_path / "config.yml"
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "EXAMPLE_CONFIG_PATH", tmp_path / "missing.yml")
    assert config.write_example_config(target) == target
    assert not target.exists()


def test_get_agent_success_and_missing():
    assert get_agent("backend").name == "backend"
    assert get_agent("does-not-exist") is None


def test_llm_package_exports_public_client_types():
    assert LLMClient is not None
    assert ClaudeCLIClient.__name__ == "ClaudeCLIClient"
    assert CodexCLIClient.__name__ == "CodexCLIClient"


def test_model_representations_and_message_serialization():
    story = Story(id=7, title="Feature", status=StoryStatus.drafting)
    ticket = Ticket(id=9, title="Task", status=TicketStatus.pending)
    execution = Execution(id=11, ticket_id=9, runtime=Runtime.codex, status="running")
    assert "Feature" in repr(story)
    assert "Task" in repr(ticket)
    assert "ticket_id=9" in repr(execution)

    assert StoryMessage(role=MessageRole.user, content="hello").to_dict() == {
        "role": "user",
        "content": "hello",
    }
    assert GrowthMessage(role=MessageRole.assistant, content="hi").to_dict() == {
        "role": "assistant",
        "content": "hi",
    }


def test_parse_json_response_rejects_all_invalid_forms():
    with pytest.raises(ValueError, match="Could not parse JSON"):
        _parse_json_response("```json\n{broken}\n``` and also {still broken}")

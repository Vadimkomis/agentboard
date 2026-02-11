"""Tests for the PM Agent triage service."""

import json
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_ticket(title="Fix login bug", description="Users can't log in"):
    t = MagicMock()
    t.title = title
    t.description = description
    return t


def _make_project(repo="testuser/test-repo", branch="main"):
    p = MagicMock()
    p.repo_full_name = repo
    p.default_branch = branch
    return p


TRIAGE_JSON = {
    "agent_type": "backend",
    "runtime": "claude",
    "priority": "high",
    "complexity": "medium",
    "branch_name": "fix/login-bug",
    "refined_description": "Fix the OAuth login flow",
    "acceptance_criteria": "Users can log in via GitHub",
    "context_files": ["src/auth.py"],
    "reasoning": "This is a backend auth issue",
}


async def test_triage_ticket_returns_expected_fields():
    """Test that triage_ticket returns proper classification."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "content": [{"type": "text", "text": json.dumps(TRIAGE_JSON)}]
    }

    with patch("src.services.pm_agent.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        from src.services.pm_agent import triage_ticket

        result = await triage_ticket(
            ticket=_make_ticket(),
            project=_make_project(),
            anthropic_key="sk-ant-test",
            repo_files=["src/auth.py", "src/main.py"],
        )

    assert result.agent_type == "backend"
    assert result.runtime == "claude"
    assert result.priority == "high"
    assert result.complexity == "medium"
    assert result.branch_name == "fix/login-bug"


async def test_triage_ticket_handles_api_error():
    """If the API call fails, triage_ticket should raise."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = Exception("API error")

    with patch("src.services.pm_agent.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        from src.services.pm_agent import triage_ticket

        with pytest.raises(Exception):
            await triage_ticket(
                ticket=_make_ticket(),
                project=_make_project(),
                anthropic_key="sk-ant-test",
            )


async def test_triage_ticket_handles_json_in_code_block():
    """The PM agent may wrap JSON in markdown code blocks."""
    wrapped = f"```json\n{json.dumps(TRIAGE_JSON)}\n```"
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "content": [{"type": "text", "text": wrapped}]
    }

    with patch("src.services.pm_agent.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        from src.services.pm_agent import triage_ticket

        result = await triage_ticket(
            ticket=_make_ticket(),
            project=_make_project(),
            anthropic_key="sk-ant-test",
        )

    assert result.agent_type == "backend"


async def test_triage_ticket_no_json_raises():
    """If the response contains no JSON, it should raise ValueError."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "content": [{"type": "text", "text": "I don't know how to help."}]
    }

    with patch("src.services.pm_agent.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        from src.services.pm_agent import triage_ticket

        with pytest.raises(ValueError, match="Could not parse"):
            await triage_ticket(
                ticket=_make_ticket(),
                project=_make_project(),
                anthropic_key="sk-ant-test",
            )


async def test_generate_planning_reply_streams_tokens():
    """generate_planning_reply should stream tokens and return full text."""

    # Build a fake streaming response with SSE lines
    async def _fake_aiter_lines():
        delta_hello = json.dumps({
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": "Hello "},
        })
        delta_world = json.dumps({
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": "world"},
        })
        events = [
            'data: {"type":"content_block_start","index":0}',
            f"data: {delta_hello}",
            f"data: {delta_world}",
            'data: {"type":"content_block_stop","index":0}',
            "data: [DONE]",
        ]
        for line in events:
            yield line

    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.aiter_lines = _fake_aiter_lines

    collected_tokens = []

    def on_token(tok: str):
        collected_tokens.append(tok)

    with patch("src.services.pm_agent.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.stream = MagicMock(return_value=mock_resp)
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        from src.services.pm_agent import generate_planning_reply

        result = await generate_planning_reply(
            ticket=_make_ticket(),
            project=_make_project(),
            conversation_history=[
                {"role": "user", "content": "Help me plan this."}
            ],
            anthropic_key="sk-ant-test",
            on_token=on_token,
        )

    assert result == "Hello world"
    assert collected_tokens == ["Hello ", "world"]


async def test_finalize_planning_returns_triage_result():
    """finalize_planning should return a TriageResult from conversation."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "content": [{"type": "text", "text": json.dumps(TRIAGE_JSON)}]
    }

    with patch("src.services.pm_agent.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        from src.services.pm_agent import finalize_planning

        result = await finalize_planning(
            ticket=_make_ticket(),
            project=_make_project(),
            conversation_history=[
                {"role": "user", "content": "Build a login page"},
                {"role": "assistant", "content": "Sure, let me analyze..."},
            ],
            anthropic_key="sk-ant-test",
        )

    assert result.agent_type == "backend"
    assert result.runtime == "claude"
    assert result.priority == "high"

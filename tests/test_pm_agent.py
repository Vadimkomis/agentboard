"""Tests for agentboard.agents.pm_agent — _parse_json_response() and PMAgent methods."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from agentboard.agents.pm_agent import PMAgent, _parse_json_response
from agentboard.core.models import AgentType, MessageRole, StoryStatus, TicketStatus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_story(**overrides):
    defaults = {
        "id": 1,
        "title": "My Feature",
        "prd_problem": None,
        "prd_solution": None,
        "prd_scope": None,
        "prd_acceptance": None,
        "prd_gtm": None,
        "status": StoryStatus.drafting,
        "tickets": [],
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_ticket(**overrides):
    defaults = {
        "id": 1,
        "story_id": 1,
        "title": "Ticket 1",
        "ticket_index": 0,
        "prd_anchor": "core.api",
        "status": TicketStatus.pending,
        "agent_type": AgentType.backend,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_story_message(role, content):
    msg = SimpleNamespace(role=MessageRole(role), content=content)
    msg.to_dict = lambda: {"role": msg.role.value, "content": msg.content}
    return msg


# ===================================================================
# _parse_json_response()
# ===================================================================


class TestParseJsonResponse:
    def test_direct_json_object(self):
        raw = '{"key": "value", "count": 42}'
        result = _parse_json_response(raw)
        assert result == {"key": "value", "count": 42}

    def test_direct_json_with_whitespace(self):
        raw = '  \n  {"key": "value"}  \n  '
        result = _parse_json_response(raw)
        assert result == {"key": "value"}

    def test_json_in_markdown_code_block(self):
        raw = """Here is the result:

```json
{"engineering_tickets": [{"title": "Ticket A"}]}
```
"""
        result = _parse_json_response(raw)
        assert result == {"engineering_tickets": [{"title": "Ticket A"}]}

    def test_json_in_markdown_code_block_without_json_label(self):
        raw = """Here:

```
{"stale_ticket_indices": [0, 2]}
```
"""
        result = _parse_json_response(raw)
        assert result == {"stale_ticket_indices": [0, 2]}

    def test_json_embedded_in_prose(self):
        raw = """I analyzed the PRD and here are the results:

{"engineering_tickets": [], "marketing_ticket": {"title": "Launch"}}

Hope that helps!"""
        result = _parse_json_response(raw)
        assert result["engineering_tickets"] == []
        assert result["marketing_ticket"]["title"] == "Launch"

    def test_nested_json_object(self):
        data = {
            "engineering_tickets": [
                {
                    "index": 0,
                    "title": "Build API",
                    "agent_type": "backend",
                    "runtime": "claude",
                },
            ],
            "marketing_ticket": {"title": "Write LAUNCH.md"},
        }
        raw = json.dumps(data)
        result = _parse_json_response(raw)
        assert len(result["engineering_tickets"]) == 1
        assert result["engineering_tickets"][0]["title"] == "Build API"

    def test_invalid_json_raises_value_error(self):
        raw = "This is not JSON at all."
        with pytest.raises(ValueError, match="Could not parse JSON"):
            _parse_json_response(raw)

    def test_empty_string_raises_value_error(self):
        with pytest.raises(ValueError, match="Could not parse JSON"):
            _parse_json_response("")

    def test_only_curly_braces_no_valid_json_raises(self):
        raw = "{ invalid json content }"
        with pytest.raises(ValueError, match="Could not parse JSON"):
            _parse_json_response(raw)

    def test_json_array_is_returned_directly_by_json_loads(self):
        # json.loads succeeds on arrays — the function returns whatever json.loads returns.
        # This is a known quirk: the return type annotation says dict, but arrays pass through.
        raw = '[{"a": 1}]'
        result = _parse_json_response(raw)
        assert result == [{"a": 1}]

    def test_multiple_json_blocks_returns_first(self):
        raw = """
```json
{"first": true}
```

And another:
```json
{"second": true}
```
"""
        result = _parse_json_response(raw)
        assert result == {"first": True}

    def test_json_with_special_characters(self):
        data = {"title": 'Fix: "quotes" & <angles>', "count": 0}
        raw = json.dumps(data)
        result = _parse_json_response(raw)
        assert result["title"] == 'Fix: "quotes" & <angles>'

    def test_multiline_json_in_code_block(self):
        raw = """```json
{
  "stale_ticket_indices": [0, 2],
  "changed_sections": ["checkout.payment-methods"],
  "summary": "Payment section changed"
}
```"""
        result = _parse_json_response(raw)
        assert result["stale_ticket_indices"] == [0, 2]
        assert result["summary"] == "Payment section changed"

    def test_json_with_unicode(self):
        raw = '{"message": "\\u2714 done"}'
        result = _parse_json_response(raw)
        assert result["message"] == "\u2714 done"


# ===================================================================
# PMAgent._build_prd_summary()
# ===================================================================


class TestBuildPrdSummary:
    def _build(self, story):
        """Call _build_prd_summary on the real PMAgent instance."""
        agent = PMAgent(llm_client=MagicMock())
        return agent._build_prd_summary(story)

    def test_no_prd_content(self):
        story = _make_story()
        result = self._build(story)
        assert result == "(No PRD content yet)"

    def test_all_sections_present(self):
        story = _make_story(
            prd_problem="Users can't pay",
            prd_solution="Add Stripe",
            prd_scope="MVP only",
            prd_acceptance="All tests pass",
            prd_gtm="SEO + launch",
        )
        result = self._build(story)
        assert "**Problem:** Users can't pay" in result
        assert "**Solution:** Add Stripe" in result
        assert "**Scope:** MVP only" in result
        assert "**Acceptance Criteria:** All tests pass" in result
        assert "**GTM:** SEO + launch" in result

    def test_partial_prd_only_problem(self):
        story = _make_story(prd_problem="Users are confused")
        result = self._build(story)
        assert "**Problem:** Users are confused" in result
        assert "**Solution:**" not in result
        assert "**Scope:**" not in result
        assert "(No PRD content yet)" not in result

    def test_partial_prd_problem_and_gtm(self):
        story = _make_story(
            prd_problem="Slow checkout",
            prd_gtm="Product-led growth",
        )
        result = self._build(story)
        assert "**Problem:** Slow checkout" in result
        assert "**GTM:** Product-led growth" in result
        assert "**Solution:**" not in result

    def test_sections_joined_by_double_newline(self):
        story = _make_story(
            prd_problem="A",
            prd_solution="B",
        )
        result = self._build(story)
        assert "\n\n" in result

    def test_empty_strings_not_included(self):
        story = _make_story(
            prd_problem="",
            prd_solution="Real solution",
        )
        result = self._build(story)
        assert "**Problem:**" not in result
        assert "**Solution:** Real solution" in result


# ===================================================================
# PMAgent.decompose()
# ===================================================================


class TestPMAgentDecompose:
    async def test_decompose_parses_response(self):
        mock_client = AsyncMock()
        mock_client.complete.return_value = json.dumps(
            {
                "engineering_tickets": [
                    {"index": 0, "title": "Build API", "agent_type": "backend"},
                    {"index": 1, "title": "Build UI", "agent_type": "frontend"},
                ],
                "marketing_ticket": {"title": "LAUNCH.md"},
            }
        )

        agent = PMAgent(llm_client=mock_client)
        story = _make_story(
            prd_problem="Users need it",
            prd_solution="Build it",
            prd_scope="MVP",
            prd_acceptance="Tests pass",
            prd_gtm="SEO",
        )
        result = await agent.decompose(story)

        assert len(result.engineering_tickets) == 2
        assert result.engineering_tickets[0]["title"] == "Build API"
        assert result.marketing_ticket["title"] == "LAUNCH.md"

    async def test_decompose_handles_empty_tickets(self):
        mock_client = AsyncMock()
        mock_client.complete.return_value = json.dumps(
            {
                "engineering_tickets": [],
                "marketing_ticket": {},
            }
        )

        agent = PMAgent(llm_client=mock_client)
        story = _make_story(prd_problem="Minimal")
        result = await agent.decompose(story)

        assert result.engineering_tickets == []
        assert result.marketing_ticket == {}

    async def test_decompose_uses_decomposition_system_prompt(self):
        mock_client = AsyncMock()
        mock_client.complete.return_value = '{"engineering_tickets": [], "marketing_ticket": {}}'

        agent = PMAgent(llm_client=mock_client)
        story = _make_story()
        await agent.decompose(story)

        call_args = mock_client.complete.call_args
        system_prompt = call_args[0][0]
        assert "decomposing a refined PRD" in system_prompt


# ===================================================================
# PMAgent.analyze_diff()
# ===================================================================


class TestPMAgentAnalyzeDiff:
    async def test_analyze_diff_returns_stale_indices(self):
        mock_client = AsyncMock()
        mock_client.complete.return_value = json.dumps(
            {
                "stale_ticket_indices": [0, 2],
                "changed_sections": ["checkout.payment-methods"],
                "summary": "Payment section rewritten",
            }
        )

        agent = PMAgent(llm_client=mock_client)
        story = _make_story()
        tickets = [
            _make_ticket(id=1, ticket_index=0, prd_anchor="checkout.payment-methods"),
            _make_ticket(id=2, ticket_index=1, prd_anchor="auth.login"),
            _make_ticket(id=3, ticket_index=2, prd_anchor="checkout.cart"),
        ]

        result = await agent.analyze_diff(
            story,
            original_prd="Old PRD",
            updated_prd="New PRD",
            existing_tickets=tickets,
        )

        assert result.stale_ticket_indices == [0, 2]
        assert result.changed_sections == ["checkout.payment-methods"]
        assert "Payment" in result.summary

    async def test_analyze_diff_no_stale_tickets(self):
        mock_client = AsyncMock()
        mock_client.complete.return_value = json.dumps(
            {
                "stale_ticket_indices": [],
                "changed_sections": [],
                "summary": "",
            }
        )

        agent = PMAgent(llm_client=mock_client)
        story = _make_story()

        result = await agent.analyze_diff(
            story, original_prd="Same", updated_prd="Same", existing_tickets=[]
        )
        assert result.stale_ticket_indices == []
        assert result.changed_sections == []

    async def test_analyze_diff_passes_ticket_summary_to_llm(self):
        mock_client = AsyncMock()
        mock_client.complete.return_value = (
            '{"stale_ticket_indices": [], "changed_sections": [], "summary": ""}'
        )

        agent = PMAgent(llm_client=mock_client)
        story = _make_story()
        tickets = [_make_ticket(id=1, ticket_index=0, title="API ticket", prd_anchor="api")]

        await agent.analyze_diff(story, "Old", "New", tickets)

        call_args = mock_client.complete.call_args
        user_msg = call_args[0][1][0]["content"]
        assert "API ticket" in user_msg
        assert "api" in user_msg


# ===================================================================
# PMAgent.triage_bug()
# ===================================================================


class TestPMAgentTriageBug:
    async def test_triage_bug_returns_parsed_dict(self):
        mock_client = AsyncMock()
        mock_client.complete.return_value = json.dumps(
            {
                "title": "Fix: Login crash",
                "prd_anchor": "bug.auth",
                "agent_type": "backend",
                "runtime": "claude",
                "priority": "high",
                "complexity": "medium",
                "branch_name": "fix/login-crash",
                "refined_description": "Steps to reproduce...",
                "acceptance_criteria": "Login works after fix",
                "context_files": ["src/auth.py"],
                "depends_on": [],
            }
        )

        agent = PMAgent(llm_client=mock_client)
        story = _make_story(prd_problem="Auth system")

        result = await agent.triage_bug(story, "Login crashes on empty email")
        assert result["title"] == "Fix: Login crash"
        assert result["priority"] == "high"
        assert result["agent_type"] == "backend"

    async def test_triage_bug_passes_bug_description_to_llm(self):
        mock_client = AsyncMock()
        mock_client.complete.return_value = '{"title": "Fix: bug", "agent_type": "backend"}'

        agent = PMAgent(llm_client=mock_client)
        story = _make_story()

        await agent.triage_bug(story, "The app crashes when clicking submit")

        call_args = mock_client.complete.call_args
        user_msg = call_args[0][1][0]["content"]
        assert "crashes when clicking submit" in user_msg

    async def test_triage_bug_uses_bug_triage_system_prompt(self):
        mock_client = AsyncMock()
        mock_client.complete.return_value = '{"title": "Fix: x"}'

        agent = PMAgent(llm_client=mock_client)
        story = _make_story()

        await agent.triage_bug(story, "Some bug")

        call_args = mock_client.complete.call_args
        system_prompt = call_args[0][0]
        assert "triaging a bug report" in system_prompt


# ===================================================================
# PMAgent.refine() — message building
# ===================================================================


class TestPMAgentRefine:
    async def test_refine_first_message_includes_prd_context(self):
        mock_client = MagicMock()
        mock_client.stream = MagicMock(return_value="mocked")

        agent = PMAgent(llm_client=mock_client)
        story = _make_story(
            title="My App",
            prd_problem="Users are confused",
        )

        await agent.refine(story, "Help me refine this", history=[], on_token=lambda x: None)

        call_args = mock_client.stream.call_args
        messages = call_args[0][1]
        assert len(messages) == 1
        assert "My App" in messages[0]["content"]
        assert "Users are confused" in messages[0]["content"]

    async def test_refine_with_history_passes_all_messages(self):
        mock_client = MagicMock()
        mock_client.stream = MagicMock(return_value="mocked")

        agent = PMAgent(llm_client=mock_client)
        story = _make_story()
        history = [
            _make_story_message("user", "First message"),
            _make_story_message("assistant", "First reply"),
        ]

        await agent.refine(story, "Follow up", history=history, on_token=lambda x: None)

        call_args = mock_client.stream.call_args
        messages = call_args[0][1]
        assert len(messages) == 3  # 2 history + 1 new
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "First message"
        assert messages[1]["role"] == "assistant"
        assert messages[2]["role"] == "user"
        assert messages[2]["content"] == "Follow up"

    async def test_refine_uses_refinement_system_prompt(self):
        mock_client = MagicMock()
        mock_client.stream = MagicMock(return_value="mocked")

        agent = PMAgent(llm_client=mock_client)
        story = _make_story()

        await agent.refine(story, "Hello", history=[], on_token=lambda x: None)

        call_args = mock_client.stream.call_args
        system_prompt = call_args[0][0]
        assert "senior product manager" in system_prompt

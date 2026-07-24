"""Behavioral tests for the growth-agent conversation and launch output."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

from agentboard.agents.growth_agent import (
    GROWTH_REFINEMENT_SYSTEM_PROMPT,
    GrowthAgent,
)


async def test_refine_seeds_story_context_for_first_message(make_story):
    client = Mock()
    stream = object()
    client.stream.return_value = stream
    story = make_story(
        title="AgentBoard",
        prd_problem="Work is scattered",
        prd_solution="One local board",
        prd_gtm="Developer communities",
    )
    on_token = Mock()

    result = await GrowthAgent(client).refine(story, "Help with launch", [], on_token)

    assert result is stream
    system, messages, callback = client.stream.call_args.args
    assert system == GROWTH_REFINEMENT_SYSTEM_PROMPT
    assert callback is on_token
    assert messages == [
        {
            "role": "user",
            "content": (
                "Story title: AgentBoard\n\n"
                "Problem: Work is scattered\n\n"
                "Solution: One local board\n\n"
                "GTM so far: Developer communities\n\n"
                "User message: Help with launch"
            ),
        }
    ]


async def test_refine_preserves_history_and_appends_user_message(make_story, make_growth_message):
    client = Mock()
    client.stream.return_value = object()
    history = [
        make_growth_message("user", "Who is this for?"),
        make_growth_message("assistant", "Small engineering teams."),
    ]

    await GrowthAgent(client).refine(make_story(), "What channel should we try?", history, Mock())

    messages = client.stream.call_args.args[1]
    assert messages == [
        {"role": "user", "content": "Who is this for?"},
        {"role": "assistant", "content": "Small engineering teams."},
        {"role": "user", "content": "What channel should we try?"},
    ]


async def test_generate_launch_md_builds_complete_context(make_story, make_growth_message):
    client = Mock()
    client.complete = AsyncMock(return_value="# LAUNCH.md")
    story = make_story(
        title="AgentBoard",
        prd_problem="Scattered work",
        prd_solution="A board",
        prd_scope="Local-first",
        prd_acceptance="One feature ships",
        prd_gtm="Communities",
    )
    history = [
        make_growth_message("user", "Target indie developers"),
        make_growth_message("assistant", "Lead with local-first"),
    ]

    result = await GrowthAgent(client).generate_launch_md(story, history)

    assert result == "# LAUNCH.md"
    system, messages = client.complete.await_args.args
    assert "# LAUNCH.md — AgentBoard" in system
    prompt = messages[0]["content"]
    assert "Problem: Scattered work" in prompt
    assert "Acceptance Criteria: One feature ships" in prompt
    assert "USER: Target indie developers" in prompt
    assert "ASSISTANT: Lead with local-first" in prompt

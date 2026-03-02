from __future__ import annotations

from types import SimpleNamespace

from agentboard.core.models import MessageRole, StoryStatus
from agentboard.tui.screens.story_detail import (
    PM_DISCUSSION_MARKER,
    _can_finalize_pm,
    _has_pm_conversation,
    _has_pm_discussion_marker,
    _should_auto_start_pm_discussion,
)


def test_can_finalize_pm_only_in_drafting_or_refining():
    assert _can_finalize_pm(StoryStatus.drafting) is True
    assert _can_finalize_pm(StoryStatus.refining) is True
    assert _can_finalize_pm(StoryStatus.decomposing) is False
    assert _can_finalize_pm(StoryStatus.engineering) is False
    assert _can_finalize_pm(StoryStatus.testing) is False
    assert _can_finalize_pm(StoryStatus.done) is False


def test_has_pm_conversation_requires_user_and_assistant_roles():
    user = SimpleNamespace(role=MessageRole.user)
    assistant = SimpleNamespace(role=MessageRole.assistant)
    system = SimpleNamespace(role=MessageRole.system)

    assert _has_pm_conversation([]) is False
    assert _has_pm_conversation([user]) is False
    assert _has_pm_conversation([assistant]) is False
    assert _has_pm_conversation([user, system]) is False
    assert _has_pm_conversation([assistant, system]) is False
    assert _has_pm_conversation([user, assistant]) is True


def test_has_pm_discussion_marker_detects_system_marker_message():
    marker = SimpleNamespace(role=MessageRole.system, content=PM_DISCUSSION_MARKER)
    other_system = SimpleNamespace(role=MessageRole.system, content="other")
    user = SimpleNamespace(role=MessageRole.user, content="hello")

    assert _has_pm_discussion_marker([]) is False
    assert _has_pm_discussion_marker([user, other_system]) is False
    assert _has_pm_discussion_marker([marker]) is True


def test_should_auto_start_pm_discussion_only_for_complete_unrefined_drafts():
    assert _should_auto_start_pm_discussion(StoryStatus.drafting, prd_complete=True, discussion_started=False)
    assert _should_auto_start_pm_discussion(StoryStatus.refining, prd_complete=True, discussion_started=False)
    assert (
        _should_auto_start_pm_discussion(
            StoryStatus.drafting, prd_complete=False, discussion_started=False
        )
        is False
    )
    assert (
        _should_auto_start_pm_discussion(
            StoryStatus.drafting, prd_complete=True, discussion_started=True
        )
        is False
    )
    assert (
        _should_auto_start_pm_discussion(
            StoryStatus.engineering, prd_complete=True, discussion_started=False
        )
        is False
    )

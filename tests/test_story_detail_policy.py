from __future__ import annotations

from types import SimpleNamespace

from agentboard.core.models import MessageRole, StoryStatus
from agentboard.tui.screens.story_detail import _can_finalize_pm, _has_pm_conversation


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

from __future__ import annotations

from agentboard.core.models import StoryStatus
from agentboard.tui.screens.board import _can_delete_story


def test_can_delete_story_only_in_drafting_or_refining():
    assert _can_delete_story(StoryStatus.drafting) is True
    assert _can_delete_story(StoryStatus.refining) is True
    assert _can_delete_story(StoryStatus.decomposing) is False
    assert _can_delete_story(StoryStatus.engineering) is False
    assert _can_delete_story(StoryStatus.testing) is False
    assert _can_delete_story(StoryStatus.done) is False

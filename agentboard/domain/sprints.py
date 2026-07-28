"""Sprint eligibility and transition rules."""

from __future__ import annotations

from datetime import datetime

from agentboard.domain.entities import Feature, Sprint
from agentboard.domain.enums import SprintState
from agentboard.domain.errors import (
    DesignApprovalRequiredError,
    SprintCompletedError,
    SprintNotPlannedError,
)


def ensure_feature_is_sprint_eligible(feature: Feature) -> None:
    if not feature.has_approved_design:
        raise DesignApprovalRequiredError(_persisted_id(feature.id))


def ensure_sprint_accepts_features(sprint: Sprint) -> None:
    if sprint.state is SprintState.completed:
        raise SprintCompletedError(_persisted_id(sprint.id))


def ensure_sprint_is_planned(sprint: Sprint) -> None:
    if sprint.state is not SprintState.planned:
        raise SprintNotPlannedError(_persisted_id(sprint.id))


def start_sprint(sprint: Sprint, started_at: datetime) -> None:
    ensure_sprint_is_planned(sprint)
    sprint.state = SprintState.active
    sprint.starts_at = started_at
    sprint.updated_at = started_at


def _persisted_id(identifier: int | None) -> int:
    if identifier is None:
        raise ValueError("The domain operation requires a persisted entity.")
    return identifier

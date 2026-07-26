"""Deterministic unit coverage for the browser-v0 domain rules."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from agentboard.domain.entities import ActiveSprint, Feature, Sprint
from agentboard.domain.enums import EngineeringState, PlanningStage, SprintState
from agentboard.domain.errors import (
    DesignApprovalRequiredError,
    DomainError,
    DuplicateIdentifiersError,
    IncompleteReorderError,
    PersistenceConflictError,
    SprintCompletedError,
    SprintNotPlannedError,
)
from agentboard.domain.ranking import contiguous_ranks, validate_exact_order
from agentboard.domain.sprints import (
    ensure_feature_is_sprint_eligible,
    ensure_sprint_accepts_features,
    start_sprint,
)

NOW = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)
LATER = datetime(2026, 7, 27, 9, 30, tzinfo=UTC)


def make_feature(
    *,
    feature_id: int | None = 11,
    project_id: int = 1,
    approved_design_hash: str | None = "design-sha-1",
) -> Feature:
    return Feature(
        id=feature_id,
        project_id=project_id,
        number=1,
        title="Deterministic Feature",
        description="A fixed test Feature",
        rank=1,
        planning_stage=PlanningStage.design_review,
        engineering_state=None,
        priority="high",
        estimate=3,
        owner="owner@example.test",
        approved_design_hash=approved_design_hash,
        completed_at=None,
        created_at=NOW,
        updated_at=NOW,
    )


def make_sprint(
    *,
    sprint_id: int | None = 21,
    project_id: int = 1,
    state: SprintState = SprintState.planned,
) -> Sprint:
    return Sprint(
        id=sprint_id,
        project_id=project_id,
        number=1,
        name="Sprint One",
        goal="Ship the foundation",
        state=state,
        starts_at=None,
        ends_at=None,
        created_at=NOW,
        updated_at=NOW,
    )


@pytest.mark.parametrize(
    ("approval", "expected"),
    [
        ("design-sha-1", True),
        (None, False),
        ("", False),
        (" \n\t ", False),
    ],
)
def test_feature_design_approval_requires_a_nonblank_exact_revision(
    approval: str | None,
    expected: bool,
) -> None:
    feature = make_feature(approved_design_hash=approval)

    assert feature.has_approved_design is expected


def test_domain_error_exposes_a_stable_code_and_user_message() -> None:
    error = DomainError("The requested operation is invalid.")

    assert error.code == "domain_error"
    assert error.user_message == "The requested operation is invalid."


def test_persistence_conflict_has_a_user_facing_typed_error() -> None:
    error = PersistenceConflictError()

    assert error.code == "persistence_conflict"
    assert error.user_message == "The change conflicts with concurrently persisted state."


def test_domain_enums_preserve_the_approved_schema_vocabulary() -> None:
    assert [stage.value for stage in PlanningStage] == [
        "inbox",
        "clarifying",
        "spec",
        "evals",
        "design",
        "design_review",
    ]
    assert [state.value for state in SprintState] == ["planned", "active", "completed"]
    assert [state.value for state in EngineeringState] == [
        "ready_for_engineering",
        "working",
        "in_review",
        "human_review",
        "ready_to_merge",
        "done",
    ]


@pytest.mark.parametrize(
    ("current_ids", "requested_ids"),
    [
        ([], []),
        ([4], [4]),
        ([1, 2, 3], [3, 1, 2]),
        ([1, 2, 3], [2, 3, 1]),
        ([1, 2, 3], [3, 2, 1]),
    ],
)
def test_exact_order_accepts_empty_single_and_complete_moves(
    current_ids: list[int],
    requested_ids: list[int],
) -> None:
    validate_exact_order(current_ids, requested_ids)


def test_exact_order_rejects_duplicate_identifiers() -> None:
    with pytest.raises(DuplicateIdentifiersError) as captured:
        validate_exact_order([1, 2, 3], [1, 2, 2])

    assert captured.value.code == "duplicate_identifiers"
    assert "exactly once" in captured.value.user_message


@pytest.mark.parametrize(
    "requested_ids",
    [
        [1, 2],
        [1, 2, 4],
        [1, 2, 3, 4],
    ],
)
def test_exact_order_rejects_missing_unknown_and_extra_identifiers(
    requested_ids: list[int],
) -> None:
    with pytest.raises(IncompleteReorderError) as captured:
        validate_exact_order([1, 2, 3], requested_ids)

    assert captured.value.code == "incomplete_reorder"


@pytest.mark.parametrize(
    ("ordered_ids", "expected"),
    [
        ([], {}),
        ([7], {7: 1}),
        ([30, 10, 20], {30: 1, 10: 2, 20: 3}),
    ],
)
def test_contiguous_ranks_are_positive_integers(
    ordered_ids: list[int],
    expected: dict[int, int],
) -> None:
    assert contiguous_ranks(ordered_ids) == expected


def test_approved_feature_is_eligible_without_mutation() -> None:
    feature = make_feature()

    ensure_feature_is_sprint_eligible(feature)

    assert feature.approved_design_hash == "design-sha-1"


@pytest.mark.parametrize("approval", [None, "", "   "])
def test_feature_without_an_exact_design_revision_is_ineligible(
    approval: str | None,
) -> None:
    feature = make_feature(approved_design_hash=approval)

    with pytest.raises(DesignApprovalRequiredError) as captured:
        ensure_feature_is_sprint_eligible(feature)

    assert captured.value.code == "design_approval_required"
    assert "Feature 11" in captured.value.user_message


def test_unpersisted_ineligible_feature_is_a_programming_error() -> None:
    feature = make_feature(feature_id=None, approved_design_hash=None)

    with pytest.raises(ValueError, match="persisted entity"):
        ensure_feature_is_sprint_eligible(feature)


@pytest.mark.parametrize("state", [SprintState.planned, SprintState.active])
def test_noncompleted_sprint_accepts_features(state: SprintState) -> None:
    sprint = make_sprint(state=state)

    ensure_sprint_accepts_features(sprint)

    assert sprint.state is state


def test_completed_sprint_rejects_new_features() -> None:
    sprint = make_sprint(state=SprintState.completed)

    with pytest.raises(SprintCompletedError) as captured:
        ensure_sprint_accepts_features(sprint)

    assert captured.value.code == "sprint_completed"
    assert "Sprint 21" in captured.value.user_message


def test_start_sprint_records_the_fixed_start_time() -> None:
    sprint = make_sprint()

    start_sprint(sprint, LATER)

    assert sprint.state is SprintState.active
    assert sprint.starts_at == LATER
    assert sprint.updated_at == LATER
    assert sprint.ends_at is None


@pytest.mark.parametrize("state", [SprintState.active, SprintState.completed])
def test_only_a_planned_sprint_can_start(state: SprintState) -> None:
    sprint = make_sprint(state=state)

    with pytest.raises(SprintNotPlannedError) as captured:
        start_sprint(sprint, LATER)

    assert captured.value.code == "sprint_not_planned"
    assert sprint.state is state
    assert sprint.starts_at is None
    assert sprint.updated_at == NOW


def test_unpersisted_nonplanned_sprint_is_a_programming_error() -> None:
    sprint = make_sprint(sprint_id=None, state=SprintState.active)

    with pytest.raises(ValueError, match="persisted entity"):
        start_sprint(sprint, LATER)


def test_active_sprint_read_model_preserves_ranked_features() -> None:
    first = make_feature(feature_id=1)
    second = make_feature(feature_id=2)
    active = ActiveSprint(sprint=make_sprint(state=SprintState.active), features=(first, second))

    assert active.features == (first, second)

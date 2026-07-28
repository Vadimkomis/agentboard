"""Typed, user-facing domain failures."""

from __future__ import annotations


class DomainError(Exception):
    """Base class for expected invalid browser-v0 operations."""

    code = "domain_error"

    @property
    def user_message(self) -> str:
        return str(self)


class InvalidInputError(DomainError):
    code = "invalid_input"


class ProjectNotFoundError(DomainError):
    code = "project_not_found"

    def __init__(self, project_id: int) -> None:
        super().__init__(f"Project {project_id} was not found.")


class DuplicateProjectKeyError(DomainError):
    code = "duplicate_project_key"

    def __init__(self, key: str) -> None:
        super().__init__(f"Project key {key!r} already exists.")


class FeatureNotFoundError(DomainError):
    code = "feature_not_found"

    def __init__(self, feature_id: int) -> None:
        super().__init__(f"Feature {feature_id} was not found.")


class SprintNotFoundError(DomainError):
    code = "sprint_not_found"

    def __init__(self, sprint_id: int) -> None:
        super().__init__(f"Sprint {sprint_id} was not found.")


class DuplicateIdentifiersError(DomainError):
    code = "duplicate_identifiers"

    def __init__(self) -> None:
        super().__init__("A ranked order must contain each identifier exactly once.")


class IncompleteReorderError(DomainError):
    code = "incomplete_reorder"

    def __init__(self) -> None:
        super().__init__("The ranked order must contain every item in the selected scope.")


class CrossProjectFeatureError(DomainError):
    code = "cross_project_feature"

    def __init__(self, feature_id: int) -> None:
        super().__init__(f"Feature {feature_id} belongs to another Project.")


class FeatureNotInSprintError(DomainError):
    code = "feature_not_in_sprint"

    def __init__(self, feature_id: int) -> None:
        super().__init__(f"Feature {feature_id} is not a member of this Sprint.")


class FeatureAlreadyInSprintError(DomainError):
    code = "feature_already_in_sprint"

    def __init__(self, feature_id: int) -> None:
        super().__init__(f"Feature {feature_id} is already in this Sprint.")


class DesignApprovalRequiredError(DomainError):
    code = "design_approval_required"

    def __init__(self, feature_id: int) -> None:
        super().__init__(f"Feature {feature_id} needs an approved exact design revision.")


class SprintNotPlannedError(DomainError):
    code = "sprint_not_planned"

    def __init__(self, sprint_id: int) -> None:
        super().__init__(f"Sprint {sprint_id} is not planned and cannot be started.")


class SprintCompletedError(DomainError):
    code = "sprint_completed"

    def __init__(self, sprint_id: int) -> None:
        super().__init__(f"Sprint {sprint_id} is completed and cannot accept Features.")


class ActiveSprintExistsError(DomainError):
    code = "active_sprint_exists"

    def __init__(self, project_id: int) -> None:
        super().__init__(f"Project {project_id} already has an active Sprint.")


class PersistenceConflictError(DomainError):
    code = "persistence_conflict"

    def __init__(self) -> None:
        super().__init__("The change conflicts with concurrently persisted state.")

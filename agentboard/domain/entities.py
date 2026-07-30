"""Persistence-independent browser-v0 entities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TypeAlias

from agentboard.domain.enums import EngineeringState, PlanningStage, SprintState

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


@dataclass(slots=True)
class Project:
    key: str
    name: str
    repository_url: str
    default_branch: str
    created_at: datetime
    updated_at: datetime
    version: int = 1
    id: int | None = None


@dataclass(slots=True)
class Feature:
    project_id: int
    number: int
    title: str
    description: str
    rank: int
    planning_stage: PlanningStage
    priority: str
    estimate: int | None
    owner: str | None
    approved_design_hash: str | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    engineering_state: EngineeringState | None = None
    id: int | None = None

    @property
    def has_approved_design(self) -> bool:
        return bool(self.approved_design_hash and self.approved_design_hash.strip())


@dataclass(slots=True)
class Sprint:
    project_id: int
    number: int
    name: str
    goal: str | None
    state: SprintState
    starts_at: datetime | None
    ends_at: datetime | None
    created_at: datetime
    updated_at: datetime
    id: int | None = None


@dataclass(slots=True)
class SprintFeature:
    sprint_id: int
    feature_id: int
    sprint_rank: int


@dataclass(slots=True)
class AuditEvent:
    project_id: int
    event_type: str
    payload: dict[str, JsonValue]
    created_at: datetime
    feature_id: int | None = None
    id: int | None = None


@dataclass(slots=True)
class CommandReceipt:
    project_id: int
    idempotency_key: str
    command_type: str
    request_hash: str
    result: dict[str, JsonValue]
    created_at: datetime
    id: int | None = None


@dataclass(frozen=True, slots=True)
class ActiveSprint:
    sprint: Sprint
    features: tuple[Feature, ...]

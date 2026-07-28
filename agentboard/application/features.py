"""Feature application commands."""

from __future__ import annotations

from datetime import datetime

from agentboard.application._support import Clock, persisted_id, require_text, utc_now
from agentboard.application.ports import UnitOfWork, UnitOfWorkFactory
from agentboard.domain.entities import AuditEvent, Feature
from agentboard.domain.enums import PlanningStage
from agentboard.domain.errors import InvalidInputError, ProjectNotFoundError


class CreateFeature:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock = utc_now) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self,
        *,
        project_id: int,
        title: str,
        description: str,
        planning_stage: PlanningStage = PlanningStage.inbox,
        priority: str = "medium",
        estimate: int | None = None,
        owner: str | None = None,
        approved_design_hash: str | None = None,
    ) -> Feature:
        title, priority = _validate_feature(title, priority, estimate)
        async with self._uow_factory() as uow:
            if await uow.projects.get(project_id) is None:
                raise ProjectNotFoundError(project_id)
            now = self._clock()
            feature = await uow.features.add(
                await _new_feature(
                    uow,
                    project_id,
                    title,
                    description,
                    planning_stage,
                    priority,
                    estimate,
                    owner,
                    approved_design_hash,
                    now,
                )
            )
            await uow.audit_events.add(_created_event(feature, now))
            await uow.commit()
            return feature


def _validate_feature(title: str, priority: str, estimate: int | None) -> tuple[str, str]:
    if estimate is not None and estimate < 0:
        raise InvalidInputError("Feature estimate must not be negative.")
    return require_text(title, "Feature title"), require_text(priority, "Feature priority")


async def _new_feature(
    uow: UnitOfWork,
    project_id: int,
    title: str,
    description: str,
    planning_stage: PlanningStage,
    priority: str,
    estimate: int | None,
    owner: str | None,
    approved_design_hash: str | None,
    now: datetime,
) -> Feature:
    number = await uow.features.next_number(project_id)
    rank = await uow.features.next_rank(project_id)
    return Feature(
        project_id,
        number,
        title,
        description,
        rank,
        planning_stage,
        priority,
        estimate,
        owner,
        approved_design_hash,
        None,
        now,
        now,
    )


def _created_event(feature: Feature, created_at: datetime) -> AuditEvent:
    feature_id = persisted_id(feature.id)
    return AuditEvent(
        project_id=feature.project_id,
        feature_id=feature_id,
        event_type="feature.created",
        payload={"feature_id": feature_id, "number": feature.number, "rank": feature.rank},
        created_at=created_at,
    )

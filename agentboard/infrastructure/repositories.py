"""SQLAlchemy implementations of browser-v0 persistence ports."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import cast

from sqlalchemy import case, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.base import Executable
from sqlalchemy.sql.elements import ColumnElement

from agentboard.domain.entities import (
    AuditEvent,
    CommandReceipt,
    Feature,
    JsonValue,
    Project,
    Sprint,
    SprintFeature,
)
from agentboard.domain.enums import EngineeringState, PlanningStage, SprintState
from agentboard.domain.ranking import contiguous_ranks, validate_exact_order
from agentboard.infrastructure.conflicts import raise_write_conflict
from agentboard.infrastructure.orm import (
    AuditEventRecord,
    CommandReceiptRecord,
    FeatureRecord,
    ProjectRecord,
    SprintFeatureRecord,
    SprintRecord,
)


class SqlAlchemyProjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, project_id: int) -> Project | None:
        record = await self._session.get(ProjectRecord, project_id)
        return None if record is None else _project_from_record(record)

    async def get_by_key(self, key: str) -> Project | None:
        record = await self._session.scalar(select(ProjectRecord).where(ProjectRecord.key == key))
        return None if record is None else _project_from_record(record)

    async def list(self) -> list[Project]:
        records = await self._session.scalars(select(ProjectRecord).order_by(ProjectRecord.id))
        return [_project_from_record(record) for record in records]

    async def add(self, project: Project) -> Project:
        record = ProjectRecord(
            id=project.id,
            key=project.key,
            name=project.name,
            repository_url=project.repository_url,
            default_branch=project.default_branch,
            version=project.version,
            created_at=project.created_at,
            updated_at=project.updated_at,
        )
        self._session.add(record)
        await _flush(self._session)
        project.id = record.id
        return project

    async def delete(self, project_id: int) -> bool:
        await _execute_write(
            self._session,
            delete(AuditEventRecord).where(AuditEventRecord.project_id == project_id),
        )
        statement = (
            delete(ProjectRecord)
            .where(ProjectRecord.id == project_id)
            .returning(ProjectRecord.id)
            .execution_options(synchronize_session=False)
        )
        try:
            return await self._session.scalar(statement) is not None
        except (IntegrityError, OperationalError) as error:
            raise_write_conflict(error)

    async def increment_version(
        self,
        project_id: int,
        expected_version: int,
    ) -> int | None:
        statement = (
            update(ProjectRecord)
            .where(
                ProjectRecord.id == project_id,
                ProjectRecord.version == expected_version,
            )
            .values(version=ProjectRecord.version + 1)
            .returning(ProjectRecord.version)
            .execution_options(synchronize_session=False)
        )
        try:
            return cast(int | None, await self._session.scalar(statement))
        except (IntegrityError, OperationalError) as error:
            raise_write_conflict(error)


class SqlAlchemyFeatureRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, feature_id: int) -> Feature | None:
        record = await self._session.get(FeatureRecord, feature_id)
        return None if record is None else _feature_from_record(record)

    async def get_by_project_number(
        self,
        project_id: int,
        feature_number: int,
    ) -> Feature | None:
        record = await self._session.scalar(
            select(FeatureRecord).where(
                FeatureRecord.project_id == project_id,
                FeatureRecord.number == feature_number,
            )
        )
        return None if record is None else _feature_from_record(record)

    async def list_for_project(self, project_id: int) -> list[Feature]:
        records = await self._session.scalars(
            select(FeatureRecord)
            .where(FeatureRecord.project_id == project_id)
            .order_by(FeatureRecord.rank, FeatureRecord.id)
        )
        return [_feature_from_record(record) for record in records]

    async def list_by_ids(
        self,
        project_id: int,
        feature_ids: Sequence[int],
    ) -> list[Feature]:
        if not feature_ids:
            return []
        records = await self._session.scalars(
            select(FeatureRecord).where(
                FeatureRecord.project_id == project_id,
                FeatureRecord.id.in_(feature_ids),
            )
        )
        features = {record.id: _feature_from_record(record) for record in records}
        return [features[feature_id] for feature_id in feature_ids if feature_id in features]

    async def list_future_backlog(self, project_id: int) -> list[Feature]:
        records = await self._session.scalars(
            select(FeatureRecord)
            .where(*_future_backlog_filters(project_id))
            .order_by(FeatureRecord.rank, FeatureRecord.id)
        )
        return [_feature_from_record(record) for record in records]

    async def next_number(self, project_id: int) -> int:
        value = await self._session.scalar(
            select(func.max(FeatureRecord.number)).where(FeatureRecord.project_id == project_id)
        )
        return 1 if value is None else value + 1

    async def next_rank(self, project_id: int) -> int:
        value = await self._session.scalar(
            select(func.max(FeatureRecord.rank)).where(FeatureRecord.project_id == project_id)
        )
        return 1 if value is None else value + 1

    async def add(self, feature: Feature) -> Feature:
        record = _feature_to_record(feature)
        self._session.add(record)
        await _flush(self._session)
        feature.id = record.id
        return feature

    async def reorder_future_backlog(
        self,
        project_id: int,
        ordered_ids: Sequence[int],
    ) -> None:
        rows = (
            await self._session.execute(
                select(FeatureRecord.id, FeatureRecord.rank)
                .where(*_future_backlog_filters(project_id))
                .order_by(FeatureRecord.rank, FeatureRecord.id)
            )
        ).all()
        current_ids = [feature_id for feature_id, _rank in rows]
        validate_exact_order(current_ids, ordered_ids)
        if not ordered_ids:
            return
        maximum_rank = await self._session.scalar(
            select(func.max(FeatureRecord.rank)).where(FeatureRecord.project_id == project_id)
        )
        high_start = (maximum_rank or 0) + 1
        temporary_ranks = {
            feature_id: high_start + index for index, feature_id in enumerate(ordered_ids)
        }
        await self._set_ranks(project_id, temporary_ranks)
        await _flush(self._session)
        rank_slots = sorted(rank for _feature_id, rank in rows)
        final_ranks = dict(zip(ordered_ids, rank_slots, strict=True))
        await self._set_ranks(project_id, final_ranks)

    async def _set_ranks(self, project_id: int, ranks: dict[int, int]) -> None:
        statement = (
            update(FeatureRecord)
            .where(
                FeatureRecord.project_id == project_id,
                FeatureRecord.id.in_(ranks),
            )
            .values(rank=case(ranks, value=FeatureRecord.id))
            .execution_options(synchronize_session=False)
        )
        await _execute_write(self._session, statement)


def _future_backlog_filters(project_id: int) -> tuple[ColumnElement[bool], ...]:
    active_feature_ids = (
        select(SprintFeatureRecord.feature_id)
        .join(SprintRecord, SprintRecord.id == SprintFeatureRecord.sprint_id)
        .where(
            SprintRecord.project_id == project_id,
            SprintRecord.state == SprintState.active.value,
        )
    )
    return (
        FeatureRecord.project_id == project_id,
        FeatureRecord.completed_at.is_(None),
        or_(
            FeatureRecord.engineering_state.is_(None),
            FeatureRecord.engineering_state != EngineeringState.done.value,
        ),
        FeatureRecord.id.not_in(active_feature_ids),
    )


class SqlAlchemySprintRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, sprint_id: int) -> Sprint | None:
        record = await self._session.get(SprintRecord, sprint_id)
        return None if record is None else _sprint_from_record(record)

    async def get_active(self, project_id: int) -> Sprint | None:
        record = await self._session.scalar(
            select(SprintRecord).where(
                SprintRecord.project_id == project_id,
                SprintRecord.state == SprintState.active.value,
            )
        )
        return None if record is None else _sprint_from_record(record)

    async def get_latest_for_feature(
        self,
        project_id: int,
        feature_id: int,
    ) -> Sprint | None:
        record = await self._session.scalar(
            select(SprintRecord)
            .join(
                SprintFeatureRecord,
                SprintFeatureRecord.sprint_id == SprintRecord.id,
            )
            .where(
                SprintRecord.project_id == project_id,
                SprintFeatureRecord.feature_id == feature_id,
            )
            .order_by(
                case(
                    (SprintRecord.state == SprintState.active.value, 0),
                    else_=1,
                ),
                SprintRecord.number.desc(),
                SprintRecord.id.desc(),
            )
        )
        return None if record is None else _sprint_from_record(record)

    async def list_completed(self, project_id: int) -> list[Sprint]:
        records = await self._session.scalars(
            select(SprintRecord)
            .where(
                SprintRecord.project_id == project_id,
                SprintRecord.state == SprintState.completed.value,
            )
            .order_by(SprintRecord.number, SprintRecord.id)
        )
        return [_sprint_from_record(record) for record in records]

    async def next_number(self, project_id: int) -> int:
        value = await self._session.scalar(
            select(func.max(SprintRecord.number)).where(SprintRecord.project_id == project_id)
        )
        return 1 if value is None else value + 1

    async def add(self, sprint: Sprint) -> Sprint:
        record = SprintRecord(
            id=sprint.id,
            project_id=sprint.project_id,
            number=sprint.number,
            name=sprint.name,
            goal=sprint.goal,
            state=sprint.state.value,
            starts_at=sprint.starts_at,
            ends_at=sprint.ends_at,
            created_at=sprint.created_at,
            updated_at=sprint.updated_at,
        )
        self._session.add(record)
        await _flush(self._session)
        sprint.id = record.id
        return sprint

    async def update(self, sprint: Sprint) -> None:
        if sprint.id is None:
            raise ValueError("Cannot update an unpersisted Sprint.")
        await _execute_write(
            self._session,
            update(SprintRecord)
            .where(SprintRecord.id == sprint.id)
            .values(
                project_id=sprint.project_id,
                number=sprint.number,
                name=sprint.name,
                goal=sprint.goal,
                state=sprint.state.value,
                starts_at=sprint.starts_at,
                ends_at=sprint.ends_at,
                created_at=sprint.created_at,
                updated_at=sprint.updated_at,
            )
            .execution_options(synchronize_session=False),
        )

    async def has_feature(self, sprint_id: int, feature_id: int) -> bool:
        membership = await self._session.get(
            SprintFeatureRecord,
            (sprint_id, feature_id),
        )
        return membership is not None

    async def next_feature_rank(self, sprint_id: int) -> int:
        value = await self._session.scalar(
            select(func.max(SprintFeatureRecord.sprint_rank)).where(
                SprintFeatureRecord.sprint_id == sprint_id
            )
        )
        return 1 if value is None else value + 1

    async def add_feature(self, membership: SprintFeature) -> None:
        self._session.add(
            SprintFeatureRecord(
                sprint_id=membership.sprint_id,
                feature_id=membership.feature_id,
                sprint_rank=membership.sprint_rank,
            )
        )
        await _flush(self._session)

    async def list_features(self, sprint_id: int) -> list[Feature]:
        records = await self._session.scalars(
            select(FeatureRecord)
            .join(
                SprintFeatureRecord,
                SprintFeatureRecord.feature_id == FeatureRecord.id,
            )
            .where(SprintFeatureRecord.sprint_id == sprint_id)
            .order_by(SprintFeatureRecord.sprint_rank, FeatureRecord.id)
        )
        return [_feature_from_record(record) for record in records]

    async def reorder_features(
        self,
        sprint_id: int,
        ordered_ids: Sequence[int],
    ) -> None:
        current_ids = list(
            await self._session.scalars(
                select(SprintFeatureRecord.feature_id)
                .where(SprintFeatureRecord.sprint_id == sprint_id)
                .order_by(
                    SprintFeatureRecord.sprint_rank,
                    SprintFeatureRecord.feature_id,
                )
            )
        )
        validate_exact_order(current_ids, ordered_ids)
        if not ordered_ids:
            return
        maximum_rank = await self._session.scalar(
            select(func.max(SprintFeatureRecord.sprint_rank)).where(
                SprintFeatureRecord.sprint_id == sprint_id
            )
        )
        high_start = (maximum_rank or 0) + 1
        temporary_ranks = {
            feature_id: high_start + index for index, feature_id in enumerate(ordered_ids)
        }
        await self._set_feature_ranks(sprint_id, temporary_ranks)
        await _flush(self._session)
        await self._set_feature_ranks(sprint_id, contiguous_ranks(ordered_ids))

    async def _set_feature_ranks(
        self,
        sprint_id: int,
        ranks: dict[int, int],
    ) -> None:
        statement = (
            update(SprintFeatureRecord)
            .where(
                SprintFeatureRecord.sprint_id == sprint_id,
                SprintFeatureRecord.feature_id.in_(ranks),
            )
            .values(
                sprint_rank=case(
                    ranks,
                    value=SprintFeatureRecord.feature_id,
                )
            )
            .execution_options(synchronize_session=False)
        )
        await _execute_write(self._session, statement)


class SqlAlchemyAuditEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, event: AuditEvent) -> AuditEvent:
        record = AuditEventRecord(
            id=event.id,
            project_id=event.project_id,
            feature_id=event.feature_id,
            event_type=event.event_type,
            payload=cast(dict[str, object], event.payload),
            created_at=event.created_at,
        )
        self._session.add(record)
        await _flush(self._session)
        event.id = record.id
        return event

    async def list_for_feature(
        self,
        project_id: int,
        feature_id: int,
    ) -> list[AuditEvent]:
        records = await self._session.scalars(
            select(AuditEventRecord)
            .where(
                AuditEventRecord.project_id == project_id,
                AuditEventRecord.feature_id == feature_id,
            )
            .order_by(AuditEventRecord.created_at, AuditEventRecord.id)
        )
        return [_audit_event_from_record(record) for record in records]


class SqlAlchemyCommandReceiptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self,
        project_id: int,
        idempotency_key: str,
    ) -> CommandReceipt | None:
        record = await self._session.scalar(
            select(CommandReceiptRecord).where(
                CommandReceiptRecord.project_id == project_id,
                CommandReceiptRecord.idempotency_key == idempotency_key,
            )
        )
        return None if record is None else _command_receipt_from_record(record)

    async def add(self, receipt: CommandReceipt) -> CommandReceipt:
        record = CommandReceiptRecord(
            id=receipt.id,
            project_id=receipt.project_id,
            idempotency_key=receipt.idempotency_key,
            command_type=receipt.command_type,
            request_hash=receipt.request_hash,
            result=cast(dict[str, object], receipt.result),
            created_at=receipt.created_at,
        )
        self._session.add(record)
        await _flush(self._session)
        receipt.id = record.id
        return receipt


async def _flush(session: AsyncSession) -> None:
    try:
        await session.flush()
    except (IntegrityError, OperationalError) as error:
        raise_write_conflict(error)


async def _execute_write(session: AsyncSession, statement: Executable) -> None:
    try:
        await session.execute(statement)
    except (IntegrityError, OperationalError) as error:
        raise_write_conflict(error)


def _project_from_record(record: ProjectRecord) -> Project:
    return Project(
        key=record.key,
        name=record.name,
        repository_url=record.repository_url,
        default_branch=record.default_branch,
        created_at=_as_utc(record.created_at),
        updated_at=_as_utc(record.updated_at),
        version=record.version,
        id=record.id,
    )


def _feature_to_record(feature: Feature) -> FeatureRecord:
    return FeatureRecord(
        id=feature.id,
        project_id=feature.project_id,
        number=feature.number,
        title=feature.title,
        description=feature.description,
        rank=feature.rank,
        planning_stage=feature.planning_stage.value,
        engineering_state=(
            None if feature.engineering_state is None else feature.engineering_state.value
        ),
        priority=feature.priority,
        estimate=feature.estimate,
        owner=feature.owner,
        approved_design_hash=feature.approved_design_hash,
        completed_at=feature.completed_at,
        created_at=feature.created_at,
        updated_at=feature.updated_at,
    )


def _feature_from_record(record: FeatureRecord) -> Feature:
    return Feature(
        project_id=record.project_id,
        number=record.number,
        title=record.title,
        description=record.description,
        rank=record.rank,
        planning_stage=PlanningStage(record.planning_stage),
        priority=record.priority,
        estimate=record.estimate,
        owner=record.owner,
        approved_design_hash=record.approved_design_hash,
        completed_at=_optional_utc(record.completed_at),
        created_at=_as_utc(record.created_at),
        updated_at=_as_utc(record.updated_at),
        engineering_state=(
            None if record.engineering_state is None else EngineeringState(record.engineering_state)
        ),
        id=record.id,
    )


def _sprint_from_record(record: SprintRecord) -> Sprint:
    return Sprint(
        project_id=record.project_id,
        number=record.number,
        name=record.name,
        goal=record.goal,
        state=SprintState(record.state),
        starts_at=_optional_utc(record.starts_at),
        ends_at=_optional_utc(record.ends_at),
        created_at=_as_utc(record.created_at),
        updated_at=_as_utc(record.updated_at),
        id=record.id,
    )


def _audit_event_from_record(record: AuditEventRecord) -> AuditEvent:
    return AuditEvent(
        project_id=record.project_id,
        feature_id=record.feature_id,
        event_type=record.event_type,
        payload=cast(dict[str, JsonValue], record.payload),
        created_at=_as_utc(record.created_at),
        id=record.id,
    )


def _command_receipt_from_record(record: CommandReceiptRecord) -> CommandReceipt:
    return CommandReceipt(
        project_id=record.project_id,
        idempotency_key=record.idempotency_key,
        command_type=record.command_type,
        request_hash=record.request_hash,
        result=cast(dict[str, JsonValue], record.result),
        created_at=_as_utc(record.created_at),
        id=record.id,
    )


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _optional_utc(value: datetime | None) -> datetime | None:
    return None if value is None else _as_utc(value)

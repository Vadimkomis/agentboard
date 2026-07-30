"""Ranked Project backlog commands and queries."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import datetime

from agentboard.application._support import Clock, persisted_id, require_text, utc_now
from agentboard.application.ports import UnitOfWork, UnitOfWorkFactory
from agentboard.domain.entities import AuditEvent, CommandReceipt, Feature, Project
from agentboard.domain.errors import (
    CrossProjectFeatureError,
    DuplicateIdentifiersError,
    FeatureNotFoundError,
    IdempotencyConflictError,
    ProjectNotFoundError,
    StaleRecordVersionError,
)
from agentboard.domain.ranking import validate_exact_order

_REORDER_COMMAND = "backlog.reorder"


class ListProjectBacklog:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def __call__(self, *, project_id: int) -> list[Feature]:
        async with self._uow_factory() as uow:
            if await uow.projects.get(project_id) is None:
                raise ProjectNotFoundError(project_id)
            return await uow.features.list_future_backlog(project_id)


class ReorderProjectBacklog:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock = utc_now) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self,
        *,
        project_id: int,
        feature_ids: Sequence[int],
        expected_version: int | None = None,
        idempotency_key: str | None = None,
    ) -> list[Feature]:
        normalized_key = _normalize_idempotency_key(idempotency_key)
        request_hash = _request_hash(feature_ids, expected_version)
        async with self._uow_factory() as uow:
            await _ensure_project(uow, project_id)
            replay = await _find_replay(uow, project_id, normalized_key, request_hash)
            if replay is not None:
                return replay
            current = await uow.features.list_future_backlog(project_id)
            await _validate_requested_features(uow, project_id, current, feature_ids)
            await _increment_version(uow, project_id, expected_version)
            await uow.features.reorder_future_backlog(project_id, feature_ids)
            now = self._clock()
            await uow.audit_events.add(_reorder_event(project_id, feature_ids, now))
            await _add_receipt(
                uow,
                project_id,
                normalized_key,
                request_hash,
                feature_ids,
                now,
            )
            await uow.commit()
            return await uow.features.list_future_backlog(project_id)


async def _ensure_project(uow: UnitOfWork, project_id: int) -> Project:
    project = await uow.projects.get(project_id)
    if project is None:
        raise ProjectNotFoundError(project_id)
    return project


async def _find_replay(
    uow: UnitOfWork,
    project_id: int,
    idempotency_key: str | None,
    request_hash: str,
) -> list[Feature] | None:
    if idempotency_key is None:
        return None
    receipt = await uow.command_receipts.get(project_id, idempotency_key)
    if receipt is None:
        return None
    if receipt.command_type != _REORDER_COMMAND or receipt.request_hash != request_hash:
        raise IdempotencyConflictError
    feature_ids = _receipt_feature_ids(receipt)
    features = await uow.features.list_by_ids(project_id, feature_ids)
    if len(features) != len(feature_ids):
        raise RuntimeError("The persisted backlog reorder receipt refers to missing Features.")
    return features


async def _increment_version(
    uow: UnitOfWork,
    project_id: int,
    expected_version: int | None,
) -> None:
    if expected_version is None:
        return
    version = await uow.projects.increment_version(project_id, expected_version)
    if version is None:
        raise StaleRecordVersionError(expected_version)


async def _add_receipt(
    uow: UnitOfWork,
    project_id: int,
    idempotency_key: str | None,
    request_hash: str,
    feature_ids: Sequence[int],
    created_at: datetime,
) -> None:
    if idempotency_key is None:
        return
    await uow.command_receipts.add(
        CommandReceipt(
            project_id=project_id,
            idempotency_key=idempotency_key,
            command_type=_REORDER_COMMAND,
            request_hash=request_hash,
            result={"feature_ids": list(feature_ids)},
            created_at=created_at,
        )
    )


async def _validate_requested_features(
    uow: UnitOfWork,
    project_id: int,
    current: Sequence[Feature],
    requested: Sequence[int],
) -> None:
    if len(requested) != len(set(requested)):
        raise DuplicateIdentifiersError
    current_ids = [persisted_id(feature.id) for feature in current]
    current_id_set = set(current_ids)
    for feature_id in requested:
        if feature_id in current_id_set:
            continue
        feature = await uow.features.get(feature_id)
        if feature is None:
            raise FeatureNotFoundError(feature_id)
        if feature.project_id != project_id:
            raise CrossProjectFeatureError(feature_id)
    validate_exact_order(current_ids, requested)


def _reorder_event(
    project_id: int,
    feature_ids: Sequence[int],
    created_at: datetime,
) -> AuditEvent:
    return AuditEvent(
        project_id=project_id,
        event_type="backlog.reordered",
        payload={"feature_ids": list(feature_ids)},
        created_at=created_at,
    )


def _normalize_idempotency_key(value: str | None) -> str | None:
    if value is None:
        return None
    return require_text(value, "Idempotency key")


def _request_hash(feature_ids: Sequence[int], expected_version: int | None) -> str:
    encoded = json.dumps(
        {
            "expected_version": expected_version,
            "feature_ids": list(feature_ids),
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _receipt_feature_ids(receipt: CommandReceipt) -> list[int]:
    feature_ids = receipt.result.get("feature_ids")
    if not isinstance(feature_ids, list):
        raise RuntimeError("The persisted backlog reorder receipt is malformed.")
    identifiers: list[int] = []
    for feature_id in feature_ids:
        if not isinstance(feature_id, int) or isinstance(feature_id, bool):
            raise RuntimeError("The persisted backlog reorder receipt is malformed.")
        identifiers.append(feature_id)
    return identifiers

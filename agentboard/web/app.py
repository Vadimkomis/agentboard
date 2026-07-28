"""FastAPI composition root for the project-scoped browser experience."""

from __future__ import annotations

import secrets
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, cast
from urllib.parse import parse_qsl

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.trustedhost import TrustedHostMiddleware

from agentboard.application import (
    GetProjectFeature,
    GetProjectWorkspace,
    ListProjectApprovals,
    ListProjectReports,
    ListProjects,
    ReorderProjectBacklog,
    presented_engineering_state,
)
from agentboard.application.ports import UnitOfWorkFactory
from agentboard.application.views import ProjectWorkspace
from agentboard.domain.entities import Feature
from agentboard.domain.enums import EngineeringState, SprintState
from agentboard.domain.errors import (
    DomainError,
    FeatureNotFoundError,
    IdempotencyConflictError,
    PersistenceConflictError,
    ProjectNotFoundError,
    StaleRecordVersionError,
)
from agentboard.infrastructure.database import Database
from agentboard.infrastructure.migrations import upgrade_database_async
from agentboard.web.security import (
    CsrfSession,
    generate_csrf_token,
    sign_session,
    verify_csrf_token,
    verify_session,
)
from agentboard.web.settings import WebSettings

_WEB_ROOT = Path(__file__).resolve().parent
_TEMPLATES = Jinja2Templates(directory=_WEB_ROOT / "templates")
_TEMPLATES.env.globals["presented_engineering_state"] = presented_engineering_state
_BOARD_STATES = (
    EngineeringState.ready_for_engineering,
    EngineeringState.working,
    EngineeringState.in_review,
    EngineeringState.human_review,
    EngineeringState.ready_to_merge,
)
_FORM_CONTENT_TYPE = "application/x-www-form-urlencoded"
_MAX_FORM_BYTES = 16_384


def create_app(settings: WebSettings) -> FastAPI:
    """Build one browser application with instance-scoped persistence."""

    app = FastAPI(
        title="AgentBoard",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=_lifespan(settings),
    )
    app.state.web_settings = settings
    _add_csrf_session(app)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts))
    _add_security_headers(app)
    app.mount("/static", StaticFiles(directory=_WEB_ROOT / "static"), name="static")
    _register_routes(app)
    _register_not_found_handlers(app)
    return app


def _lifespan(settings: WebSettings) -> Any:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await upgrade_database_async(settings.database_path)
        database = Database(settings.database_path)
        app.state.database = database
        try:
            yield
        finally:
            await database.dispose()

    return lifespan


def _add_csrf_session(app: FastAPI) -> None:
    @app.middleware("http")
    async def csrf_session(request: Request, call_next: Any) -> Response:
        settings = _settings(request)
        claims = verify_session(
            settings.session_secret,
            request.cookies.get(settings.session_cookie_name),
        )
        token: str | None = None
        if claims is None:
            claims, token = _new_csrf_session(settings)
        request.state.csrf_session = claims
        response = cast(Response, await call_next(request))
        if token is not None:
            _set_session_cookie(response, settings, token)
        return response


def _add_security_headers(app: FastAPI) -> None:
    @app.middleware("http")
    async def security_headers(request: Request, call_next: Any) -> Response:
        response = cast(Response, await call_next(request))
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; base-uri 'none'; frame-ancestors 'none'; "
            "form-action 'self'; object-src 'none'; script-src 'self'; "
            "style-src 'self'; img-src 'self' data:"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Cache-Control"] = "no-store"
        return response


def _register_routes(app: FastAPI) -> None:
    app.add_api_route("/", _root, methods=["GET"], include_in_schema=False)
    app.add_api_route("/projects", _projects, methods=["GET"], response_class=HTMLResponse)
    app.add_api_route(
        "/projects/{project_key}/backlog",
        _backlog,
        methods=["GET"],
        response_class=HTMLResponse,
    )
    app.add_api_route(
        "/projects/{project_key}/backlog/reorder",
        _reorder_backlog,
        methods=["POST"],
        response_class=HTMLResponse,
    )
    app.add_api_route(
        "/projects/{project_key}/board",
        _board,
        methods=["GET"],
        response_class=HTMLResponse,
    )
    app.add_api_route(
        "/projects/{project_key}/features/{feature_number}",
        _feature_detail,
        methods=["GET"],
        response_class=HTMLResponse,
    )
    app.add_api_route(
        "/projects/{project_key}/approvals",
        _approvals,
        methods=["GET"],
        response_class=HTMLResponse,
    )
    app.add_api_route(
        "/projects/{project_key}/reports",
        _reports,
        methods=["GET"],
        response_class=HTMLResponse,
    )


def _register_not_found_handlers(app: FastAPI) -> None:
    @app.exception_handler(ProjectNotFoundError)
    async def project_not_found(_request: Request, _error: ProjectNotFoundError) -> Response:
        return PlainTextResponse("Not found", status_code=status.HTTP_404_NOT_FOUND)

    @app.exception_handler(FeatureNotFoundError)
    async def feature_not_found(_request: Request, _error: FeatureNotFoundError) -> Response:
        return PlainTextResponse("Not found", status_code=status.HTTP_404_NOT_FOUND)


async def _root(_claims: Annotated[CsrfSession, Depends(_csrf_session)]) -> Response:
    return RedirectResponse("/projects", status_code=status.HTTP_303_SEE_OTHER)


async def _projects(
    request: Request,
    claims: Annotated[CsrfSession, Depends(_csrf_session)],
) -> Response:
    projects = await ListProjects(_uow_factory(request))()
    context = {
        **_base_context(request),
        "csrf_token": claims.csrf_token,
        "projects": projects,
    }
    return _TEMPLATES.TemplateResponse(request, "projects.html", context)


async def _backlog(
    request: Request,
    project_key: str,
    claims: Annotated[CsrfSession, Depends(_csrf_session)],
) -> Response:
    workspace = await _workspace(request, project_key)
    context = await _workspace_context(request, workspace, claims, "backlog")
    return _TEMPLATES.TemplateResponse(request, "backlog.html", context)


async def _board(
    request: Request,
    project_key: str,
    claims: Annotated[CsrfSession, Depends(_csrf_session)],
) -> Response:
    workspace = await _workspace(request, project_key)
    columns, done = _board_features(workspace)
    context = await _workspace_context(request, workspace, claims, "board")
    context.update({"board_columns": columns, "done_features": done})
    return _TEMPLATES.TemplateResponse(request, "board.html", context)


async def _feature_detail(
    request: Request,
    project_key: str,
    feature_number: int,
    claims: Annotated[CsrfSession, Depends(_csrf_session)],
) -> Response:
    factory = _uow_factory(request)
    detail = await GetProjectFeature(factory)(
        project_key=project_key,
        feature_number=feature_number,
    )
    approvals = await ListProjectApprovals(factory)(project_key=project_key)
    context = {
        **_base_context(request),
        "active_page": "",
        "active_sprint_member": (
            detail.sprint is not None and detail.sprint.state is SprintState.active
        ),
        "approval_count": len(approvals),
        "csrf_token": claims.csrf_token,
        "detail": detail,
        "project": detail.project,
    }
    return _TEMPLATES.TemplateResponse(request, "feature_detail.html", context)


async def _approvals(
    request: Request,
    project_key: str,
    claims: Annotated[CsrfSession, Depends(_csrf_session)],
) -> Response:
    workspace = await _workspace(request, project_key)
    approvals = await ListProjectApprovals(_uow_factory(request))(project_key=project_key)
    context = await _workspace_context(request, workspace, claims, "approvals")
    context["approvals"] = approvals
    return _TEMPLATES.TemplateResponse(request, "approvals.html", context)


async def _reports(
    request: Request,
    project_key: str,
    claims: Annotated[CsrfSession, Depends(_csrf_session)],
) -> Response:
    workspace = await _workspace(request, project_key)
    reports = await ListProjectReports(_uow_factory(request))(project_key=project_key)
    context = await _workspace_context(request, workspace, claims, "reports")
    context["reports"] = reports
    return _TEMPLATES.TemplateResponse(request, "reports.html", context)


async def _reorder_backlog(
    request: Request,
    project_key: str,
    claims: Annotated[CsrfSession, Depends(_csrf_session)],
) -> Response:
    workspace = await _workspace(request, project_key)
    form = await _reorder_form(request)
    _require_csrf(claims, _single_value(form, "csrf_token"))
    try:
        feature_ids, expected_version, idempotency_key = _reorder_values(form)
        await ReorderProjectBacklog(_uow_factory(request))(
            project_id=_project_id(workspace),
            feature_ids=feature_ids,
            expected_version=expected_version,
            idempotency_key=idempotency_key,
        )
    except (StaleRecordVersionError, IdempotencyConflictError, PersistenceConflictError) as error:
        return await _reorder_error(request, project_key, claims, error, status.HTTP_409_CONFLICT)
    except DomainError as error:
        return await _reorder_error(
            request, project_key, claims, error, status.HTTP_400_BAD_REQUEST
        )
    return RedirectResponse(
        f"/projects/{project_key}/backlog",
        status_code=status.HTTP_303_SEE_OTHER,
    )


async def _workspace(request: Request, project_key: str) -> ProjectWorkspace:
    return await GetProjectWorkspace(_uow_factory(request))(project_key=project_key)


async def _workspace_context(
    request: Request,
    workspace: ProjectWorkspace,
    claims: CsrfSession,
    active_page: str,
) -> dict[str, Any]:
    approvals = await ListProjectApprovals(_uow_factory(request))(project_key=workspace.project.key)
    _, done_features = _board_features(workspace)
    sprint_features = workspace.active_sprint.features if workspace.active_sprint else ()
    active_features = [feature for feature in sprint_features if not _is_completed(feature)]
    return {
        **_base_context(request),
        "active_page": active_page,
        "active_features": active_features,
        "active_sprint": workspace.active_sprint,
        "approval_count": len(approvals),
        "csrf_token": claims.csrf_token,
        "expected_version": workspace.project.version,
        "future_backlog": workspace.future_backlog,
        "idempotency_key": secrets.token_urlsafe(24),
        "project": workspace.project,
        "done_features": done_features,
    }


def _board_features(
    workspace: ProjectWorkspace,
) -> tuple[dict[str, list[Feature]], list[Feature]]:
    columns: dict[str, list[Feature]] = {state.value: [] for state in _BOARD_STATES}
    done: list[Feature] = []
    features = workspace.active_sprint.features if workspace.active_sprint else ()
    for feature in features:
        state = presented_engineering_state(feature, in_active_sprint=True)
        if state is EngineeringState.done:
            done.append(feature)
            continue
        assert state is not None
        columns[state.value].append(feature)
    return columns, done


def _is_completed(feature: Feature) -> bool:
    return feature.completed_at is not None or feature.engineering_state is EngineeringState.done


async def _reorder_error(
    request: Request,
    project_key: str,
    claims: CsrfSession,
    error: DomainError,
    status_code: int,
) -> Response:
    workspace = await _workspace(request, project_key)
    context = await _workspace_context(request, workspace, claims, "backlog")
    message = _safe_reorder_message(error)
    context["flash"] = {"kind": "error", "message": message}
    return _TEMPLATES.TemplateResponse(
        request,
        "backlog.html",
        context,
        status_code=status_code,
    )


def _safe_reorder_message(error: DomainError) -> str:
    if isinstance(error, StaleRecordVersionError):
        return (
            "The backlog changed in another browser session. Review the latest order and try again."
        )
    if isinstance(error, (IdempotencyConflictError, PersistenceConflictError)):
        return "This change conflicts with another request. Reload the backlog and try again."
    return "The submitted order is not the exact current future backlog."


def _csrf_session(request: Request) -> CsrfSession:
    claims = cast(CsrfSession | None, request.state.csrf_session)
    if claims is None:
        raise RuntimeError("Browser session middleware did not initialize a session.")
    return claims


def _new_csrf_session(settings: WebSettings) -> tuple[CsrfSession, str]:
    now = int(time.time())
    csrf_token = generate_csrf_token()
    claims = CsrfSession(
        csrf_token=csrf_token,
        issued_at=now,
        expires_at=now + settings.session_ttl_seconds,
    )
    token = sign_session(
        settings.session_secret,
        csrf_token=csrf_token,
        now=now,
        ttl_seconds=settings.session_ttl_seconds,
    )
    return claims, token


def _set_session_cookie(
    response: Response,
    settings: WebSettings,
    token: str,
) -> None:
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_ttl_seconds,
        path="/",
        secure=settings.secure_cookies,
        httponly=True,
        samesite="strict",
    )


async def _reorder_form(request: Request) -> dict[str, list[str]]:
    _require_form_content_type(request)
    body = await _bounded_body(request)
    try:
        text = body.decode("utf-8")
        pairs = parse_qsl(
            text,
            keep_blank_values=True,
            strict_parsing=True,
            encoding="utf-8",
            errors="strict",
            max_num_fields=64,
        )
    except (UnicodeDecodeError, ValueError) as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST) from error
    values: dict[str, list[str]] = {}
    for key, value in pairs:
        values.setdefault(key, []).append(value)
    return values


async def _bounded_body(request: Request) -> bytes:
    declared_length = _content_length(request)
    if declared_length is not None and declared_length > _MAX_FORM_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > _MAX_FORM_BYTES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)
    return bytes(body)


def _content_length(request: Request) -> int | None:
    value = request.headers.get("content-length")
    if value is None:
        return None
    try:
        length = int(value)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST) from error
    if length < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)
    return length


def _reorder_values(form: dict[str, list[str]]) -> tuple[list[int], int, str]:
    version_text = _single_value(form, "expected_version")
    idempotency_key = _single_value(form, "idempotency_key")
    raw_feature_ids = form.get("feature_ids")
    if version_text is None or idempotency_key is None or raw_feature_ids is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)
    expected_version = _positive_integer(version_text)
    feature_ids = _feature_identifiers(raw_feature_ids)
    if not idempotency_key.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)
    return feature_ids, expected_version, idempotency_key


def _feature_identifiers(values: list[str]) -> list[int]:
    segments = [segment.strip() for value in values for segment in value.split(",")]
    if segments == [""]:
        return []
    if not segments or any(not segment for segment in segments):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)
    return [_positive_integer(segment) for segment in segments]


def _positive_integer(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST) from error
    if parsed <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)
    return parsed


def _single_value(form: dict[str, list[str]], name: str) -> str | None:
    values = form.get(name)
    if values is None:
        return None
    if len(values) != 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)
    return values[0]


def _require_csrf(claims: CsrfSession, submitted: str | None) -> None:
    if not verify_csrf_token(claims.csrf_token, submitted):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)


def _require_form_content_type(request: Request) -> None:
    content_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
    if content_type != _FORM_CONTENT_TYPE:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)


def _project_id(workspace: ProjectWorkspace) -> int:
    if workspace.project.id is None:
        raise RuntimeError("A persisted Project must have an identifier.")
    return workspace.project.id


def _base_context(request: Request) -> dict[str, Any]:
    return {
        "request": request,
        "project": None,
        "active_page": "",
        "approval_count": 0,
        "csrf_token": None,
        "flash": None,
    }


def _database(request: Request) -> Database:
    return cast(Database, request.app.state.database)


def _uow_factory(request: Request) -> UnitOfWorkFactory:
    return _database(request).unit_of_work


def _settings(request: Request) -> WebSettings:
    return cast(WebSettings, request.app.state.web_settings)

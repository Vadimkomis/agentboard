"""HTTP regression tests for the project-scoped browser experience."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from sqlalchemy import update

from agentboard.application import (
    AddFeatureToSprint,
    CreateFeature,
    CreatePlannedSprint,
    CreateProject,
    SeedDemoWorkspace,
    StartSprint,
)
from agentboard.domain.enums import EngineeringState, PlanningStage, SprintState
from agentboard.infrastructure.database import Database
from agentboard.infrastructure.migrations import upgrade_database
from agentboard.infrastructure.orm import FeatureRecord, SprintRecord
from agentboard.web import WebSettings, create_app

NOW = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)


@pytest.fixture
async def seeded_web_path(tmp_path: Path) -> Path:
    path = tmp_path / "browser-web.db"
    upgrade_database(path)
    await _seed(path)
    return path


@pytest.fixture
async def seeded_demo_path(tmp_path: Path) -> Path:
    path = tmp_path / "browser-demo.db"
    upgrade_database(path)
    database = Database(path)
    try:
        await SeedDemoWorkspace(database.unit_of_work, lambda: NOW)()
    finally:
        await database.dispose()
    return path


@pytest.fixture
async def web_client(seeded_web_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    settings = WebSettings(
        database_path=seeded_web_path,
        session_secret="test-session-secret-that-is-long-enough-for-hmac",
        allowed_hosts=("testserver",),
        secure_cookies=False,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
            follow_redirects=True,
        ) as client:
            yield client


async def _seed(path: Path) -> None:
    database = Database(path)
    try:
        project_a = await CreateProject(database.unit_of_work, lambda: NOW)(
            key="AB",
            name="AgentBoard",
            repository_url="https://github.com/example/agentboard",
            default_branch="main",
        )
        project_b = await CreateProject(database.unit_of_work, lambda: NOW)(
            key="TJ",
            name="Trail Journal",
            repository_url="https://github.com/example/trail-journal",
            default_branch="main",
        )
        future = await CreateFeature(database.unit_of_work, lambda: NOW)(
            project_id=project_a.id,
            title="<Future & safe>",
            description="<script>window.evil = true</script> Useful description.",
            planning_stage=PlanningStage.design_review,
            priority="highest",
            estimate=None,
            owner=None,
        )
        current = await CreateFeature(database.unit_of_work, lambda: NOW)(
            project_id=project_a.id,
            title="Current sprint item",
            description="Build the browser.",
            planning_stage=PlanningStage.design_review,
            priority="high",
            estimate=5,
            owner="Vadim",
            approved_design_hash="design-current",
        )
        human_review = await CreateFeature(database.unit_of_work, lambda: NOW)(
            project_id=project_a.id,
            title="Human review item",
            description="Needs owner attention.",
            planning_stage=PlanningStage.design_review,
            priority="high",
            estimate=3,
            owner="Vadim",
            approved_design_hash="design-review",
        )
        done = await CreateFeature(database.unit_of_work, lambda: NOW)(
            project_id=project_a.id,
            title="Done this sprint",
            description="Completed work.",
            planning_stage=PlanningStage.design_review,
            priority="medium",
            estimate=2,
            owner="Vadim",
            approved_design_hash="design-done",
        )
        await CreateFeature(database.unit_of_work, lambda: NOW)(
            project_id=project_a.id,
            title="Second future item",
            description="Reorder this future work.",
            planning_stage=PlanningStage.design,
            priority="medium",
            estimate=2,
            owner="Vadim",
            approved_design_hash="design-future",
        )
        await CreateFeature(database.unit_of_work, lambda: NOW)(
            project_id=project_b.id,
            title="PROJECT_B_MUST_NOT_LEAK",
            description="Private to project B.",
            planning_stage=PlanningStage.inbox,
            priority="low",
        )
        sprint = await CreatePlannedSprint(database.unit_of_work, lambda: NOW)(
            project_id=project_a.id,
            name="Sprint 1",
            goal="Deliver the browser experience",
        )
        for feature in (current, human_review, done):
            await AddFeatureToSprint(database.unit_of_work, lambda: NOW)(
                sprint_id=sprint.id,
                feature_id=feature.id,
            )
        await StartSprint(database.unit_of_work, lambda: NOW)(sprint_id=sprint.id)
        report_feature = await CreateFeature(database.unit_of_work, lambda: NOW)(
            project_id=project_a.id,
            title="Reported feature",
            description="Preserved history.",
            planning_stage=PlanningStage.design_review,
            priority="medium",
            estimate=1,
            owner="Vadim",
            approved_design_hash="design-report",
        )
        report_sprint = await CreatePlannedSprint(database.unit_of_work, lambda: NOW)(
            project_id=project_a.id,
            name="Sprint 0",
        )
        await AddFeatureToSprint(database.unit_of_work, lambda: NOW)(
            sprint_id=report_sprint.id,
            feature_id=report_feature.id,
        )
        async with database.session() as session:
            await session.execute(
                update(FeatureRecord)
                .where(FeatureRecord.id == human_review.id)
                .values(engineering_state=EngineeringState.human_review.value)
            )
            await session.execute(
                update(FeatureRecord)
                .where(FeatureRecord.id == done.id)
                .values(engineering_state=EngineeringState.done.value, completed_at=NOW)
            )
            await session.execute(
                update(FeatureRecord)
                .where(FeatureRecord.id == report_feature.id)
                .values(engineering_state=EngineeringState.done.value, completed_at=NOW)
            )
            await session.execute(
                update(SprintRecord)
                .where(SprintRecord.id == report_sprint.id)
                .values(state=SprintState.completed.value, ends_at=NOW)
            )
            await session.commit()
        assert future.number == 1
    finally:
        await database.dispose()


async def test_loopback_default_opens_without_login_and_retains_csrf(
    web_client: httpx.AsyncClient,
) -> None:
    projects = await web_client.get("/projects")
    backlog = await web_client.get("/projects/AB/backlog")
    csrf = _hidden_value(backlog.text, "csrf_token")
    rejected = await web_client.post(
        "/projects/AB/backlog/reorder",
        data={
            "expected_version": "1",
            "idempotency_key": "missing-local-csrf",
            "feature_ids": ["5", "1"],
        },
    )

    assert projects.status_code == 200
    assert "agentboard_session" in projects.cookies
    assert 'action="/logout"' not in projects.text
    assert backlog.status_code == 200
    assert csrf
    assert rejected.status_code == 403


async def test_browser_replaces_an_invalid_csrf_session(
    web_client: httpx.AsyncClient,
) -> None:
    web_client.cookies.set("agentboard_session", "tampered")

    response = await web_client.get("/projects")

    assert response.status_code == 200
    assert response.cookies["agentboard_session"] != "tampered"


async def test_password_authentication_routes_are_not_exposed(
    web_client: httpx.AsyncClient,
) -> None:
    login_page = await web_client.get("/login")
    login_submission = await web_client.post(
        "/login",
        data={"password": "unneeded"},
    )
    logout = await web_client.post("/logout")

    assert login_page.status_code == 404
    assert login_submission.status_code == 404
    assert logout.status_code == 404


async def test_seeded_demo_renders_representative_data_in_every_browser_view(
    seeded_demo_path: Path,
) -> None:
    settings = WebSettings(
        database_path=seeded_demo_path,
        session_secret="test-session-secret-that-is-long-enough-for-hmac",
        allowed_hosts=("testserver",),
        secure_cookies=False,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            backlog = await client.get("/projects/DEMO/backlog")
            board = await client.get("/projects/DEMO/board")
            feature = await client.get("/projects/DEMO/features/2")
            approvals = await client.get("/projects/DEMO/approvals")
            reports = await client.get("/projects/DEMO/reports")

    assert all(
        response.status_code == 200 for response in (backlog, board, feature, approvals, reports)
    )
    assert "Current Sprint" in backlog.text
    assert "Define notification preferences" in backlog.text
    assert "data-reorder-form" in backlog.text
    assert board.text.count("data-board-column=") == 5
    assert "Publish seeded workspace" in board.text
    assert "Prepare browser workspace" in feature.text
    assert "Design approval" in approvals.text
    assert "Approve release candidate" in approvals.text
    assert "Sprint 1" in reports.text
    assert "Ship project foundation" in reports.text


async def test_project_selector_is_deterministic_and_links_scoped_routes(
    web_client: httpx.AsyncClient,
) -> None:
    response = await web_client.get("/projects")

    assert response.status_code == 200
    assert response.text.index("AgentBoard") < response.text.index("Trail Journal")
    assert 'href="/projects/AB/backlog"' in response.text
    assert 'href="/projects/TJ/backlog"' in response.text


async def test_backlog_renders_current_sprint_before_future_work_without_leakage(
    web_client: httpx.AsyncClient,
) -> None:
    response = await web_client.get("/projects/AB/backlog")

    assert response.status_code == 200
    assert "data-reorder-form" in response.text
    assert 'data-reorder-enabled="true"' in response.text
    assert response.text.count('data-drag-handle draggable="true"') == 2
    assert "hx-" not in response.text
    assert response.text.index("Current Sprint") < response.text.index("Future backlog")
    assert "Current sprint item" in response.text
    assert "&lt;Future &amp; safe&gt;" in response.text
    for field in ("Planning stage", "Priority", "Estimate", "Owner", "Readiness"):
        assert field in response.text
    assert "PROJECT_B_MUST_NOT_LEAK" not in response.text


async def test_active_sprint_uses_sprint_label_and_combines_merge_ready_with_done(
    web_client: httpx.AsyncClient,
    seeded_web_path: Path,
) -> None:
    database = Database(seeded_web_path)
    try:
        async with database.session() as session:
            await session.execute(
                update(FeatureRecord)
                .where(FeatureRecord.id == 2)
                .values(engineering_state=EngineeringState.ready_to_merge.value)
            )
            await session.commit()
    finally:
        await database.dispose()

    response = await web_client.get("/projects/AB/board")

    assert response.status_code == 200
    states = [
        "ready_for_engineering",
        "working",
        "in_review",
        "human_review",
        "done",
    ]
    positions = [response.text.index(f'data-board-column="{state}"') for state in states]
    done_column = response.text.split('data-board-column="done"', 1)[1]
    assert positions == sorted(positions)
    assert response.text.count("data-board-column=") == 5
    assert 'data-board-column="ready_to_merge"' not in response.text
    assert 'data-completed-section="true"' not in response.text
    assert "Current sprint item" in done_column
    assert "Done this sprint" in done_column
    assert "<title>Sprint · AgentBoard · AgentBoard</title>" in response.text
    assert "<h1>Sprint</h1>" in response.text
    assert "<span>Sprint</span>" in response.text
    assert "<h1>Board</h1>" not in response.text
    assert "<span>Board</span>" not in response.text
    assert "PROJECT_B_MUST_NOT_LEAK" not in response.text


async def test_active_sprint_default_state_is_consistent_across_browser_views(
    web_client: httpx.AsyncClient,
) -> None:
    backlog = await web_client.get("/projects/AB/backlog")
    board = await web_client.get("/projects/AB/board")
    detail = await web_client.get("/projects/AB/features/2")
    future_detail = await web_client.get("/projects/AB/features/5")

    backlog_row = backlog.text.split('data-feature-number="2"', 1)[1].split("</article>", 1)[0]
    ready_column = board.text.split('data-board-column="ready_for_engineering"', 1)[1].split(
        'data-board-column="working"', 1
    )[0]

    assert "Ready for Engineering" in backlog_row
    assert "Current sprint item" in ready_column
    assert '<span class="detail-state">Ready for Engineering</span>' in detail.text
    assert "<span>Sprint</span>" in backlog.text
    assert "<span>Sprint</span>" in detail.text
    assert "Second future item" not in board.text
    assert "Ready for sprint" in future_detail.text


async def test_completion_timestamp_moves_active_sprint_work_to_done_column(
    web_client: httpx.AsyncClient,
    seeded_web_path: Path,
) -> None:
    async def mark_completed() -> None:
        database = Database(seeded_web_path)
        try:
            async with database.session() as session:
                await session.execute(
                    update(FeatureRecord)
                    .where(FeatureRecord.id == 2)
                    .values(completed_at=NOW, engineering_state=None)
                )
                await session.commit()
        finally:
            await database.dispose()

    await mark_completed()
    board = await web_client.get("/projects/AB/board")
    backlog = await web_client.get("/projects/AB/backlog")

    assert board.text.index("Current sprint item") > board.text.index('data-board-column="done"')
    assert 'data-completed-section="true"' not in board.text
    assert backlog.text.index("Current sprint item") > backlog.text.index(
        'data-completed-section="true"'
    )


async def test_feature_detail_is_escaped_and_cross_project_safe(
    web_client: httpx.AsyncClient,
) -> None:
    response = await web_client.get("/projects/AB/features/1")

    assert response.status_code == 200
    assert "&lt;Future &amp; safe&gt;" in response.text
    assert "&lt;script&gt;window.evil = true&lt;/script&gt;" in response.text
    assert "<script>window.evil = true</script>" not in response.text
    assert "Recent history" in response.text
    assert (await web_client.get("/projects/TJ/features/2")).status_code == 404


async def test_approvals_show_durable_attention_without_inventing_revisions(
    web_client: httpx.AsyncClient,
) -> None:
    response = await web_client.get("/projects/AB/approvals")

    assert response.status_code == 200
    assert "attention items" in response.text
    assert "Potential decisions awaiting immutable evidence" in response.text
    assert "Design approval" in response.text
    assert "&lt;Future &amp; safe&gt;" in response.text
    assert "Pull request approval" in response.text
    assert "Human review item" in response.text
    assert "Exact revision unavailable" in response.text
    assert "PROJECT_B_MUST_NOT_LEAK" not in response.text


async def test_reports_render_only_completed_sprint_history(
    web_client: httpx.AsyncClient,
) -> None:
    response = await web_client.get("/projects/AB/reports")

    assert response.status_code == 200
    assert "Sprint 0" in response.text
    assert "Reported feature" in response.text
    assert "Vadim" in response.text
    assert "Done this sprint" not in response.text
    assert "PROJECT_B_MUST_NOT_LEAK" not in response.text


async def test_unknown_or_cross_project_resources_are_not_found(
    web_client: httpx.AsyncClient,
) -> None:
    assert (await web_client.get("/projects/missing/backlog")).status_code == 404
    assert (await web_client.get("/projects/AB/features/999")).status_code == 404


async def test_theme_and_interaction_assets_exclude_unused_htmx(
    web_client: httpx.AsyncClient,
) -> None:
    page = await web_client.get("/projects/AB/board")
    css = await web_client.get("/static/app.css")
    javascript = await web_client.get("/static/app.js")
    htmx = await web_client.get("/static/htmx.min.js")

    assert 'data-theme-toggle="true"' in page.text
    assert 'src="/static/app.js"' in page.text
    assert "htmx" not in page.text.lower()
    assert "https://unpkg.com" not in page.text
    assert css.status_code == 200
    assert "--page:" in css.text
    assert '[data-theme="light"]' in css.text
    rank_buttons = css.text.split(".rank-buttons {", 1)[1].split("}", 1)[0]
    rank_button = css.text.split(".rank-button {", 1)[1].split("}", 1)[0]
    assert "gap: 4px;" in rank_buttons
    assert "width: 32px;" in rank_button
    assert "height: 32px;" in rank_button
    assert javascript.status_code == 200
    assert "agentboard-theme" in javascript.text
    assert "localStorage" in javascript.text
    assert htmx.status_code == 404


async def test_backlog_reorder_requires_csrf_and_persists_exact_future_order(
    web_client: httpx.AsyncClient,
) -> None:
    page = await web_client.get("/projects/AB/backlog")
    csrf = _hidden_value(page.text, "csrf_token")

    rejected = await web_client.post(
        "/projects/AB/backlog/reorder",
        data={
            "expected_version": "1",
            "idempotency_key": "browser-reorder-rejected",
            "feature_ids": ["5", "1"],
        },
    )
    accepted = await web_client.post(
        "/projects/AB/backlog/reorder",
        data={
            "csrf_token": csrf,
            "expected_version": "1",
            "idempotency_key": "browser-reorder-1",
            "feature_ids": ["5", "1"],
        },
        follow_redirects=False,
    )
    refreshed = await web_client.get("/projects/AB/backlog")

    assert rejected.status_code == 403
    assert accepted.status_code == 303
    assert accepted.headers["location"] == "/projects/AB/backlog"
    assert refreshed.text.index("Second future item") < refreshed.text.index(
        "&lt;Future &amp; safe&gt;"
    )


async def test_backlog_reorder_replay_is_safe_and_stale_version_is_conflict(
    web_client: httpx.AsyncClient,
) -> None:
    page = await web_client.get("/projects/AB/backlog")
    csrf = _hidden_value(page.text, "csrf_token")
    payload = {
        "csrf_token": csrf,
        "expected_version": "1",
        "idempotency_key": "browser-reorder-1",
        "feature_ids": ["5", "1"],
    }

    first = await web_client.post("/projects/AB/backlog/reorder", data=payload)
    replay = await web_client.post("/projects/AB/backlog/reorder", data=payload)
    stale = await web_client.post(
        "/projects/AB/backlog/reorder",
        data={
            **payload,
            "idempotency_key": "browser-reorder-2",
            "feature_ids": ["1", "5"],
        },
    )

    assert first.status_code == 200
    assert replay.status_code == 200
    assert stale.status_code == 409
    assert "changed in another browser session" in stale.text


def _hidden_value(html: str, name: str) -> str:
    marker = f'name="{name}" value="'
    start = html.index(marker) + len(marker)
    return html[start : html.index('"', start)]

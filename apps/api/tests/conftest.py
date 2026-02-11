import os
import uuid
from datetime import datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Must set env before importing app modules
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-tests")
os.environ.setdefault("ENCRYPTION_KEY", "dGVzdGtleS0xMjM0NTY3ODkwMTIzNDU2")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://tempsaas:tempsaas@localhost:5432/tempsaas_test",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")

from src.auth import create_access_token
from src.database import Base, get_db
from src.main import app
from src.models import (
    Board,
    BoardColumn,
    Execution,
    ExecutionLog,
    Notification,
    PlanningMessage,
    Project,
    Ticket,
    User,
)
from src.models.team import Team, TeamMember

TEST_DATABASE_URL = os.environ["DATABASE_URL"]

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSession = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

# Track whether DB is available
_db_available: bool | None = None


async def _check_db() -> bool:
    global _db_available
    if _db_available is not None:
        return _db_available
    try:
        async with test_engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        _db_available = True
    except Exception:
        _db_available = False
    return _db_available


requires_db = pytest.mark.skipif(
    "not config.getoption('--db', default=True)",
    reason="Database not available",
)


@pytest.fixture(scope="session", autouse=True)
async def setup_database():
    """Create all tables before tests, drop after. Skip if DB unavailable."""
    if not await _check_db():
        yield
        return
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


@pytest.fixture(autouse=True)
async def clean_tables():
    """Truncate all tables between tests for isolation."""
    yield
    if not _db_available:
        return
    try:
        async with test_engine.begin() as conn:
            await conn.execute(
                text(
                    "TRUNCATE TABLE planning_messages, execution_logs, executions, "
                    "tickets, board_columns, boards, notifications, team_members, "
                    "teams, agent_configs, projects, users CASCADE"
                )
            )
    except Exception:
        pass


@pytest.fixture
async def db():
    """Provide a test database session."""
    if not _db_available:
        pytest.skip("PostgreSQL not available")
    async with TestSession() as session:
        yield session


@pytest.fixture
async def override_db(db: AsyncSession):
    """Override the app's get_db dependency to use the test session."""

    async def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    yield db
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
async def user(override_db: AsyncSession) -> User:
    """Create a test user."""
    db = override_db
    u = User(
        id=uuid.uuid4(),
        github_id=12345,
        login="testuser",
        name="Test User",
        email="test@example.com",
        avatar_url="https://example.com/avatar.png",
        plan_tier="free",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest.fixture
async def second_user(override_db: AsyncSession) -> User:
    """Create a second test user for isolation tests."""
    db = override_db
    u = User(
        id=uuid.uuid4(),
        github_id=67890,
        login="otheruser",
        name="Other User",
        email="other@example.com",
        plan_tier="free",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest.fixture
async def auth_client(user: User) -> AsyncClient:
    """An authenticated httpx client."""
    token = create_access_token(user.id)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        ac.headers["Authorization"] = f"Bearer {token}"
        yield ac


@pytest.fixture
async def unauth_client() -> AsyncClient:
    """An unauthenticated httpx client."""
    if not _db_available:
        pytest.skip("PostgreSQL not available")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def project(user: User, override_db: AsyncSession) -> Project:
    """Create a test project with default board and columns."""
    db = override_db
    p = Project(
        id=uuid.uuid4(),
        owner_id=user.id,
        name="Test Project",
        repo_full_name="testuser/test-repo",
        repo_url="https://github.com/testuser/test-repo",
        default_branch="main",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(p)
    await db.flush()

    b = Board(id=uuid.uuid4(), project_id=p.id, name="Main Board")
    db.add(b)
    await db.flush()

    columns_data = [
        ("Backlog", 0, "backlog"),
        ("Triaging", 1, "triaging"),
        ("Ready", 2, "ready"),
        ("In Progress", 3, "in_progress"),
        ("In Review", 4, "in_review"),
        ("Done", 5, "done"),
    ]
    for name, pos, status in columns_data:
        col = BoardColumn(
            id=uuid.uuid4(),
            board_id=b.id,
            name=name,
            position=pos,
            ticket_status=status,
        )
        db.add(col)

    await db.commit()
    await db.refresh(p)
    return p


@pytest.fixture
async def board(project: Project, override_db: AsyncSession) -> Board:
    """Get the board for the test project."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    db = override_db
    result = await db.execute(
        select(Board)
        .where(Board.project_id == project.id)
        .options(selectinload(Board.columns))
    )
    return result.scalar_one()


@pytest.fixture
async def backlog_column(board: Board) -> BoardColumn:
    """Get the backlog column."""
    return next(c for c in board.columns if c.ticket_status == "backlog")


@pytest.fixture
async def ready_column(board: Board) -> BoardColumn:
    """Get the ready column."""
    return next(c for c in board.columns if c.ticket_status == "ready")


@pytest.fixture
async def done_column(board: Board) -> BoardColumn:
    """Get the done column."""
    return next(c for c in board.columns if c.ticket_status == "done")


@pytest.fixture
async def ticket(
    project: Project,
    user: User,
    backlog_column: BoardColumn,
    override_db: AsyncSession,
) -> Ticket:
    """Create a test ticket."""
    db = override_db
    t = Ticket(
        id=uuid.uuid4(),
        project_id=project.id,
        created_by_id=user.id,
        column_id=backlog_column.id,
        title="Test Ticket",
        description="A test ticket description",
        position=1,
        status="backlog",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t


@pytest.fixture
async def planning_ticket(
    project: Project,
    user: User,
    backlog_column: BoardColumn,
    override_db: AsyncSession,
) -> Ticket:
    """Create a ticket in 'planning' status with one assistant message."""
    db = override_db
    t = Ticket(
        id=uuid.uuid4(),
        project_id=project.id,
        created_by_id=user.id,
        column_id=backlog_column.id,
        title="Plan This Feature",
        description="Need help planning this feature",
        position=1,
        status="planning",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(t)
    await db.flush()

    msg = PlanningMessage(
        id=uuid.uuid4(),
        ticket_id=t.id,
        sequence=1,
        role="assistant",
        content="I've analyzed your ticket. Here are my thoughts...",
    )
    db.add(msg)
    await db.commit()
    await db.refresh(t)
    return t


@pytest.fixture
async def ready_ticket(
    project: Project,
    user: User,
    ready_column: BoardColumn,
    override_db: AsyncSession,
) -> Ticket:
    """Create a ticket in 'ready' status."""
    db = override_db
    t = Ticket(
        id=uuid.uuid4(),
        project_id=project.id,
        created_by_id=user.id,
        column_id=ready_column.id,
        title="Ready Ticket",
        description="This ticket is ready",
        position=1,
        status="ready",
        agent_type="backend",
        runtime="claude",
        priority="medium",
        complexity="simple",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(t)
    await db.flush()

    msg = PlanningMessage(
        id=uuid.uuid4(),
        ticket_id=t.id,
        sequence=1,
        role="assistant",
        content="Plan finalized.",
    )
    db.add(msg)
    await db.commit()
    await db.refresh(t)
    return t

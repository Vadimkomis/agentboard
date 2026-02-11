from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
from src.routers import (
    auth,
    billing,
    boards,
    dashboard,
    events,
    executions,
    notifications,
    planning,
    projects,
    teams,
    tickets,
    users,
    webhooks,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="AgentBoard API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(projects.router, prefix="/api")
app.include_router(boards.router, prefix="/api")
app.include_router(tickets.router, prefix="/api")
app.include_router(planning.router, prefix="/api")
app.include_router(executions.router, prefix="/api")
app.include_router(events.router, prefix="/api")
app.include_router(notifications.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(webhooks.router, prefix="/api")
app.include_router(teams.router, prefix="/api")
app.include_router(billing.router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok"}

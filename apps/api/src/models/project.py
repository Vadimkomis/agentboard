import uuid
from datetime import datetime

from sqlalchemy import String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    repo_full_name: Mapped[str] = mapped_column(String(255))  # e.g. "owner/repo"
    repo_url: Mapped[str] = mapped_column(Text)
    default_branch: Mapped[str] = mapped_column(String(100), default="main")
    settings: Mapped[str | None] = mapped_column(Text)  # JSON blob for project-level settings
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    owner: Mapped["User"] = relationship(back_populates="projects")  # noqa: F821
    boards: Mapped[list["Board"]] = relationship(back_populates="project")  # noqa: F821
    agent_configs: Mapped[list["AgentConfig"]] = relationship(  # noqa: F821
        back_populates="project"
    )

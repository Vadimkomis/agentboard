import uuid
from datetime import datetime

from sqlalchemy import String, Text, Integer, Float, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


class AgentConfig(Base):
    __tablename__ = "agent_configs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE")
    )
    agent_type: Mapped[str] = mapped_column(String(50))  # mobile, backend, frontend, etc.
    system_prompt: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(100), default="claude-sonnet-4-5-20250929")
    max_tokens: Mapped[int] = mapped_column(Integer, default=100000)
    max_cost_per_run: Mapped[float] = mapped_column(Float, default=5.0)
    allowed_tools: Mapped[str | None] = mapped_column(Text)  # JSON list of allowed MCP tools
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    project: Mapped["Project"] = relationship(back_populates="agent_configs")  # noqa: F821

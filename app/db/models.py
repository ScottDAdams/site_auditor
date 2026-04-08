from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class DecisionRule(Base):
    __tablename__ = "decision_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    conditions_json: Mapped[str] = mapped_column(Text, nullable=False)
    outcomes_json: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)


class AuditReport(Base):
    """Persisted audit for /reports index and detail views."""

    __tablename__ = "audit_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    domains: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    priority_level: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    report_html: Mapped[str] = mapped_column(Text, nullable=False, default="")
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

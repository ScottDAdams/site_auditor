from sqlalchemy import Boolean, Integer, String, Text
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

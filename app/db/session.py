import json
import os

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base, DecisionRule
from app.paths import site_auditor_data_dir, sqlite_database_path


def get_engine():
    url = (os.getenv("DATABASE_URL") or "").strip()
    if not url:
        db_path = sqlite_database_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{db_path}"
    return create_engine(
        url,
        connect_args={"check_same_thread": False} if url.startswith("sqlite") else {},
    )


engine = get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    site_auditor_data_dir().mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    _seed_default_rules_if_empty()


DEFAULT_RULE_SEEDS = [
    {
        "name": "FAQ + informational",
        "conditions": {"page_type": "faq", "intent": "informational"},
        "outcomes": {
            "duplication": "acceptable",
            "action": "none",
            "reason": "Duplication is appropriate for this content type",
        },
        "priority": 10,
        "active": True,
    },
    {
        "name": "Product + awareness stage",
        "conditions": {"page_type": "product", "decision_stage": "awareness"},
        "outcomes": {
            "duplication": "acceptable",
            "action": "none",
            "reason": "Duplication is appropriate for this content type",
        },
        "priority": 15,
        "active": True,
    },
    {
        "name": "Decision-stage overlap",
        "conditions": {"decision_stage": "decision"},
        "outcomes": {
            "duplication": "competitive",
            "action": "differentiate",
            "reason": "Pages compete for the same decision-stage intent",
        },
        "priority": 25,
        "active": True,
    },
    {
        "name": "Landing + commercial intent",
        "conditions": {"page_type": "landing", "intent": "commercial"},
        "outcomes": {
            "duplication": "competitive",
            "action": "differentiate",
            "reason": "Pages compete for the same decision-stage intent",
        },
        "priority": 30,
        "active": True,
    },
    {
        "name": "Landing + transactional intent",
        "conditions": {"page_type": "landing", "intent": "transactional"},
        "outcomes": {
            "duplication": "competitive",
            "action": "differentiate",
            "reason": "Pages compete for the same decision-stage intent",
        },
        "priority": 31,
        "active": True,
    },
]


def _seed_default_rules_if_empty() -> None:
    with Session(engine) as session:
        n = session.scalar(select(DecisionRule.id).limit(1))
        if n is not None:
            return
        for row in DEFAULT_RULE_SEEDS:
            session.add(
                DecisionRule(
                    name=row["name"],
                    conditions_json=json.dumps(row["conditions"], sort_keys=True),
                    outcomes_json=json.dumps(row["outcomes"], sort_keys=True),
                    priority=row["priority"],
                    active=row["active"],
                )
            )
        session.commit()

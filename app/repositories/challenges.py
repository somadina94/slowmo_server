from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.challenge import AuthChallenge


def get_by_public_id(db: Session, public_id: str) -> AuthChallenge | None:
    return db.scalar(select(AuthChallenge).where(AuthChallenge.public_id == public_id))


def add(db: Session, challenge: AuthChallenge) -> AuthChallenge:
    db.add(challenge)
    db.flush()
    return challenge


def invalidate_open(db: Session, user_id: int, purpose: str) -> None:
    rows = db.scalars(
        select(AuthChallenge).where(
            AuthChallenge.user_id == user_id,
            AuthChallenge.purpose == purpose,
            AuthChallenge.consumed.is_(False),
        )
    ).all()
    for row in rows:
        row.consumed = True

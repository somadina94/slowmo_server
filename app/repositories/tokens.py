from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.token import RefreshToken


def add(db: Session, token: RefreshToken) -> RefreshToken:
    db.add(token)
    db.flush()
    return token


def list_active_for_user(db: Session, user_id: int) -> list[RefreshToken]:
    return list(
        db.scalars(
            select(RefreshToken).where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked.is_(False),
            )
        )
    )


def revoke_all(db: Session, user_id: int) -> int:
    tokens = list_active_for_user(db, user_id)
    for token in tokens:
        token.revoked = True
    return len(tokens)

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.user import User


def get_by_id(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def get_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email.lower()))


def list_customers(db: Session, search: str = "") -> list[User]:
    stmt = select(User).where(User.role == "customer")
    if search:
        like = f"%{search.lower()}%"
        stmt = stmt.where(or_(User.email.ilike(like), User.name.ilike(like)))
    return list(db.scalars(stmt.order_by(User.id.desc())))


def list_staff(db: Session) -> list[User]:
    stmt = select(User).where(User.role.in_(("founder", "admin", "ops", "clinician")))
    return list(db.scalars(stmt.order_by(User.id.asc())))


def add(db: Session, user: User) -> User:
    db.add(user)
    db.flush()
    return user

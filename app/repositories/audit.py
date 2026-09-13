from sqlalchemy.orm import Session

from app.models.audit import AuditLog


def write(db: Session, actor_id: int | None, action: str, entity: str, entity_id: str = "", detail: str = "") -> AuditLog:
    log = AuditLog(actor_id=actor_id, action=action, entity=entity, entity_id=entity_id, detail=detail)
    db.add(log)
    db.flush()
    return log

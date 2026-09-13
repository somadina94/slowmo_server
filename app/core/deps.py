from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.rbac import is_staff, require_permission
from app.core.security import decode_token
from app.integrations.notifications import Notifier
from app.integrations.razorpay import RazorpayGateway
from app.integrations.shipping import get_shipping_provider
from app.integrations.storage import FileStorage
from app.models.user import User
from app.repositories import users as user_repo

DbDep = Annotated[Session, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_gateway(settings: SettingsDep) -> RazorpayGateway:
    return RazorpayGateway(settings)


def get_notifier(settings: SettingsDep) -> Notifier:
    return Notifier(settings)


def get_storage(settings: SettingsDep) -> FileStorage:
    return FileStorage(settings)


def get_shipper(settings: SettingsDep):
    return get_shipping_provider(settings.shipping_provider)


def _user_from_header(db: Session, settings: Settings, authorization: str | None) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise UnauthorizedError()
    token = authorization.split(" ", 1)[1]
    try:
        payload = decode_token(token, settings.jwt_access_secret, "access")
    except Exception as exc:
        raise UnauthorizedError("Invalid access token") from exc
    user = user_repo.get_by_id(db, int(payload["sub"]))
    if user is None or not user.is_active:
        raise UnauthorizedError("Invalid access token")
    return user


def get_current_user(
    db: DbDep,
    settings: SettingsDep,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    return _user_from_header(db, settings, authorization)


def get_current_staff(user: Annotated[User, Depends(get_current_user)]) -> User:
    if not is_staff(user.role):
        raise ForbiddenError("Staff only")
    return user


def require(permission: str):
    def _inner(user: Annotated[User, Depends(get_current_staff)]) -> User:
        require_permission(user.role, permission)
        return user

    return _inner


CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentStaff = Annotated[User, Depends(get_current_staff)]

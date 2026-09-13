import pytest
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.deps import _user_from_header
from app.core.exceptions import UnauthorizedError
from app.core.security import create_token
from app.repositories import users as user_repo
from app.seed import seed
from app.services import auth as auth_service
from datetime import timedelta


def test_user_from_header_inactive(db: Session, settings: Settings):
    seed(db, settings)
    pair = auth_service.register(db, settings, "dead@test.com", "password1", "Dead User")
    user = user_repo.get_by_email(db, "dead@test.com")
    user.is_active = False
    db.flush()
    with pytest.raises(UnauthorizedError):
        _user_from_header(db, settings, f"Bearer {pair.access_token}")
    with pytest.raises(UnauthorizedError):
        _user_from_header(db, settings, None)
    missing_user = create_token("9999", "customer", settings.jwt_access_secret, "access", timedelta(minutes=5))
    with pytest.raises(UnauthorizedError):
        _user_from_header(db, settings, f"Bearer {missing_user}")

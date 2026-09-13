from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, UnauthorizedError, ValidationAppError
from app.core.config import Settings
from app.integrations.notifications import Notifier
from app.integrations.razorpay import RazorpayError, RazorpayGateway
from app.integrations.shipping import StubShippingProvider, get_shipping_provider
from app.integrations.storage import FileStorage, StorageError
from app.repositories import catalog as catalog_repo
from app.repositories import users as user_repo
from app.schemas.orders import AddressIn, ConsultIn, OrderCreate
from app.seed import seed
from app.services import admin as admin_service
from app.services import auth as auth_service
from app.services import inventory as inventory_service
from app.services import orders as order_service
from app.services.auth import as_utc
from app.services.ids import (
    allowed_order_transition,
    allowed_shipment_transition,
    days_of_cover,
    format_inr,
    greeting_for_hour,
    make_order_id,
    make_rx_code,
    stock_level,
)


def test_as_utc():
    naive = datetime(2026, 1, 1, 12, 0, 0)
    assert as_utc(naive).tzinfo is not None
    aware = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert as_utc(aware) is aware


def test_ids_and_money():
    assert make_order_id(datetime(2026, 9, 12, tzinfo=timezone.utc)).startswith("SM-")
    assert make_rx_code("SM-849271") == "RX-SM-9271"
    assert stock_level(100, 0, 0) == "hi"
    assert stock_level(0, 0, 0) == "lo"
    assert stock_level(200, 0, 100) == "hi"
    assert stock_level(90, 0, 100) == "mid"
    assert stock_level(10, 0, 100) == "lo"
    assert days_of_cover(100, 0, 0) == 99
    assert days_of_cover(10, 10, 10) == 0
    assert days_of_cover(70, 0, 70) == 7
    assert format_inr(50_000) == "₹50,000"
    assert "L" in format_inr(142_000)
    assert "Cr" in format_inr(12_400_000)
    assert greeting_for_hour(8) == "Good morning"
    assert greeting_for_hour(13) == "Good afternoon"
    assert greeting_for_hour(20) == "Good evening"
    assert allowed_order_transition("consult", "confirmed")
    assert not allowed_order_transition("delivered", "hold")
    assert allowed_shipment_transition("packed", "picked")
    assert not allowed_shipment_transition("packed", "delivered")
    assert not allowed_shipment_transition("nope", "packed")


def test_auth_flow(db: Session, settings: Settings):
    seed(db, settings)
    notifier = Notifier(settings)
    pair = auth_service.register(db, settings, "priya@test.com", "password1", "Priya Sharma", "999", notifier)
    assert pair.user.initials == "PS"
    assert auth_service.initials_for("") == "?"
    assert auth_service.initials_for("Meera") == "M"
    assert auth_service.email_hint("a@b.com") == "a***@b.com"
    assert auth_service.email_hint("nodomain") == "***"
    with pytest.raises(ConflictError):
        auth_service.register(db, settings, "priya@test.com", "password1", "Priya")
    with pytest.raises(ValidationAppError):
        auth_service.register(db, settings, "new@test.com", "short", "N")
    with pytest.raises(UnauthorizedError):
        auth_service.login(db, settings, "priya@test.com", "wrong", notifier)
    with pytest.raises(UnauthorizedError):
        auth_service.login(db, settings, "missing@test.com", "password1", notifier)
    challenge = auth_service.login(db, settings, "priya@test.com", "password1", notifier)
    assert challenge.requires_2fa and challenge.debug_code
    with pytest.raises(UnauthorizedError):
        auth_service.verify_login(db, settings, challenge.challenge_id, "000000")
    customer = auth_service.verify_login(db, settings, challenge.challenge_id, challenge.debug_code)
    with pytest.raises(UnauthorizedError):
        auth_service.verify_login(db, settings, challenge.challenge_id, challenge.debug_code)
    with pytest.raises(UnauthorizedError):
        auth_service.login(db, settings, "priya@test.com", "password1", notifier, staff_only=True)
    staff_challenge = auth_service.login(
        db, settings, settings.seed_founder_email, settings.seed_founder_password, notifier, staff_only=True
    )
    staff = auth_service.verify_login(db, settings, staff_challenge.challenge_id, staff_challenge.debug_code or "")
    refreshed = auth_service.refresh(db, settings, staff.refresh_token)
    assert refreshed.access_token
    with pytest.raises(UnauthorizedError):
        auth_service.refresh(db, settings, staff.refresh_token)
    with pytest.raises(UnauthorizedError):
        auth_service.refresh(db, settings, "not-a-token")
    assert auth_service.logout(db, settings, refreshed.refresh_token, staff.user.id) >= 1
    more = auth_service.logout(db, settings, "", customer.user.id)
    assert more >= 1
    bad = auth_service.logout(db, settings, "nope", customer.user.id)
    assert bad >= 0
    ops = auth_service.create_staff(db, "ops@test.com", "password1", "Ops Person", "ops")
    assert ops.role == "ops"
    with pytest.raises(ConflictError):
        auth_service.create_staff(db, "ops@test.com", "password1", "Ops", "ops")
    with pytest.raises(ValidationAppError):
        auth_service.create_staff(db, "x@test.com", "password1", "X", "nope")
    founder_user = user_repo.get_by_email(db, settings.seed_founder_email)
    assert founder_user
    with pytest.raises(ValidationAppError):
        auth_service.update_role(db, founder_user.id, "admin", founder_user)
    auth_service.update_role(db, ops.id, "admin", founder_user)
    assert ops.role == "admin"
    with pytest.raises(ForbiddenError):
        auth_service.update_role(db, ops.id, "founder", ops)
    with pytest.raises(NotFoundError):
        auth_service.update_role(db, 999999, "ops", founder_user)
    with pytest.raises(ValidationAppError):
        auth_service.update_role(db, ops.id, "nope", founder_user)
    forgot = auth_service.forgot_password(db, settings, "missing@test.com", notifier)
    assert "reset" in forgot.message.lower() or "email" in forgot.message.lower()
    sent = auth_service.forgot_password(db, settings, "priya@test.com", notifier)
    assert sent.debug_token
    with pytest.raises(ValidationAppError):
        auth_service.reset_password(db, settings, sent.debug_token or "", "short", notifier)
    reset = auth_service.reset_password(db, settings, sent.debug_token or "", "password2", notifier)
    assert "updated" in reset.message.lower()
    with pytest.raises(UnauthorizedError):
        auth_service.login(db, settings, "priya@test.com", "password1", notifier)
    again = auth_service.login(db, settings, "priya@test.com", "password2", notifier)
    auth_service.verify_login(db, settings, again.challenge_id, again.debug_code or "")
    settings.app_debug = False
    silent = auth_service.login(db, settings, "priya@test.com", "password2", notifier)
    assert silent.debug_code is None
    settings.app_debug = True
    settings.otp_max_attempts = 1
    locked = auth_service.login(db, settings, "priya@test.com", "password2", notifier)
    with pytest.raises(UnauthorizedError):
        auth_service.verify_login(db, settings, locked.challenge_id, "111111")
    with pytest.raises(UnauthorizedError):
        auth_service.verify_login(db, settings, locked.challenge_id, locked.debug_code or "222222")
    settings.otp_max_attempts = 5
    expired = auth_service.login(db, settings, "priya@test.com", "password2", notifier)
    from app.repositories import challenges as challenge_repo

    row = challenge_repo.get_by_public_id(db, expired.challenge_id)
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.flush()
    with pytest.raises(UnauthorizedError):
        auth_service.verify_login(db, settings, expired.challenge_id, expired.debug_code or "123456")

    inactive_ch = auth_service.login(db, settings, "priya@test.com", "password2", notifier)
    user_row = user_repo.get_by_email(db, "priya@test.com")
    user_row.is_active = False
    db.flush()
    with pytest.raises(UnauthorizedError):
        auth_service.verify_login(db, settings, inactive_ch.challenge_id, inactive_ch.debug_code or "123456")
    user_row.is_active = True
    db.flush()
    dead_reset = auth_service.forgot_password(db, settings, "priya@test.com", notifier)
    user_row.is_active = False
    db.flush()
    with pytest.raises(UnauthorizedError):
        auth_service.reset_password(db, settings, dead_reset.debug_token or "x", "password3", notifier)
    user_row.is_active = True
    db.flush()
    auth_service.forgot_password(db, settings, "priya@test.com", notifier)


def test_inactive_and_expired_refresh(db: Session, settings: Settings):
    notifier = Notifier(settings)
    pair = auth_service.register(db, settings, "gone@test.com", "password1", "Gone User")
    from app.repositories import users as user_repo

    user = user_repo.get_by_email(db, "gone@test.com")
    user.is_active = False
    db.flush()
    with pytest.raises(UnauthorizedError):
        auth_service.login(db, settings, "gone@test.com", "password1", notifier)
    with pytest.raises(UnauthorizedError):
        auth_service.refresh(db, settings, pair.refresh_token)

    live = auth_service.register(db, settings, "live@test.com", "password1", "Live User")
    from app.core.security import decode_token
    from app.repositories import tokens as token_repo

    payload = decode_token(live.refresh_token, settings.jwt_refresh_secret, "refresh")
    token = token_repo.list_active_for_user(db, live.user.id)[0]
    token.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.flush()
    with pytest.raises(UnauthorizedError):
        auth_service.refresh(db, settings, live.refresh_token)
    assert payload["jti"]


def test_inventory_and_orders(db: Session, settings: Settings):
    seed(db, settings)
    gateway = RazorpayGateway(settings)
    notifier = Notifier(settings)
    user = auth_service.register(db, settings, "buy@test.com", "password1", "Buyer One").user
    address = AddressIn(name="Buyer One", phone="1", email="buy@test.com", line="12 Main", city="Bengaluru", pincode="560001", state="Karnataka")
    with pytest.raises(ValidationAppError):
        order_service.create_order(
            db, settings, user.id,
            OrderCreate(sku="SM-MB-10", address=address, payment="cod", age_confirmed=False),
            gateway, notifier,
        )
    with pytest.raises(ValidationAppError):
        order_service.create_order(
            db, settings, user.id,
            OrderCreate(sku="SM-MB-10", address=address, payment="cod", age_confirmed=True),
            gateway, notifier,
        )
    with pytest.raises(ValidationAppError):
        order_service.create_order(
            db, settings, user.id,
            OrderCreate(sku="SM-MB-10", program_key="nope", consult=ConsultIn(name="A", phone="1", email="a@b.com"), address=address, payment="cod", age_confirmed=True),
            gateway, notifier,
        )
    with pytest.raises(ValidationAppError):
        order_service.create_order(
            db, settings, user.id,
            OrderCreate(sku="SM-MB-10", program_key="sleep30", program_skipped=True, consult=ConsultIn(name="A", phone="1", email="a@b.com"), address=address, payment="cod", age_confirmed=True),
            gateway, notifier,
        )
    with pytest.raises(NotFoundError):
        order_service.create_order(
            db, settings, user.id,
            OrderCreate(sku="NOPE", consult=ConsultIn(name="A", phone="1", email="a@b.com"), address=address, payment="cod", age_confirmed=True),
            gateway, notifier,
        )
    with pytest.raises(NotFoundError):
        order_service.create_order(
            db, settings, user.id,
            OrderCreate(sku="SM-MB-10", rx_file_id=999, address=address, payment="cod", age_confirmed=True),
            gateway, notifier,
        )
    created = order_service.create_order(
        db, settings, user.id,
        OrderCreate(
            sku="SM-MB-10",
            program_key="sleep30",
            consult=ConsultIn(name="Buyer One", phone="1", email="buy@test.com", reason="racing thoughts", slot="Morning (9AM–12PM)"),
            address=address,
            payment="cod",
            age_confirmed=True,
        ),
        gateway,
        notifier,
    )
    assert created.status == "consult"
    assert notifier.sent
    mine = order_service.list_mine(db, user.id)
    assert mine[0].public_id == created.public_id
    fetched = order_service.get_order(db, created.public_id, user.id, False)
    assert fetched.total == 3390
    assert fetched.age_confirmed is True
    assert fetched.consult is not None
    assert fetched.consult.notes == ""
    assert fetched.prescription is None
    assert fetched.shipment is None
    other = auth_service.register(db, settings, "other@test.com", "password1", "Other").user
    with pytest.raises(Exception):
        order_service.get_order(db, created.public_id, other.id, False)
    with pytest.raises(NotFoundError):
        order_service.get_order(db, "SM-000000", user.id, True)
    confirmed = order_service.transition(db, created.public_id, "confirmed", 1, notifier)
    assert confirmed.status == "confirmed"
    with pytest.raises(ValidationAppError):
        order_service.transition(db, created.public_id, "consult", 1)
    with pytest.raises(NotFoundError):
        order_service.transition(db, "SM-000000", "hold", 1)
    hold = order_service.transition(db, created.public_id, "hold", 1, notifier)
    assert hold.status == "hold"
    order_service.transition(db, created.public_id, "cancelled", 1, notifier)

    prepaid = order_service.create_order(
        db, settings, user.id,
        OrderCreate(sku="SM-MB-15", consult=ConsultIn(name="B", phone="2", email="b@c.com"), address=address, payment="prepaid", age_confirmed=True),
        gateway, notifier,
    )
    assert prepaid.status == "pending_payment"
    assert prepaid.razorpay is not None
    from app.repositories import orders as order_repo

    row = order_repo.get_by_public_id(db, prepaid.public_id)
    paid = order_service.mark_paid(db, row, "pay_1", notifier)
    assert paid.status == "consult"
    with pytest.raises(ValidationAppError):
        order_service.mark_paid(db, row, "pay_2", notifier)

    snap = inventory_service.snapshot(db)
    assert snap["skus"]
    inventory_service.receive(db, "SM-MB-10", 5, "restock", "B-TEST-1")
    created_sku = inventory_service.create_sku(
        db,
        code="sm-mb-45",
        name="Slow Mo · 45 pack",
        pack_qty=45,
        price=12000,
        mrp=14000,
        stock=10,
        weekly_forecast=2,
    )
    assert any(row["sku"] == "SM-MB-45" for row in created_sku["skus"])
    with pytest.raises(ConflictError):
        inventory_service.create_sku(db, code="SM-MB-45", name="Dup", pack_qty=45, price=1, mrp=2)
    with pytest.raises(ValidationAppError):
        inventory_service.create_sku(db, code="", name="x", pack_qty=1, price=1, mrp=1)
    with pytest.raises(ValidationAppError):
        inventory_service.create_sku(db, code="X", name="x", pack_qty=0, price=1, mrp=1)
    with pytest.raises(ValidationAppError):
        inventory_service.create_sku(db, code="Y", name="y", pack_qty=1, price=5, mrp=4)
    from app.models.product import Product
    from app.repositories import inventory as inv_repo

    # Cover path when catalog product is missing.
    for product in list(db.query(Product).all()):
        for variant in list(product.variants):
            record = inv_repo.get_sku(db, variant.sku)
            if record is not None:
                for batch in list(record.batches):
                    db.delete(batch)
                for movement in list(record.movements):
                    db.delete(movement)
                db.delete(record)
            db.delete(variant)
        db.delete(product)
    db.flush()
    fresh = inventory_service.create_sku(
        db,
        code="SM-NEW-1",
        name="New pack",
        pack_qty=5,
        price=100,
        mrp=120,
        label="New",
        description="fresh",
    )
    assert any(row["sku"] == "SM-NEW-1" for row in fresh["skus"])
    with pytest.raises(NotFoundError):
        inventory_service.allocate(db, "NOPE", 1)
    with pytest.raises(NotFoundError):
        inventory_service.deallocate(db, "NOPE", 1)
    with pytest.raises(NotFoundError):
        inventory_service.receive(db, "NOPE", 1, "x")
    with pytest.raises(ValidationAppError):
        inventory_service.receive(db, "SM-NEW-1", 0, "x")
    sku = catalog_repo.get_variant_by_sku(db, "SM-NEW-1")
    assert sku
    record = inv_repo.get_sku(db, "SM-NEW-1")
    record.stock = 0
    record.allocated = 0
    db.flush()
    with pytest.raises(ValidationAppError):
        inventory_service.allocate(db, "SM-NEW-1", 1)
    existing = order_repo.get_by_public_id(db, created.public_id)
    ids = iter([existing.public_id, "SM-NEW01"])
    assert order_service.next_public_id(db, maker=lambda: next(ids)) == "SM-NEW01"


def test_admin_and_shipping(db: Session, settings: Settings):
    seed(db, settings)
    gateway = RazorpayGateway(settings)
    notifier = Notifier(settings)
    provider = StubShippingProvider()
    founder_ch = auth_service.login(db, settings, settings.seed_founder_email, settings.seed_founder_password, notifier, True)
    founder = auth_service.verify_login(db, settings, founder_ch.challenge_id, founder_ch.debug_code or "").user
    from app.repositories import users as user_repo

    staff = user_repo.get_by_id(db, founder.id)
    user = auth_service.register(db, settings, "c@test.com", "password1", "Cust Omer", "900").user
    address = AddressIn(name="Cust Omer", phone="900", email="c@test.com", line="x", city="Mumbai", pincode="400001", state="Maharashtra")
    created = order_service.create_order(
        db, settings, user.id,
        OrderCreate(sku="SM-MB-10", consult=ConsultIn(name="Cust", phone="900", email="c@test.com"), address=address, payment="cod", age_confirmed=True),
        gateway, notifier,
    )
    data = admin_service.overview(db, staff, datetime(2026, 9, 12, 9, 41))
    assert data["pending_consults"] >= 1
    afternoon = admin_service.overview(db, staff, datetime(2026, 9, 12, 15, 0))
    assert "afternoon" in afternoon["greeting"].lower() or "Good" in afternoon["greeting"]
    evening = admin_service.overview(db, staff, datetime(2026, 9, 12, 19, 0))
    assert evening["greeting"]
    assert admin_service.orders_page(db, "consult")["count"] >= 1
    assert admin_service.consults_page(db)["remaining"] >= 1
    from app.models.consult import RxFile
    from app.repositories import orders as order_repo

    order_row = order_repo.get_by_public_id(db, created.public_id)
    assert order_row is not None
    order_row.rx_file = RxFile(
        user_id=user.id,
        filename="rx.pdf",
        stored_name="rx.pdf",
        mime="application/pdf",
        size=10,
        status="pending_verify",
    )
    db.flush()
    assert admin_service.consults_page(db)["pending_rx"]
    admin_service.reschedule_consult(db, created.public_id, "Evening (5–9PM)", staff.id, notifier)
    admin_service.complete_consult(db, created.public_id, staff.id, "ok", notifier)
    with pytest.raises(NotFoundError):
        admin_service.complete_consult(db, "SM-000000", staff.id)
    with pytest.raises(NotFoundError):
        admin_service.reschedule_consult(db, "SM-000000", "x", staff.id)
    admin_service.verify_rx(db, created.public_id, staff.id, True, notifier)
    with pytest.raises(NotFoundError):
        admin_service.verify_rx(db, "SM-000000", staff.id, False)
    customers = admin_service.customers_page(db, "cust")
    assert customers["total"] >= 1
    assert admin_service.analytics_page(db)["kpis"]
    assert admin_service.counts(db)["orders"] >= 0
    assert admin_service.inventory_page(db)["warehouse"] == "Bengaluru"
    with pytest.raises(NotFoundError):
        admin_service.create_shipment(db, "SM-000000", staff.id, provider)
    with pytest.raises(ValidationAppError):
        pending = order_service.create_order(
            db, settings, user.id,
            OrderCreate(sku="SM-MB-15", consult=ConsultIn(name="C", phone="1", email="c@test.com"), address=address, payment="prepaid", age_confirmed=True),
            gateway, notifier,
        )
        admin_service.create_shipment(db, pending.public_id, staff.id, provider)
    shipped = admin_service.create_shipment(db, created.public_id, staff.id, provider, notifier)
    assert shipped["columns"]
    admin_service.create_shipment(db, created.public_id, staff.id, provider, notifier)
    admin_service.move_shipment(db, created.public_id, "picked", staff.id, provider)
    admin_service.move_shipment(db, created.public_id, "transit", staff.id, provider)
    admin_service.move_shipment(db, created.public_id, "delivered", staff.id, provider, notifier)
    detailed = order_service.get_order(db, created.public_id, staff.id, True)
    assert detailed.prescription is not None
    assert detailed.prescription.code
    assert detailed.shipment is not None
    assert detailed.shipment.events
    assert detailed.consult is not None
    assert detailed.consult.notes == "ok"
    with pytest.raises(ValidationAppError):
        admin_service.move_shipment(db, created.public_id, "packed", staff.id, provider)
    with pytest.raises(NotFoundError):
        admin_service.move_shipment(db, "SM-000000", "picked", staff.id, provider)
    with pytest.raises(NotFoundError):
        admin_service.schedule_pickup(db, "SM-000000", staff.id, provider)
    pickup = admin_service.schedule_pickup(db, created.public_id, staff.id, provider)
    assert pickup["pickup_id"]
    assert "awb" in admin_service.manifest(db, provider)
    assert "id,name" in admin_service.export_orders_csv(db)


def test_integrations(tmp_path, settings: Settings):
    settings.storage_dir = str(tmp_path)
    storage = FileStorage(settings)
    from unittest.mock import Mock, patch

    from botocore.exceptions import ClientError

    from app.integrations.storage import content_disposition, normalize_b2_endpoint, safe_download_name

    assert normalize_b2_endpoint("s3.example.com") == "https://s3.example.com"
    assert normalize_b2_endpoint("https://s3.example.com") == "https://s3.example.com"
    assert normalize_b2_endpoint("") == ""
    assert safe_download_name("Screenshot\u202f2024.png") == "Screenshot_2024.png"
    assert safe_download_name('bad/"name".pdf') == "bad__name_.pdf"
    assert safe_download_name("___") == "prescription"
    assert content_disposition("rx\u202f.png").startswith('inline; filename="rx_.png"')
    stored, original = storage.validate("rx.pdf", "application/pdf", 12)
    assert original == "rx.pdf"
    path = storage.save(stored, b"%PDF-test")
    assert storage.read(stored)
    settings.storage_backend = "b2"
    settings.b2_endpoint = "s3.us-east-005.backblazeb2.com"
    settings.b2_bucket_name = "bucket"
    settings.b2_application_key_id = "key-id"
    settings.b2_application_key = "key"
    settings.b2_bucket_region = "us-east-005"
    settings.b2_public_file_base_url = "https://cdn.example.com"
    mock_client = Mock()
    mock_client.put_object.return_value = {}
    mock_body = Mock()
    mock_body.read.return_value = b"from-b2"
    mock_client.get_object.return_value = {"Body": mock_body}
    with patch("app.integrations.storage.boto3.client", return_value=mock_client):
        b2_storage = FileStorage(settings)
        key = b2_storage.save("rx.pdf", b"x", content_type="application/pdf")
        assert key == "rx/rx.pdf"
        assert b2_storage.object_key("rx/already.pdf") == "rx/already.pdf"
        assert b2_storage.read("rx.pdf") == b"from-b2"
        assert b2_storage.public_url("rx.pdf") == "https://cdn.example.com/rx/rx.pdf"
        mock_client.put_object.assert_called_once()
        mock_client.put_object.side_effect = ClientError({"Error": {"Code": "500", "Message": "x"}}, "PutObject")
        with pytest.raises(StorageError):
            b2_storage.save_b2("fail.pdf", b"x")
        mock_client.put_object.side_effect = None
        mock_client.get_object.side_effect = ClientError({"Error": {"Code": "404", "Message": "x"}}, "GetObject")
        with pytest.raises(StorageError):
            b2_storage.read_b2("missing.pdf")
        mock_client.get_object.side_effect = None
    settings.b2_public_file_base_url = ""
    assert FileStorage(settings).public_url("rx.pdf").endswith("/bucket/rx/rx.pdf")
    settings.b2_endpoint = ""
    assert FileStorage(settings).public_url("rx.pdf") == "rx/rx.pdf"
    settings.b2_endpoint = "s3.us-east-005.backblazeb2.com"
    settings.b2_bucket_name = ""
    with pytest.raises(StorageError):
        FileStorage(settings).save_b2("x.pdf", b"x")
    settings.b2_bucket_name = "bucket"
    settings.b2_application_key = ""
    with pytest.raises(StorageError):
        FileStorage(settings).save_b2("x.pdf", b"x")
    settings.b2_application_key = "key"
    settings.b2_endpoint = ""
    with pytest.raises(StorageError):
        FileStorage(settings).save_b2("x.pdf", b"x")
    settings.storage_backend = "local"
    with pytest.raises(Exception):
        storage.validate("x.exe", "application/octet-stream", 10)
    with pytest.raises(Exception):
        storage.validate("x.pdf", "application/pdf", 11 * 1024 * 1024)
    with pytest.raises(StorageError):
        storage.read("missing.pdf")
    gateway = RazorpayGateway(settings)
    with pytest.raises(RazorpayError):
        gateway.create_order(0, "r")
    order = gateway.create_order(100, "r")
    sig = gateway.sign_payment(order.id, "pay")
    assert gateway.verify_payment(order.id, "pay", sig)
    assert not gateway.verify_payment(order.id, "pay", "no")
    body = b'{"a":1}'
    import hashlib, hmac

    import httpx

    wh = hmac.new(settings.razorpay_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    assert gateway.verify_webhook(body, wh)
    live_settings = settings.model_copy(update={"razorpay_key_id": "rzp_test_livekey", "razorpay_key_secret": "live_secret"})
    live = RazorpayGateway(live_settings)
    assert not live._stubbed()
    ok = Mock()
    ok.raise_for_status = Mock()
    ok.json = Mock(return_value={"id": "order_real", "amount": 200, "currency": "INR"})
    with patch("app.integrations.razorpay.httpx.post", return_value=ok) as posted:
        created = live.create_order(200, "SM-RECEIPT")
        assert created.id == "order_real"
        posted.assert_called_once()
    bad = Mock()
    bad.raise_for_status = Mock(side_effect=httpx.HTTPStatusError("boom", request=Mock(), response=Mock()))
    with patch("app.integrations.razorpay.httpx.post", return_value=bad):
        with pytest.raises(RazorpayError):
            live.create_order(200, "SM-X")
    empty = Mock()
    empty.raise_for_status = Mock()
    empty.json = Mock(return_value={})
    with patch("app.integrations.razorpay.httpx.post", return_value=empty):
        with pytest.raises(RazorpayError):
            live.create_order(200, "SM-Y")
    assert get_shipping_provider("stub").track("A")["provider"] == "stub"
    with pytest.raises(ValueError):
        get_shipping_provider("nope")
    settings.mail_backend = "smtp"
    settings.smtp_host = "smtp.test"
    settings.smtp_user = "mailer@test"
    settings.smtp_password = "secret"
    mail = Notifier(settings)
    with patch("app.integrations.notifications.smtplib.SMTP") as smtp_cls:
        server = Mock()
        smtp_cls.return_value.__enter__.return_value = server
        mail.order_placed("a@b.com", "900", "SM-1", "Ada")
        mail.welcome("a@b.com", "Ada")
        mail.login_otp("a@b.com", "Ada", "123456")
        mail.password_reset("a@b.com", "Ada", "tok")
        mail.password_changed("a@b.com", "Ada")
        mail.order_paid("a@b.com", "SM-1", "Ada")
        mail.order_status("a@b.com", "SM-1", "confirmed", "Ada")
        mail.order_status("a@b.com", "SM-1", "weird", "Ada")
        mail.rx_decision("a@b.com", "SM-1", True, "Ada")
        mail.rx_decision("a@b.com", "SM-1", False, "Ada")
        mail.consult_update("a@b.com", "SM-1", "Soon", "Ada")
        assert mail.sent
        assert server.sendmail.called
        assert server.login.called

import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from tests.conftest import auth_header


def test_health(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["razorpay_webhook_url"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_auth_and_me(client: TestClient):
    bad = client.post("/api/v1/auth/login", json={"email": "no@x.com", "password": "password1"})
    assert bad.status_code == 401
    created = client.post(
        "/api/v1/auth/register",
        json={"email": "user@test.com", "password": "password1", "name": "User Test", "phone": "1"},
    )
    assert created.status_code == 200
    headers = {"Authorization": f"Bearer {created.json()['access_token']}"}
    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    refresh = client.post("/api/v1/auth/refresh", json={"refresh_token": created.json()["refresh_token"]})
    assert refresh.status_code == 200
    logout = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh.json()["refresh_token"]},
        headers={"Authorization": f"Bearer {refresh.json()['access_token']}"},
    )
    assert logout.status_code == 200
    staff = client.post("/api/v1/auth/staff/login", json={"email": "user@test.com", "password": "password1"})
    assert staff.status_code == 401
    founder = client.post("/api/v1/auth/staff/login", json={"email": "meera@slowmo.co", "password": "FounderDev123!"})
    assert founder.status_code == 200
    assert founder.json()["requires_2fa"] is True
    verified = client.post(
        "/api/v1/auth/verify-login",
        json={"challenge_id": founder.json()["challenge_id"], "code": founder.json()["debug_code"]},
    )
    assert verified.status_code == 200
    forgot = client.post("/api/v1/auth/forgot-password", json={"email": "user@test.com"})
    assert forgot.status_code == 200
    assert forgot.json().get("debug_token")
    reset = client.post(
        "/api/v1/auth/reset-password",
        json={"token": forgot.json()["debug_token"], "password": "password9"},
    )
    assert reset.status_code == 200
    missing = client.get("/api/v1/auth/me")
    assert missing.status_code == 401
    garbage = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer nope"})
    assert garbage.status_code == 401


def test_catalog_and_order_flow(client: TestClient):
    products = client.get("/api/v1/products")
    assert products.status_code == 200
    assert products.json()[0]["variants"]
    programs = client.get("/api/v1/programs")
    assert len(programs.json()) == 3
    client.post("/api/v1/auth/register", json={"email": "buyer@test.com", "password": "password1", "name": "Buyer Test"})
    headers = auth_header(client, "buyer@test.com", "password1")
    upload = client.post(
        "/api/v1/files/rx",
        headers=headers,
        files={"file": ("rx.pdf", b"%PDF-1.4 test", "application/pdf")},
    )
    assert upload.status_code == 200
    file_id = upload.json()["id"]
    download = client.get(f"/api/v1/files/rx/{file_id}", headers=headers)
    assert download.status_code == 200
    assert "filename=" in download.headers.get("content-disposition", "")
    unicode_name = client.post(
        "/api/v1/files/rx",
        headers=headers,
        files={"file": ("Screenshot\u202f2024.png", b"\x89PNG\r\n", "image/png")},
    )
    assert unicode_name.status_code == 200
    unicode_dl = client.get(f"/api/v1/files/rx/{unicode_name.json()['id']}", headers=headers)
    assert unicode_dl.status_code == 200
    missing = client.get("/api/v1/files/rx/9999", headers=headers)
    assert missing.status_code == 404
    other = client.post("/api/v1/auth/register", json={"email": "oth@test.com", "password": "password1", "name": "Oth Er"})
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
    denied = client.get(f"/api/v1/files/rx/{file_id}", headers=other_headers)
    assert denied.status_code == 403
    bad_file = client.post(
        "/api/v1/files/rx",
        headers=headers,
        files={"file": ("x.exe", b"xx", "application/octet-stream")},
    )
    assert bad_file.status_code == 422
    order = client.post(
        "/api/v1/orders",
        headers=headers,
        json={
            "sku": "SM-MB-10",
            "program_key": "sleep30",
            "rx_file_id": file_id,
            "address": {
                "name": "Buyer Test",
                "phone": "900",
                "email": "buyer@test.com",
                "line": "1 Street",
                "city": "Bengaluru",
                "pincode": "560001",
                "state": "Karnataka",
            },
            "payment": "cod",
            "age_confirmed": True,
        },
    )
    assert order.status_code == 200
    public_id = order.json()["public_id"]
    listed = client.get("/api/v1/orders", headers=headers)
    assert listed.json()[0]["public_id"] == public_id
    one = client.get(f"/api/v1/orders/{public_id}", headers=headers)
    assert one.status_code == 200
    quiz = client.post("/api/v1/quiz", headers=headers, json={"answers": [[0], [1], [2]]})
    assert quiz.json()["result"] == "fit"
    prepaid = client.post(
        "/api/v1/orders",
        headers=headers,
        json={
            "sku": "SM-MB-15",
            "consult": {"name": "Buyer Test", "phone": "900", "email": "buyer@test.com"},
            "address": {
                "name": "Buyer Test",
                "phone": "900",
                "email": "buyer@test.com",
                "line": "1 Street",
                "city": "Delhi",
                "pincode": "110001",
                "state": "Delhi",
            },
            "payment": "prepaid",
            "age_confirmed": True,
        },
    )
    assert prepaid.status_code == 200
    rz = prepaid.json()["razorpay"]
    from app.core.config import Settings

    # verify with matching signature from same settings used by app
    secret = client.app.dependency_overrides  # noqa
    from app.integrations.razorpay import RazorpayGateway
    from app.core.config import get_settings

    settings = client.app.dependency_overrides[get_settings]()
    gateway = RazorpayGateway(settings)
    signature = gateway.sign_payment(rz["order_id"], "pay_test")
    verified = client.post(
        "/api/v1/payments/razorpay/verify",
        headers=headers,
        json={
            "public_id": prepaid.json()["public_id"],
            "razorpay_order_id": rz["order_id"],
            "razorpay_payment_id": "pay_test",
            "razorpay_signature": signature,
        },
    )
    assert verified.status_code == 200
    bad_sig = client.post(
        "/api/v1/payments/razorpay/verify",
        headers=headers,
        json={
            "public_id": prepaid.json()["public_id"],
            "razorpay_order_id": rz["order_id"],
            "razorpay_payment_id": "pay_test",
            "razorpay_signature": "nope",
        },
    )
    assert bad_sig.status_code == 422
    missing_order = client.post(
        "/api/v1/payments/razorpay/verify",
        headers=headers,
        json={
            "public_id": "SM-000000",
            "razorpay_order_id": "x",
            "razorpay_payment_id": "y",
            "razorpay_signature": "z",
        },
    )
    assert missing_order.status_code == 422


def test_webhook_and_admin(client: TestClient):
    client.post("/api/v1/auth/register", json={"email": "w@test.com", "password": "password1", "name": "Web Hook"})
    user_headers = auth_header(client, "w@test.com", "password1")
    prepaid = client.post(
        "/api/v1/orders",
        headers=user_headers,
        json={
            "sku": "SM-MB-30",
            "consult": {"name": "Web Hook", "phone": "1", "email": "w@test.com"},
            "address": {
                "name": "Web Hook",
                "phone": "1",
                "email": "w@test.com",
                "line": "x",
                "city": "Pune",
                "pincode": "411001",
                "state": "Maharashtra",
            },
            "payment": "prepaid",
            "age_confirmed": True,
        },
    )
    rz_id = prepaid.json()["razorpay"]["order_id"]
    from app.core.config import get_settings

    settings = client.app.dependency_overrides[get_settings]()
    body = json.dumps(
        {
            "event": "payment.captured",
            "payload": {"payment": {"entity": {"id": "pay_wh", "order_id": rz_id}}},
        }
    ).encode()
    signature = hmac.new(settings.razorpay_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    ok = client.post("/api/v1/webhooks/razorpay", data=body, headers={"X-Razorpay-Signature": signature})
    assert ok.status_code == 200
    bad = client.post("/api/v1/webhooks/razorpay", data=body, headers={"X-Razorpay-Signature": "x"})
    assert bad.status_code == 422
    empty = client.post(
        "/api/v1/webhooks/razorpay",
        data=b"{}",
        headers={"X-Razorpay-Signature": hmac.new(settings.razorpay_webhook_secret.encode(), b"{}", hashlib.sha256).hexdigest()},
    )
    assert empty.status_code == 200

    staff = auth_header(client, "meera@slowmo.co", "FounderDev123!", staff=True)
    customer_headers = user_headers
    blocked = client.get("/api/v1/admin/overview", headers=customer_headers)
    assert blocked.status_code == 403
    assert client.get("/api/v1/admin/me", headers=staff).status_code == 200
    config = client.get("/api/v1/payments/razorpay/config", headers=staff)
    assert config.status_code == 200
    assert config.json()["webhook_url"]
    assert config.json()["key_id"]
    customer_cfg = client.get("/api/v1/payments/razorpay/config", headers=customer_headers)
    assert customer_cfg.status_code == 403
    assert client.get("/api/v1/admin/counts", headers=staff).status_code == 200
    assert client.get("/api/v1/admin/overview", headers=staff).status_code == 200
    assert client.get("/api/v1/admin/orders", headers=staff).status_code == 200
    assert client.get("/api/v1/admin/orders/export", headers=staff).status_code == 200
    assert client.get("/api/v1/admin/consults", headers=staff).status_code == 200
    assert client.get("/api/v1/admin/customers", headers=staff).status_code == 200
    assert client.get("/api/v1/admin/analytics", headers=staff).status_code == 200
    assert client.get("/api/v1/admin/inventory", headers=staff).status_code == 200
    assert client.get("/api/v1/admin/dispatch", headers=staff).status_code == 200
    assert client.get("/api/v1/admin/dispatch/manifest", headers=staff).status_code == 200
    created = client.post(
        "/api/v1/auth/register",
        json={"email": "ship@test.com", "password": "password1", "name": "Ship User"},
    )
    ship_headers = {"Authorization": f"Bearer {created.json()['access_token']}"}
    order = client.post(
        "/api/v1/orders",
        headers=ship_headers,
        json={
            "sku": "SM-MB-10",
            "consult": {"name": "Ship User", "phone": "2", "email": "ship@test.com", "reason": "insomnia"},
            "address": {
                "name": "Ship User",
                "phone": "2",
                "email": "ship@test.com",
                "line": "y",
                "city": "Chennai",
                "pincode": "600001",
                "state": "Tamil Nadu",
            },
            "payment": "cod",
            "age_confirmed": True,
        },
    )
    public_id = order.json()["public_id"]
    client.post(f"/api/v1/admin/consults/{public_id}/reschedule", headers=staff, json={"slot": "Afternoon (12–5PM)"})
    client.post(f"/api/v1/admin/consults/{public_id}/complete", headers=staff, json={"notes": "done"})
    held = client.post(f"/api/v1/admin/orders/{public_id}/status", headers=staff, json={"status": "hold"})
    assert held.status_code == 200
    client.post(f"/api/v1/admin/orders/{public_id}/status", headers=staff, json={"status": "confirmed"})
    client.post(f"/api/v1/admin/dispatch/{public_id}", headers=staff)
    client.patch(f"/api/v1/admin/dispatch/{public_id}", headers=staff, json={"stage": "picked"})
    client.post(f"/api/v1/admin/dispatch/{public_id}/pickup", headers=staff)
    detailed = client.get(f"/api/v1/orders/{public_id}", headers=staff)
    assert detailed.status_code == 200
    body = detailed.json()
    assert body["age_confirmed"] is True
    assert body["consult"]["notes"] == "done"
    assert body["prescription"]["code"]
    assert body["shipment"]["stage"]
    receipt = client.post(
        "/api/v1/admin/inventory/receipts",
        headers=staff,
        json={"sku": "SM-MB-10", "qty": 3, "note": "box", "batch_code": "B-API-1"},
    )
    assert receipt.status_code == 200
    created = client.post(
        "/api/v1/admin/inventory/skus",
        headers=staff,
        json={
            "sku": "SM-MB-45",
            "name": "Slow Mo · 45 pack",
            "pack_qty": 45,
            "price": 12000,
            "mrp": 14000,
            "stock": 5,
            "weekly_forecast": 1,
        },
    )
    assert created.status_code == 200
    assert any(row["sku"] == "SM-MB-45" for row in created.json()["skus"])
    patched = client.patch("/api/v1/admin/products/SM-MB-10", headers=staff, json={"price": 3290})
    assert patched.status_code == 200
    missing_sku = client.patch("/api/v1/admin/products/NOPE", headers=staff, json={"active": False})
    assert missing_sku.status_code == 404
    staff_user = client.post(
        "/api/v1/admin/staff",
        headers=staff,
        json={"email": "clin@test.com", "password": "password1", "name": "Clin Ician", "role": "clinician"},
    )
    assert staff_user.status_code == 200
    rx_user = client.post("/api/v1/auth/register", json={"email": "rx@test.com", "password": "password1", "name": "Rx User"})
    rx_headers = {"Authorization": f"Bearer {rx_user.json()['access_token']}"}
    uploaded = client.post("/api/v1/files/rx", headers=rx_headers, files={"file": ("p.png", b"pngdata", "image/png")})
    rx_order = client.post(
        "/api/v1/orders",
        headers=rx_headers,
        json={
            "sku": "SM-MB-10",
            "rx_file_id": uploaded.json()["id"],
            "address": {
                "name": "Rx User",
                "phone": "3",
                "email": "rx@test.com",
                "line": "z",
                "city": "Kochi",
                "pincode": "682001",
                "state": "Kerala",
            },
            "payment": "cod",
            "age_confirmed": True,
        },
    )
    client.post(f"/api/v1/admin/consults/{rx_order.json()['public_id']}/verify-rx?accept=true", headers=staff)
    client.post(f"/api/v1/admin/consults/{rx_order.json()['public_id']}/verify-rx?accept=false", headers=staff)
    staff_download = client.get(f"/api/v1/files/rx/{uploaded.json()['id']}", headers=staff)
    assert staff_download.status_code == 200


def test_rate_limit_auth(client: TestClient):
    from app.core.config import get_settings
    from app.core.rate_limit import limiter

    settings = client.app.dependency_overrides[get_settings]()
    settings.rate_limit_auth = 1
    limiter.reset()
    first = client.post("/api/v1/auth/login", json={"email": "meera@slowmo.co", "password": "FounderDev123!"})
    assert first.status_code == 200
    second = client.post("/api/v1/auth/login", json={"email": "meera@slowmo.co", "password": "FounderDev123!"})
    assert second.status_code == 429
    settings.rate_limit_auth = 1000
    limiter.reset()
    settings.rate_limit_webhook = 1
    body = b"{}"
    signature = hmac.new(settings.razorpay_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    first_wh = client.post("/api/v1/webhooks/razorpay", data=body, headers={"X-Razorpay-Signature": signature})
    assert first_wh.status_code == 200
    second_wh = client.post("/api/v1/webhooks/razorpay", data=body, headers={"X-Razorpay-Signature": signature})
    assert second_wh.status_code == 429
    settings.rate_limit_webhook = 1000
    limiter.reset()

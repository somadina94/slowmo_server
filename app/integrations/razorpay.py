import hashlib
import hmac
from dataclasses import dataclass
from uuid import uuid4

import httpx

from app.core.config import Settings


class RazorpayError(Exception):
    pass


@dataclass
class RazorpayOrder:
    id: str
    amount: int
    currency: str


class RazorpayGateway:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _stubbed(self) -> bool:
        key = self.settings.razorpay_key_id.lower()
        secret = self.settings.razorpay_key_secret.lower()
        return "placeholder" in key or "placeholder" in secret

    def create_order(self, amount_paise: int, receipt: str) -> RazorpayOrder:
        if amount_paise <= 0:
            raise RazorpayError("amount must be positive")
        if self._stubbed():
            prefix = "order_" if not self.settings.is_prod else "order_live_"
            return RazorpayOrder(id=f"{prefix}{uuid4().hex[:14]}", amount=amount_paise, currency="INR")
        try:
            response = httpx.post(
                "https://api.razorpay.com/v1/orders",
                auth=(self.settings.razorpay_key_id, self.settings.razorpay_key_secret),
                json={"amount": amount_paise, "currency": "INR", "receipt": receipt[:40]},
                timeout=20.0,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            raise RazorpayError("failed to create Razorpay order") from exc
        order_id = data.get("id")
        if not order_id:
            raise RazorpayError("Razorpay order response missing id")
        return RazorpayOrder(
            id=str(order_id),
            amount=int(data.get("amount", amount_paise)),
            currency=str(data.get("currency", "INR")),
        )

    def verify_payment(self, order_id: str, payment_id: str, signature: str) -> bool:
        payload = f"{order_id}|{payment_id}".encode()
        expected = hmac.new(self.settings.razorpay_key_secret.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def verify_webhook(self, body: bytes, signature: str) -> bool:
        expected = hmac.new(self.settings.razorpay_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def sign_payment(self, order_id: str, payment_id: str) -> str:
        payload = f"{order_id}|{payment_id}".encode()
        return hmac.new(self.settings.razorpay_key_secret.encode(), payload, hashlib.sha256).hexdigest()

from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4


@dataclass
class ShipmentResult:
    awb: str
    carrier: str
    pickup_id: str = ""


class ShippingProvider(Protocol):
    def create_shipment(self, order_public_id: str, city: str) -> ShipmentResult: ...
    def track(self, awb: str) -> dict: ...
    def schedule_pickup(self, awb: str) -> str: ...
    def manifest(self, awbs: list[str]) -> str: ...


class StubShippingProvider:
    def create_shipment(self, order_public_id: str, city: str) -> ShipmentResult:
        return ShipmentResult(awb=f"STUB-{order_public_id}", carrier="stub")

    def track(self, awb: str) -> dict:
        return {"awb": awb, "status": "in_transit", "provider": "stub"}

    def schedule_pickup(self, awb: str) -> str:
        return f"PICKUP-{awb}-{uuid4().hex[:6]}"

    def manifest(self, awbs: list[str]) -> str:
        header = "awb"
        rows = "\n".join(awbs)
        return f"{header}\n{rows}\n"


def get_shipping_provider(name: str) -> ShippingProvider:
    if name == "stub":
        return StubShippingProvider()
    raise ValueError(f"unknown shipping provider: {name}")

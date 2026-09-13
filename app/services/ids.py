from datetime import datetime, timezone


def make_order_id(now: datetime | None = None) -> str:
    stamp = now or datetime.now(timezone.utc)
    return "SM-" + str(int(stamp.timestamp() * 1000))[-6:].upper()


def make_rx_code(order_public_id: str) -> str:
    tail = order_public_id.replace("SM-", "")[-4:]
    return f"RX-SM-{tail}"


def stock_level(stock: int, allocated: int, forecast: int) -> str:
    available = stock - allocated
    if forecast <= 0:
        return "hi" if available > 0 else "lo"
    cover = available / forecast
    if cover >= 1.5:
        return "hi"
    if cover >= 0.8:
        return "mid"
    return "lo"


def days_of_cover(stock: int, allocated: int, forecast: int) -> int:
    available = max(stock - allocated, 0)
    if forecast <= 0:
        return 99
    return max(int((available / forecast) * 7), 0)


def format_inr(value: int) -> str:
    if value >= 10000000:
        return f"₹{value / 10000000:.2f}Cr".replace(".00", "")
    if value >= 100000:
        formatted = value / 100000
        text = f"{formatted:.2f}".rstrip("0").rstrip(".")
        return f"₹{text}L"
    return f"₹{value:,}"


def greeting_for_hour(hour: int) -> str:
    if hour < 12:
        return "Good morning"
    if hour < 17:
        return "Good afternoon"
    return "Good evening"


def allowed_order_transition(current: str, nxt: str) -> bool:
    allowed = {
        "pending_payment": {"consult", "cancelled"},
        "consult": {"confirmed", "hold", "cancelled"},
        "confirmed": {"dispatched", "hold", "cancelled"},
        "dispatched": {"delivered"},
        "hold": {"consult", "confirmed", "cancelled"},
        "delivered": set(),
        "cancelled": set(),
    }
    return nxt in allowed.get(current, set())


def allowed_shipment_transition(current: str, nxt: str) -> bool:
    order = ["packed", "picked", "transit", "delivered"]
    if current not in order or nxt not in order:
        return False
    return order.index(nxt) == order.index(current) + 1

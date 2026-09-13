from collections.abc import Iterable

from app.core.exceptions import ForbiddenError

STAFF_ROLES = frozenset({"founder", "ops", "clinician", "admin"})
CUSTOMER_ROLE = "customer"

PERMISSIONS: dict[str, frozenset[str]] = {
    "founder": frozenset({"*"}),
    "admin": frozenset(
        {
            "admin.read",
            "admin.users",
            "orders.read",
            "orders.write",
            "consults.read",
            "consults.write",
            "inventory.read",
            "inventory.write",
            "dispatch.read",
            "dispatch.write",
            "analytics.read",
            "customers.read",
            "products.write",
        }
    ),
    "ops": frozenset(
        {
            "admin.read",
            "orders.read",
            "orders.write",
            "inventory.read",
            "inventory.write",
            "dispatch.read",
            "dispatch.write",
            "analytics.read",
            "customers.read",
        }
    ),
    "clinician": frozenset(
        {
            "admin.read",
            "consults.read",
            "consults.write",
            "orders.read",
            "customers.read",
        }
    ),
    "customer": frozenset({"account.read", "orders.own"}),
}


def is_staff(role: str) -> bool:
    return role in STAFF_ROLES


def has_permission(role: str, permission: str) -> bool:
    granted = PERMISSIONS.get(role, frozenset())
    return "*" in granted or permission in granted


def require_permission(role: str, permission: str) -> None:
    if not has_permission(role, permission):
        raise ForbiddenError("Insufficient permissions")


def require_any(role: str, permissions: Iterable[str]) -> None:
    if not any(has_permission(role, item) for item in permissions):
        raise ForbiddenError("Insufficient permissions")

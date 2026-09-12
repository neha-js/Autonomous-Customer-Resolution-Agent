"""
simulated_systems.py

Simulated enterprise systems the agent talks to:
- CustomerDB
- OrderAPI
- InventoryAPI
- ActionAPI (refund / replace / cancel - state changing)
- VerificationAPI (confirms the state change actually took effect)

Everything is in-memory so the whole thing runs with zero external
dependencies and zero setup. Swap these classes for real HTTP clients
later without touching the agent logic.
"""

from __future__ import annotations
import random
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Domain exceptions - these are what let the agent "notice" a blocked action
# ---------------------------------------------------------------------------

class SystemConflictError(Exception):
    """Base class for any simulated system pushing back on an action."""


class InsufficientStockError(SystemConflictError):
    pass


class PolicyViolationError(SystemConflictError):
    pass


class OrderStateError(SystemConflictError):
    pass


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class OrderStatus(str, Enum):
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
    REPLACED = "replaced"


@dataclass
class Customer:
    customer_id: str
    name: str
    tier: str  # "standard" | "premium"
    refund_disputes_last_90d: int = 0


@dataclass
class OrderItem:
    sku: str
    name: str
    qty: int
    unit_price: float


@dataclass
class Order:
    order_id: str
    customer_id: str
    items: list
    status: OrderStatus
    delivered_days_ago: Optional[int]  # None if not delivered yet
    total: float


# ---------------------------------------------------------------------------
# CustomerDB
# ---------------------------------------------------------------------------

class CustomerDB:
    def __init__(self):
        self._data = {
            "CUST-001": Customer("CUST-001", "Anjali Menon", "premium", refund_disputes_last_90d=0),
            "CUST-002": Customer("CUST-002", "Rahul Nair", "standard", refund_disputes_last_90d=3),
        }

    def get_customer(self, customer_id: str) -> Customer:
        if customer_id not in self._data:
            raise LookupError(f"No such customer: {customer_id}")
        return self._data[customer_id]


# ---------------------------------------------------------------------------
# OrderAPI
# ---------------------------------------------------------------------------

class OrderAPI:
    def __init__(self):
        self._data = {
            "ORD-1001": Order(
                "ORD-1001", "CUST-001",
                [OrderItem("SKU-BT-200", "Bluetooth Headphones (Black)", 1, 2499.0)],
                OrderStatus.DELIVERED, delivered_days_ago=4, total=2499.0,
            ),
            "ORD-1002": Order(
                "ORD-1002", "CUST-001",
                [OrderItem("SKU-KB-77", "Mechanical Keyboard", 1, 4200.0)],
                OrderStatus.DELIVERED, delivered_days_ago=2, total=4200.0,
            ),
            "ORD-1003": Order(
                "ORD-1003", "CUST-002",
                [OrderItem("SKU-SH-14", "Running Shoes (UK 9)", 1, 3199.0)],
                OrderStatus.DELIVERED, delivered_days_ago=45, total=3199.0,
            ),
            "ORD-1004": Order(
                "ORD-1004", "CUST-001",
                [OrderItem("SKU-MS-55", "Wireless Mouse", 1, 1499.0)],
                OrderStatus.DELIVERED, delivered_days_ago=3, total=1499.0,
            ),
            "ORD-1005": Order(
                "ORD-1005", "CUST-001",
                [OrderItem("SKU-BP-09", "Laptop Backpack", 1, 2799.0)],
                OrderStatus.DELIVERED, delivered_days_ago=60, total=2799.0,
            ),
        }

    def get_order(self, order_id: str) -> Order:
        if order_id not in self._data:
            raise LookupError(f"No such order: {order_id}")
        return self._data[order_id]

    def set_status(self, order_id: str, status: OrderStatus):
        self._data[order_id].status = status


# ---------------------------------------------------------------------------
# InventoryAPI
# ---------------------------------------------------------------------------

class InventoryAPI:
    def __init__(self):
        self._stock = {
            "SKU-BT-200": 0,     # out of stock -> forces replan away from replacement
            "SKU-KB-77": 12,
            "SKU-SH-14": 5,
            "SKU-MS-55": 1,      # looks available at check time...
            "SKU-BP-09": 8,
        }
        # SKUs in here fail their NEXT reserve() call exactly once, simulating
        # a downstream system (e.g. warehouse reservation) reporting a
        # conflict even though the earlier read-only stock check said OK.
        # This is what forces a genuine replan rather than a pre-filtered plan.
        self._force_fail_once = set()

    def check_stock(self, sku: str) -> int:
        return self._stock.get(sku, 0)

    def force_fail_next_reserve(self, sku: str):
        self._force_fail_once.add(sku)

    def reserve(self, sku: str, qty: int = 1):
        """Reserve stock for a replacement. Raises if blocked at execution time."""
        if sku in self._force_fail_once:
            self._force_fail_once.discard(sku)
            raise InsufficientStockError(
                f"Warehouse reservation system reports the last unit of {sku} "
                "was consumed by a concurrent order (race condition at execution time)"
            )
        available = self._stock.get(sku, 0)
        if available < qty:
            raise InsufficientStockError(f"Only {available} unit(s) of {sku} available, need {qty}")
        self._stock[sku] -= qty


# ---------------------------------------------------------------------------
# ActionAPI - the state-changing endpoints
# ---------------------------------------------------------------------------

class ActionAPI:
    def __init__(self, order_api: OrderAPI, inventory_api: InventoryAPI):
        self.order_api = order_api
        self.inventory_api = inventory_api
        self.action_log = {}  # action_id -> record, used by VerificationAPI

    def refund(self, order_id: str, amount: float) -> str:
        order = self.order_api.get_order(order_id)
        if order.status == OrderStatus.CANCELLED:
            raise OrderStateError("Cannot refund a cancelled order")
        action_id = str(uuid.uuid4())[:8]
        self.order_api.set_status(order_id, OrderStatus.REFUNDED)
        self.action_log[action_id] = {
            "type": "refund", "order_id": order_id, "amount": amount,
            "committed": True, "timestamp": time.time(),
        }
        return action_id

    def replace(self, order_id: str, sku: str) -> str:
        order = self.order_api.get_order(order_id)
        if order.status not in (OrderStatus.DELIVERED, OrderStatus.SHIPPED):
            raise OrderStateError(f"Cannot replace order in status {order.status}")
        # This is where a stock race condition can surface even if an earlier
        # read-only check_stock() call said stock was available.
        self.inventory_api.reserve(sku, qty=1)
        action_id = str(uuid.uuid4())[:8]
        self.order_api.set_status(order_id, OrderStatus.REPLACED)
        self.action_log[action_id] = {
            "type": "replace", "order_id": order_id, "sku": sku,
            "committed": True, "timestamp": time.time(),
        }
        return action_id

    def cancel(self, order_id: str) -> str:
        order = self.order_api.get_order(order_id)
        if order.status == OrderStatus.DELIVERED:
            raise OrderStateError("Cannot cancel an already-delivered order")
        action_id = str(uuid.uuid4())[:8]
        self.order_api.set_status(order_id, OrderStatus.CANCELLED)
        self.action_log[action_id] = {
            "type": "cancel", "order_id": order_id,
            "committed": True, "timestamp": time.time(),
        }
        return action_id


# ---------------------------------------------------------------------------
# VerificationAPI - independently re-queries system-of-record state
# ---------------------------------------------------------------------------

class VerificationAPI:
    def __init__(self, order_api: OrderAPI, action_api: ActionAPI):
        self.order_api = order_api
        self.action_api = action_api

    def verify(self, order_id: str, action_id: str, expected_status: OrderStatus) -> bool:
        record = self.action_api.action_log.get(action_id)
        if not record or not record.get("committed"):
            return False
        order = self.order_api.get_order(order_id)
        return order.status == expected_status

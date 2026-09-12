"""
agent.py

The autonomous loop itself. This is the piece the problem statement is
actually asking for: not a classifier, not a reply generator, but
something that:

  1. Understands the customer's goal and current case state
  2. Retrieves customer/order/inventory/policy evidence
  3. Selects a resolution
  4. Executes a state-changing action
  5. Verifies the effect
  6. Replans if blocked
  7. Escalates only when it genuinely cannot proceed safely

Every step is appended to an audit trail so the whole decision is
explainable after the fact - important both for a hackathon demo and
for a real support-ops setting.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from simulated_systems import (
    CustomerDB, OrderAPI, InventoryAPI, ActionAPI, VerificationAPI,
    OrderStatus, SystemConflictError,
)
from policy_rag import PolicyRAG
from planner import classify_issue, plan_resolution, ActionType, Candidate


@dataclass
class CaseResult:
    order_id: str
    resolved: bool
    final_action: Optional[str]
    escalated: bool
    audit_trail: list = field(default_factory=list)

    def log(self, msg: str):
        self.audit_trail.append(msg)

    def print_trail(self):
        for line in self.audit_trail:
            print(line)


class CustomerResolutionAgent:
    def __init__(self):
        self.customer_db = CustomerDB()
        self.order_api = OrderAPI()
        self.inventory_api = InventoryAPI()
        self.action_api = ActionAPI(self.order_api, self.inventory_api)
        self.verification_api = VerificationAPI(self.order_api, self.action_api)
        self.policy_rag = PolicyRAG()

    def handle_case(self, customer_id: str, order_id: str, message: str) -> CaseResult:
        result = CaseResult(order_id=order_id, resolved=False, final_action=None, escalated=False)

        # --- 1. Understand the goal -----------------------------------
        result.log(f"[UNDERSTAND] Customer message: \"{message}\"")
        issue_type = classify_issue(message)
        result.log(f"[UNDERSTAND] Classified issue type: {issue_type.value}")

        # --- 2. Retrieve evidence ---------------------------------------
        try:
            customer = self.customer_db.get_customer(customer_id)
            order = self.order_api.get_order(order_id)
        except LookupError as e:
            result.log(f"[RETRIEVE] Lookup failed: {e}")
            result.escalated = True
            result.log("[ESCALATE] Cannot proceed without valid customer/order records.")
            return result

        result.log(f"[RETRIEVE] Customer: {customer.name} (tier={customer.tier}, "
                    f"disputes_90d={customer.refund_disputes_last_90d})")
        result.log(f"[RETRIEVE] Order {order.order_id}: status={order.status.value}, "
                    f"item={order.items[0].name}, total={order.total}")

        stock_available = self.inventory_api.check_stock(order.items[0].sku)
        result.log(f"[RETRIEVE] Inventory check for {order.items[0].sku}: {stock_available} unit(s) on hand")

        policy_query = f"{issue_type.value} {message}"
        policy_chunks = self.policy_rag.retrieve(policy_query, k=3)
        result.log(f"[RETRIEVE] Policy RAG matched: {[c.doc_id for c in policy_chunks]}")

        # --- 3. Select a resolution (ranked candidates) ------------------
        candidates = plan_resolution(issue_type, order, customer, stock_available, policy_chunks)
        result.log(f"[PLAN] Candidate actions (ranked): "
                    f"{[c.action.value for c in candidates]}")

        # --- 4-6. Execute -> Verify -> Replan loop ------------------------
        for idx, candidate in enumerate(candidates):
            result.log(f"[PLAN] Attempting candidate #{idx+1}: {candidate.action.value} "
                        f"- {candidate.reason}")

            if candidate.action == ActionType.ESCALATE:
                result.escalated = True
                result.log(f"[ESCALATE] {candidate.reason}")
                return result

            try:
                action_id, expected_status = self._execute(order.order_id, candidate)
                result.log(f"[EXECUTE] {candidate.action.value} committed "
                            f"(action_id={action_id})")
            except SystemConflictError as e:
                result.log(f"[EXECUTE] BLOCKED: {e}")
                result.log("[REPLAN] Falling back to next candidate action.")
                continue  # replan: try the next candidate

            # --- 5. Verify ------------------------------------------------
            verified = self.verification_api.verify(order.order_id, action_id, expected_status)
            if verified:
                result.log(f"[VERIFY] Confirmed order {order.order_id} status is now "
                            f"'{expected_status.value}'.")
                result.resolved = True
                result.final_action = candidate.action.value
                return result
            else:
                result.log("[VERIFY] Could not confirm expected state change - treating as blocked.")
                result.log("[REPLAN] Falling back to next candidate action.")
                continue

        # If we exhaust every candidate without success, escalate.
        result.escalated = True
        result.log("[ESCALATE] All candidate resolutions were blocked or unverifiable - "
                    "handing off to a human agent rather than leaving the case unresolved.")
        return result

    def _execute(self, order_id: str, candidate: Candidate):
        """Dispatch to the right action endpoint. Returns (action_id, expected_status)."""
        if candidate.action == ActionType.REPLACE:
            action_id = self.action_api.replace(order_id, candidate.sku)
            return action_id, OrderStatus.REPLACED
        elif candidate.action == ActionType.REFUND:
            action_id = self.action_api.refund(order_id, candidate.amount)
            return action_id, OrderStatus.REFUNDED
        elif candidate.action == ActionType.CANCEL:
            action_id = self.action_api.cancel(order_id)
            return action_id, OrderStatus.CANCELLED
        else:
            raise ValueError(f"No executor for action {candidate.action}")

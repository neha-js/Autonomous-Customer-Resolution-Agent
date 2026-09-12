"""
planner.py

Turns (customer message + retrieved evidence + policy) into a RANKED list
of candidate resolutions. Returning a ranked list rather than one decision
is what makes replanning cheap: if candidate #1 gets blocked at execution
time, the agent just tries candidate #2 without re-reasoning from scratch.

This is intentionally rule-based + policy-grounded rather than a black box,
so every decision is explainable to a judge/reviewer. The `reasoner_hook`
at the bottom shows where you'd swap in an LLM call (e.g. Claude) for the
classification step in a production version.
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from simulated_systems import Order, OrderStatus, Customer


class IssueType(str, Enum):
    DAMAGED_DEFECTIVE = "damaged_defective"
    WRONG_ITEM = "wrong_item"
    CHANGE_OF_MIND = "change_of_mind"
    LATE_DELIVERY = "late_delivery"
    UNKNOWN = "unknown"


class ActionType(str, Enum):
    REPLACE = "replace"
    REFUND = "refund"
    CANCEL = "cancel"
    ESCALATE = "escalate"


@dataclass
class Candidate:
    action: ActionType
    reason: str
    sku: Optional[str] = None
    amount: Optional[float] = None


_KEYWORDS = {
    IssueType.DAMAGED_DEFECTIVE: ["damaged", "broken", "defective", "not working", "doesn't work", "faulty"],
    IssueType.WRONG_ITEM: ["wrong item", "wrong size", "wrong color", "different product", "not what i ordered"],
    IssueType.CHANGE_OF_MIND: ["don't want", "changed my mind", "no longer need", "return it"],
    IssueType.LATE_DELIVERY: ["late", "hasn't arrived", "still waiting", "delayed"],
}


def classify_issue(message: str) -> IssueType:
    """Rule-based intent classification. Swap for an LLM call for nuance."""
    lowered = message.lower()
    for issue_type, keywords in _KEYWORDS.items():
        if any(kw in lowered for kw in keywords):
            return issue_type
    return IssueType.UNKNOWN


def plan_resolution(
    issue_type: IssueType,
    order: Order,
    customer: Customer,
    stock_available: int,
    policy_chunks: list,
) -> list:
    """
    Returns a ranked list of Candidate resolutions, most-preferred first.
    The executor will try them in order until one succeeds or the list
    is exhausted (-> escalate).
    """
    candidates: list = []
    policy_ids = {c.doc_id for c in policy_chunks}

    # Hard gate: fraud/dispute risk always escalates first, regardless of
    # how clean the underlying claim looks. This mirrors FRAUD-RISK policy.
    if customer.refund_disputes_last_90d > 2:
        return [Candidate(
            ActionType.ESCALATE,
            reason=(
                f"Customer has {customer.refund_disputes_last_90d} refund disputes "
                "in the last 90 days -> requires manual review per FRAUD-RISK policy "
                "before any automated refund/replacement."
            ),
        )]

    item = order.items[0]

    if issue_type == IssueType.DAMAGED_DEFECTIVE:
        # Prefer replacement if in stock; fall back to refund.
        if stock_available > 0:
            candidates.append(Candidate(ActionType.REPLACE, sku=item.sku,
                               reason="Item reported damaged/defective and replacement stock is available "
                                      "(DAMAGED-DEFECTIVE policy: free replacement or refund)."))
        candidates.append(Candidate(ActionType.REFUND, amount=order.total,
                           reason="Fallback/primary refund for damaged/defective item per DAMAGED-DEFECTIVE policy."))

    elif issue_type == IssueType.WRONG_ITEM:
        if stock_available > 0:
            candidates.append(Candidate(ActionType.REPLACE, sku=item.sku,
                               reason="Fulfillment error (wrong item) - free replacement per WRONG-ITEM policy."))
        candidates.append(Candidate(ActionType.REFUND, amount=order.total,
                           reason="Fulfillment error (wrong item) - full refund, return window waived per WRONG-ITEM policy."))

    elif issue_type == IssueType.CHANGE_OF_MIND:
        if order.status in (OrderStatus.PROCESSING, OrderStatus.SHIPPED):
            candidates.append(Candidate(ActionType.CANCEL,
                               reason="Order not yet delivered - free cancellation available per CANCELLATION policy."))
        elif order.delivered_days_ago is not None and order.delivered_days_ago <= 30:
            candidates.append(Candidate(ActionType.REFUND, amount=order.total,
                               reason=f"Within standard {order.delivered_days_ago}-day return window per RETURN-WINDOW policy."))
        else:
            candidates.append(Candidate(ActionType.ESCALATE,
                               reason="Change-of-mind return requested outside the standard return window; "
                                      "no policy exception applies - needs human judgment call."))

    else:  # UNKNOWN / LATE_DELIVERY / anything not clearly covered
        candidates.append(Candidate(ActionType.ESCALATE,
                           reason=f"Issue type '{issue_type.value}' is not confidently classified against "
                                  "available policy documents - escalating rather than guessing."))

    return candidates


# ---------------------------------------------------------------------------
# Where an LLM reasoner would slot in for a production version
# ---------------------------------------------------------------------------

def reasoner_hook_placeholder():
    """
    In production, classify_issue() and the ranking inside plan_resolution()
    could be replaced by a single Claude call that is given:
      - the customer message
      - retrieved policy chunks
      - order/customer/inventory snapshots
    and asked to return a ranked JSON list of candidate actions with
    reasons. The rest of the agent loop (execute/verify/replan/escalate)
    does not need to change at all - it only depends on getting back a
    list[Candidate].
    """
    raise NotImplementedError("Hook point only - see docstring.")

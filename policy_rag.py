"""
policy_rag.py

A minimal retrieval-augmented policy lookup. Real deployments would swap
this for a proper embedding index (e.g. LangChain + a vector store), but
the *interface* the agent depends on - retrieve(query, k) -> [chunks] -
stays identical, so this is a drop-in upgrade path.

Retrieval here uses simple token-overlap scoring (TF-based cosine on
bag-of-words) so the demo has zero external dependencies and is fully
deterministic for grading/testing.
"""

from __future__ import annotations
import math
import re
from collections import Counter
from dataclasses import dataclass


@dataclass
class PolicyChunk:
    doc_id: str
    text: str


POLICY_DOCS = [
    PolicyChunk(
        "RETURN-WINDOW",
        "Standard return and refund window is 30 days from delivery for all "
        "products, except electronics which have a 7 day window for "
        "change-of-mind returns.",
    ),
    PolicyChunk(
        "DAMAGED-DEFECTIVE",
        "If an item arrives damaged or defective, the customer is entitled to "
        "a free replacement or a full refund regardless of the standard "
        "return window, provided the claim is made within 15 days of delivery.",
    ),
    PolicyChunk(
        "WRONG-ITEM",
        "If the item delivered does not match the order (wrong SKU, size, or "
        "color), this is treated as a fulfillment error. The customer may "
        "request replacement or refund at no cost, and the standard return "
        "window does not apply.",
    ),
    PolicyChunk(
        "REPLACEMENT-STOCK",
        "Replacements can only be issued if the requested SKU is in stock. "
        "If out of stock, the case must fall back to a full refund instead "
        "of an indefinite backorder.",
    ),
    PolicyChunk(
        "REFUND-METHOD",
        "Refunds are issued to the original payment method within 5-7 "
        "business days of approval. Premium tier customers are eligible for "
        "instant refund processing.",
    ),
    PolicyChunk(
        "FRAUD-RISK",
        "Any refund request from a customer with more than 2 refund disputes "
        "in the last 90 days must be escalated to a human agent for manual "
        "review before any refund or replacement is issued, even if the "
        "underlying claim appears valid.",
    ),
    PolicyChunk(
        "CANCELLATION",
        "Orders can be cancelled free of charge only while in 'processing' "
        "or 'shipped' status. Once an order is marked delivered, cancellation "
        "is no longer available and the case must be handled as a return.",
    ),
]


def _tokenize(text: str) -> Counter:
    words = re.findall(r"[a-z]+", text.lower())
    return Counter(words)


def _cosine(a: Counter, b: Counter) -> float:
    common = set(a) & set(b)
    dot = sum(a[t] * b[t] for t in common)
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class PolicyRAG:
    def __init__(self, docs=None):
        self.docs = docs or POLICY_DOCS
        self._vectors = [(d, _tokenize(d.text)) for d in self.docs]

    def retrieve(self, query: str, k: int = 3) -> list:
        q_vec = _tokenize(query)
        scored = [(_cosine(q_vec, v), d) for d, v in self._vectors]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [d for score, d in scored[:k] if score > 0]

# Autonomous Customer Resolution Agent

This agent **resolves** tickets end to end
against simulated enterprise systems — it doesn't just classify or draft a
reply. It inspects evidence, picks an action, executes a state change,
verifies it landed, and replans if something blocks it.

## Run it

```bash
python main.py            # runs 4 built-in demo scenarios with full audit trails
python main.py --case      # interactive: type your own customer_id/order_id/message
```

No external dependencies, no API keys — everything is simulated in-memory
so it runs anywhere Python 3 does.

## Files

| File | Role |
|---|---|
| `simulated_systems.py` | CustomerDB, OrderAPI, InventoryAPI, ActionAPI (refund/replace/cancel), VerificationAPI. Raises domain exceptions (`InsufficientStockError`, `OrderStateError`, `PolicyViolationError`) when an action is blocked — that's the signal the agent replans on. |
| `policy_rag.py` | Retrieval over a small policy corpus (return window, damaged/defective, wrong item, fraud-risk, cancellation rules). Cosine-similarity over bag-of-words — zero dependencies, deterministic, and swappable for a real embedding index later. |
| `planner.py` | Classifies the issue type and produces a **ranked list** of candidate actions given evidence + policy. Ranking (not a single decision) is what makes replanning cheap. |
| `agent.py` | The orchestration loop: understand → retrieve → plan → execute → verify → replan → escalate. Produces a full audit trail per case. |
| `scenarios.py` / `main.py` | Four demo cases and a CLI runner. |

## How each requirement is met

- **Understand goal + case state** — `classify_issue()` + evidence retrieval in `agent.handle_case()`.
- **Retrieve customer/order/inventory/policy** — `CustomerDB`, `OrderAPI`, `InventoryAPI`, `PolicyRAG`, all called before any decision is made.
- **Select a resolution from evidence + constraints** — `plan_resolution()`, gated by a hard fraud/dispute-risk check before anything else.
- **Execute a state-changing action** — `ActionAPI.refund/replace/cancel()`, which actually mutate the simulated order/inventory state.
- **Verify the effect** — `VerificationAPI.verify()` independently re-queries the order record rather than trusting the action call's return value.
- **Replan when blocked** — Scenario B: inventory shows 1 unit at check time, but the reservation call fails at execution time (simulated race condition). The agent catches `InsufficientStockError` and falls back to the next ranked candidate (refund), then verifies that instead.
- **Escalate only when it can't safely proceed** — two distinct paths: Scenario C escalates immediately on a fraud/dispute-risk gate (never attempts an action), Scenario D escalates because no policy exception covers a change-of-mind return outside the window — the agent declines to guess rather than taking an ungrounded action.

## Extending toward a "smarter" reasoner

`classify_issue()` and the ranking logic in `plan_resolution()` are rule-based
by design, so every decision is explainable during a demo/review. The
natural upgrade path (noted in `planner.reasoner_hook_placeholder`) is to
replace just that step with an LLM call — e.g. Claude given the customer
message + retrieved policy chunks + order/customer/inventory snapshot,
returning a ranked JSON list of candidates. Nothing else in the loop
(execute/verify/replan/escalate) needs to change, since it only depends on
getting back a `list[Candidate]`.

Similarly, `policy_rag.py`'s bag-of-words retrieval is a drop-in point for
a real embedding index (e.g. LangChain + FAISS/Chroma) if you want to scale
the policy corpus beyond a handful of documents.

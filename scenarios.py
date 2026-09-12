"""
scenarios.py

Four demo cases chosen to exercise every branch the problem statement
asks for:

  A. Straightforward resolution      - damaged item, stock available, replace succeeds first try.
  B. Genuine replan                  - stock LOOKS available at check time, but the reservation
                                        call is blocked at execution time (race condition), so the
                                        agent falls back to its next candidate (refund) and verifies it.
  C. Escalation - fraud/risk gate    - a refund request from a customer with a bad dispute history
                                        is escalated for manual review BEFORE any action is attempted,
                                        even though the underlying claim looks clean.
  D. Escalation - policy gap         - a change-of-mind return requested well outside the standard
                                        return window, where no policy exception applies, so the
                                        agent declines to guess and hands off to a human.
"""

from agent import CustomerResolutionAgent


def run_scenario(title: str, fn):
    print("=" * 78)
    print(title)
    print("=" * 78)
    fn()
    print()


def scenario_a_straightforward():
    agent = CustomerResolutionAgent()
    result = agent.handle_case(
        customer_id="CUST-001",
        order_id="ORD-1002",
        message="My mechanical keyboard arrived damaged, several keys don't work.",
    )
    result.print_trail()
    print(f"\n>> resolved={result.resolved} action={result.final_action} escalated={result.escalated}")


def scenario_b_replan_on_race_condition():
    agent = CustomerResolutionAgent()
    # Force the SKU's reservation to fail exactly once, simulating a
    # downstream system conflict discovered only at execution time.
    agent.inventory_api.force_fail_next_reserve("SKU-MS-55")
    result = agent.handle_case(
        customer_id="CUST-001",
        order_id="ORD-1004",
        message="The wireless mouse I received is defective, the scroll wheel doesn't work.",
    )
    result.print_trail()
    print(f"\n>> resolved={result.resolved} action={result.final_action} escalated={result.escalated}")


def scenario_c_escalate_fraud_gate():
    agent = CustomerResolutionAgent()
    result = agent.handle_case(
        customer_id="CUST-002",  # has 3 refund disputes in last 90 days
        order_id="ORD-1003",
        message="I'd like to return these shoes, I changed my mind.",
    )
    result.print_trail()
    print(f"\n>> resolved={result.resolved} action={result.final_action} escalated={result.escalated}")


def scenario_d_escalate_policy_gap():
    agent = CustomerResolutionAgent()
    result = agent.handle_case(
        customer_id="CUST-001",
        order_id="ORD-1005",
        message="I don't want this backpack anymore, can I return it?",
    )
    result.print_trail()
    print(f"\n>> resolved={result.resolved} action={result.final_action} escalated={result.escalated}")


if __name__ == "__main__":
    run_scenario("SCENARIO A - Straightforward replacement (damaged item, stock available)",
                 scenario_a_straightforward)
    run_scenario("SCENARIO B - Replan after execution-time stock conflict (race condition)",
                 scenario_b_replan_on_race_condition)
    run_scenario("SCENARIO C - Escalation: fraud/dispute-risk gate fires before any action",
                 scenario_c_escalate_fraud_gate)
    run_scenario("SCENARIO D - Escalation: outside return window, no policy exception applies",
                 scenario_d_escalate_policy_gap)

"""
main.py

Run:
    python main.py            -> runs all 4 demo scenarios with full audit trails
    python main.py --case     -> interactive mode, type your own customer_id/order_id/message
"""

import sys
from agent import CustomerResolutionAgent
import scenarios


def interactive():
    print("Autonomous Customer Resolution Agent - interactive mode")
    print("Known customers: CUST-001 (clean history), CUST-002 (3 disputes/90d)")
    print("Known orders: ORD-1001, ORD-1002, ORD-1003, ORD-1004, ORD-1005\n")
    agent = CustomerResolutionAgent()
    customer_id = input("customer_id: ").strip() or "CUST-001"
    order_id = input("order_id: ").strip() or "ORD-1002"
    message = input("customer message: ").strip() or "This item arrived damaged."
    result = agent.handle_case(customer_id, order_id, message)
    print()
    result.print_trail()
    print(f"\n>> resolved={result.resolved} action={result.final_action} escalated={result.escalated}")


if __name__ == "__main__":
    if "--case" in sys.argv:
        interactive()
    else:
        scenarios.run_scenario("SCENARIO A - Straightforward replacement (damaged item, stock available)",
                                scenarios.scenario_a_straightforward)
        scenarios.run_scenario("SCENARIO B - Replan after execution-time stock conflict (race condition)",
                                scenarios.scenario_b_replan_on_race_condition)
        scenarios.run_scenario("SCENARIO C - Escalation: fraud/dispute-risk gate fires before any action",
                                scenarios.scenario_c_escalate_fraud_gate)
        scenarios.run_scenario("SCENARIO D - Escalation: outside return window, no policy exception applies",
                                scenarios.scenario_d_escalate_policy_gap)

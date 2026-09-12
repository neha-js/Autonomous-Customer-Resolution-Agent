"""
streamlit_app.py

Interactive web front-end for the Autonomous Customer Resolution Agent.
Run locally with:  streamlit run streamlit_app.py
Deploy free on Streamlit Community Cloud (see README.md).
"""

import re
import streamlit as st
from agent import CustomerResolutionAgent

st.set_page_config(
    page_title="Resolution Agent",
    page_icon=None,
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# Custom styling - dark, black/grey, no default Streamlit chrome
# ---------------------------------------------------------------------------
st.markdown("""
<style>
#MainMenu, footer, header {visibility: hidden;}
html, body, [class*="css"] {
    font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}
.block-container {
    max-width: 760px;
    padding-top: 2.5rem;
    padding-bottom: 3rem;
}

/* Header */
.app-eyebrow {
    color: #8A8F98;
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin-bottom: 0.35rem;
}
.app-title {
    color: #F4F4F5;
    font-size: 2.05rem;
    font-weight: 700;
    letter-spacing: -0.01em;
    margin-bottom: 0.5rem;
}
.app-sub {
    color: #A1A1AA;
    font-size: 0.98rem;
    line-height: 1.55;
    margin-bottom: 1.9rem;
    max-width: 620px;
}

/* Section label */
.section-label {
    color: #D4D4D8;
    font-size: 0.9rem;
    font-weight: 600;
    margin: 1.6rem 0 0.6rem 0;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}
.section-label::before {
    content: "";
    display: inline-block;
    width: 6px; height: 6px;
    border-radius: 50%;
    background: #52525B;
}

/* Native widget restyle */
div[data-testid="stSelectbox"] > div > div,
div[data-testid="stTextInput"] input,
div[data-testid="stTextArea"] textarea {
    background-color: #17181A !important;
    border: 1px solid #2A2B2E !important;
    color: #E4E4E7 !important;
    border-radius: 8px !important;
}
div[data-testid="stTextInput"] input:disabled,
div[data-testid="stTextArea"] textarea:disabled {
    color: #8A8F98 !important;
    -webkit-text-fill-color: #8A8F98 !important;
    opacity: 1 !important;
}
label { color: #A1A1AA !important; font-size: 0.83rem !important; }

button[kind="primary"], button[kind="secondary"] {
    border-radius: 8px !important;
    font-weight: 600 !important;
    border: 1px solid #2A2B2E !important;
}
button[kind="primary"] {
    background-color: #E4E4E7 !important;
    color: #0B0B0C !important;
}
button[kind="primary"]:hover { background-color: #FFFFFF !important; }
button[kind="secondary"] {
    background-color: transparent !important;
    color: #A1A1AA !important;
}

.stCaption, [data-testid="stCaptionContainer"] { color: #71717A !important; }

/* Status pill */
.status-pill {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 0.95rem;
    border-radius: 999px;
    font-size: 0.86rem;
    font-weight: 600;
    margin: 0.3rem 0 1rem 0;
}
.status-resolved { background: #0E2A1B; color: #4ADE80; border: 1px solid #16532F; }
.status-escalated { background: #2A1A0E; color: #FBBF24; border: 1px solid #53390F; }
.status-dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }

/* Terminal-style audit trail */
.trail-box {
    background: #0F0F10;
    border: 1px solid #232427;
    border-radius: 10px;
    padding: 1.1rem 1.2rem;
    font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
    font-size: 0.82rem;
    line-height: 1.85;
    overflow-x: auto;
    white-space: pre-wrap;
    word-break: break-word;
}
.tag-understand { color: #A78BFA; }
.tag-retrieve   { color: #60A5FA; }
.tag-plan       { color: #E4E4E7; }
.tag-execute    { color: #FBBF24; }
.tag-verify     { color: #4ADE80; }
.tag-replan     { color: #FB923C; }
.tag-escalate   { color: #F87171; }
.trail-line { color: #D4D4D8; }

.footer-note {
    color: #52525B;
    font-size: 0.78rem;
    margin-top: 2.2rem;
    border-top: 1px solid #1F2023;
    padding-top: 1rem;
}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown('<div class="app-title">Autonomous Customer Resolution Agent</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="app-sub">Retrieves customer, order, inventory and policy evidence, '
    'executes a state-changing action against simulated enterprise systems, verifies the '
    'effect, and replans on its own when it gets blocked.</div>',
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Agent state
# ---------------------------------------------------------------------------
if "agent" not in st.session_state:
    st.session_state.agent = CustomerResolutionAgent()
    st.session_state.agent.inventory_api.force_fail_next_reserve("SKU-MS-55")

agent = st.session_state.agent

PRESETS = {
    "A · Damaged item, stock available": (
        "CUST-001", "ORD-1002", "My mechanical keyboard arrived damaged, several keys don't work."
    ),
    "B · Replan on a blocked action (race condition)": (
        "CUST-001", "ORD-1004", "The wireless mouse I received is defective, the scroll wheel doesn't work."
    ),
    "C · Escalation — fraud / dispute-risk gate": (
        "CUST-002", "ORD-1003", "I'd like to return these shoes, I changed my mind."
    ),
    "D · Escalation — outside return window": (
        "CUST-001", "ORD-1005", "I don't want this backpack anymore, can I return it?"
    ),
    "Custom case": None,
}

st.markdown('<div class="section-label">RUN A CASE</div>', unsafe_allow_html=True)
choice = st.selectbox("Scenario", list(PRESETS.keys()), label_visibility="collapsed")

if choice == "Custom case":
    col1, col2 = st.columns(2)
    customer_id = col1.text_input("Customer ID", value="CUST-001")
    order_id = col2.text_input("Order ID", value="ORD-1002")
    message = st.text_area("Customer message", value="This item arrived damaged.", height=90)
else:
    customer_id, order_id, message = PRESETS[choice]
    col1, col2 = st.columns(2)
    col1.text_input("Customer ID", value=customer_id, disabled=True)
    col2.text_input("Order ID", value=order_id, disabled=True)
    st.text_area("Customer message", value=message, disabled=True, height=90)

st.caption("Known customers  ·  CUST-001 (clean history)  ·  CUST-002 (3 refund disputes / 90d)")
st.caption("Known orders  ·  ORD-1001 · ORD-1002 · ORD-1003 · ORD-1004 · ORD-1005")

run_clicked = st.button("Run agent", type="primary", use_container_width=True)

# ---------------------------------------------------------------------------
# Result rendering
# ---------------------------------------------------------------------------
TAG_CLASS = {
    "UNDERSTAND": "tag-understand",
    "RETRIEVE": "tag-retrieve",
    "PLAN": "tag-plan",
    "EXECUTE": "tag-execute",
    "VERIFY": "tag-verify",
    "REPLAN": "tag-replan",
    "ESCALATE": "tag-escalate",
}

def render_trail(trail_lines):
    html_lines = []
    for line in trail_lines:
        m = re.match(r"^\[([A-Z]+)\](.*)$", line)
        if m:
            tag, rest = m.group(1), m.group(2)
            cls = TAG_CLASS.get(tag, "trail-line")
            html_lines.append(f'<span class="{cls}">[{tag}]</span><span class="trail-line">{rest}</span>')
        else:
            html_lines.append(f'<span class="trail-line">{line}</span>')
    return '<div class="trail-box">' + "\n".join(html_lines) + "</div>"

if run_clicked:
    with st.spinner("Understanding → retrieving → planning → executing → verifying..."):
        result = agent.handle_case(customer_id, order_id, message)

    if result.resolved:
        st.markdown(
            f'<div class="status-pill status-resolved"><span class="status-dot"></span>'
            f'Resolved &middot; action taken: {result.final_action}</div>',
            unsafe_allow_html=True,
        )
    elif result.escalated:
        st.markdown(
            '<div class="status-pill status-escalated"><span class="status-dot"></span>'
            'Escalated to a human agent</div>',
            unsafe_allow_html=True,
        )

    st.markdown('<div class="section-label">AUDIT TRAIL</div>', unsafe_allow_html=True)
    st.markdown(render_trail(result.audit_trail), unsafe_allow_html=True)

st.markdown(
    '<div class="footer-note">Neha Jose · B.Tech CSE, Vimal Jyothi Engineering College</div>',
    unsafe_allow_html=True,
)

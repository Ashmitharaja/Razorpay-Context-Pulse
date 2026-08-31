import os
import json
import sqlite3
import pandas as pd
import requests
import streamlit as st

st.set_page_config(
    page_title="Razorpay ContextPulse", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- WHITE AND ORANGE THEME STYLING WITH HIGH CONTRAST INPUTS ---
st.markdown(
    """
    <style>
    /* Main App Background */
    .stApp {
        background: linear-gradient(135deg, #FFF8F5 0%, #FFFFFF 100%);
        color: #1A202C !important;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }

    /* Force global text color visibility */
    h1, h2, h3, h4, h5, h6, p, label, span, div {
        color: #2D3748 !important;
    }

    /* Sidebar Background */
    section[data-testid="stSidebar"] {
        background-color: #FFF0E6 !important;
        border-right: 1px solid #FFD8C2 !important;
    }
    
    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3,
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] span {
        color: #2D3748 !important;
        font-weight: 600 !important;
    }

    /* Target all Input Fields (Number inputs, Text inputs) */
    div[data-baseweb="input"], div[data-baseweb="input"] > div {
        background-color: #FFFFFF !important;
        border: 1.5px solid #FF6B00 !important;
        border-radius: 6px !important;
    }

    /* Force Typed Text inside Input Boxes to be Bold Dark Black */
    input[type="text"], input[type="number"], .stNumberInput input {
        color: #000000 !important;
        background-color: #FFFFFF !important;
        -webkit-text-fill-color: #000000 !important;
        font-weight: 600 !important;
        font-size: 1rem !important;
    }

    /* Number Input Buttons (+ / -) */
    button[title="Decrease value"], button[title="Increase value"] {
        background-color: #FFFFFF !important;
        color: #FF6B00 !important;
        border-color: #FF6B00 !important;
    }

    /* Metric Cards */
    [data-testid="stMetric"] {
        background-color: #FFFFFF !important;
        border: 1px solid #FFE4D6 !important;
        border-radius: 10px !important;
        padding: 16px !important;
        box-shadow: 0px 4px 12px rgba(255, 107, 0, 0.05) !important;
    }
    
    [data-testid="stMetricLabel"] {
        color: #4A5568 !important;
        font-weight: 700 !important;
        font-size: 0.85rem !important;
        letter-spacing: 0.5px;
    }
    
    [data-testid="stMetricValue"] {
        color: #FF6B00 !important;
        font-weight: 800 !important;
    }

    /* Reasoning Trace Box */
    .trace-card {
        background-color: #FFFFFF;
        border-left: 5px solid #FF6B00;
        border-radius: 8px;
        padding: 20px;
        box-shadow: 0px 2px 8px rgba(0, 0, 0, 0.04);
        border-top: 1px solid #FFE4D6;
        border-right: 1px solid #FFE4D6;
        border-bottom: 1px solid #FFE4D6;
        margin-top: 8px;
        color: #2D3748 !important;
    }

    /* Divider Lines */
    hr {
        border-top: 1px solid #FFE4D6 !important;
    }
    
    /* Main Sidebar Trigger Button */
    .stButton button {
        background-color: #FF6B00 !important;
        color: #FFFFFF !important;
        border: none !important;
        border-radius: 6px !important;
        font-weight: 700 !important;
        width: 100%;
    }
    .stButton button:hover {
        background-color: #E05D00 !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

DB_PATH = os.getenv("DATABASE_PATH", "contextpulse.db")
BACKEND_URL = os.getenv("BASE_URL", "http://localhost:8000")


def get_db_connection():
    if not os.path.exists(DB_PATH):
        return None
    return sqlite3.connect(DB_PATH)


def fetch_metrics_from_backend():
    try:
        res = requests.get(f"{BACKEND_URL}/metrics", timeout=3)
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return None


def fetch_latest_events():
    conn = get_db_connection()
    if conn is None:
        return pd.DataFrame()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [t[0] for t in cursor.fetchall()]
        
        table_name = "recovery_records" if "recovery_records" in tables else "recoveries"
        if table_name not in tables:
            conn.close()
            return pd.DataFrame()

        df = pd.read_sql_query(f"SELECT * FROM {table_name} ORDER BY id DESC", conn)
        conn.close()
        return df
    except Exception:
        if conn:
            conn.close()
        return pd.DataFrame()


# --- SIDEBAR: CONTROLS & TEST SIMULATION ---
st.sidebar.title("Configuration & Actions")
send_twilio = st.sidebar.checkbox("Send SMS via Twilio", value=False)
auto_refresh = st.sidebar.checkbox("Auto-Refresh UI", value=True)

st.sidebar.markdown("---")
st.sidebar.subheader("Test Simulation")

# Empty defaults so you can type manually, with optional placeholder guides
test_amount = st.sidebar.number_input("Transaction Amount (INR)", value=None, placeholder="e.g. 500")
test_phone = st.sidebar.text_input("Customer Phone", value="", placeholder="+91 9876543210")
trigger_btn = st.sidebar.button("Trigger payment.failed Webhook")

if trigger_btn:
    if not test_amount or not test_phone:
        st.sidebar.error("Please enter both an amount and a phone number.")
    else:
        clean_phone = test_phone.replace(" ", "").strip()
        payload = {
            "amount": float(test_amount),
            "customer_phone": clean_phone,
            "send_notifications": send_twilio,
        }
        
        try:
            res = requests.post(f"{BACKEND_URL}/simulate/payment-failed", json=payload, timeout=60)
            if res.status_code == 200:
                st.sidebar.success("Webhook triggered successfully!")
                st.rerun()
            else:
                st.sidebar.error(f"Failed with status: {res.status_code}")
        except Exception as e:
            st.sidebar.error(f"Could not connect to backend: {e}")

# --- MAIN DASHBOARD HEADER ---
st.title("Razorpay ContextPulse")
st.caption("Agentic Auto-Fallback and Micro-Channel Revenue Recovery")
st.markdown("<br>", unsafe_allow_html=True)

# Fetch Metrics Data
df_events = fetch_latest_events()
metrics_api = fetch_metrics_from_backend()

if metrics_api:
    total_analyzed = metrics_api.get("total_events", 0)
    failed_revenue = metrics_api.get("failed_revenue_analyzed", 0.0)
    successful_recoveries = metrics_api.get("auto_recoveries", 0)
    recovered_amount = metrics_api.get("recovered_amount", 0.0)
    lift = metrics_api.get("conversion_lift_pct", 0.0)
elif not df_events.empty:
    total_analyzed = len(df_events)
    recovered_col = "recovered" if "recovered" in df_events.columns else "is_recovered"
    successful_recoveries = len(df_events[df_events[recovered_col] == 1]) if recovered_col in df_events.columns else 0
    failed_revenue = df_events["amount"].sum() if "amount" in df_events.columns else 0.0
    recovered_amount = df_events[df_events[recovered_col] == 1]["amount"].sum() if (recovered_col in df_events.columns and "amount" in df_events.columns) else 0.0
    lift = (recovered_amount / failed_revenue * 100.0) if failed_revenue > 0 else 0.0
else:
    total_analyzed = 0
    successful_recoveries = 0
    failed_revenue = 0.0
    recovered_amount = 0.0
    lift = 0.0

# Extract Reasoning & Links
if not df_events.empty:
    latest_event = df_events.iloc[0]
    reasoning_raw = latest_event.get("reasoning_json") or latest_event.get("reasoning") or ""
    if isinstance(reasoning_raw, str):
        try:
            reasoning_trace = json.loads(reasoning_raw)
        except Exception:
            reasoning_trace = reasoning_raw
    else:
        reasoning_trace = reasoning_raw or "No decision recorded."

    payment_link = latest_event.get("payment_link") or "No link generated."
    decided_by = latest_event.get("decided_by") or "Rule Engine Fallback"
else:
    reasoning_trace = "Waiting for payment.failed webhook events..."
    payment_link = "No active link generated yet."
    decided_by = "N/A"

# --- TOP METRICS DISPLAY ---
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(label="FAILED REVENUE ANALYZED", value=f"INR {int(failed_revenue):,}")

with col2:
    st.metric(label="SUCCESSFUL AUTO-RECOVERIES", value=f"{successful_recoveries} / {total_analyzed}")

with col3:
    st.metric(label="RECOVERED AMOUNT", value=f"INR {int(recovered_amount):,}")

with col4:
    st.metric(label="EST. CONVERSION LIFT", value=f"{lift:.1f}%")

st.markdown("<hr>", unsafe_allow_html=True)

# --- REASONING TRACE & PAYMENT LINK PANEL ---
left_col, right_col = st.columns([1.3, 1])

with left_col:
    st.subheader("Agent Reasoning Trace")
    st.markdown(f"**Decision Engine:** `{decided_by}`")
    
    # Render structured output card
    with st.container():
        st.markdown('<div class="trace-card">', unsafe_allow_html=True)
        if isinstance(reasoning_trace, list):
            for step in reasoning_trace:
                st.markdown(f"- {step}")
        else:
            st.markdown(str(reasoning_trace))
        st.markdown('</div>', unsafe_allow_html=True)

with right_col:
    st.subheader("Live Razorpay Payment Link")
    st.markdown("<br>", unsafe_allow_html=True)
    st.text_input(
        label="Active Recovery URL",
        value=payment_link,
        disabled=True,
    )
    if isinstance(payment_link, str) and payment_link.startswith("http"):
        st.success("Sent via Razorpay Native SMS")
    else:
        st.warning("No recovery SMS sent yet")

st.markdown("<hr>", unsafe_allow_html=True)

# --- RECENT WEBHOOK & RECOVERY EVENTS TABLE ---
st.subheader("Recent Webhook & Recovery Events")

if not df_events.empty:
    display_df = df_events.copy()
    
    # Format boolean / numeric columns for better visibility
    if "recovered" in display_df.columns:
        display_df["recovered"] = display_df["recovered"].apply(lambda x: "Recovered" if x in [1, True] else "Pending")
    
    if "amount" in display_df.columns:
        display_df["amount"] = display_df["amount"].apply(lambda x: f"INR {x:,.2f}")
        
    # Standardize column header titles
    column_mapping = {
        "event_id": "Event ID",
        "order_reference": "Order Ref",
        "customer_name": "Customer Name",
        "customer_phone": "Phone Number",
        "amount": "Amount",
        "decline_reason": "Decline Reason",
        "payment_method": "Method",
        "decided_by": "Engine",
        "recovered": "Status",
        "created_at": "Timestamp"
    }
    
    display_df = display_df.rename(columns=column_mapping)
    
    # Select available columns for clean layout
    preferred_cols = ["Event ID", "Customer Name", "Phone Number", "Amount", "Decline Reason", "Method", "Engine", "Status", "Timestamp"]
    cols_to_show = [c for c in preferred_cols if c in display_df.columns]
    
    st.dataframe(
        display_df[cols_to_show] if cols_to_show else display_df, 
        use_container_width=True,
        hide_index=True
    )
else:
    st.info("No recovery records stored in contextpulse.db yet.")
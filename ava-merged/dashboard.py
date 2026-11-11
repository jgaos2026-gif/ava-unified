"""AVA Sovereign Intelligence Dashboard — CORRECTED version.

Fix vs the pasted dashboard: statuses are MEASURED via healthcheck.py,
not hardcoded. A service that does not answer shows OFFLINE.
Requires: pip install streamlit (see requirements.txt, optional section).
The health-check logic itself is in healthcheck.py and is tested
without Streamlit.
"""
import httpx
import streamlit as st

from healthcheck import check_all

st.set_page_config(page_title="AVA Sovereign Intelligence Dashboard", layout="wide")
st.title("AVA Core Telemetry (measured, not labeled)")

results = check_all()
cols = st.columns(len(results))
for col, r in zip(cols, results):
    with col:
        st.metric(r["service"], r["status"])

st.write("### Execute an orchestration cycle")
user_input = st.text_input("Enter a brief:")
if st.button("Launch orchestration"):
    if user_input:
        with st.spinner("Calling the orchestrator..."):
            try:
                res = httpx.post("http://127.0.0.1:8775/orchestrate",
                                 json={"context_stream": user_input}, timeout=15.0)
                data = res.json()
                st.success("Cycle completed.")
                st.write(f"Vector context injected: {data.get('vector_context_injected')}")
                st.write(f"Brain fallback (no model): {data.get('brain_fallback')}")
                st.info(data.get("ai_reasoning_output"))
            except Exception as e:
                st.error(f"Orchestrator unreachable: {e}")
    else:
        st.warning("Please enter a brief first.")

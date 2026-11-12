import os
import sys
from pathlib import Path
import json

# Fix Matplotlib cache directory before any import
os.environ["MPLCONFIGDIR"] = str(Path(__file__).resolve().parent / ".cache" / "matplotlib")

import streamlit as st
import pandas as pd

import config
from main import run_chipgen_pipeline, DEFAULT_HARDWARE_PROMPT

# Configure Streamlit page
st.set_page_config(
    page_title="ChipGen AI | 4-Stage Hardware Synthesis Pipeline",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Dark Theme CSS
st.markdown("""
<style>
    .stApp {
        background-color: #0B0F19;
        color: #E2E8F0;
    }
    div[data-testid="stMetric"] {
        background-color: #1E293B;
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 12px 16px;
    }
    div[data-testid="stMetricLabel"] {
        color: #94A3B8;
        font-size: 0.85rem;
    }
    div[data-testid="stMetricValue"] {
        color: #F8FAFC;
        font-weight: 700;
    }
</style>
""", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.title("⚡ ChipGen AI")
    st.markdown("**Autonomous RTL Generation, Verification & PPA Optimization**")
    st.markdown("---")

    api_key_input = st.text_input(
        "Google Gemini API Key",
        value=config.GOOGLE_API_KEY or "",
        type="password",
        help="Required for Specification, RTL Generation, and Optimization"
    )

    model_choice = st.selectbox(
        "Gemini Model",
        ["gemini-3.5-flash-lite", "gemini-2.5-flash", "gemini-2.5-pro"],
        index=0
    )

    max_opt_iterations = st.slider("Max Optimization Iterations", min_value=1, max_value=5, value=2)

    st.markdown("---")
    st.markdown("### 🛠️ EDA Tools Status")
    tool_status = {
        "iverilog": bool(config.IVERILOG_PATH),
        "vvp": bool(config.VVP_PATH),
        "yosys": bool(config.YOSYS_PATH)
    }
    for tool, ok in tool_status.items():
        st.write(f"**{tool.upper()}**: {'🟢 Available' if ok else '🔴 Missing'}")

# Main Layout
st.title("Autonomous Chip Generation Pipeline")
st.markdown(
    "Accepts natural language hardware requirements &rarr; **Specification Agent** &rarr; "
    "**RTL Generation Agent** &rarr; **Verification Agent** &rarr; **PPA Optimization Agent**."
)

user_input = st.text_area(
    "Enter Hardware Specification Prompt:",
    value=DEFAULT_HARDWARE_PROMPT,
    height=120,
    help="Describe any custom digital hardware (e.g. ALU, saturating arithmetic, MAC unit, FIR filter)."
)

col1, col2 = st.columns([1, 4])
with col1:
    run_btn = st.button("🚀 Run Pipeline", type="primary")

if run_btn:
    if not api_key_input:
        st.error("Please enter a Google Gemini API Key in the sidebar.")
    else:
        with st.spinner("Executing 4-stage ChipGen AI Pipeline..."):
            try:
                res = run_chipgen_pipeline(
                    user_prompt=user_input,
                    api_key=api_key_input,
                    model_name=model_choice,
                    max_opt_iterations=max_opt_iterations
                )
                st.session_state["pipeline_result"] = res
                st.success("✅ Complete Pipeline Executed Successfully!")
            except Exception as e:
                st.error(f"Pipeline error: {e}")

# Render Results
if "pipeline_result" in st.session_state:
    res = st.session_state["pipeline_result"]
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📄 Verified RTL",
        "🧪 Self-Checking Testbench",
        "📊 Synthesis & PPA Reports",
        "📈 PPA Comparison",
        "⚡ Circuit Schematic"
    ])

    with tab1:
        st.subheader("Verified Synthesizable Verilog RTL")
        if Path(res["verified_rtl"]).is_file():
            st.code(Path(res["verified_rtl"]).read_text(encoding="utf-8"), language="verilog")

    with tab2:
        st.subheader("Auto-Generated Self-Checking Testbench")
        if Path(res["testbench"]).is_file():
            st.code(Path(res["testbench"]).read_text(encoding="utf-8"), language="verilog")

    with tab3:
        st.subheader("Synthesis Reports & Logs")
        if Path(res["synthesis_reports"]).is_file():
            with open(res["synthesis_reports"], "r", encoding="utf-8") as f:
                data = json.load(f)
            st.json(data)

    with tab4:
        st.subheader("PPA Synthesis Comparison")
        if Path(res["ppa_comparison"]).is_file():
            st.image(res["ppa_comparison"], caption="PPA Comparison Matrix (Area, Timing, Power Proxy)")

    with tab5:
        st.subheader("RTL Circuit Schematic")
        if Path(res["circuit_visualization"]).is_file():
            st.image(res["circuit_visualization"], caption="Synthesized Gate-Level Schematic Diagram")

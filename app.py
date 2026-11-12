import os
from pathlib import Path

# Fix Matplotlib cache directory before any import
os.environ["MPLCONFIGDIR"] = str(Path(__file__).resolve().parent / ".cache" / "matplotlib")

import json
import streamlit as st
import pandas as pd

import config
from eda.simulator import Simulator
from eda.synthesizer import Synthesizer
from agents.rtl_generator import RTLGenerator
from agents.verification_agent import VerificationAgent
from agents.synthesis_agent import SynthesisAgent
from agents.optimization_agent import OptimizationAgent
from utils.file_manager import FileManager
from utils.visualization import generate_comparison_charts
from main import DEFAULT_ALU_SPEC, run_pipeline

# Configure Streamlit page
st.set_page_config(
    page_title="ChipGen AI | RTL Generation & PPA Optimization",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Dark Theme CSS
st.markdown("""
<style>
    /* Dark Theme Core */
    .stApp {
        background-color: #0B0F19;
        color: #E2E8F0;
    }
    .css-1d391kg, .css-12oz5g7 {
        background-color: #111827;
    }
    /* Metric Cards */
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
        color: #38BDF8;
        font-weight: 700;
    }
    /* Status Badges */
    .badge-pass {
        background-color: #064E3B;
        color: #34D399;
        padding: 4px 10px;
        border-radius: 6px;
        font-weight: bold;
        display: inline-block;
    }
    .badge-fail {
        background-color: #7F1D1D;
        color: #F87171;
        padding: 4px 10px;
        border-radius: 6px;
        font-weight: bold;
        display: inline-block;
    }
    .badge-info {
        background-color: #0C4A6E;
        color: #38BDF8;
        padding: 4px 10px;
        border-radius: 6px;
        font-weight: bold;
        display: inline-block;
    }
    /* Headers */
    h1, h2, h3 {
        color: #F8FAFC !important;
    }
</style>
""", unsafe_allow_html=True)

# Session State Initialization
if "current_rtl" not in st.session_state:
    baseline_path = FileManager.get_baseline_rtl_path()
    st.session_state.current_rtl = FileManager.load_rtl(baseline_path) if baseline_path.is_file() else ""
if "current_rtl_path" not in st.session_state:
    st.session_state.current_rtl_path = str(FileManager.get_baseline_rtl_path())
if "sim_result" not in st.session_state:
    st.session_state.sim_result = None
if "synth_metrics" not in st.session_state:
    st.session_state.synth_metrics = None
if "opt_report" not in st.session_state:
    st.session_state.opt_report = None
if "benchmark_results" not in st.session_state:
    st.session_state.benchmark_results = None

# Sidebar Controls
with st.sidebar:
    st.markdown("## ⚡ ChipGen AI")
    st.caption("Hardware Design Automation & Optimization Agent")
    st.divider()

    # EDA Tool Status Indicator
    st.markdown("### 🛠️ EDA Tool Status")
    eda_status = config.get_eda_status()
    for tool_name, info in eda_status.items():
        found = info["found"]
        c1, c2 = st.columns([1, 2])
        c1.markdown(f"**{tool_name}**")
        if found:
            c2.markdown('<span class="badge-pass">ONLINE</span>', unsafe_allow_html=True)
        else:
            c2.markdown('<span class="badge-fail">MISSING</span>', unsafe_allow_html=True)

    st.divider()

    # API Configuration
    st.markdown("### 🔑 API & Model Settings")
    api_key_input = st.text_input(
        "Google API Key",
        value=config.GOOGLE_API_KEY or "",
        type="password",
        help="Enter your Google Gemini API key to enable live LLM generation and optimization."
    )
    model_choice = st.selectbox(
        "Gemini Model",
        ["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-3.8-flash"],
        index=0
    )
    max_rep = st.slider("Max Repair Attempts", 1, 5, 3)
    max_opt = st.slider("Max Optimization Iterations", 1, 5, 3)

    st.divider()

    # Quick Benchmark Action
    if st.button("🚀 Run 3-Stage Benchmark", type="primary", use_container_width=True):
        with st.spinner("Executing full baseline vs one-shot vs optimized evaluation with real EDA tools..."):
            res = run_pipeline(
                api_key=api_key_input if api_key_input else None,
                model_name=model_choice,
                max_repair_attempts=max_rep,
                max_optimization_attempts=max_opt
            )
            st.session_state.benchmark_results = res.get("results")
            st.success("Benchmark evaluation completed!")

# Main Application Tabs
tab_gen, tab_verif, tab_synth, tab_opt, tab_bench, tab_diag = st.tabs([
    "📝 RTL Generation",
    "🧪 Verification",
    "⚡ Yosys Synthesis",
    "🛠️ PPA Optimization",
    "📊 Benchmark Matrix",
    "🔍 EDA Diagnostics"
])

# -------------------------------------------------------------
# TAB 1: RTL Generation
# -------------------------------------------------------------
with tab_gen:
    st.markdown("### 📝 Natural Language Hardware Specification")
    spec_text = st.text_area(
        "Hardware Functional Specification",
        value=DEFAULT_ALU_SPEC,
        height=280
    )

    c_btn1, c_btn2, c_btn3 = st.columns([1, 1, 3])
    with c_btn1:
        gen_btn = st.button("✨ Generate RTL (LLM)", type="primary", use_container_width=True)
    with c_btn2:
        load_base_btn = st.button("📁 Load Baseline ALU", use_container_width=True)

    if load_base_btn:
        b_path = FileManager.get_baseline_rtl_path()
        if b_path.is_file():
            st.session_state.current_rtl = FileManager.load_rtl(b_path)
            st.session_state.current_rtl_path = str(b_path)
            st.info("Loaded baseline 16-bit ALU RTL.")

    if gen_btn:
        if not api_key_input:
            st.error("Please enter a Google API Key in the sidebar to generate RTL with Gemini.")
        else:
            with st.spinner("Querying Gemini with structured Pydantic schema..."):
                try:
                    generator = RTLGenerator(api_key=api_key_input, model_name=model_choice)
                    output, saved_path = generator.generate(
                        specification=spec_text,
                        module_name="alu_16bit",
                        save_filename="alu_16bit_generated.v"
                    )
                    st.session_state.current_rtl = output.verilog_code
                    st.session_state.current_rtl_path = str(saved_path)
                    st.success(f"Generated module `{output.module_name}` successfully! Saved to `{saved_path}`.")
                except Exception as e:
                    st.error(f"Generation failed: {e}")

    st.markdown("#### 📄 Current Verilog RTL")
    edited_code = st.text_area("Verilog Source Code", value=st.session_state.current_rtl, height=350)
    st.session_state.current_rtl = edited_code

    st.download_button(
        "⬇️ Download RTL (.v)",
        data=st.session_state.current_rtl,
        file_name="alu_16bit.v",
        mime="text/plain"
    )

# -------------------------------------------------------------
# TAB 2: Verification
# -------------------------------------------------------------
with tab_verif:
    st.markdown("### 🧪 Deterministic RTL Verification")
    st.caption("Compiles with Icarus Verilog (`iverilog`) and simulates reference vectors with `vvp`.")

    col_v1, col_v2 = st.columns([1, 2])
    with col_v1:
        verify_btn = st.button("▶️ Run Functional Verification", type="primary", use_container_width=True)
    with col_v2:
        auto_repair = st.checkbox("Enable Automated LLM Error Repair (up to 3 attempts)", value=True)

    if verify_btn:
        temp_path = FileManager.save_rtl(st.session_state.current_rtl, "generated", "current_active.v")
        st.session_state.current_rtl_path = str(temp_path)

        with st.spinner("Running simulation with Icarus Verilog..."):
            sim = Simulator()
            if auto_repair and api_key_input:
                verifier = VerificationAgent(
                    simulator=sim,
                    api_key=api_key_input,
                    model_name=model_choice,
                    max_repair_attempts=max_rep
                )
                rep = verifier.verify_and_repair(
                    rtl_path=temp_path,
                    specification=spec_text,
                    module_name="alu_16bit"
                )
                st.session_state.sim_result = rep.final_simulation
                if rep.passed:
                    st.session_state.current_rtl = FileManager.load_rtl(rep.final_rtl_path)
                    st.session_state.current_rtl_path = rep.final_rtl_path
                    st.success(rep.summary)
                else:
                    st.error(rep.summary)
            else:
                tb_path = FileManager.get_deterministic_tb_path()
                sim_res = sim.run_simulation(temp_path, tb_path)
                st.session_state.sim_result = sim_res
                if sim_res.passed:
                    st.success(f"Verification PASSED: {sim_res.tests_passed}/{sim_res.tests_run} tests passed.")
                else:
                    st.error(f"Verification FAILED: {sim_res.tests_failed}/{sim_res.tests_run} tests failed.")

    if st.session_state.sim_result:
        res = st.session_state.sim_result
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Status", "PASSED" if res.passed else "FAILED")
        m2.metric("Tests Run", res.tests_run)
        m3.metric("Passed", res.tests_passed)
        m4.metric("Failed", res.tests_failed)

        with st.expander("📋 Simulation Console Logs (vvp stdout)", expanded=True):
            st.code(res.simulation_stdout or "No simulation stdout captured.", language="text")

        if res.compilation_stderr or res.simulation_stderr or res.error_summary:
            with st.expander("⚠️ Error & Failure Details", expanded=not res.passed):
                st.code(res.error_summary, language="text")

# -------------------------------------------------------------
# TAB 3: Yosys Synthesis
# -------------------------------------------------------------
with tab_synth:
    st.markdown("### ⚡ Real RTL Synthesis with Yosys")
    st.caption("Executes standard generic gate mapping via Yosys and extracts structural cell statistics.")

    synth_run_btn = st.button("⚙️ Synthesize Current RTL", type="primary")

    if synth_run_btn:
        temp_path = FileManager.save_rtl(st.session_state.current_rtl, "generated", "current_active.v")
        with st.spinner("Synthesizing with Yosys..."):
            synth = Synthesizer()
            metrics = synth.synthesize(temp_path, top_module="alu_16bit")
            st.session_state.synth_metrics = metrics
            if metrics.success:
                st.success(f"Synthesis completed in {metrics.synthesis_time_seconds:.3f}s!")
            else:
                st.error(f"Synthesis failed: {metrics.error_message}")

    if st.session_state.synth_metrics:
        m = st.session_state.synth_metrics
        st.info(f"ℹ️ {m.metric_type_note}")

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Total Cells", m.total_cells, help="Logic complexity proxy")
        c2.metric("MUX Cells", m.mux_count, help="Multiplexer count")
        c3.metric("Logic Gates", m.logic_cell_count, help="Combinational logic")
        c4.metric("Sequential Cells", m.sequential_cell_count, help="Flip-flops / Latches")
        c5.metric("Runtime", f"{m.synthesis_time_seconds:.3f}s")

        st.markdown("#### 📊 Cell Primitive Breakdown")
        if m.cell_types:
            df_cells = pd.DataFrame(list(m.cell_types.items()), columns=["Cell Primitive", "Count"])
            st.bar_chart(df_cells.set_index("Cell Primitive"))

        with st.expander("📄 Complete Yosys Synthesis Log", expanded=False):
            if m.log_path and os.path.isfile(m.log_path):
                with open(m.log_path, "r", encoding="utf-8") as lf:
                    st.code(lf.read(), language="text")

# -------------------------------------------------------------
# TAB 4: PPA Optimization
# -------------------------------------------------------------
with tab_opt:
    st.markdown("### 🛠️ LLM-Guided Iterative PPA Optimization")
    st.caption("Iteratively optimizes RTL while verifying every candidate with Icarus Verilog and Yosys.")

    opt_obj = st.selectbox(
        "Optimization Objective",
        [
            "Minimize total generic cell count and multiplexer logic through arithmetic resource sharing",
            "Minimize multiplexer trees and routing congestion",
            "Boolean logic factoring and expression sharing"
        ]
    )

    opt_btn = st.button("🚀 Start Iterative Optimization", type="primary")

    if opt_btn:
        if not api_key_input:
            st.error("Please enter a Google API Key in the sidebar to run LLM optimization.")
        else:
            temp_path = FileManager.save_rtl(st.session_state.current_rtl, "generated", "current_active.v")
            # Synthesize current to get base metrics if not yet available
            if not st.session_state.synth_metrics or not st.session_state.synth_metrics.success:
                st.session_state.synth_metrics = Synthesizer().synthesize(temp_path, top_module="alu_16bit")

            with st.spinner("Running iterative optimization candidates..."):
                opt_agent = OptimizationAgent(
                    api_key=api_key_input,
                    model_name=model_choice,
                    max_iterations=max_opt
                )
                report = opt_agent.optimize(
                    initial_rtl_path=temp_path,
                    specification=spec_text,
                    initial_metrics=st.session_state.synth_metrics,
                    optimization_objective=opt_obj,
                    module_name="alu_16bit"
                )
                st.session_state.opt_report = report
                st.session_state.current_rtl = FileManager.load_rtl(report.best_rtl_path)
                st.session_state.current_rtl_path = report.best_rtl_path
                st.session_state.synth_metrics = report.best_metrics
                if report.optimization_accepted:
                    st.success(f"🏆 {report.summary}")
                else:
                    st.warning(f"⚠️ {report.summary}")

    if st.session_state.opt_report:
        rep = st.session_state.opt_report
        st.markdown("#### 📈 Optimization Run Audit")
        col_o1, col_o2, col_o3, col_o4 = st.columns(4)
        col_o1.metric("Evaluated", rep.total_candidates_evaluated)
        col_o2.metric("Accepted", rep.candidates_accepted)
        col_o3.metric("Rejected", rep.candidates_rejected)
        col_o4.metric("Reduction", f"{rep.cell_count_reduction_pct:+.1f}%")

        if not rep.optimization_accepted:
            st.info("ℹ️ Honest EDA Reporting: No candidate improved generic cell count or MUX complexity while maintaining 100% functional verification. The verified baseline/one-shot implementation was retained.")

        rows = []
        for c in rep.candidates:
            rows.append({
                "Iteration": c.iteration,
                "Candidate": c.candidate_name,
                "Verified": "✅ PASS" if c.verification_passed else "❌ FAIL",
                "Repairs Used": c.repair_attempts,
                "Synthesized": "✅ YES" if c.synthesis_success else "❌ NO",
                "Total Cells": c.synthesis_metrics.total_cells if c.synthesis_metrics else "N/A",
                "MUX Count": c.synthesis_metrics.mux_count if c.synthesis_metrics else "N/A",
                "Status": "🏆 ACCEPTED" if c.accepted else "❌ REJECTED",
                "Notes": c.improvement_notes
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True)

# -------------------------------------------------------------
# TAB 5: Benchmark Matrix
# -------------------------------------------------------------
with tab_bench:
    st.markdown("### 📊 Hardware Synthesis & PPA Comparison Matrix")
    st.caption("Empirical EDA measurements across Baseline, One-Shot AI, and Optimized AI designs.")

    report_json_path = config.REPORTS_DIR / "experiment_results.json"
    chart_png_path = config.REPORTS_DIR / "comparison_chart.png"

    # Load latest benchmark data
    if report_json_path.is_file():
        with open(report_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            st.session_state.benchmark_results = data.get("results", [])

    if st.session_state.benchmark_results:
        results = st.session_state.benchmark_results
        cols = ["name", "verification_passed", "total_cells", "mux_count", "logic_cell_count", "sequential_cell_count", "synthesis_time_seconds"]
        if "cell_delta_vs_baseline_pct" in results[0]:
            cols.append("cell_delta_vs_baseline_pct")
            df = pd.DataFrame(results)[cols]
            df.columns = ["Design", "Verified", "Total Cells (Proxy)", "MUX Count", "Logic Gates", "Sequential", "Runtime (s)", "vs Baseline"]
            df["vs Baseline"] = df["vs Baseline"].apply(lambda x: f"{x:+.1f}%" if pd.notnull(x) else "0.0%")
        else:
            df = pd.DataFrame(results)[cols]
            df.columns = ["Design", "Verified", "Total Cells (Proxy)", "MUX Count", "Logic Gates", "Sequential", "Runtime (s)"]
        st.dataframe(df, use_container_width=True)

        if chart_png_path.is_file():
            st.image(str(chart_png_path), caption="PPA Synthesis Comparison Matrix (Matplotlib)", use_container_width=True)

        col_d1, col_d2 = st.columns(2)
        with col_d1:
            if report_json_path.is_file():
                with open(report_json_path, "r", encoding="utf-8") as jf:
                    st.download_button(
                        "⬇️ Download Experiment JSON",
                        data=jf.read(),
                        file_name="experiment_results.json",
                        mime="application/json"
                    )
        with col_d2:
            if chart_png_path.is_file():
                with open(chart_png_path, "rb") as pf:
                    st.download_button(
                        "⬇️ Download Comparison Chart (.png)",
                        data=pf.read(),
                        file_name="comparison_chart.png",
                        mime="image/png"
                    )
    else:
        st.info("Click '🚀 Run 3-Stage Benchmark' in the sidebar to generate the comparison matrix.")

# -------------------------------------------------------------
# TAB 6: EDA Diagnostics
# -------------------------------------------------------------
with tab_diag:
    st.markdown("### 🔍 EDA Tool Diagnostics & System Environment")
    st.json(eda_status)

    st.markdown("#### Testbench Specification (`alu_16bit_tb.v`)")
    tb_file = FileManager.get_deterministic_tb_path()
    if tb_file.is_file():
        with open(tb_file, "r", encoding="utf-8") as tbf:
            st.code(tbf.read()[:1500] + "\n// ... [truncated for display]", language="verilog")


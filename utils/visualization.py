import os
import subprocess
import tempfile
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
import pydot

import config

os.environ.setdefault("MPLCONFIGDIR", str(config.BASE_DIR / ".cache" / "matplotlib"))

def generate_circuit_visualization(
    verilog_path: str | Path,
    top_module: str,
    output_png_path: str | Path | None = None
) -> Path:
    """
    Renders high-resolution circuit schematic diagram from synthesizable Verilog
    using Yosys AST/RTL elaborator (proc) and export to Graphviz DOT, then renders via NetworkX.
    """
    v_path = Path(verilog_path).resolve()
    out_png = Path(output_png_path or (config.REPORTS_DIR / "circuit_schematic.png")).resolve()
    out_png.parent.mkdir(parents=True, exist_ok=True)

    dot_temp = out_png.with_suffix(".dot")
    clean_v_path = str(v_path).replace(chr(92), "/")
    prefix = str(dot_temp.with_suffix("")).replace(chr(92), "/")

    script = f"""
read_verilog -sv "{clean_v_path}"
hierarchy -check -top {top_module}
proc
opt_clean
show -format dot -prefix "{prefix}"
"""

    with tempfile.NamedTemporaryFile(suffix=".ys", mode="w", delete=False) as f:
        f.write(script)
        script_path = f.name

    try:
        env = os.environ.copy()
        if config.YOSYS_LIB_DIR:
            env["PATH"] = f"{config.YOSYS_LIB_DIR};" + env.get("PATH", "")

        cmd = [config.YOSYS_PATH, "-s", script_path]
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
        
        # Check if dot file exists
        if not dot_temp.is_file():
            # Yosys adds .dot automatically
            alt_dot = Path(f"{prefix}.dot")
            if alt_dot.is_file():
                dot_temp = alt_dot

        if dot_temp.is_file():
            # Render via pydot and NetworkX
            try:
                graphs = pydot.graph_from_dot_file(str(dot_temp))
                if graphs:
                    G = nx.drawing.nx_pydot.from_pydot(graphs[0])
                    
                    plt.figure(figsize=(14, 10), facecolor="#0B0F19")
                    ax = plt.gca()
                    ax.set_facecolor("#0F172A")
                    
                    pos = nx.spring_layout(G, seed=42, k=0.3)
                    nx.draw_networkx_nodes(G, pos, node_size=80, node_color="#38BDF8", alpha=0.9, ax=ax)
                    nx.draw_networkx_edges(G, pos, edge_color="#475569", alpha=0.6, arrows=True, arrowsize=10, ax=ax)
                    
                    # Highlight module and port labels
                    labels = {n: str(n).replace('\\', '') for n in G.nodes() if not str(n).startswith('$')}
                    nx.draw_networkx_labels(G, pos, labels=labels, font_size=8, font_color="#F8FAFC", font_weight="bold", ax=ax)
                    
                    plt.title(f"ChipGen AI: Synthesized RTL Circuit Graph ({top_module})", fontsize=15, fontweight="bold", color="#F8FAFC", pad=15)
                    plt.axis("off")
                    plt.tight_layout()
                    plt.savefig(out_png, dpi=200, facecolor="#0B0F19", edgecolor="none")
                    plt.close()
                    print(f"[CircuitViz] Circuit schematic saved to: {out_png}")
                    return out_png
            except Exception as e:
                print(f"[CircuitViz] NetworkX rendering failed: {e}")
    finally:
        if os.path.exists(script_path):
            try:
                os.remove(script_path)
            except OSError:
                pass

    return out_png

def generate_comparison_charts(
    results: list[dict],
    output_path: str | Path | None = None
) -> Path:
    """
    Generates professional dark-themed comparison bar charts comparing:
    - Total Cell Count (Area Complexity Proxy)
    - Multiplexer Cell Count
    - Timing: Critical Path Logic Depth (LTP)
    - Power Proxy: Wire Bits
    """
    save_path = Path(output_path or (config.REPORTS_DIR / "comparison_chart.png"))
    save_path.parent.mkdir(parents=True, exist_ok=True)

    if not results:
        fig, ax = plt.subplots(figsize=(6, 4), facecolor="#0B0F19")
        ax.set_facecolor("#1E293B")
        ax.text(0.5, 0.5, "No experiment results to display", ha="center", va="center", color="#94A3B8")
        plt.savefig(save_path, facecolor=fig.get_facecolor())
        plt.close()
        return save_path

    labels = [r["name"] for r in results]
    total_cells = [r.get("total_cells", 0) for r in results]
    mux_cells = [r.get("mux_count", 0) for r in results]
    timing_depth = [r.get("longest_path_depth", 0) for r in results]
    power_wires = [r.get("num_wire_bits", 0) for r in results]

    # Fallback to logic cells if timing depth is not yet captured
    if not any(timing_depth):
        timing_depth = [r.get("logic_cell_count", 0) for r in results]
        t_title = "Logic Gates (Gate Count)"
        t_label = "Gate Count"
    else:
        t_title = "Timing: Longest Path Logic Depth (LTP)"
        t_label = "Levels of Logic"

    if not any(power_wires):
        power_wires = [int(r.get("synthesis_time_seconds", 0) * 1000) for r in results]
        p_title = "Synthesis Runtime (ms)"
        p_label = "Milliseconds"
    else:
        p_title = "Power/Interconnect Proxy: Wire Bits"
        p_label = "Wire Bits"

    # Dark theme styling
    plt.style.use("dark_background")
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.patch.set_facecolor("#0F172A")

    colors = ["#38BDF8", "#818CF8", "#34D399"]
    edge_color = "#E2E8F0"

    # 1. Total Cells (Area Complexity Proxy)
    ax1 = axes[0, 0]
    ax1.set_facecolor("#1E293B")
    bars1 = ax1.bar(labels, total_cells, color=colors[:len(labels)], edgecolor=edge_color, width=0.45)
    ax1.set_title("Area: Total Synthesized Cells", fontsize=13, fontweight="bold", color="#F8FAFC", pad=12)
    ax1.set_ylabel("Generic Cells", color="#94A3B8")
    ax1.tick_params(colors="#94A3B8")
    ax1.grid(axis="y", linestyle="--", alpha=0.3)
    for b in bars1:
        yval = b.get_height()
        ax1.text(b.get_x() + b.get_width() / 2, yval + (max(total_cells) * 0.02 if total_cells else 1), f"{yval}", ha="center", va="bottom", color="#FFFFFF", fontweight="bold")

    # 2. Multiplexer Cells
    ax2 = axes[0, 1]
    ax2.set_facecolor("#1E293B")
    bars2 = ax2.bar(labels, mux_cells, color=["#F59E0B", "#FBBF24", "#F43F5E"][:len(labels)], edgecolor=edge_color, width=0.45)
    ax2.set_title("Multiplexer Logic (MUX Cells)", fontsize=13, fontweight="bold", color="#F8FAFC", pad=12)
    ax2.set_ylabel("MUX Cells", color="#94A3B8")
    ax2.tick_params(colors="#94A3B8")
    ax2.grid(axis="y", linestyle="--", alpha=0.3)
    for b in bars2:
        yval = b.get_height()
        ax2.text(b.get_x() + b.get_width() / 2, yval + (max(mux_cells) * 0.02 if mux_cells else 1), f"{yval}", ha="center", va="bottom", color="#FFFFFF", fontweight="bold")

    # 3. Timing: Critical Path Logic Depth
    ax3 = axes[1, 0]
    ax3.set_facecolor("#1E293B")
    bars3 = ax3.bar(labels, timing_depth, color=["#A855F7", "#C084FC", "#06B6D4"][:len(labels)], edgecolor=edge_color, width=0.45)
    ax3.set_title(t_title, fontsize=13, fontweight="bold", color="#F8FAFC", pad=12)
    ax3.set_ylabel(t_label, color="#94A3B8")
    ax3.tick_params(colors="#94A3B8")
    ax3.grid(axis="y", linestyle="--", alpha=0.3)
    for b in bars3:
        yval = b.get_height()
        ax3.text(b.get_x() + b.get_width() / 2, yval + (max(timing_depth) * 0.02 if timing_depth else 1), f"{yval}", ha="center", va="bottom", color="#FFFFFF", fontweight="bold")

    # 4. Power Proxy: Total Wire Bits
    ax4 = axes[1, 1]
    ax4.set_facecolor("#1E293B")
    bars4 = ax4.bar(labels, power_wires, color=["#22D3EE", "#38BDF8", "#60A5FA"][:len(labels)], edgecolor=edge_color, width=0.45)
    ax4.set_title(p_title, fontsize=13, fontweight="bold", color="#F8FAFC", pad=12)
    ax4.set_ylabel(p_label, color="#94A3B8")
    ax4.tick_params(colors="#94A3B8")
    ax4.grid(axis="y", linestyle="--", alpha=0.3)
    for b in bars4:
        yval = b.get_height()
        ax4.text(b.get_x() + b.get_width() / 2, yval + (max(power_wires) * 0.02 if power_wires else 1), f"{yval}", ha="center", va="bottom", color="#FFFFFF", fontweight="bold")

    plt.suptitle("ChipGen AI: Hardware Synthesis & PPA Comparison Matrix", fontsize=16, fontweight="bold", color="#F8FAFC", y=0.98)
    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    plt.savefig(save_path, dpi=300, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close()
    return save_path

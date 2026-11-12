import os
import matplotlib
# Use non-interactive Agg backend for safe server and headless environments
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path
import config

# Set temporary cache dir to avoid permission warnings on Windows
os.environ.setdefault("MPLCONFIGDIR", str(config.BASE_DIR / ".cache" / "matplotlib"))

def generate_comparison_charts(
    results: list[dict],
    output_path: str | Path | None = None
) -> Path:
    """
    Generates professional dark-themed comparison bar charts comparing:
    - Total Cell Count (Logic Complexity Proxy)
    - Multiplexer Cell Count
    - Combinational Logic Gates Count
    - Synthesis Execution Time (Seconds)
    """
    save_path = Path(output_path or (config.REPORTS_DIR / "comparison_chart.png"))
    save_path.parent.mkdir(parents=True, exist_ok=True)

    labels = [r["name"] for r in results]
    total_cells = [r.get("total_cells", 0) for r in results]
    mux_cells = [r.get("mux_count", 0) for r in results]
    logic_cells = [r.get("logic_cell_count", 0) for r in results]
    synth_times = [r.get("synthesis_time_seconds", 0.0) for r in results]

    # Dark theme styling
    plt.style.use("dark_background")
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.patch.set_facecolor("#0F172A")

    colors = ["#38BDF8", "#818CF8", "#34D399"]
    edge_color = "#E2E8F0"

    # 1. Total Cells (Complexity Proxy)
    ax1 = axes[0, 0]
    ax1.set_facecolor("#1E293B")
    bars1 = ax1.bar(labels, total_cells, color=colors[:len(labels)], edgecolor=edge_color, width=0.45)
    ax1.set_title("Total Synthesized Cells (Proxy Metric)", fontsize=13, fontweight="bold", color="#F8FAFC", pad=12)
    ax1.set_ylabel("Generic Cell Count", color="#94A3B8")
    ax1.tick_params(colors="#94A3B8")
    ax1.grid(axis="y", linestyle="--", alpha=0.3)
    for b in bars1:
        yval = b.get_height()
        ax1.text(b.get_x() + b.get_width() / 2, yval + (max(total_cells) * 0.02), f"{yval}", ha="center", va="bottom", color="#FFFFFF", fontweight="bold")

    # 2. Multiplexer Cells
    ax2 = axes[0, 1]
    ax2.set_facecolor("#1E293B")
    bars2 = ax2.bar(labels, mux_cells, color=["#F59E0B", "#FBBF24", "#F43F5E"][:len(labels)], edgecolor=edge_color, width=0.45)
    ax2.set_title("Multiplexer Count (MUX$_*$_)", fontsize=13, fontweight="bold", color="#F8FAFC", pad=12)
    ax2.set_ylabel("MUX Cells", color="#94A3B8")
    ax2.tick_params(colors="#94A3B8")
    ax2.grid(axis="y", linestyle="--", alpha=0.3)
    for b in bars2:
        yval = b.get_height()
        ax2.text(b.get_x() + b.get_width() / 2, yval + (max(mux_cells) * 0.02), f"{yval}", ha="center", va="bottom", color="#FFFFFF", fontweight="bold")

    # 3. Combinational Logic Cells
    ax3 = axes[1, 0]
    ax3.set_facecolor("#1E293B")
    bars3 = ax3.bar(labels, logic_cells, color=["#A855F7", "#C084FC", "#06B6D4"][:len(labels)], edgecolor=edge_color, width=0.45)
    ax3.set_title("Logic Gates (AND/NAND/OR/XOR)", fontsize=13, fontweight="bold", color="#F8FAFC", pad=12)
    ax3.set_ylabel("Gate Count", color="#94A3B8")
    ax3.tick_params(colors="#94A3B8")
    ax3.grid(axis="y", linestyle="--", alpha=0.3)
    for b in bars3:
        yval = b.get_height()
        ax3.text(b.get_x() + b.get_width() / 2, yval + (max(logic_cells) * 0.02), f"{yval}", ha="center", va="bottom", color="#FFFFFF", fontweight="bold")

    # 4. Synthesis Execution Time
    ax4 = axes[1, 1]
    ax4.set_facecolor("#1E293B")
    bars4 = ax4.bar(labels, synth_times, color=["#22D3EE", "#38BDF8", "#60A5FA"][:len(labels)], edgecolor=edge_color, width=0.45)
    ax4.set_title("Synthesis Runtime (Actual Measurement)", fontsize=13, fontweight="bold", color="#F8FAFC", pad=12)
    ax4.set_ylabel("Seconds (s)", color="#94A3B8")
    ax4.tick_params(colors="#94A3B8")
    ax4.grid(axis="y", linestyle="--", alpha=0.3)
    for b in bars4:
        yval = b.get_height()
        ax4.text(b.get_x() + b.get_width() / 2, yval + (max(synth_times) * 0.02 if synth_times else 0.01), f"{yval:.3f}s", ha="center", va="bottom", color="#FFFFFF", fontweight="bold")

    plt.suptitle("ChipGen AI: Hardware Synthesis & PPA Comparison Matrix", fontsize=16, fontweight="bold", color="#F8FAFC", y=0.98)
    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    plt.savefig(save_path, dpi=300, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close()
    return save_path


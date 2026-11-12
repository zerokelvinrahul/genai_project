import os
import sys
from pathlib import Path
import json
import argparse
from typing import Any

# Force unbuffered line-level output for real-time console feedback
sys.stdout.reconfigure(line_buffering=True)
os.environ["MPLCONFIGDIR"] = str(Path(__file__).resolve().parent / ".cache" / "matplotlib")

import config
from eda.simulator import Simulator
from eda.synthesizer import Synthesizer, SynthesisMetrics
from agents.spec_agent import SpecificationAgent
from agents.rtl_generator import RTLGenerator
from agents.verification_agent import VerificationAgent
from agents.optimization_agent import OptimizationAgent
from utils.file_manager import FileManager
from utils.visualization import generate_comparison_charts, generate_circuit_visualization

DEFAULT_HARDWARE_PROMPT = "Design a 16-bit ALU supporting addition, subtraction, AND, OR and XOR."

def check_eda_environment() -> dict[str, Any]:
    env_status = {
        "iverilog": {"found": bool(config.IVERILOG_PATH), "path": config.IVERILOG_PATH},
        "vvp": {"found": bool(config.VVP_PATH), "path": config.VVP_PATH},
        "yosys": {"found": bool(config.YOSYS_PATH), "path": config.YOSYS_PATH, "lib_dir": config.YOSYS_LIB_DIR}
    }
    print("\n[EDA Environment Check]")
    for tool, info in env_status.items():
        status = "[AVAILABLE]" if info["found"] else "[MISSING]"
        print(f"  - {tool:<10}: {status} at {info['path']}")
    return env_status

def run_chipgen_pipeline(
    user_prompt: str = DEFAULT_HARDWARE_PROMPT,
    api_key: str | None = None,
    model_name: str | None = None,
    max_opt_iterations: int = 3
) -> dict[str, Any]:
    """
    Executes the exact 4-stage ChipGen AI Pipeline:
    1. Specification Agent: Converts requirements to structured hardware specification.
    2. RTL Generation Agent: Generates synthesizable Verilog code.
    3. Verification Agent: Generates testbenches, runs simulations, and identifies functional errors.
    4. PPA Optimization Agent: Analyzes area, timing, power reports, and proposes improved RTL.
    Final output: Verified RTL + testbench + synthesis reports + PPA comparison + circuit visualization.
    """
    effective_api_key = api_key or config.GOOGLE_API_KEY
    effective_model = model_name or config.GEMINI_MODEL

    print("=" * 70)
    print("           ChipGen AI: 4-Stage Hardware Synthesis Pipeline")
    print("=" * 70)
    print(f"User Input: \"{user_prompt}\"")

    check_eda_environment()
    simulator = Simulator()
    synthesizer = Synthesizer()

    # =========================================================================
    # STAGE 1: SPECIFICATION AGENT
    # =========================================================================
    print("\n" + "=" * 50)
    print("STAGE 1: Specification Agent")
    print("=" * 50)
    spec_agent = SpecificationAgent(api_key=effective_api_key, model_name=effective_model)
    print("-> Converting user requirement into structured hardware specification...")
    spec = spec_agent.parse_specification(user_prompt)
    print(f"   Module Name : {spec.module_name}")
    print(f"   Parameters  : {spec.parameters}")
    print(f"   Ports       : {len(spec.ports)} ports defined")
    print(f"   Operations  : {len(spec.operation_table)} opcodes defined")
    
    formatted_spec_text = spec.to_formatted_prompt_text()
    module_name = spec.module_name

    # =========================================================================
    # STAGE 2: RTL GENERATION AGENT
    # =========================================================================
    print("\n" + "=" * 50)
    print("STAGE 2: RTL Generation Agent")
    print("=" * 50)
    rtl_gen = RTLGenerator(api_key=effective_api_key, model_name=effective_model)
    print("-> Generating synthesizable Verilog RTL...")
    gen_filename = f"{module_name}_generated.v"
    gen_output, gen_rtl_path = rtl_gen.generate(
        specification=formatted_spec_text,
        module_name=module_name,
        save_filename=gen_filename
    )
    print(f"   Synthesizable RTL saved to: {gen_rtl_path}")

    # =========================================================================
    # STAGE 3: VERIFICATION AGENT
    # =========================================================================
    print("\n" + "=" * 50)
    print("STAGE 3: Verification Agent")
    print("=" * 50)
    verif_agent = VerificationAgent(
        simulator=simulator,
        api_key=effective_api_key,
        model_name=effective_model,
        max_repair_attempts=3
    )

    # 3a. Generate self-checking testbench
    print("-> Generating deterministic self-checking testbench...")
    tb_filename = f"{module_name}_tb.v"
    tb_path = verif_agent.generate_testbench(
        specification=formatted_spec_text,
        verilog_code=gen_output.verilog_code,
        module_name=module_name,
        output_tb_filename=tb_filename
    )

    # 3b. Run functional simulation and repair if needed
    print("-> Executing Icarus Verilog simulation and functional verification...")
    verif_report = verif_agent.verify_and_repair(
        rtl_path=gen_rtl_path,
        specification=formatted_spec_text,
        testbench_path=tb_path,
        module_name=module_name,
        category="generated"
    )

    verified_rtl_path = Path(verif_report.final_rtl_path)
    if not verif_report.passed:
        print(f"   [WARNING] Verification could not pass all tests: {verif_report.summary}")
    else:
        print(f"   [SUCCESS] Verified RTL on attempt {verif_report.total_attempts}")

    # Synthesize verified baseline design
    print("-> Synthesizing initial design with Yosys...")
    init_metrics = synthesizer.synthesize(verified_rtl_path, top_module=module_name)
    print(f"   Initial PPA: Cells={init_metrics.total_cells}, MUX={init_metrics.mux_count}, Logic Depth={init_metrics.longest_path_depth}")

    # =========================================================================
    # STAGE 4: PPA OPTIMIZATION AGENT
    # =========================================================================
    print("\n" + "=" * 50)
    print("STAGE 4: PPA Optimization Agent")
    print("=" * 50)
    opt_agent = OptimizationAgent(
        simulator=simulator,
        synthesizer=synthesizer,
        verification_agent=verif_agent,
        api_key=effective_api_key,
        model_name=effective_model,
        max_iterations=max_opt_iterations
    )
    
    print("-> Initiating PPA optimization loop across Area, Timing, and Power...")
    opt_report = opt_agent.optimize(
        initial_rtl_path=verified_rtl_path,
        specification=formatted_spec_text,
        initial_metrics=init_metrics,
        module_name=module_name,
        testbench_path=tb_path
    )

    final_best_rtl_path = Path(opt_report.best_rtl_path)
    final_best_metrics = opt_report.best_metrics

    # =========================================================================
    # FINAL OUTPUT PACKAGING & VISUALIZATION
    # =========================================================================
    print("\n" + "=" * 50)
    print("PACKAGING FINAL DELIVERABLES")
    print("=" * 50)

    # 1. Verified RTL copy
    final_rtl_dest = config.REPORTS_DIR / f"{module_name}_verified.v"
    final_rtl_dest.write_text(FileManager.load_rtl(final_best_rtl_path), encoding="utf-8")
    print(f"1. Verified RTL           : {final_rtl_dest}")

    # 2. Testbench copy
    final_tb_dest = config.REPORTS_DIR / f"{module_name}_testbench.v"
    final_tb_dest.write_text(FileManager.load_rtl(tb_path), encoding="utf-8")
    print(f"2. Testbench              : {final_tb_dest}")

    # 3. Synthesis Reports
    metrics_summary_path = config.REPORTS_DIR / "synthesis_reports.json"
    synthesis_payload = {
        "specification": spec.model_dump(),
        "initial_metrics": init_metrics.model_dump(),
        "optimized_metrics": final_best_metrics.model_dump(),
        "optimization_report": opt_report.model_dump()
    }
    with open(metrics_summary_path, "w", encoding="utf-8") as f:
        json.dump(synthesis_payload, f, indent=2)
    print(f"3. Synthesis Reports      : {metrics_summary_path}")

    # 4. PPA Comparison Chart
    comparison_table = [
        {
            "name": "1. Initial Generated",
            "total_cells": init_metrics.total_cells,
            "mux_count": init_metrics.mux_count,
            "logic_cell_count": init_metrics.logic_cell_count,
            "longest_path_depth": init_metrics.longest_path_depth,
            "num_wire_bits": init_metrics.num_wire_bits,
            "synthesis_time_seconds": init_metrics.synthesis_time_seconds
        },
        {
            "name": "2. PPA Optimized" if opt_report.optimization_accepted else "2. Final AI Design",
            "total_cells": final_best_metrics.total_cells,
            "mux_count": final_best_metrics.mux_count,
            "logic_cell_count": final_best_metrics.logic_cell_count,
            "longest_path_depth": final_best_metrics.longest_path_depth,
            "num_wire_bits": final_best_metrics.num_wire_bits,
            "synthesis_time_seconds": final_best_metrics.synthesis_time_seconds
        }
    ]
    chart_path = generate_comparison_charts(comparison_table, config.REPORTS_DIR / "ppa_comparison.png")
    print(f"4. PPA Comparison Chart   : {chart_path}")

    # 5. Circuit Visualization
    circuit_png = generate_circuit_visualization(final_best_rtl_path, top_module=module_name, output_png_path=config.REPORTS_DIR / "circuit_schematic.png")
    print(f"5. Circuit Visualization  : {circuit_png}")

    print("\n" + "=" * 70)
    print("                      PIPELINE SUMMARY")
    print("=" * 70)
    print(f"Design Module          : {module_name}")
    print(f"Initial Cells          : {init_metrics.total_cells} (LTP Depth: {init_metrics.longest_path_depth})")
    print(f"Optimized Cells        : {final_best_metrics.total_cells} (LTP Depth: {final_best_metrics.longest_path_depth})")
    print(f"PPA Optimization Result: {'SUCCESS' if opt_report.optimization_accepted else 'RETAINED BEST INITIAL'}")
    if opt_report.optimization_accepted:
        print(f"Cell Reduction         : {opt_report.cell_count_reduction_pct:.2f}%")
    print("=" * 70)

    return {
        "status": "success",
        "verified_rtl": str(final_rtl_dest),
        "testbench": str(final_tb_dest),
        "synthesis_reports": str(metrics_summary_path),
        "ppa_comparison": str(chart_path),
        "circuit_visualization": str(circuit_png),
        "optimization_accepted": opt_report.optimization_accepted
    }

def main():
    parser = argparse.ArgumentParser(description="ChipGen AI: 4-Stage Hardware Synthesis Pipeline")
    parser.add_argument("--prompt", type=str, default=DEFAULT_HARDWARE_PROMPT, help="Natural language hardware request")
    parser.add_argument("--api-key", type=str, default=None, help="Google Gemini API Key")
    parser.add_argument("--model", type=str, default=None, help="Gemini Model Identifier")
    parser.add_argument("--max-opt", type=int, default=3, help="Max PPA optimization iterations")
    args = parser.parse_args()

    run_chipgen_pipeline(
        user_prompt=args.prompt,
        api_key=args.api_key,
        model_name=args.model,
        max_opt_iterations=args.max_opt
    )

if __name__ == "__main__":
    main()

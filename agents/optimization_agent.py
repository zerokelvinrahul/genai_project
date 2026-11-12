import os
import re
from pathlib import Path
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

import config
from agents.base_agent import BaseLLMAgent
from eda.simulator import Simulator, SimulationResult
from eda.synthesizer import Synthesizer, SynthesisMetrics
from agents.verification_agent import VerificationAgent, VerificationReport
from utils.parsing import (
    RTLOptimizationOutput,
    extract_verilog_code,
    extract_module_name,
    validate_verilog_syntax_basic
)
from utils.file_manager import FileManager

class OptimizationCandidateResult(BaseModel):
    iteration: int
    candidate_name: str
    strategy: str
    rtl_path: str
    verification_passed: bool
    synthesis_success: bool
    repair_attempts: int = 0
    simulation_result: SimulationResult | None = None
    synthesis_metrics: SynthesisMetrics | None = None
    accepted: bool = False
    improvement_notes: str = ""

class OptimizationRunReport(BaseModel):
    baseline_metrics: SynthesisMetrics
    best_metrics: SynthesisMetrics
    best_rtl_path: str
    initial_rtl_path: str
    optimization_accepted: bool = False
    total_candidates_evaluated: int = 0
    candidates_accepted: int = 0
    candidates_rejected: int = 0
    cell_count_reduction_pct: float = 0.0
    candidates: list[OptimizationCandidateResult] = Field(default_factory=list)
    summary: str = ""

class OptimizationAgent(BaseLLMAgent):
    def __init__(
        self,
        simulator: Simulator | None = None,
        synthesizer: Synthesizer | None = None,
        verification_agent: VerificationAgent | None = None,
        api_key: str | None = None,
        model_name: str | None = None,
        max_iterations: int = 3,
        max_repairs_per_candidate: int = 3
    ):
        super().__init__(api_key=api_key, model_name=model_name, temperature=0.2)
        self.simulator = simulator or Simulator()
        self.synthesizer = synthesizer or Synthesizer()
        self.max_iterations = max_iterations
        self.max_repairs_per_candidate = max_repairs_per_candidate
        self.verifier = verification_agent or VerificationAgent(
            simulator=self.simulator,
            api_key=self.api_key,
            model_name=self.model_name,
            max_repair_attempts=self.max_repairs_per_candidate
        )

    def optimize(
        self,
        initial_rtl_path: str | Path,
        specification: str,
        initial_metrics: SynthesisMetrics,
        optimization_objective: str = "Minimize total generic cell count and multiplexer logic through arithmetic resource sharing and control optimization",
        module_name: str = "alu_16bit",
        testbench_path: str | Path | None = None
    ) -> OptimizationRunReport:
        tb_path = Path(testbench_path or FileManager.get_deterministic_tb_path()).resolve()
        
        current_best_rtl_path = str(Path(initial_rtl_path).resolve())
        current_best_metrics = initial_metrics
        current_best_code = FileManager.load_rtl(current_best_rtl_path)

        candidates: list[OptimizationCandidateResult] = []
        failure_history: list[str] = []

        strategies = [
            "Arithmetic Resource Sharing: Unify adder and subtractor into a single shared 16-bit adder core (a + (is_sub ? ~b : b) + is_sub). CRITICAL: Remember carry_out for subtraction must be the borrow bit, so invert adder carry (carry_out = ~adder_carry)!",
            "Multiplexer & Control Optimization: Structure opcode decoding into a hierarchical 2-stage multiplexer (e.g. separating arithmetic/logic from shift/pass) and eliminate redundant multiplexer branches.",
            "Boolean Logic Factoring: Factor common sub-expressions across bitwise operations (AND, OR, XOR) and pass-through."
        ]

        for i in range(1, self.max_iterations + 1):
            strategy_hint = strategies[(i - 1) % len(strategies)]
            print(f"\n[OptimizationAgent] Starting Optimization Iteration {i}/{self.max_iterations}...")
            print(f"[OptimizationAgent] Strategy: {strategy_hint}")

            # Prepare failure context from previous candidates if any
            if failure_history:
                prev_context = "LESSONS FROM PREVIOUS CANDIDATE ATTEMPTS (DO NOT REPEAT THESE ERRORS):\n" + "\n".join(
                    f"- {f}" for f in failure_history[-3:]
                )
            else:
                prev_context = ""

            # 1. Ask LLM for candidate optimization
            try:
                candidate_data = self._generate_candidate(
                    current_rtl=current_best_code,
                    specification=specification,
                    current_metrics=current_best_metrics,
                    objective=f"{optimization_objective}. Suggested technique: {strategy_hint}",
                    previous_failure_context=prev_context,
                    module_name=module_name,
                    iteration=i
                )
            except Exception as e:
                print(f"[OptimizationAgent] LLM generation failed for candidate v{i}: {e}")
                failure_history.append(f"Iteration {i} LLM call error: {e}")
                continue

            # 2. Save candidate RTL
            cand_filename = f"{Path(initial_rtl_path).stem}_opt_v{i}.v"
            cand_path = FileManager.save_rtl(
                code=candidate_data.optimized_verilog_code,
                category="optimized",
                filename=cand_filename
            )

            # 3. Deterministic Functional Verification with up to 3 repair attempts
            print(f"[OptimizationAgent] Verifying Candidate v{i} with deterministic testbench (max {self.max_repairs_per_candidate} repairs allowed)...")
            verif_report = self.verifier.verify_and_repair(
                rtl_path=cand_path,
                specification=specification,
                testbench_path=tb_path,
                module_name=module_name,
                category="optimized"
            )

            final_sim = verif_report.final_simulation
            repairs_used = max(0, verif_report.total_attempts - 1)

            if not verif_report.passed:
                print(f"[OptimizationAgent] Candidate v{i} FAILED functional verification after {verif_report.total_attempts} attempts. Rejecting candidate.")
                summary_err = final_sim.error_summary if final_sim else "Verification failed"
                failure_history.append(f"Candidate v{i} failed verification: {summary_err[:120]}")
                candidates.append(OptimizationCandidateResult(
                    iteration=i,
                    candidate_name=candidate_data.candidate_name,
                    strategy=candidate_data.optimization_strategy,
                    rtl_path=str(cand_path),
                    verification_passed=False,
                    synthesis_success=False,
                    repair_attempts=repairs_used,
                    simulation_result=final_sim,
                    accepted=False,
                    improvement_notes=f"Rejected: Verification failed after {repairs_used} repair cycles."
                ))
                continue

            verified_rtl_path = Path(verif_report.final_rtl_path)
            print(f"[OptimizationAgent] Candidate v{i} PASSED functional verification (Repairs used: {repairs_used}). Proceeding to Yosys synthesis...")

            # 4. Yosys Synthesis on verified candidate
            synth_metrics = self.synthesizer.synthesize(
                design_file=verified_rtl_path,
                top_module=module_name,
                log_name=f"synth_opt_v{i}.log"
            )

            if not synth_metrics.success:
                print(f"[OptimizationAgent] Candidate v{i} FAILED synthesis. Rejecting candidate.")
                failure_history.append(f"Candidate v{i} synthesis failed: {synth_metrics.error_message}")
                candidates.append(OptimizationCandidateResult(
                    iteration=i,
                    candidate_name=candidate_data.candidate_name,
                    strategy=candidate_data.optimization_strategy,
                    rtl_path=str(verified_rtl_path),
                    verification_passed=True,
                    synthesis_success=False,
                    repair_attempts=repairs_used,
                    simulation_result=final_sim,
                    synthesis_metrics=synth_metrics,
                    accepted=False,
                    improvement_notes=f"Rejected: Synthesis failed: {synth_metrics.error_message}"
                ))
                continue

            # 5. Objective Evaluation
            # Condition to accept: Verified + Synthesizable + Lower total cells or lower mux count without cell count explosion
            old_cells = current_best_metrics.total_cells
            new_cells = synth_metrics.total_cells
            old_mux = current_best_metrics.mux_count
            new_mux = synth_metrics.mux_count

            improved = False
            notes = ""

            if new_cells < old_cells:
                improved = True
                pct = ((old_cells - new_cells) / old_cells) * 100
                notes = f"Accepted: Total cell count improved from {old_cells} to {new_cells} ({pct:.1f}% reduction). MUX count: {new_mux} (prev {old_mux})."
            elif new_cells == old_cells and new_mux < old_mux:
                improved = True
                notes = f"Accepted: MUX count improved from {old_mux} to {new_mux} with identical cell count ({new_cells})."
            else:
                improved = False
                notes = f"Rejected: No improvement (Cells: {new_cells} vs best {old_cells}; MUX: {new_mux} vs best {old_mux})."

            print(f"[OptimizationAgent] {notes}")

            candidates.append(OptimizationCandidateResult(
                iteration=i,
                candidate_name=candidate_data.candidate_name,
                strategy=candidate_data.optimization_strategy,
                rtl_path=str(verified_rtl_path),
                verification_passed=True,
                synthesis_success=True,
                repair_attempts=repairs_used,
                simulation_result=final_sim,
                synthesis_metrics=synth_metrics,
                accepted=improved,
                improvement_notes=notes
            ))

            if improved:
                current_best_metrics = synth_metrics
                current_best_rtl_path = str(verified_rtl_path)
                current_best_code = FileManager.load_rtl(verified_rtl_path)

        accepted_count = sum(1 for c in candidates if c.accepted)
        rejected_count = len(candidates) - accepted_count
        opt_accepted = accepted_count > 0 and (current_best_metrics.total_cells < initial_metrics.total_cells or current_best_metrics.mux_count < initial_metrics.mux_count)
        
        reduction_pct = 0.0
        if initial_metrics.total_cells > 0:
            reduction_pct = round(((initial_metrics.total_cells - current_best_metrics.total_cells) / initial_metrics.total_cells) * 100, 2)

        if opt_accepted:
            summary = (
                f"Optimization succeeded! Out of {len(candidates)} candidates evaluated, "
                f"{accepted_count} improved the design ({rejected_count} rejected). "
                f"Initial cell count: {initial_metrics.total_cells} -> Optimized cell count: {current_best_metrics.total_cells} "
                f"({reduction_pct:.1f}% reduction). MUX count: {initial_metrics.mux_count} -> {current_best_metrics.mux_count}."
            )
        else:
            summary = (
                f"No optimization candidate improved upon the design while passing functional verification. "
                f"Out of {len(candidates)} candidate(s) evaluated, 0 were accepted ({rejected_count} rejected). "
                f"Initial verified design retained with {initial_metrics.total_cells} generic cells."
            )

        return OptimizationRunReport(
            baseline_metrics=initial_metrics,
            best_metrics=current_best_metrics,
            best_rtl_path=current_best_rtl_path,
            initial_rtl_path=str(initial_rtl_path),
            optimization_accepted=opt_accepted,
            total_candidates_evaluated=len(candidates),
            candidates_accepted=accepted_count,
            candidates_rejected=rejected_count,
            cell_count_reduction_pct=reduction_pct if opt_accepted else 0.0,
            candidates=candidates,
            summary=summary
        )

    def _generate_candidate(
        self,
        current_rtl: str,
        specification: str,
        current_metrics: SynthesisMetrics,
        objective: str,
        previous_failure_context: str,
        module_name: str,
        iteration: int
    ) -> RTLOptimizationOutput:
        prompt_template = (config.PROMPTS_DIR / "optimization.txt").read_text(encoding="utf-8")
        prompt = (
            prompt_template
            .replace("{specification}", specification)
            .replace("{current_rtl}", current_rtl)
            .replace("{total_cells}", str(current_metrics.total_cells))
            .replace("{mux_count}", str(current_metrics.mux_count))
            .replace("{logic_cell_count}", str(current_metrics.logic_cell_count))
            .replace("{sequential_cell_count}", str(current_metrics.sequential_cell_count))
            .replace("{longest_path_depth}", str(current_metrics.longest_path_depth))
            .replace("{num_wire_bits}", str(current_metrics.num_wire_bits))
            .replace("{num_wires}", str(current_metrics.num_wires))
            .replace("{synthesis_time}", str(current_metrics.synthesis_time_seconds))
            .replace("{optimization_objective}", objective)
            .replace("{previous_failure_context}", previous_failure_context)
            .replace("{module_name}", module_name)
        )

        messages = [
            SystemMessage(content="You are a senior ASIC VLSI synthesis and logic optimization engineer."),
            HumanMessage(content=prompt)
        ]
        try:
            structured_llm = llm.with_structured_output(RTLOptimizationOutput)
            result = self.invoke_with_retry(messages)
            if hasattr(result, "optimized_verilog_code"):
                code = extract_verilog_code(result.optimized_verilog_code)
                result.optimized_verilog_code = code
            else:
                code = extract_verilog_code(result.content)
                result = RTLOptimizationOutput(
                    candidate_name=f"opt_cand_v{iteration}",
                    optimized_verilog_code=code,
                    optimization_strategy=objective,
                    expected_improvement="Targeted cell and mux count reduction",
                    modifications=["Logic refactoring"]
                )
        except Exception:
            raw = self.invoke_with_retry([
                SystemMessage(content="You are a senior ASIC VLSI synthesis and logic optimization engineer."),
                HumanMessage(content=prompt + "\nReturn ONLY the optimized Verilog in a ```verilog code block.")
            ])
            code = extract_verilog_code(raw.content)
            result = RTLOptimizationOutput(
                candidate_name=f"opt_cand_v{iteration}",
                optimized_verilog_code=code,
                optimization_strategy=objective,
                expected_improvement="Targeted cell and mux count reduction",
                modifications=["Logic refactoring"]
            )

        valid, msg = validate_verilog_syntax_basic(result.optimized_verilog_code)
        if not valid:
            raise ValueError(f"Candidate v{iteration} syntax invalid: {msg}")

        detected = extract_module_name(result.optimized_verilog_code)
        if detected and detected != module_name:
            result.optimized_verilog_code = re.sub(
                rf"\bmodule\s+{re.escape(detected)}\b",
                f"module {module_name}",
                result.optimized_verilog_code,
                count=1
            )

        return result

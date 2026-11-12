import os
import re
from pathlib import Path
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

import config
from agents.base_agent import BaseLLMAgent
from eda.simulator import Simulator, SimulationResult
from utils.parsing import (
    RTLRepairOutput,
    extract_verilog_code,
    extract_module_name,
    validate_verilog_syntax_basic
)
from utils.file_manager import FileManager

class VerificationAttempt(BaseModel):
    attempt_index: int
    rtl_path: str
    simulation_result: SimulationResult
    repaired: bool = False
    repair_notes: str = ""

class VerificationReport(BaseModel):
    passed: bool
    final_rtl_path: str
    total_attempts: int
    attempts: list[VerificationAttempt] = Field(default_factory=list)
    final_simulation: SimulationResult | None = None
    summary: str = ""

class VerificationAgent(BaseLLMAgent):
    def __init__(
        self,
        simulator: Simulator | None = None,
        api_key: str | None = None,
        model_name: str | None = None,
        max_repair_attempts: int = 3
    ):
        super().__init__(api_key=api_key, model_name=model_name, temperature=0.1)
        self.simulator = simulator or Simulator()
        self.max_repair_attempts = max_repair_attempts

    def generate_testbench(
        self,
        specification: str,
        verilog_code: str,
        module_name: str,
        output_tb_filename: str | None = None
    ) -> Path:
        """
        Dynamically generates a deterministic, self-checking Verilog-2001 testbench
        tailored for the specified hardware module and operation table.
        """
        tb_template_path = config.PROMPTS_DIR / "testbench_generation.txt"
        if not tb_template_path.is_file():
            raise FileNotFoundError(f"Missing prompt template: {tb_template_path}")
            
        prompt = (
            tb_template_path.read_text(encoding="utf-8")
            .replace("{specification}", specification)
            .replace("{verilog_code}", verilog_code)
            .replace("{module_name}", module_name)
        )

        messages = [
            SystemMessage(content="You are an expert digital VLSI verification engineer writing deterministic self-checking testbenches."),
            HumanMessage(content=prompt)
        ]
        raw = self.invoke_with_retry(messages)
        tb_code = extract_verilog_code(raw.content)

        # Fix any LLM newline-split string literals (e.g. "ADD_OVERFLOW\n")
        tb_code = re.sub(r'"([^"\n]*)\n\s*([^"\n]*)"', r'"\1_\2"', tb_code)

        tb_filename = output_tb_filename or f"{module_name}_tb.v"
        tb_path = config.TESTBENCHES_DIR / tb_filename
        tb_path.write_text(tb_code, encoding="utf-8")
        print(f"[VerificationAgent] Generated dynamic self-checking testbench at: {tb_path}")
        return tb_path

    def verify_and_repair(
        self,
        rtl_path: str | Path,
        specification: str,
        testbench_path: str | Path | None = None,
        module_name: str = "alu_16bit",
        category: str = "generated"
    ) -> VerificationReport:
        current_path = Path(rtl_path).resolve()
        tb_path = Path(testbench_path or FileManager.get_deterministic_tb_path()).resolve()

        attempts: list[VerificationAttempt] = []
        attempt_num = 0

        # Base stem to avoid accumulating nested _repair_att suffixes
        base_stem = current_path.stem
        if "_repair_att" in base_stem:
            base_stem = base_stem.split("_repair_att")[0]

        while attempt_num <= self.max_repair_attempts:
            # Run deterministic hardware simulation
            sim_result = self.simulator.run_simulation(current_path, tb_path)

            attempt = VerificationAttempt(
                attempt_index=attempt_num,
                rtl_path=str(current_path),
                simulation_result=sim_result
            )

            # Python application strictly determines pass/fail condition
            if sim_result.passed:
                attempt.repaired = True if attempt_num > 0 else False
                attempt.repair_notes = "All functional checks and compilation passed."
                attempts.append(attempt)
                return VerificationReport(
                    passed=True,
                    final_rtl_path=str(current_path),
                    total_attempts=attempt_num + 1,
                    attempts=attempts,
                    final_simulation=sim_result,
                    summary=f"Design verified successfully on attempt {attempt_num + 1} ({sim_result.tests_passed}/{sim_result.tests_run} tests passed)."
                )

            # Failure detected
            attempt.repair_notes = sim_result.error_summary
            attempts.append(attempt)

            # Check if we have repair budget remaining
            if attempt_num >= self.max_repair_attempts:
                break

            attempt_num += 1
            print(f"[VerificationAgent] Verification failed on attempt {attempt_num}. Initiating LLM repair...")

            # Request LLM repair
            try:
                current_rtl = FileManager.load_rtl(current_path)
                repaired_code, diagnosis = self._request_repair(
                    current_rtl=current_rtl,
                    specification=specification,
                    error_log=sim_result.error_summary,
                    sim_stdout=sim_result.simulation_stdout,
                    module_name=module_name
                )

                # Save repaired RTL candidate using clean base_stem
                repaired_filename = f"{base_stem}_repair_att{attempt_num}.v"
                current_path = FileManager.save_rtl(
                    code=repaired_code,
                    category=category,
                    filename=repaired_filename
                )
            except Exception as e:
                print(f"[VerificationAgent] Repair request failed: {e}")
                break

        # Max attempts reached without passing
        last_sim = attempts[-1].simulation_result if attempts else None
        return VerificationReport(
            passed=False,
            final_rtl_path=str(current_path),
            total_attempts=len(attempts),
            attempts=attempts,
            final_simulation=last_sim,
            summary=f"Verification failed after {len(attempts)} attempts. Last error: {last_sim.error_summary if last_sim else 'Unknown'}"
        )

    def _request_repair(
        self,
        current_rtl: str,
        specification: str,
        error_log: str,
        sim_stdout: str,
        module_name: str
    ) -> tuple[str, str]:
        prompt_template = (config.PROMPTS_DIR / "verification.txt").read_text(encoding="utf-8")
        prompt = (
            prompt_template
            .replace("{specification}", specification)
            .replace("{current_rtl}", current_rtl)
            .replace("{error_log}", error_log)
            .replace("{failure_details}", sim_stdout[-2000:])
            .replace("{module_name}", module_name)
        )

        llm = self._get_llm()
        try:
            structured_llm = llm.with_structured_output(RTLRepairOutput)
            messages = [
                SystemMessage(content="You are an expert digital VLSI verification engineer fixing bugs in RTL."),
                HumanMessage(content=prompt)
            ]
            result = self.invoke_with_retry(messages)
            if hasattr(result, "repaired_verilog_code"):
                code = extract_verilog_code(result.repaired_verilog_code)
                diagnosis = result.bug_explanation
            else:
                code = extract_verilog_code(result.content)
                diagnosis = "Repaired via direct response"
        except Exception:
            messages = [
                SystemMessage(content="You are an expert digital VLSI verification engineer fixing bugs in RTL."),
                HumanMessage(content=prompt + "\nReturn ONLY the corrected Verilog RTL in a ```verilog code block.")
            ]
            raw = self.invoke_with_retry(messages)
            code = extract_verilog_code(raw.content)
            diagnosis = "Repaired via direct prompt fallback"

        valid, msg = validate_verilog_syntax_basic(code)
        if not valid:
            raise ValueError(f"Repaired RTL invalid: {msg}")

        # Ensure module name matches
        detected_name = extract_module_name(code)
        if detected_name and detected_name != module_name:
            code = re.sub(rf"\bmodule\s+{re.escape(detected_name)}\b", f"module {module_name}", code, count=1)

        return code, diagnosis


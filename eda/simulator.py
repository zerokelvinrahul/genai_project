import os
import re
import time
import subprocess
import tempfile
from pathlib import Path
from pydantic import BaseModel, Field

import config

class SimulationResult(BaseModel):
    compiled: bool = Field(..., description="Whether iverilog compilation succeeded")
    simulated: bool = Field(..., description="Whether vvp simulation ran to completion")
    passed: bool = Field(..., description="Whether all functional checks passed")
    compilation_stdout: str = ""
    compilation_stderr: str = ""
    simulation_stdout: str = ""
    simulation_stderr: str = ""
    tests_run: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    error_summary: str = ""
    execution_time_seconds: float = 0.0
    log_path: str = Field(default="", description="Path to complete simulation log file")

class Simulator:
    def __init__(self, iverilog_path: str | None = None, vvp_path: str | None = None):
        self.iverilog_path = iverilog_path or config.IVERILOG_PATH
        self.vvp_path = vvp_path or config.VVP_PATH
        if not self.iverilog_path or not os.path.isfile(self.iverilog_path):
            raise FileNotFoundError(f"Icarus Verilog executable not found at: {self.iverilog_path}")
        if not self.vvp_path or not os.path.isfile(self.vvp_path):
            raise FileNotFoundError(f"vvp executable not found at: {self.vvp_path}")

    def run_simulation(
        self,
        design_file: str | Path,
        testbench_file: str | Path,
        log_name: str | None = None,
        timeout: int = config.TIMEOUT_SIMULATION
    ) -> SimulationResult:
        design_path = Path(design_file).resolve()
        tb_path = Path(testbench_file).resolve()
        start_time = time.time()
        timestamp = int(start_time)
        file_stem = design_path.stem
        log_filename = log_name or f"sim_{file_stem}_{timestamp}.log"
        log_file = config.LOGS_DIR / log_filename

        def _write_sim_log(c_out: str, c_err: str, s_out: str, s_err: str, err_sum: str) -> str:
            try:
                content = (
                    f"=== SIMULATION LOG: {design_path.name} ===\n"
                    f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"Design File: {design_path}\n"
                    f"Testbench: {tb_path}\n\n"
                    f"--- COMPILATION STDOUT ---\n{c_out}\n"
                    f"--- COMPILATION STDERR ---\n{c_err}\n"
                    f"--- SIMULATION STDOUT ---\n{s_out}\n"
                    f"--- SIMULATION STDERR ---\n{s_err}\n"
                    f"--- SUMMARY ---\n{err_sum}\n"
                )
                log_file.write_text(content, encoding="utf-8")
                return str(log_file)
            except Exception:
                return ""

        if not design_path.is_file():
            err_sum = f"Design file does not exist: {design_path}"
            lp = _write_sim_log("", "", "", "", err_sum)
            return SimulationResult(
                compiled=False,
                simulated=False,
                passed=False,
                error_summary=err_sum,
                log_path=lp
            )
        if not tb_path.is_file():
            err_sum = f"Testbench file does not exist: {tb_path}"
            lp = _write_sim_log("", "", "", "", err_sum)
            return SimulationResult(
                compiled=False,
                simulated=False,
                passed=False,
                error_summary=err_sum,
                log_path=lp
            )

        start_time = time.time()

        # Create temporary file for compiled simulation binary (.vvp)
        with tempfile.NamedTemporaryFile(suffix=".vvp", delete=False) as tmp_vvp:
            vvp_out = tmp_vvp.name

        try:
            # 1. Compilation Step (iverilog)
            env = os.environ.copy()
            iverilog_dir = str(Path(self.iverilog_path).parent)
            env["PATH"] = f"{iverilog_dir};" + env.get("PATH", "")

            # -g2001 or -g2005 for modern Verilog support
            compile_cmd = [
                self.iverilog_path,
                "-g2001",
                "-o", vvp_out,
                str(design_path),
                str(tb_path)
            ]

            try:
                c_proc = subprocess.run(
                    compile_cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    env=env
                )
            except subprocess.TimeoutExpired:
                err_sum = f"Compilation timed out after {timeout} seconds"
                lp = _write_sim_log("", "", "", "", err_sum)
                return SimulationResult(
                    compiled=False,
                    simulated=False,
                    passed=False,
                    error_summary=err_sum,
                    execution_time_seconds=time.time() - start_time,
                    log_path=lp
                )

            if c_proc.returncode != 0:
                err_msg = c_proc.stderr.strip() or c_proc.stdout.strip()
                err_sum = f"Compilation failed (exit code {c_proc.returncode}):\n{err_msg}"
                lp = _write_sim_log(c_proc.stdout, c_proc.stderr, "", "", err_sum)
                return SimulationResult(
                    compiled=False,
                    simulated=False,
                    passed=False,
                    compilation_stdout=c_proc.stdout,
                    compilation_stderr=c_proc.stderr,
                    error_summary=err_sum,
                    execution_time_seconds=time.time() - start_time,
                    log_path=lp
                )

            # 2. Simulation Step (vvp)
            sim_cmd = [self.vvp_path, vvp_out]
            try:
                s_proc = subprocess.run(
                    sim_cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    env=env
                )
            except subprocess.TimeoutExpired:
                err_sum = f"Simulation timed out after {timeout} seconds (infinite loop or hang)"
                lp = _write_sim_log(c_proc.stdout, c_proc.stderr, "", "", err_sum)
                return SimulationResult(
                    compiled=True,
                    simulated=False,
                    passed=False,
                    compilation_stdout=c_proc.stdout,
                    compilation_stderr=c_proc.stderr,
                    error_summary=err_sum,
                    execution_time_seconds=time.time() - start_time,
                    log_path=lp
                )

            total_time = time.time() - start_time
            sim_stdout = s_proc.stdout
            sim_stderr = s_proc.stderr

            # 3. Parse Output
            tests_run = 0
            tests_passed = 0
            tests_failed = 0
            passed = False

            # Extract counts from summary
            m_total = re.search(r"TOTAL TESTS\s*:\s*(\d+)", sim_stdout)
            m_pass = re.search(r"PASSED\s*:\s*(\d+)", sim_stdout)
            m_fail = re.search(r"FAILED\s*:\s*(\d+)", sim_stdout)
            m_status = re.search(r"STATUS\s*:\s*([A-Z]+)", sim_stdout)

            if m_total:
                tests_run = int(m_total.group(1))
            if m_pass:
                tests_passed = int(m_pass.group(1))
            if m_fail:
                tests_failed = int(m_fail.group(1))

            if m_status and m_status.group(1) == "PASSED" and tests_failed == 0 and tests_run > 0:
                passed = True
                error_summary = ""
            elif "STATUS: PASSED" in sim_stdout and tests_failed == 0:
                passed = True
                error_summary = ""
            else:
                passed = False
                failures = [line for line in sim_stdout.splitlines() if "[FAIL]" in line]
                if failures:
                    error_summary = "Functional Verification Failures:\n" + "\n".join(failures[:10])
                else:
                    error_summary = f"Simulation ended with exit code {s_proc.returncode} without passing status."
                if sim_stderr:
                    error_summary += f"\nStderr:\n{sim_stderr}"

            lp = _write_sim_log(c_proc.stdout, c_proc.stderr, sim_stdout, sim_stderr, error_summary)

            return SimulationResult(
                compiled=True,
                simulated=(s_proc.returncode == 0 or tests_run > 0),
                passed=passed,
                compilation_stdout=c_proc.stdout,
                compilation_stderr=c_proc.stderr,
                simulation_stdout=sim_stdout,
                simulation_stderr=sim_stderr,
                tests_run=tests_run,
                tests_passed=tests_passed,
                tests_failed=tests_failed,
                error_summary=error_summary,
                execution_time_seconds=round(total_time, 4),
                log_path=lp
            )

        finally:
            if os.path.exists(vvp_out):
                try:
                    os.remove(vvp_out)
                except OSError:
                    pass


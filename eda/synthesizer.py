import os
import re
import json
import time
import subprocess
import tempfile
from pathlib import Path
from pydantic import BaseModel, Field

import config

class SynthesisMetrics(BaseModel):
    success: bool = Field(..., description="Whether synthesis succeeded")
    top_module: str = Field(..., description="Top module synthesized")
    total_cells: int = Field(default=0, description="Total generic cell count (complexity proxy)")
    mux_count: int = Field(default=0, description="Total multiplexer cell count")
    logic_cell_count: int = Field(default=0, description="Combinational logic gates count")
    sequential_cell_count: int = Field(default=0, description="Sequential flip-flop/latch count")
    num_wires: int = Field(default=0, description="Total wires count")
    num_wire_bits: int = Field(default=0, description="Total wire bits")
    num_ports: int = Field(default=0, description="Total I/O ports")
    cell_types: dict[str, int] = Field(default_factory=dict, description="Detailed count by cell primitive")
    synthesis_time_seconds: float = Field(default=0.0, description="Time spent in synthesis execution")
    error_message: str = Field(default="", description="Error description if synthesis failed")
    log_path: str = Field(default="", description="Path to complete synthesis log file")
    metric_type_note: str = Field(
        default="Cell counts are architectural logic proxies (generic gate primitives), not calibrated physical silicon area (um^2).",
        description="Clarification of metric measurement nature"
    )

class Synthesizer:
    def __init__(self, yosys_path: str | None = None, lib_dir: str | None = None):
        self.yosys_path = yosys_path or config.YOSYS_PATH
        self.lib_dir = lib_dir or config.YOSYS_LIB_DIR
        if not self.yosys_path or not os.path.isfile(self.yosys_path):
            raise FileNotFoundError(f"Yosys executable not found at: {self.yosys_path}")

    def synthesize(
        self,
        design_file: str | Path,
        top_module: str = "alu_16bit",
        log_name: str | None = None,
        timeout: int = config.TIMEOUT_SYNTHESIS
    ) -> SynthesisMetrics:
        design_path = Path(design_file).resolve()
        if not design_path.is_file():
            return SynthesisMetrics(
                success=False,
                top_module=top_module,
                error_message=f"Verilog file not found: {design_path}"
            )

        start_time = time.time()
        timestamp = int(start_time)
        file_stem = design_path.stem
        log_filename = log_name or f"synth_{file_stem}_{timestamp}.log"
        log_file = config.LOGS_DIR / log_filename
        metrics_file = config.METRICS_DIR / f"metrics_{file_stem}_{timestamp}.json"

        # Standard, consistent synthesis script for fair comparison across candidates
        # Uses standard Yosys generic gate mapping (synth -top <module> followed by stat -json)
        clean_design_path = str(design_path).replace(chr(92), "/")
        script_content = f"""
read_verilog -sv "{clean_design_path}"
hierarchy -check -top {top_module}
synth -top {top_module}
stat -json
"""

        with tempfile.NamedTemporaryFile(suffix=".ys", mode="w", delete=False) as tmp_script:
            tmp_script.write(script_content)
            script_path = tmp_script.name

        try:
            env = os.environ.copy()
            if self.lib_dir:
                env["PATH"] = f"{self.lib_dir};" + env.get("PATH", "")

            cmd = [self.yosys_path, "-s", script_path]
            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    env=env
                )
            except subprocess.TimeoutExpired:
                err = f"Yosys synthesis timed out after {timeout} seconds"
                with open(log_file, "w") as lf:
                    lf.write(f"ERROR: {err}\n")
                return SynthesisMetrics(
                    success=False,
                    top_module=top_module,
                    error_message=err,
                    log_path=str(log_file),
                    synthesis_time_seconds=round(time.time() - start_time, 4)
                )

            full_log = f"=== YOSYS STDOUT ===\n{proc.stdout}\n=== YOSYS STDERR ===\n{proc.stderr}\n"
            with open(log_file, "w", encoding="utf-8") as lf:
                lf.write(full_log)

            synth_time = round(time.time() - start_time, 4)

            if proc.returncode != 0:
                err_lines = [l for l in proc.stdout.splitlines() if "ERROR:" in l or "syntax error" in l.lower()]
                if not err_lines and proc.stderr:
                    err_lines = proc.stderr.splitlines()
                err_msg = "\n".join(err_lines[-5:]) if err_lines else f"Yosys exited with code {proc.returncode}"
                return SynthesisMetrics(
                    success=False,
                    top_module=top_module,
                    error_message=f"Synthesis failed:\n{err_msg}",
                    log_path=str(log_file),
                    synthesis_time_seconds=synth_time
                )

            # Extract JSON block from stdout
            json_block = self._extract_json(proc.stdout)
            if not json_block:
                return SynthesisMetrics(
                    success=False,
                    top_module=top_module,
                    error_message="Could not parse JSON statistics from Yosys output",
                    log_path=str(log_file),
                    synthesis_time_seconds=synth_time
                )

            metrics = self._parse_metrics(json_block, top_module, synth_time, str(log_file))

            # Save metrics JSON to disk
            with open(metrics_file, "w", encoding="utf-8") as mf:
                json.dump(metrics.model_dump(), mf, indent=2)

            return metrics

        finally:
            if os.path.exists(script_path):
                try:
                    os.remove(script_path)
                except OSError:
                    pass

    def _extract_json(self, stdout: str) -> dict | None:
        """Extract the JSON output generated by Yosys stat -json"""
        json_start = stdout.find("{\n")
        json_end = stdout.rfind("\n}")
        if json_start != -1 and json_end != -1:
            raw_json = stdout[json_start : json_end + 2]
            try:
                return json.loads(raw_json)
            except json.JSONDecodeError:
                pass

        # Fallback: scan with regex
        matches = list(re.finditer(r"(\{[\s\S]*\"design\"[\s\S]*\})", stdout))
        for m in reversed(matches):
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                continue
        return None

    def _parse_metrics(self, data: dict, top_module: str, synth_time: float, log_path: str) -> SynthesisMetrics:
        # Check module specific stats or global design stats
        mod_key = f"\\{top_module}"
        stats = None
        if "modules" in data:
            if mod_key in data["modules"]:
                stats = data["modules"][mod_key]
            elif top_module in data["modules"]:
                stats = data["modules"][top_module]
            elif len(data["modules"]) == 1:
                stats = list(data["modules"].values())[0]

        if not stats and "design" in data:
            stats = data["design"]

        if not stats:
            stats = {}

        total_cells = stats.get("num_cells", 0)
        num_wires = stats.get("num_wires", 0)
        num_wire_bits = stats.get("num_wire_bits", 0)
        num_ports = stats.get("num_ports", 0)
        cell_types = stats.get("num_cells_by_type", {})

        mux_count = 0
        sequential_count = 0
        logic_count = 0

        for ctype, count in cell_types.items():
            cupper = ctype.upper()
            if "MUX" in cupper:
                mux_count += count
            elif any(seq in cupper for seq in ["DFF", "LATCH", "FF", "REGISTER"]):
                sequential_count += count
            else:
                logic_count += count

        return SynthesisMetrics(
            success=True,
            top_module=top_module,
            total_cells=total_cells,
            mux_count=mux_count,
            logic_cell_count=logic_count,
            sequential_cell_count=sequential_count,
            num_wires=num_wires,
            num_wire_bits=num_wire_bits,
            num_ports=num_ports,
            cell_types=cell_types,
            synthesis_time_seconds=synth_time,
            log_path=log_path
        )

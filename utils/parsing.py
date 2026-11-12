import re
from pydantic import BaseModel, Field

class PortDefinition(BaseModel):
    name: str = Field(..., description="Port identifier (e.g. 'a', 'result')")
    direction: str = Field(..., description="'input' or 'output'")
    port_type: str = Field(default="wire", description="'wire' or 'reg'")
    width: str = Field(..., description="Bit-width range or '1' (e.g. '[DATA_WIDTH-1:0]', '[2:0]', '1')")
    is_signed: bool = Field(default=False, description="Whether port is signed")
    description: str = Field(default="", description="Functional description of port")

class OpcodeDefinition(BaseModel):
    opcode: str = Field(..., description="Binary/hex opcode literal (e.g. '3b000')")
    operation_name: str = Field(..., description="Descriptive name (e.g. 'Addition', 'Absolute Difference')")
    description: str = Field(..., description="Detailed mathematical behavior, flags affected, and clamping")

class StructuredHardwareSpecification(BaseModel):
    module_name: str = Field(..., description="Clean snake_case module identifier")
    description: str = Field(..., description="High-level hardware architectural summary")
    parameters: dict[str, str] = Field(default_factory=dict, description="Verilog parameters with default values (e.g. {'DATA_WIDTH': '16'})")
    ports: list[PortDefinition] = Field(default_factory=list, description="List of all input and output ports")
    operation_table: list[OpcodeDefinition] = Field(default_factory=list, description="Opcode mappings")
    status_flags: list[str] = Field(default_factory=list, description="Summary of status flags (e.g. zero, carry, saturated)")
    design_constraints: list[str] = Field(default_factory=list, description="Synthesizability and latch prevention rules")
    raw_spec_text: str = Field(default="", description="Full human-readable specification text")

    def to_formatted_prompt_text(self) -> str:
        """Formats the structured spec into clean markdown text for subsequent LLM agents."""
        lines = [
            f"# Hardware Specification: {self.module_name}",
            f"{self.description}\n",
            "## Parameters:"
        ]
        for k, v in self.parameters.items():
            lines.append(f"- {k} = {v}")
        
        lines.append("\n## Ports:")
        for p in self.ports:
            signed_str = " signed" if p.is_signed else ""
            lines.append(f"- {p.direction} {p.port_type}{signed_str} {p.width} {p.name}: {p.description}")
            
        lines.append("\n## Operation Table:")
        for op in self.operation_table:
            lines.append(f"- {op.opcode}: {op.operation_name} -> {op.description}")
            
        if self.status_flags:
            lines.append("\n## Status Flags:")
            for flag in self.status_flags:
                lines.append(f"- {flag}")
                
        if self.design_constraints:
            lines.append("\n## Design Constraints:")
            for c in self.design_constraints:
                lines.append(f"- {c}")
                
        return "\n".join(lines)

class RTLGenerationOutput(BaseModel):
    module_name: str = Field(..., description="The name of the top-level Verilog module (e.g. alu_16bit)")
    verilog_code: str = Field(..., description="The full, synthesizable Verilog RTL source code")
    explanation: str = Field(..., description="High-level architectural explanation of the implementation")
    supported_operations: list[str] = Field(default_factory=list, description="List of operations supported by opcodes")
    interface_description: str = Field(default="", description="Summary of module inputs and outputs")

class RTLRepairOutput(BaseModel):
    module_name: str = Field(..., description="The name of the top-level module")
    repaired_verilog_code: str = Field(..., description="The corrected, synthesizable Verilog code")
    bug_explanation: str = Field(..., description="Detailed diagnosis of what caused the simulation or compilation failure")
    changes_made: list[str] = Field(default_factory=list, description="List of specific code edits made to fix the bug")

class RTLOptimizationOutput(BaseModel):
    candidate_name: str = Field(..., description="Identifier for this optimization candidate (e.g. opt_sharing_v1)")
    optimized_verilog_code: str = Field(..., description="The optimized synthesizable Verilog RTL")
    optimization_strategy: str = Field(..., description="The hardware technique applied (e.g. Resource sharing, Boolean factoring)")
    expected_improvement: str = Field(..., description="Why this candidate is expected to reduce cell count or mux count")
    modifications: list[str] = Field(default_factory=list, description="Specific RTL logic modifications")

def extract_verilog_code(raw_text: str | list) -> str:
    """
    Robustly extracts Verilog code from an LLM response.
    Handles ```verilog ... ``` code blocks, generic ``` blocks, or bare Verilog code.
    Also handles LangChain list-of-content-blocks responses.
    """
    if isinstance(raw_text, list):
        parts = []
        for item in raw_text:
            if isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
            elif isinstance(item, str):
                parts.append(item)
            elif hasattr(item, "text"):
                parts.append(str(item.text))
            else:
                parts.append(str(item))
        text = "\n".join(parts).strip()
    else:
        text = str(raw_text).strip()
    
    # 1. Match ```verilog ... ```
    m_vlog = re.search(r"```(?:verilog|systemverilog|v)\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if m_vlog:
        return m_vlog.group(1).strip()
    
    # 2. Match generic ``` ... ```
    m_gen = re.search(r"```\s*([\s\S]*?)\s*```", text)
    if m_gen:
        candidate = m_gen.group(1).strip()
        if "module" in candidate and "endmodule" in candidate:
            return candidate

    # 3. Match from the first 'module' to the last 'endmodule'
    m_mod = re.search(r"(\bmodule\b[\s\S]*?\bendmodule\b)", text)
    if m_mod:
        return m_mod.group(1).strip()

    # 4. If all else fails, return raw text
    return text

def extract_module_name(verilog_code: str) -> str | None:
    """Extracts top module name from Verilog code."""
    m = re.search(r"\bmodule\s+([a-zA-Z_][a-zA-Z0-9_]*)", verilog_code)
    if m:
        return m.group(1)
    return None

def validate_verilog_syntax_basic(verilog_code: str) -> tuple[bool, str]:
    """Basic lexical checks to reject obviously truncated or incomplete RTL."""
    if not verilog_code or not verilog_code.strip():
        return False, "Verilog code is empty."
    if "module" not in verilog_code:
        return False, "Missing 'module' declaration."
    if "endmodule" not in verilog_code:
        return False, "Missing 'endmodule' termination."
    
    mod_count = len(re.findall(r"\bmodule\b", verilog_code))
    end_count = len(re.findall(r"\bendmodule\b", verilog_code))
    if mod_count != end_count:
        return False, f"Mismatched module ({mod_count}) and endmodule ({end_count}) statements."
    
    return True, "Basic syntax check passed."


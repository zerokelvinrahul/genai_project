import re
from pydantic import BaseModel, Field

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


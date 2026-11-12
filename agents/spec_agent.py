from pathlib import Path
from langchain_core.messages import SystemMessage, HumanMessage

import config
from agents.base_agent import BaseLLMAgent
from utils.parsing import (
    StructuredHardwareSpecification,
    PortDefinition,
    OpcodeDefinition
)

class SpecificationAgent(BaseLLMAgent):
    """
    Stage 1: Specification Agent.
    Converts a free-form natural language hardware requirement into a 
    structured, unambiguous hardware specification.
    """
    def __init__(self, api_key: str | None = None, model_name: str | None = None):
        super().__init__(api_key=api_key, model_name=model_name, temperature=0.1)

    def parse_specification(self, user_prompt: str) -> StructuredHardwareSpecification:
        """
        Parses free-form user prompt into StructuredHardwareSpecification via structured output.
        """
        prompt_template = (config.PROMPTS_DIR / "specification.txt").read_text(encoding="utf-8")
        prompt = prompt_template.replace("{user_prompt}", user_prompt)
        llm = self._get_llm()

        try:
            structured_llm = llm.with_structured_output(StructuredHardwareSpecification)
            messages = [
                SystemMessage(content="You are a Principal Digital VLSI Architect defining standard synthesizable Verilog-2001 hardware."),
                HumanMessage(content=prompt)
            ]
            result: StructuredHardwareSpecification = self.invoke_with_retry(messages)
            # if invoke returned a Message instead of model because of raw fallback:
            if hasattr(result, "content"):
                spec_text = str(result.content)
                result = StructuredHardwareSpecification(
                    module_name="alu_16bit",
                    description=spec_text[:100],
                    parameters={"DATA_WIDTH": "16"},
                    ports=[],
                    operation_table=[],
                    raw_spec_text=spec_text
                )
            if not result.raw_spec_text:
                result.raw_spec_text = result.to_formatted_prompt_text()
            return result
        except Exception as e:
            print(f"[SpecificationAgent] Structured output fallback: {e}")
            messages = [
                SystemMessage(content="You are a Principal Digital VLSI Architect defining standard synthesizable Verilog-2001 hardware."),
                HumanMessage(content=prompt)
            ]
            raw = self.invoke_with_retry(messages)
            spec_text = str(raw.content)
            # Create a baseline structured spec from raw text
            return StructuredHardwareSpecification(
                module_name="custom_hardware_unit",
                description="Parsed hardware block from user description",
                parameters={"DATA_WIDTH": "16"},
                ports=[
                    PortDefinition(name="a", direction="input", port_type="wire", width="[DATA_WIDTH-1:0]", description="Operand A"),
                    PortDefinition(name="b", direction="input", port_type="wire", width="[DATA_WIDTH-1:0]", description="Operand B"),
                    PortDefinition(name="opcode", direction="input", port_type="wire", width="[2:0]", description="Operation select"),
                    PortDefinition(name="result", direction="output", port_type="reg", width="[DATA_WIDTH-1:0]", description="Calculated output"),
                    PortDefinition(name="zero", direction="output", port_type="wire", width="1", description="Zero flag")
                ],
                operation_table=[],
                status_flags=["zero"],
                design_constraints=["Pure synthesizable Verilog-2001", "No latches"],
                raw_spec_text=spec_text
            )


from pathlib import Path
from eda.synthesizer import Synthesizer, SynthesisMetrics
from utils.file_manager import FileManager

class SynthesisAgent:
    def __init__(self, synthesizer: Synthesizer | None = None):
        self.synthesizer = synthesizer or Synthesizer()

    def run_synthesis(
        self,
        rtl_path: str | Path,
        top_module: str = "alu_16bit",
        log_name: str | None = None
    ) -> SynthesisMetrics:
        """
        Executes consistent synthesis using Yosys on verified RTL and extracts metrics.
        """
        path = Path(rtl_path).resolve()
        metrics = self.synthesizer.synthesize(
            design_file=path,
            top_module=top_module,
            log_name=log_name
        )
        return metrics


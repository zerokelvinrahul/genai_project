import json
import shutil
from pathlib import Path
import config

class FileManager:
    @staticmethod
    def save_rtl(code: str, category: str, filename: str) -> Path:
        """
        Saves RTL code to rtl/<category>/<filename>.
        category: 'baseline', 'generated', 'optimized'
        """
        target_dir = {
            "baseline": config.RTL_BASELINE_DIR,
            "generated": config.RTL_GENERATED_DIR,
            "optimized": config.RTL_OPTIMIZED_DIR
        }.get(category, config.RTL_GENERATED_DIR)

        target_dir.mkdir(parents=True, exist_ok=True)
        out_path = target_dir / filename
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(code)
        return out_path

    @staticmethod
    def load_rtl(path: str | Path) -> str:
        """Loads RTL source code from a file."""
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    @staticmethod
    def save_report(data: dict, filename: str) -> Path:
        """Saves a JSON report to results/reports/<filename>."""
        out_path = config.REPORTS_DIR / filename
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return out_path

    @staticmethod
    def get_baseline_rtl_path() -> Path:
        return config.RTL_BASELINE_DIR / "alu_16bit.v"

    @staticmethod
    def get_deterministic_tb_path() -> Path:
        return config.TESTBENCHES_DIR / "alu_16bit_tb.v"


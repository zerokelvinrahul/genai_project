import os
import shutil
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

# Base project directory
BASE_DIR = Path(__file__).resolve().parent

# RTL and Testbench paths
RTL_BASELINE_DIR = BASE_DIR / "rtl" / "baseline"
RTL_GENERATED_DIR = BASE_DIR / "rtl" / "generated"
RTL_OPTIMIZED_DIR = BASE_DIR / "rtl" / "optimized"
TESTBENCHES_DIR = BASE_DIR / "testbenches"
PROMPTS_DIR = BASE_DIR / "prompts"

# Results paths
RESULTS_DIR = BASE_DIR / "results"
LOGS_DIR = RESULTS_DIR / "logs"
METRICS_DIR = RESULTS_DIR / "metrics"
REPORTS_DIR = RESULTS_DIR / "reports"

for d in [RTL_BASELINE_DIR, RTL_GENERATED_DIR, RTL_OPTIMIZED_DIR, 
          TESTBENCHES_DIR, RESULTS_DIR, LOGS_DIR, METRICS_DIR, REPORTS_DIR, PROMPTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# EDA Tool Detection
def find_tool(tool_name: str, candidate_paths: list[str]) -> str | None:
    # 1. Check if tool is in PATH
    in_path = shutil.which(tool_name)
    if in_path and os.path.isfile(in_path):
        return in_path
    # 2. Check candidate explicit paths
    for cp in candidate_paths:
        if os.path.isfile(cp):
            return cp
    return None

IVERILOG_CANDIDATES = [
    r"C:\iverilog\bin\iverilog.exe",
    r"E:\oss-cad-suite\bin\iverilog.exe",
    r"C:\oss-cad-suite\bin\iverilog.exe",
]
VVP_CANDIDATES = [
    r"C:\iverilog\bin\vvp.exe",
    r"E:\oss-cad-suite\bin\vvp.exe",
    r"C:\oss-cad-suite\bin\vvp.exe",
]
YOSYS_CANDIDATES = [
    r"E:\oss-cad-suite\bin\yosys.exe",
    r"C:\oss-cad-suite\bin\yosys.exe",
    r"C:\yosys\yosys.exe",
]
YOSYS_LIB_CANDIDATES = [
    r"E:\oss-cad-suite\lib",
    r"C:\oss-cad-suite\lib",
]

IVERILOG_PATH = os.environ.get("IVERILOG_PATH") or find_tool("iverilog", IVERILOG_CANDIDATES)
VVP_PATH = os.environ.get("VVP_PATH") or find_tool("vvp", VVP_CANDIDATES)
YOSYS_PATH = os.environ.get("YOSYS_PATH") or find_tool("yosys", YOSYS_CANDIDATES)

YOSYS_LIB_DIR = None
for yld in YOSYS_LIB_CANDIDATES:
    if os.path.isdir(yld):
        YOSYS_LIB_DIR = yld
        break

# LLM Configuration
_raw_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
GOOGLE_API_KEY = _raw_key.strip("'\"") if _raw_key else None
# Default model: gemini-3.5-flash-lite (fastest on free tier)
_raw_model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
GEMINI_MODEL = _raw_model.strip("'\"") if _raw_model else "gemini-3.5-flash-lite"

# Subprocess timeouts (seconds)
TIMEOUT_SIMULATION = int(os.environ.get("TIMEOUT_SIMULATION", "30"))
TIMEOUT_SYNTHESIS = int(os.environ.get("TIMEOUT_SYNTHESIS", "60"))

# Tool Status Check
def get_eda_status() -> dict[str, dict]:
    return {
        "iverilog": {
            "found": IVERILOG_PATH is not None,
            "path": IVERILOG_PATH,
        },
        "vvp": {
            "found": VVP_PATH is not None,
            "path": VVP_PATH,
        },
        "yosys": {
            "found": YOSYS_PATH is not None,
            "path": YOSYS_PATH,
            "lib_dir": YOSYS_LIB_DIR,
        }
    }


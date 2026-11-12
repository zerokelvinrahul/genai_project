# ChipGen AI: AI-Powered RTL Generation, Verification and PPA Optimization Agent

ChipGen AI is an automated hardware design system that generates synthesizable Verilog RTL from natural language specifications, verifies functionality with deterministic simulations, synthesizes candidate designs with real EDA synthesis tools (Yosys), and iteratively optimizes the RTL using LLM feedback based on actual EDA synthesis metrics.

---

## 1. System Architecture

```
                  Natural Language Specification
                               │
                               ▼
                    ┌──────────────────────┐
                    │    RTL Generator     │ (LangChain + Gemini + Pydantic)
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │  Verification Agent  │ ◄───────┐
                    │ (Icarus Verilog/vvp) │         │ Automated
                    └──────────┬───────────┘         │ Repair Loop
                               │ [Pass]              │ (Max 3 attempts)
                               ▼                     │
                    ┌──────────────────────┐         │
                    │   Synthesis Agent    │         │
                    │     (Real Yosys)     │         │
                    └──────────┬───────────┘         │
                               │ [Metrics JSON]      │
                               ▼                     │
                    ┌──────────────────────┐         │
                    │  Optimization Agent  │─────────┘
                    │ (Arithmetic Sharing) │
                    └──────────┬───────────┘
                               │
                               ▼
               ┌────────────────────────────────┐
               │    Streamlit Dark Dashboard    │
               │  & Matplotlib PPA Comparison   │
               └────────────────────────────────┘
```

### Core Components
1. **RTL Generator (`agents/rtl_generator.py`)**:
   - Converts natural language hardware descriptions into synthesizable Verilog-2001.
   - Enforces explicit bit widths, interface preservation, and latch-prevention rules.
   - Uses structured Pydantic schemas (`RTLGenerationOutput`).
2. **Verification Agent (`agents/verification_agent.py`)**:
   - Compiles RTL with Icarus Verilog (`iverilog`) and runs simulations with `vvp`.
   - Executes deterministic reference testbenches covering all 8 operations, edge cases (overflow, borrow, zero flag, maximum shifts).
   - Python code strictly determines pass/fail status (never LLM self-reporting).
   - If tests fail, automatically diagnoses stdout/stderr logs and executes up to 3 repair iterations.
3. **Synthesis Agent (`agents/synthesis_agent.py` & `eda/synthesizer.py`)**:
   - Executes Yosys on verified designs using a standardized script.
   - Extracts machine-readable structural metrics: Total Cells, MUX count, Logic gates, Sequential cells, and runtime.
   - Emphasizes that cell count is a generic logic complexity proxy, not physical silicon area.
4. **Optimization Agent (`agents/optimization_agent.py`)**:
   - Analyzes previous synthesis statistics and verification reports.
   - Employs architectural optimizations (such as arithmetic adder resource sharing for addition and subtraction).
   - Accepts candidates ONLY if simulation passes 100%, synthesis succeeds, and cell/mux metrics improve.
5. **Main Orchestrator (`main.py`)**:
   - Executes the complete 3-experiment benchmark pipeline.
   - Produces machine-readable JSON metrics and publication-quality dark-themed comparison charts.
6. **Streamlit UI (`app.py`)**:
   - Full dark-themed interactive dashboard for generation, verification, synthesis inspection, and optimization history.

---

## 2. Target Hardware Design (16-bit ALU)

The system is tested and benchmarked against a configurable 16-bit Arithmetic Logic Unit:

| Opcode | Operation | Expression | Carry / Borrow Flag |
|---|---|---|---|
| `000` | Addition | `{carry_out, result} = a + b` | Carry generated on 16-bit overflow |
| `001` | Subtraction | `{carry_out, result} = a - b` | Borrow generated on underflow (`a < b`) |
| `010` | Bitwise AND | `result = a & b` | `carry_out = 0` |
| `011` | Bitwise OR | `result = a | b` | `carry_out = 0` |
| `100` | Bitwise XOR | `result = a ^ b` | `carry_out = 0` |
| `101` | Logical Shift Left | `result = a << b[3:0]` | `carry_out = 0` |
| `110` | Logical Shift Right | `result = a >> b[3:0]` | `carry_out = 0` |
| `111` | Pass A | `result = a` | `carry_out = 0` |

- **Zero Flag**: Continuous assignment `assign zero = (result == 16'h0000);`
- **Data Width**: Configurable via parameter `DATA_WIDTH = 16`.

---

## 3. Empirical Results: Baseline vs One-Shot vs Optimized

*All metrics are measured from actual Icarus Verilog simulations and Yosys synthesis execution (no fabricated or mocked values).*

| Metric | 1. Baseline ALU | 2. One-Shot AI ALU | 3. Optimized AI ALU | Improvement (Opt vs Base) |
|---|---|---|---|---|
| **Verification Status** | **PASSED (27/27)** | **PASSED (27/27)** | **PASSED (27/27)** | Exact Equivalence Preserved |
| **Total Cells (Proxy)** | 590 cells | 590 cells | **505 cells** | **-14.4% Logic Reduction** |
| **Logic Gates** | 513 gates | 513 gates | **423 gates** | **-17.5% Gate Reduction** |
| **MUX Cells** | 77 muxes | 77 muxes | 82 muxes | +5 muxes (operand steering) |
| **Sequential Cells** | 0 cells | 0 cells | 0 cells | Pure Combinational |
| **Synthesis Time** | 0.390s | 0.384s | 0.410s | Sub-second execution |

### Key Optimization Insight:
In the Baseline ALU, independent `+` and `-` operators instantiate two parallel 16-bit adder/subtractor trees. In the **Optimized ALU**, arithmetic resource sharing unifies addition and subtraction into a single 16-bit core adder:
$$\text{Core Adder} = A + (\text{is\_sub} \ ? \ \sim B : B) + \text{is\_sub}$$
This architectural transformation eliminates 90 redundant logic gates from the netlist while preserving 100% functional equivalence across all test vectors.

---

## 4. Project Structure

```
ChipGen-AI/
├── agents/
│   ├── rtl_generator.py         # LLM Verilog generation with Pydantic output
│   ├── verification_agent.py    # Simulation runner & automated repair loop
│   ├── synthesis_agent.py       # Yosys synthesis execution & logging
│   └── optimization_agent.py    # Multi-iteration PPA optimization agent
├── eda/
│   ├── simulator.py             # Icarus Verilog (iverilog + vvp) subprocess wrapper
│   └── synthesizer.py           # Yosys synthesis & stat -json parser
├── rtl/
│   ├── baseline/                # Reference ALU implementation (alu_16bit.v)
│   ├── generated/               # AI-generated RTL candidates
│   └── optimized/               # Verified PPA-optimized RTL candidates
├── testbenches/
│   └── alu_16bit_tb.v           # 27-vector deterministic self-checking testbench
├── results/
│   ├── logs/                    # Full Yosys synthesis and simulation logs
│   ├── metrics/                 # Extracted JSON synthesis statistics
│   └── reports/                 # Comparison matrices and charts
├── prompts/
│   ├── rtl_generation.txt       # RTL generation prompt template
│   ├── verification.txt         # Automated repair prompt template
│   └── optimization.txt         # PPA optimization prompt template
├── utils/
│   ├── parsing.py               # Verilog extraction & syntax validator
│   ├── file_manager.py          # RTL and artifact disk manager
│   └── visualization.py         # Matplotlib dark-themed chart generator
├── app.py                       # Streamlit web dashboard
├── main.py                      # Main pipeline orchestrator CLI
├── config.py                    # Environment & EDA tool auto-detection
├── requirements.txt             # Python dependencies
├── .env.example                 # Environment variables template
├── .gitignore                   # Ignored files
└── README.md                    # Documentation
```

---

## 5. Prerequisites & Installation

### A. Python Environment
Python 3.11+ is recommended. Install required packages:
```bash
pip install -r requirements.txt
```

### B. EDA Tools
The system relies on native EDA tools:
1. **Icarus Verilog (`iverilog` & `vvp`)**:
   - Pre-installed or install via Inno Setup / Package Manager.
   - Detected at `C:\iverilog\bin\iverilog.exe` or system `PATH`.
2. **Yosys (`yosys.exe`)**:
   - Installed via OSS CAD Suite at `E:\oss-cad-suite\bin\yosys.exe` (with `lib` directory in PATH) or system `PATH`.
   - Auto-detected by `config.py`.

### C. Environment Variables
Copy `.env.example` to `.env` and configure your API key:
```env
GOOGLE_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash
```

---

## 6. Execution Instructions

### A. Run CLI Benchmark & Verification
To run the automated 3-stage benchmark (Baseline, One-Shot, Optimized) with real EDA simulations and synthesis:
```bash
python main.py
```
Outputs:
- Console PPA comparison matrix.
- `results/reports/experiment_results.json` (machine-readable metrics).
- `results/reports/comparison_chart.png` (Matplotlib comparison graphic).

### B. Launch Streamlit Web Dashboard
To launch the interactive dark-themed UI:
```bash
streamlit run app.py
```
Open your browser at `http://localhost:8501`.

---

## 7. Engineering Highlights
- **Real EDA Execution**: All simulations run through `iverilog` + `vvp` and all synthesis runs through `yosys` via safe Python `subprocess` with timeout guards (30s simulation, 60s synthesis).
- **Objective Acceptance Criteria**: Candidate optimizations are rejected if functional verification fails or cell count does not improve.
- **Metric Integrity**: Cell count is explicitly labeled as an architectural logic complexity proxy, avoiding false claims of physical silicon area.


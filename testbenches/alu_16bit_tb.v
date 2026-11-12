// Deterministic Self-Checking Testbench for 16-bit ALU
// ChipGen AI Verification Suite
`timescale 1ns / 1ps

module alu_16bit_tb;

    parameter DATA_WIDTH = 16;

    reg  [DATA_WIDTH-1:0] a;
    reg  [DATA_WIDTH-1:0] b;
    reg  [2:0]            opcode;
    wire [DATA_WIDTH-1:0] result;
    wire                  carry_out;
    wire                  zero;

    integer errors = 0;
    integer tests_run = 0;

    // Instantiate Unit Under Test (UUT)
    alu_16bit #(
        .DATA_WIDTH(DATA_WIDTH)
    ) uut (
        .a(a),
        .b(b),
        .opcode(opcode),
        .result(result),
        .carry_out(carry_out),
        .zero(zero)
    );

    // Task to check outputs
    task check_result;
        input [DATA_WIDTH-1:0] exp_result;
        input                  exp_carry;
        input                  exp_zero;
        input [80*8:1]         test_name;
        begin
            #5; // Wait for combinational propagation
            tests_run = tests_run + 1;
            if (result !== exp_result || carry_out !== exp_carry || zero !== exp_zero) begin
                $display("[FAIL] Test %0d (%0s) - Op:%b A:%h B:%h | Res:%h (Exp:%h) Cout:%b (Exp:%b) Zero:%b (Exp:%b)",
                         tests_run, test_name, opcode, a, b, result, exp_result, carry_out, exp_carry, zero, exp_zero);
                errors = errors + 1;
            end else begin
                $display("[PASS] Test %0d (%0s) - Op:%b A:%h B:%h -> Res:%h Cout:%b Zero:%b",
                         tests_run, test_name, opcode, a, b, result, carry_out, zero);
            end
        end
    endtask

    initial begin
        $display("Starting Deterministic Verification for alu_16bit...");

        // ---------------------------------------------------------
        // Opcode 000: Addition
        // ---------------------------------------------------------
        opcode = 3'b000; a = 16'h0005; b = 16'h0003; check_result(16'h0008, 1'b0, 1'b0, "ADD_BASIC");
        opcode = 3'b000; a = 16'hFFFF; b = 16'h0001; check_result(16'h0000, 1'b1, 1'b1, "ADD_OVERFLOW_ZERO");
        opcode = 3'b000; a = 16'h8000; b = 16'h8000; check_result(16'h0000, 1'b1, 1'b1, "ADD_CARRY_ONLY");
        opcode = 3'b000; a = 16'h1234; b = 16'h4321; check_result(16'h5555, 1'b0, 1'b0, "ADD_ARBITRARY");

        // ---------------------------------------------------------
        // Opcode 001: Subtraction
        // ---------------------------------------------------------
        opcode = 3'b001; a = 16'h000A; b = 16'h0003; check_result(16'h0007, 1'b0, 1'b0, "SUB_BASIC");
        opcode = 3'b001; a = 16'h0005; b = 16'h0005; check_result(16'h0000, 1'b0, 1'b1, "SUB_ZERO");
        opcode = 3'b001; a = 16'h0000; b = 16'h0001; check_result(16'hFFFF, 1'b1, 1'b0, "SUB_BORROW");
        opcode = 3'b001; a = 16'h7FFF; b = 16'h0001; check_result(16'h7FFE, 1'b0, 1'b0, "SUB_ARBITRARY");

        // ---------------------------------------------------------
        // Opcode 010: Bitwise AND
        // ---------------------------------------------------------
        opcode = 3'b010; a = 16'hFF00; b = 16'h0FF0; check_result(16'h0F00, 1'b0, 1'b0, "AND_OVERLAP");
        opcode = 3'b010; a = 16'hAAAA; b = 16'h5555; check_result(16'h0000, 1'b0, 1'b1, "AND_DISJOINT_ZERO");
        opcode = 3'b010; a = 16'hFFFF; b = 16'hFFFF; check_result(16'hFFFF, 1'b0, 1'b0, "AND_ALL_ONES");

        // ---------------------------------------------------------
        // Opcode 011: Bitwise OR
        // ---------------------------------------------------------
        opcode = 3'b011; a = 16'hFF00; b = 16'h00FF; check_result(16'hFFFF, 1'b0, 1'b0, "OR_COMPLEMENT");
        opcode = 3'b011; a = 16'h0000; b = 16'h0000; check_result(16'h0000, 1'b0, 1'b1, "OR_ZEROS");
        opcode = 3'b011; a = 16'h1200; b = 16'h0034; check_result(16'h1234, 1'b0, 1'b0, "OR_PATTERN");

        // ---------------------------------------------------------
        // Opcode 100: Bitwise XOR
        // ---------------------------------------------------------
        opcode = 3'b100; a = 16'hAAAA; b = 16'h5555; check_result(16'hFFFF, 1'b0, 1'b0, "XOR_INVERT");
        opcode = 3'b100; a = 16'hBEEF; b = 16'hBEEF; check_result(16'h0000, 1'b0, 1'b1, "XOR_SELF_ZERO");
        opcode = 3'b100; a = 16'h1234; b = 16'h0000; check_result(16'h1234, 1'b0, 1'b0, "XOR_IDENTITY");

        // ---------------------------------------------------------
        // Opcode 101: Shift Left
        // ---------------------------------------------------------
        opcode = 3'b101; a = 16'h0001; b = 16'h0004; check_result(16'h0010, 1'b0, 1'b0, "SHL_4");
        opcode = 3'b101; a = 16'h0001; b = 16'h000F; check_result(16'h8000, 1'b0, 1'b0, "SHL_15");
        opcode = 3'b101; a = 16'h0080; b = 16'h0009; check_result(16'h0000, 1'b0, 1'b1, "SHL_OUT_ZERO");
        opcode = 3'b101; a = 16'hABCD; b = 16'h0000; check_result(16'hABCD, 1'b0, 1'b0, "SHL_0");

        // ---------------------------------------------------------
        // Opcode 110: Shift Right
        // ---------------------------------------------------------
        opcode = 3'b110; a = 16'h8000; b = 16'h0004; check_result(16'h0800, 1'b0, 1'b0, "SHR_4");
        opcode = 3'b110; a = 16'h8000; b = 16'h000F; check_result(16'h0001, 1'b0, 1'b0, "SHR_15");
        opcode = 3'b110; a = 16'h0001; b = 16'h0001; check_result(16'h0000, 1'b0, 1'b1, "SHR_OUT_ZERO");
        opcode = 3'b110; a = 16'hABCD; b = 16'h0000; check_result(16'hABCD, 1'b0, 1'b0, "SHR_0");

        // ---------------------------------------------------------
        // Opcode 111: Pass A
        // ---------------------------------------------------------
        opcode = 3'b111; a = 16'hCAFE; b = 16'h1234; check_result(16'hCAFE, 1'b0, 1'b0, "PASS_A_NONZERO");
        opcode = 3'b111; a = 16'h0000; b = 16'hFFFF; check_result(16'h0000, 1'b0, 1'b1, "PASS_A_ZERO");

        // ---------------------------------------------------------
        // Verification Summary Report
        // ---------------------------------------------------------
        $display("\n=== VERIFICATION SUMMARY ===");
        $display("TOTAL TESTS : %0d", tests_run);
        $display("PASSED      : %0d", (tests_run - errors));
        $display("FAILED      : %0d", errors);

        if (errors == 0) begin
            $display("STATUS: PASSED");
        end else begin
            $display("STATUS: FAILED");
        end
        $finish;
    end

endmodule


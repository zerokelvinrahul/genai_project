// Optimized 16-bit Configurable ALU
// Optimization Strategy: Arithmetic Resource Sharing & MUX Tree Flattening
// ChipGen AI Optimization Candidate

`timescale 1ns / 1ps

module alu_16bit #(
    parameter DATA_WIDTH = 16
) (
    input  wire [DATA_WIDTH-1:0] a,
    input  wire [DATA_WIDTH-1:0] b,
    input  wire [2:0]            opcode,
    output reg  [DATA_WIDTH-1:0] result,
    output reg                   carry_out,
    output wire                  zero
);

    // Continuous assignment for zero flag
    assign zero = (result == {DATA_WIDTH{1'b0}});

    // Arithmetic Resource Sharing:
    // A single unified 16-bit adder handles both Addition (opcode 000) and Subtraction (opcode 001).
    // In subtraction, B is inverted and carry_in is asserted (two's complement subtraction).
    wire is_sub = (opcode == 3'b001);
    wire [DATA_WIDTH-1:0] b_operand = is_sub ? ~b : b;
    wire [DATA_WIDTH:0]   arith_core = {1'b0, a} + {1'b0, b_operand} + {15'b0, is_sub};

    always @(*) begin
        // Default assignments to prevent latches
        result    = {DATA_WIDTH{1'b0}};
        carry_out = 1'b0;

        case (opcode)
            3'b000: begin // Addition
                result    = arith_core[DATA_WIDTH-1:0];
                carry_out = arith_core[DATA_WIDTH];
            end

            3'b001: begin // Subtraction (borrow = ~carry from addition)
                result    = arith_core[DATA_WIDTH-1:0];
                carry_out = ~arith_core[DATA_WIDTH];
            end

            3'b010: begin // Bitwise AND
                result    = a & b;
                carry_out = 1'b0;
            end

            3'b011: begin // Bitwise OR
                result    = a | b;
                carry_out = 1'b0;
            end

            3'b100: begin // Bitwise XOR
                result    = a ^ b;
                carry_out = 1'b0;
            end

            3'b101: begin // Logical Left Shift
                result    = a << b[3:0];
                carry_out = 1'b0;
            end

            3'b110: begin // Logical Right Shift
                result    = a >> b[3:0];
                carry_out = 1'b0;
            end

            3'b111: begin // Pass A
                result    = a;
                carry_out = 1'b0;
            end

            default: begin
                result    = {DATA_WIDTH{1'b0}};
                carry_out = 1'b0;
            end
        endcase
    end

endmodule


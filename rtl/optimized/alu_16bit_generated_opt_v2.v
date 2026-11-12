module alu_16bit #(
    parameter DATA_WIDTH = 16
)(
    input  wire [DATA_WIDTH-1:0] a,
    input  wire [DATA_WIDTH-1:0] b,

    input  wire [2:0]            opcode,
    output reg  [DATA_WIDTH-1:0] result,
    output reg                   carry_out,
    output wire                  zero
);

    // Zero flag continuous assignment
    assign zero = (result == {DATA_WIDTH{1'b0}});

    // Arithmetic resource sharing: unified adder/subtractor core
    wire        is_sub;
    wire [DATA_WIDTH-1:0] b_operand;
    wire [DATA_WIDTH:0]   adder_result;

    // Detect subtraction opcode (3'b001)
    assign is_sub    = (opcode == 3'b001);
    
    // Invert b if subtraction, keeping b unchanged otherwise
    assign b_operand = b ^ {DATA_WIDTH{is_sub}};
    
    // Single shared adder core: a + b_operand + is_sub
    assign adder_result = {1'b0, a} + {1'b0, b_operand} + { {DATA_WIDTH{1'b0}}, is_sub };

    // Pre-compute parallel functional group results to optimize MUX trees
    wire [DATA_WIDTH-1:0] logic_result;
    wire [DATA_WIDTH-1:0] shift_result;

    // Logic operations decoding using opcode[1:0] when opcode[2] is 0
    // 3'b010: AND, 3'b011: OR, 3'b100: XOR
    wire [DATA_WIDTH-1:0] and_res = a & b;
    wire [DATA_WIDTH-1:0] or_res  = a | b;
    wire [DATA_WIDTH-1:0] xor_res = a ^ b;

    // Shift operations decoding using opcode[0]
    // 3'b101: Shift Left, 3'b110: Shift Right
    wire [DATA_WIDTH-1:0] shl_res = a << b[3:0];
    wire [DATA_WIDTH-1:0] shr_res = a >> b[3:0];

    // Combinational ALU logic structured with hierarchical multiplexing
    always @(*) begin
        // Default assignments to prevent latches and unassigned paths
        result     = {DATA_WIDTH{1'b0}};
        carry_out  = 1'b0;

        case (opcode[2])
            1'b0: begin
                // Group 0: Arithmetic and Bitwise Logic (opcodes 3'b000 to 3'b011)
                case (opcode[1:0])
                    2'b00: begin
                        // Addition: {carry_out, result} = a + b
                        result     = adder_result[DATA_WIDTH-1:0];
                        carry_out  = adder_result[DATA_WIDTH];
                    end
                    2'b01: begin
                        // Subtraction: {carry_out, result} = a - b
                        result     = adder_result[DATA_WIDTH-1:0];
                        carry_out  = ~adder_result[DATA_WIDTH];
                    end
                    2'b10: begin
                        // Bitwise AND
                        result     = and_res;
                        carry_out  = 1'b0;
                    end
                    2'b11: begin
                        // Bitwise OR
                        result     = or_res;
                        carry_out  = 1'b0;
                    end
                endcase
            end

            1'b1: begin
                // Group 1: Bitwise XOR, Shifts, and Pass A (opcodes 3'b100 to 3'b111)
                case (opcode[1:0])
                    2'b00: begin
                        // Bitwise XOR
                        result     = xor_res;
                        carry_out  = 1'b0;
                    end
                    2'b01: begin
                        // Shift Left
                        result     = shl_res;
                        carry_out  = 1'b0;
                    end
                    2'b10: begin
                        // Shift Right
                        result     = shr_res;
                        carry_out  = 1'b0;
                    end
                    2'b11: begin
                        // Pass A
                        result     = a;
                        carry_out  = 1'b0;
                    end
                endcase
            end
        endcase
    end

endmodule
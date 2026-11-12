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

    // Combinational ALU logic
    always @(*) begin
        // Default assignments to prevent latches and unassigned paths
        result     = {DATA_WIDTH{1'b0}};
        carry_out  = 1'b0;

        case (opcode)
            3'b000: begin
                // Addition: {carry_out, result} = a + b
                result     = adder_result[DATA_WIDTH-1:0];
                carry_out  = adder_result[DATA_WIDTH];
            end

            3'b001: begin
                // Subtraction: {carry_out, result} = a - b
                // Carry out acts as borrow-out: 1 when a < b, which is inverted adder carry
                result     = adder_result[DATA_WIDTH-1:0];
                carry_out  = ~adder_result[DATA_WIDTH];
            end

            3'b010: begin
                // Bitwise AND
                result     = a & b;
                carry_out  = 1'b0;
            end

            3'b011: begin
                // Bitwise OR
                result     = a | b;
                carry_out  = 1'b0;
            end

            3'b100: begin
                // Bitwise XOR
                result     = a ^ b;
                carry_out  = 1'b0;
            end

            3'b101: begin
                // Shift Left
                result     = a << b[3:0];
                carry_out  = 1'b0;
            end

            3'b110: begin
                // Shift Right
                result     = a >> b[3:0];
                carry_out  = 1'b0;
            end

            3'b111: begin
                // Pass A
                result     = a;
                carry_out  = 1'b0;
            end

            default: begin
                result     = {DATA_WIDTH{1'b0}};
                carry_out  = 1'b0;
            end
        endcase
    end

endmodule
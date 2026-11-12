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

    // Internal extended result for addition and subtraction carry/borrow generation
    reg [DATA_WIDTH:0] ext_result;

    // Zero flag continuous assignment
    assign zero = (result == {DATA_WIDTH{1'b0}});

    // Combinational ALU logic
    always @(*) begin
        // Default assignments to prevent latches and unassigned paths
        result     = {DATA_WIDTH{1'b0}};
        carry_out  = 1'b0;
        ext_result = {DATA_WIDTH+1{1'b0}};

        case (opcode)
            3'b000: begin
                // Addition: {carry_out, result} = a + b
                ext_result = {1'b0, a} + {1'b0, b};
                result     = ext_result[DATA_WIDTH-1:0];
                carry_out  = ext_result[DATA_WIDTH];
            end

            3'b001: begin
                // Subtraction: {carry_out, result} = a - b
                // Note: carry_out acts as borrow-out inverted (standard adder-based sub)
                ext_result = {1'b0, a} - {1'b0, b};
                result     = ext_result[DATA_WIDTH-1:0];
                carry_out  = ext_result[DATA_WIDTH];
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
                // Shift Left (using lower bits of b for shift amount)
                result     = a << b[3:0];
                carry_out  = 1'b0;
            end

            3'b110: begin
                // Shift Right (logical shift using lower bits of b)
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
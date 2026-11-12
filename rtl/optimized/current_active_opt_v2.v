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

    assign zero = (result == {DATA_WIDTH{1'b0}});

    // Arithmetic shared adder operand and carry-in generation
    wire [DATA_WIDTH-1:0] add_sub_b = b ^ {DATA_WIDTH{opcode[0]}};
    wire [DATA_WIDTH:0]   add_sub_result = {1'b0, a} + {1'b0, add_sub_b} + {{(DATA_WIDTH){1'b0}}, opcode[0]};

    always @(*) begin
        // Default assignments to avoid latches and reduce redundant assignments in branches
        result    = {DATA_WIDTH{1'b0}};
        carry_out = 1'b0;

        case (opcode)
            3'b000, 3'b001: begin
                result    = add_sub_result[DATA_WIDTH-1:0];
                carry_out = add_sub_result[DATA_WIDTH];
            end
            3'b010: result = a & b;
            3'b011: result = a | b;
            3'b100: result = a ^ b;
            3'b101: result = a << b[3:0];
            3'b110: result = a >> b[3:0];
            3'b111: result = a;
            default: begin
                result    = {DATA_WIDTH{1'b0}};
                carry_out = 1'b0;
            end
        endcase
    end

endmodule
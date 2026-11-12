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

    wire is_sub = (opcode == 3'b001);
    wire [DATA_WIDTH-1:0] b_mux = is_sub ? ~b : b;
    wire [DATA_WIDTH:0] add_sub = {1'b0, a} + {1'b0, b_mux} + is_sub;

    assign zero = (result == {DATA_WIDTH{1'b0}});

    always @(*) begin
        carry_out = 1'b0;
        case (opcode)
            3'b000: begin
                result    = add_sub[DATA_WIDTH-1:0];
                carry_out = add_sub[DATA_WIDTH];
            end
            3'b001: begin
                result    = add_sub[DATA_WIDTH-1:0];
                carry_out = ~add_sub[DATA_WIDTH];
            end
            3'b010:  result = a & b;
            3'b011:  result = a | b;
            3'b100:  result = a ^ b;
            3'b101:  result = a << b[3:0];
            3'b110:  result = a >> b[3:0];
            3'b111:  result = a;
            default: result = {DATA_WIDTH{1'b0}};
        endcase
    end

endmodule
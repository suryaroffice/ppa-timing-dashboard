// 16-bit registered adder: inputs and output are registered, so the
// timing-critical path is flop -> 16-bit adder -> flop.
module top (
    input         clk,
    input  [15:0] a,
    input  [15:0] b,
    output reg [15:0] sum
);
    reg [15:0] ra, rb;
    always @(posedge clk) begin
        ra  <= a;
        rb  <= b;
        sum <= ra + rb;
    end
endmodule

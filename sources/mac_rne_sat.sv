`timescale 1ns/1ps
module mac_rne_sat (
    input  logic               clk,
    input  logic               rst,       // synchronous, active-high
    input  logic               en,        // accumulate a*b this cycle
    input  logic               clr,       // clear accumulator this cycle
    input  logic               rd,        // request readout snapshot this cycle
    input  logic signed [7:0]  a,
    input  logic signed [7:0]  b,
    output logic signed [15:0] res,       // rounded + saturated snapshot
    output logic               res_valid, // 1-cycle pulse, one cycle after rd
    output logic               ovf        // sticky saturation flag
);

    // --- Accumulator logic ---
    logic signed [27:0] acc;
    logic signed [15:0] p;
    logic signed [27:0] p_ext;

    assign p = a * b;
    assign p_ext = 28'(p);

    // --- Readout Combinational Logic ---
    logic signed [19:0] q;
    logic        [7:0]  r;
    logic               round_up;
    logic signed [20:0] q_rounded; // Extra bit for rounding overflow
    
    // In 2's complement, an arithmetic shift right by 8 exactly matches floor(snapshot/256)
    // Taking the bottom 8 bits unsigned exactly matches snapshot - 256*q.
    assign q = acc[27:8];
    assign r = acc[7:0];

    // Round-half-to-even logic
    always_comb begin
        if (r < 8'd128) begin
            round_up = 1'b0;
        end else if (r > 8'd128) begin
            round_up = 1'b1;
        end else begin
            // Tie-breaker: round to even
            round_up = q[0];
        end
    end

    assign q_rounded = 21'(q) + 21'(round_up);

    // Saturation Logic
    logic signed [15:0] res_next;
    logic               is_sat;

    always_comb begin
        if (q_rounded > 21'sd32767) begin
            res_next = 16'sd32767;
            is_sat   = 1'b1;
        end else if (q_rounded < -21'sd32768) begin
            res_next = -16'sd32768;
            is_sat   = 1'b1;
        end else begin
            res_next = 16'(q_rounded);
            is_sat   = 1'b0;
        end
    end

    // --- Registers ---
    always_ff @(posedge clk) begin
        if (rst) begin
            acc       <= '0;
            res       <= '0;
            res_valid <= 1'b0;
            ovf       <= 1'b0;
        end else begin
            // 1. Accumulator Update
            if (clr) begin
                acc <= en ? p_ext : 28'sd0;
            end else if (en) begin
                acc <= acc + p_ext;
            end

            // 2. Readout Path (res_valid is a 1-cycle pulse)
            res_valid <= rd;
            if (rd) begin
                res <= res_next;
            end

            // 3. Overflow Sticky Flag (Same-cycle priority implementation)
            if (rd && is_sat) begin
                ovf <= 1'b1; // Saturation set wins
            end else if (clr) begin
                ovf <= 1'b0; // Normal clear if no saturation occurred
            end
        end
    end

endmodule

"""
Hidden grading testbench for mac_rne_sat.

Grading contract: an implementation passes iff it matches a cycle-accurate,
independently-computed Python reference model on every cycle for res,
res_valid and ovf -- across directed corner sequences and a fixed-seed
randomized stress run. No magic numbers: all expectations come from MacModel.

Failure-mode map (FM-x tags refer to the difficulty analysis):
  FM-1  round-half-up instead of round-half-to-even        -> directed RNE ties
  FM-2  wrong rounding for negative accumulator values     -> directed negative ties
  FM-3  rounding applied per-accumulation, not at readout  -> directed 3x96 + random phases
  FM-4  clr+en priority wrong (clear wins / en wins)       -> directed clr+en with distinct loads
  FM-5  rd snapshot includes same-cycle en accumulation    -> directed rd+en
  FM-6  rd+clr ordering wrong (snapshot must pre-date clr) -> directed rd+clr
  FM-7  saturate-before-round / dropped rounding carry     -> directed +32767.5 tie
  FM-8  ovf not sticky, or set by non-saturating readouts  -> continuous ovf checks
  FM-9  clr allowed to mask a same-cycle saturating set    -> directed neg-sat + clr+rd
  FM-10 over-eager saturation flag at exact -2^15 boundary -> directed acc = -2^23
  FM-11 res not held between readouts / res_valid too wide -> post-read idle checks
"""

import random
from pathlib import Path

import cocotb
from cocotb.triggers import RisingEdge, FallingEdge, Timer

SEED   = 0xC0FFEE
CLK_NS = 10


def to_signed(v, bits):
    v = int(v)
    return v - (1 << bits) if (v >> (bits - 1)) & 1 else v


class MacModel:
    """Cycle-accurate reference model (independent golden algorithm)."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.acc = 0
        self.res = 0
        self.res_valid = 0
        self.ovf = 0

    def step(self, en, clr, rd, a, b):
        """Advance one clock edge with this cycle's sampled inputs."""
        prod = a * b
        snap = self.acc                    # snapshot BEFORE this cycle's update
        q    = snap >> 8                   # floor division by 256
        rem  = snap & 0xFF                 # non-negative remainder
        round_up = 1 if (rem > 0x80 or (rem == 0x80 and (q & 1))) else 0
        rq   = q + round_up
        sat  = (rq > 32767) or (rq < -32768)
        rres = 32767 if rq > 32767 else (-32768 if rq < -32768 else rq)

        self.res_valid = 1 if rd else 0
        if rd:
            self.res = rres
        self.ovf = (0 if clr else self.ovf) | (1 if (rd and sat) else 0)

        if clr and en:
            self.acc = prod
        elif clr:
            self.acc = 0
        elif en:
            self.acc = self.acc + prod

        assert abs(self.acc) < (1 << 27), \
            "TB bug: stimulus overflowed the accumulator guard band"


async def clock_gen(clk):
    while True:
        clk.value = 0
        await Timer(CLK_NS // 2, "ns")
        clk.value = 1
        await Timer(CLK_NS // 2, "ns")


class Bench:
    def __init__(self, dut):
        self.dut = dut
        self.m = MacModel()
        self.n = 0

    async def reset(self, cycles=3):
        d = self.dut
        d.rst.value = 1
        d.en.value = 0
        d.clr.value = 0
        d.rd.value = 0
        d.a.value = 0
        d.b.value = 0
        for _ in range(cycles):
            await RisingEdge(d.clk)
        await FallingEdge(d.clk)
        d.rst.value = 0
        self.m.reset()

    async def cyc(self, en=0, clr=0, rd=0, a=0, b=0, note=""):
        """Drive one cycle's inputs, step the model, check registered outputs."""
        d = self.dut
        d.en.value = en
        d.clr.value = clr
        d.rd.value = rd
        d.a.value = a & 0xFF
        d.b.value = b & 0xFF
        await RisingEdge(d.clk)
        self.m.step(en, clr, rd, a, b)
        self.n += 1
        await FallingEdge(d.clk)
        got_v = int(d.res_valid.value)
        got_r = to_signed(d.res.value, 16)
        got_o = int(d.ovf.value)
        m, c = self.m, self.n
        assert got_v == m.res_valid, \
            f"[cyc {c}] {note} res_valid mismatch: exp {m.res_valid} got {got_v}"
        assert got_r == m.res, \
            f"[cyc {c}] {note} res mismatch: exp {m.res} got {got_r}"
        assert got_o == m.ovf, \
            f"[cyc {c}] {note} ovf mismatch: exp {m.ovf} got {got_o}"


@cocotb.test()
async def directed_corners(dut):
    """Directed sequences that isolate each specified corner (FM-1 .. FM-11)."""
    cocotb.start_soon(clock_gen(dut.clk))
    b = Bench(dut)
    await b.reset()
    m = b.m

    async def load(a_, b_, note=""):
        # clr+en loads acc with exactly a_*b_ (also exercises FM-4 priority)
        await b.cyc(en=1, clr=1, a=a_, b=b_, note=note)

    async def read(note=""):
        await b.cyc(rd=1, note=note)
        await b.cyc(note=note + " /post")

    # ---- FM-1: positive round-half-to-even ties -------------------------
    await load(64, 10, "RNE 640")
    await read("RNE +2.5 -> 2 (even quotient stays)")
    assert m.res == 2
    await load(64, 14, "RNE 896")
    await read("RNE +3.5 -> 4 (odd quotient bumps)")
    assert m.res == 4

    # ---- FM-2: negative rounding, incl. negative ties -------------------
    await load(-96, 4, "RNE -384")
    await read("RNE -1.5 -> -2 (even quotient stays)")
    assert m.res == -2
    await load(-80, 8, "RNE -640")
    await read("RNE -2.5 -> -2 (odd quotient bumps toward +inf)")
    assert m.res == -2
    await load(-64, 11, "-704")
    await read("-704: floor -3, rem 0x40 < half -> stays -3")
    assert m.res == -3

    # ---- non-tie sanity above/below half --------------------------------
    await load(64, 11, "704")
    await read("+704: rem 0xC0 > half -> rounds up to 3")
    assert m.res == 3
    await load(127, 127, "16129")
    await read("16129: rem 0x01 -> stays 63")
    assert m.res == 63

    # ---- FM-3: rounding must happen at readout only ----------------------
    await b.cyc(clr=1, note="FM-3 clean")
    for k in range(3):
        await b.cyc(en=1, a=32, b=3, note=f"FM-3 acc 96 x{k}")   # 3 x 96 = 288
    await read("3x96=288 -> 1; per-accumulation rounding would give 0")
    assert m.res == 1

    # ---- FM-4: clr+en priority (acc <= product alone) --------------------
    await load(64, 10, "FM-4 preload 640")
    await b.cyc(en=1, clr=1, a=64, b=14, note="FM-4 clr+en -> acc = 896 only")
    await read("clr+en: 4 (clear-wins bug -> 0, en-wins bug -> 6)")
    assert m.res == 4

    # ---- FM-5: rd snapshot excludes same-cycle en ------------------------
    await load(64, 8, "FM-5 preload 512")
    await b.cyc(en=1, rd=1, a=64, b=8, note="FM-5 rd+en snapshot pre-update")
    assert m.res == 2
    await read("FM-5 next readout sees 1024 -> 4")
    assert m.res == 4

    # ---- FM-6: rd+clr (snapshot pre-dates the clear) ----------------------
    await load(64, 12, "FM-6 preload 768")
    await b.cyc(clr=1, rd=1, note="FM-6 rd+clr: res=3, acc cleared after")
    assert m.res == 3
    await read("FM-6 post-clear readout -> 0")
    assert m.res == 0

    # ---- FM-6b: rd+clr+en all together ------------------------------------
    await load(64, 16, "FM-6b preload 1024")
    await b.cyc(en=1, clr=1, rd=1, a=64, b=20,
                note="FM-6b snapshot 1024, acc becomes 1280")
    assert m.res == 4
    await read("FM-6b next readout 1280 -> 5")
    assert m.res == 5

    # ---- FM-7: tie at +32767.5 must round up, then saturate; sets ovf ----
    await load(-128, -128, "FM-7 base 16384")
    for _ in range(510):
        await b.cyc(en=1, a=-128, b=-128, note="FM-7 build")
    await b.cyc(en=1, a=-127, b=-128, note="FM-7 top-off (+16256)")
    # acc = 511*16384 + 16256 = 8388480 = 0x7FFF80 -> q=32767 (odd), tie
    await read("FM-7 +32767.5 tie: round to 32768, saturate to 32767, ovf=1")
    assert m.res == 32767 and m.ovf == 1

    # ---- FM-8: ovf is sticky; only clr clears it --------------------------
    await b.cyc(note="FM-8 sticky hold 1")
    await b.cyc(note="FM-8 sticky hold 2")
    assert m.ovf == 1
    await b.cyc(clr=1, note="FM-8 clr clears ovf")
    await b.cyc(note="FM-8 post-clr")
    assert m.ovf == 0

    # ---- FM-9: saturating readout coincident with clr still sets ovf ------
    for _ in range(520):
        await b.cyc(en=1, a=127, b=-128, note="FM-9 neg-sat build")  # -16256/cy
    # acc = -8453120 -> floor/256 = -33020 -> saturates low
    await b.cyc(clr=1, rd=1, note="FM-9 rd+clr on saturating value")
    assert m.res == -32768 and m.ovf == 1
    await b.cyc(clr=1, note="FM-9 clr")
    await b.cyc(note="FM-9 post")
    assert m.ovf == 0

    # ---- FM-10: exact acc = -2^23 -> res = -32768 with NO saturation ------
    for _ in range(516):
        await b.cyc(en=1, a=127, b=-128, note="FM-10 build")         # -8388096
    await b.cyc(en=1, a=-64, b=8, note="FM-10 top-off (-512)")       # -8388608
    await read("FM-10 acc=-2^23: res=-32768 exactly, ovf must stay 0")
    assert m.res == -32768 and m.ovf == 0

    # ---- FM-11: res holds between readouts; res_valid is one cycle wide ---
    await load(64, 10, "FM-11 preload 640")
    await b.cyc(rd=1, note="FM-11 read")
    for k in range(4):
        await b.cyc(note=f"FM-11 hold {k}: res stays 2, res_valid low")
    assert m.res == 2

    # ---- mid-operation synchronous reset ----------------------------------
    await load(77, 91, "pre-reset garbage")
    await b.reset()
    await b.cyc(rd=1, note="readout after reset -> 0")
    await b.cyc(note="post-reset")
    assert m.res == 0 and m.ovf == 0


@cocotb.test()
async def randomized_lockstep(dut):
    """Fixed-seed random stress. Any semantic divergence (FM-3, FM-4..6
    simultaneity, ovf bookkeeping) accumulates state error and is caught by
    the per-cycle lockstep compare."""
    cocotb.start_soon(clock_gen(dut.clk))
    b = Bench(dut)
    await b.reset()
    rnd = random.Random(SEED)

    # Phase A: mixed traffic with frequent simultaneous control combos.
    for i in range(1500):
        await b.cyc(en=1 if rnd.random() < 0.60 else 0,
                    clr=1 if rnd.random() < 0.06 else 0,
                    rd=1 if rnd.random() < 0.22 else 0,
                    a=rnd.randint(-128, 127),
                    b=rnd.randint(-128, 127),
                    note=f"randA[{i}]")

    # Phase B: long accumulation bursts -> deep state, rare clears.
    await b.cyc(clr=1, note="phaseB clean")
    for i in range(600):
        await b.cyc(en=1 if rnd.random() < 0.95 else 0,
                    clr=1 if rnd.random() < 0.01 else 0,
                    rd=1 if rnd.random() < 0.15 else 0,
                    a=rnd.randint(-128, 127),
                    b=rnd.randint(-128, 127),
                    note=f"randB[{i}]")


def test_mac_rne_sat_runner():
    """pytest entry point: build sources/mac_rne_sat.sv under Icarus and run
    this cocotb module against it."""
    try:
        from cocotb_tools.runner import get_runner   # cocotb >= 2.0
    except ImportError:                              # cocotb 1.9.x fallback
        from cocotb.runner import get_runner
    proj = Path(__file__).resolve().parent.parent
    runner = get_runner("icarus")
    runner.build(
        sources=[proj / "sources" / "mac_rne_sat.sv"],
        hdl_toplevel="mac_rne_sat",
        build_args=["-g2012"],
        build_dir=str(proj / "sim_build"),
        always=True,
    )
    runner.test(
        hdl_toplevel="mac_rne_sat",
        test_module="test_mac_rne_sat",
        test_dir=str(Path(__file__).resolve().parent),
    )

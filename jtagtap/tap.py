from nmigen import *
from nmigen.hdl.rec import *
from nmigen.lib.cdc import MultiReg


__all__ = ["JTAGTap"]


connector_layout = [
    ("tck",  1, DIR_FANIN),
    ("tdi",  1, DIR_FANIN),
    ("tdo",  1, DIR_FANOUT),
    ("tms",  1, DIR_FANIN),
    ("trst", 1, DIR_FANIN) # TODO
]


class _JTAGRegPortLayout(Layout):
    def __init__(self, fields):
        def fanout(fields):
            r = []
            for f in fields:
                if isinstance(f[1], (int, tuple)):
                    r.append((f[0], f[1], DIR_FANOUT))
                else:
                    r.append((f[0], fanout(f[1])))
            return r

        full_fields = [
            ("r", fanout(fields)),
            ("w", fanout(fields)),
            ("update",  1, DIR_FANOUT),
            ("capture", 1, DIR_FANOUT),
            ("reset",   1, DIR_FANOUT)
        ]
        super().__init__(full_fields)


class JTAGTap(Elaboratable):
    def __init__(self, reg_map, ir_width=5, ir_reset=0x01):
        self.port = Record(connector_layout)
        self.regs = {a: Record(_JTAGRegPortLayout(f)) for a, f in reg_map.items()}
        self.ir = Signal(ir_width, reset=ir_reset)
        self.dr = Signal(max(len(port.r) for port in self.regs.values()))

    def elaborate(self, platform):
        m = Module()

        tck = Signal.like(self.port.tck)
        tdi = Signal.like(self.port.tdi)
        tms = Signal.like(self.port.tms)
        m.submodules += [
            MultiReg(self.port.tck, tck),
            MultiReg(self.port.tdi, tdi),
            MultiReg(self.port.tms, tms)
        ]

        latch_tck = Signal()
        tck_rise = Signal()
        tck_fall = Signal()
        tck_low = Signal()
        m.d.sync += [
            latch_tck.eq(tck),
            tck_low.eq(tck_fall)
        ]
        m.d.comb += [
            tck_rise.eq(~latch_tck &  tck),
            tck_fall.eq( latch_tck & ~tck)
        ]

        ntms = Signal()
        ntdi = Signal()
        with m.If(tck_rise):
            m.d.sync += [
                ntms.eq(tms),
                ntdi.eq(tdi)
            ]

        with m.FSM() as fsm:
            with m.State("TEST-LOGIC-RESET"):
                m.d.comb += (port.reset.eq(1) for port in self.regs.values())
                m.d.sync += self.ir.eq(self.ir.reset)
                with m.If(tck_fall):
                    with m.If(ntms):
                        m.next = "TEST-LOGIC-RESET"
                    with m.Else():
                        m.next = "RUN-TEST-IDLE"

            with m.State("RUN-TEST-IDLE"):
                with m.If(tck_fall):
                    with m.If(ntms):
                        m.next = "SELECT-DR-SCAN"

            with m.State("SELECT-DR-SCAN"):
                with m.If(tck_fall):
                    with m.If(ntms):
                        m.next = "SELECT-IR-SCAN"
                    with m.Else():
                        m.next = "CAPTURE-DR"

            with m.State("CAPTURE-DR"):
                with m.Switch(self.ir):
                    for addr, port in self.regs.items():
                        with m.Case(addr):
                            m.d.sync += self.dr.eq(port.r)
                            m.d.comb += port.capture.eq(tck_fall)
                with m.If(tck_fall):
                    with m.If(ntms):
                        m.next = "EXIT1-DR"
                    with m.Else():
                        m.next = "SHIFT-DR"

            with m.State("SHIFT-DR"):
                m.d.comb += self.port.tdo.eq(self.dr[0])
                with m.Switch(self.ir):
                    for addr, port in self.regs.items():
                        with m.Case(addr):
                            with m.If(tck_fall):
                                m.d.sync += self.dr.eq(Cat(self.dr[1:len(port.r)], ntdi))
                with m.If(tck_fall):
                    with m.If(ntms):
                        m.next = "EXIT1-DR"

            with m.State("EXIT1-DR"):
                m.d.comb += self.port.tdo.eq(0)
                with m.If(tck_fall):
                    with m.If(ntms):
                        m.next = "UPDATE-DR"
                    with m.Else():
                        m.next = "PAUSE-DR"

            with m.State("PAUSE-DR"):
                with m.If(tck_fall):
                    with m.If(ntms):
                        m.next = "EXIT2-DR"

            with m.State("EXIT2-DR"):
                with m.If(tck_fall):
                    with m.If(ntms):
                        m.next = "UPDATE-DR"
                    with m.Else():
                        m.next = "SHIFT-DR"

            with m.State("UPDATE-DR"):
                with m.Switch(self.ir):
                    for addr, port in self.regs.items():
                        with m.Case(addr):
                            m.d.sync += port.w.eq(self.dr)
                            m.d.comb += port.update.eq(tck_fall)
                with m.If(tck_fall):
                    with m.If(ntms):
                        m.next = "SELECT-DR-SCAN"
                    with m.Else():
                        m.next = "RUN-TEST-IDLE"

            with m.State("SELECT-IR-SCAN"):
                with m.If(tck_fall):
                    with m.If(ntms):
                        m.next = "TEST-LOGIC-RESET"
                    with m.Else():
                        m.next = "CAPTURE-IR"

            with m.State("CAPTURE-IR"):
                with m.If(tck_fall):
                    with m.If(ntms):
                        m.next = "EXIT1-IR"
                    with m.Else():
                        m.next = "SHIFT-IR"

            with m.State("SHIFT-IR"):
                m.d.comb += self.port.tdo.eq(self.ir[0])
                with m.If(tck_fall):
                    m.d.sync += self.ir.eq(Cat(self.ir[1:], ntdi))
                    with m.If(ntms):
                        m.next = "EXIT1-IR"

            with m.State("EXIT1-IR"):
                m.d.comb += self.port.tdo.eq(0)
                with m.If(tck_fall):
                    with m.If(ntms):
                        m.next = "UPDATE-IR"
                    with m.Else():
                        m.next = "PAUSE-IR"

            with m.State("PAUSE-IR"):
                with m.If(tck_fall):
                    with m.If(ntms):
                        m.next = "EXIT2-IR"

            with m.State("EXIT2-IR"):
                with m.If(tck_fall):
                    with m.If(ntms):
                        m.next = "UPDATE-IR"
                    with m.Else():
                        m.next = "SHIFT-IR"

            with m.State("UPDATE-IR"):
                with m.If(tck_fall):
                    with m.If(ntms):
                        m.next = "SELECT-DR-SCAN"
                    with m.Else():
                        m.next = "RUN-TEST-IDLE"

        return m

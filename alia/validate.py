"""Validate the deterministic pipeline end-to-end on two fixtures:
  (1) RC low-pass filter  -> analytic ground truth for the AC/measure path
  (2) gf180 common-source amp -> real MOS rendering + a real analog gain metric
"""
import math
from ir import Circuit, Device
from render import render_netlist
from sim import run_ngspice, measure_ac
from spec import evaluate

DATA = "/tmp/alia/ac.dat"


def rc_lowpass():
    # R=1k, C=1.5915uF  -> f_3dB = 1/(2*pi*R*C) = 100 Hz
    ckt = Circuit(name="RC low-pass (analytic check)", devices=[
        Device("Vin", "vsource", ["in", "0"], {"dc": 0, "ac": 1}),
        Device("R1", "res", ["in", "out"], {"value": "1k"}),
        Device("C1", "cap", ["out", "0"], {"value": "1.5915u"}),
    ])
    tb = {"analysis": "ac", "sweep": "dec", "points": 40,
          "fstart": 1, "fstop": "100k", "out": "out", "datafile": DATA}
    return ckt, tb, 1.0 / (2 * math.pi * 1e3 * 1.5915e-6)


def cs_amp():
    # gf180 common-source amp, gate biased at 0.9 V, 20k load
    ckt = Circuit(name="gf180 common-source amp", devices=[
        Device("Vdd", "vsource", ["vdd", "0"], {"dc": 3.3}),
        Device("Vin", "vsource", ["in", "0"], {"dc": 0.9, "ac": 1}),
        Device("RD", "res", ["vdd", "out"], {"value": "20k"}),
        Device("M1", "nmos", ["out", "in", "0", "0"],
               {"W": "10u", "L": "0.5u", "nf": 1, "m": 1}),
    ])
    tb = {"analysis": "ac", "sweep": "dec", "points": 30,
          "fstart": 1, "fstop": "1G", "out": "out", "datafile": DATA}
    return ckt, tb


def show(title, deck, res, meas):
    print("=" * 70)
    print(title)
    print("-" * 70)
    print(deck)
    print("-- ngspice returncode:", res["returncode"])
    if res["returncode"] != 0:
        print("STDERR tail:", res["stderr"][-400:])
    print("-- measured:", meas)


# (1) RC low-pass
ckt, tb, f3_analytic = rc_lowpass()
deck = render_netlist(ckt, tb)
res = run_ngspice(deck)
meas = measure_ac(DATA)
show("FIXTURE 1: RC low-pass", deck, res, meas)
print(f"-- analytic f_3dB = {f3_analytic:.2f} Hz ; measured = {meas.get('f_3db_hz')}")
ok, r = evaluate(meas, {"f_3db_hz": ("~", f3_analytic)})
print("-- spec (f_3dB within 5%):", "PASS" if ok else "FAIL", r["f_3db_hz"])

# (2) gf180 common-source amp
ckt, tb = cs_amp()
deck = render_netlist(ckt, tb)
res = run_ngspice(deck)
meas = measure_ac(DATA)
show("FIXTURE 2: gf180 common-source amp", deck, res, meas)
ok, r = evaluate(meas, {"dc_gain_db": (">=", 10.0)})
print("-- spec (DC gain >= 10 dB):", "PASS" if ok else "FAIL", r["dc_gain_db"])

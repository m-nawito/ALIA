"""Two-stage Miller OTA fixture — validates the ALIA measurement chain on a
two-stage topology (phase convention, PM at unity crossing, supply current).

Topology (all gf180 3.3V devices, harness interface inp/inn/out/vdd/nbias/0):
  Stage 1: NMOS diff pair M1 (inp), M2 (inn); PMOS mirror M3/M4 with the
           DIODE side on M2's drain -> stage-1 output x at M1's drain
           (inverting w.r.t. inp), NMOS tail M5 from nbias.
  Stage 2: PMOS common-source M6 (gate x), NMOS sink M7 (gate nbias) -> out.
           Two inversions -> overall NON-inverting w.r.t. inp (DC phase ~0),
           same convention the 5T episodes satisfied.
  Comp:    Cc from x to out (+ optional Rz).
"""
import sys, os, json, copy
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "alia"))
from ir import Circuit, Device
from render import render_netlist
from sim import run_ngspice, measure_ac, measure_op_current

VDD, CL, VICM = 3.3, "5p", 1.65

def core(W1, L1, W34, L34, W5, L5, W6, L6, W7, L7, Cc, Rz=None):
    devs = [
        Device("M1", "nmos", ["x",  "inp", "ntail", "0"],   {"W": W1,  "L": L1}),
        Device("M2", "nmos", ["y",  "inn", "ntail", "0"],   {"W": W1,  "L": L1}),
        Device("M3", "pmos", ["x",  "y",   "vdd",  "vdd"],  {"W": W34, "L": L34}),
        Device("M4", "pmos", ["y",  "y",   "vdd",  "vdd"],  {"W": W34, "L": L34}),
        Device("M5", "nmos", ["ntail", "nbias", "0", "0"],  {"W": W5,  "L": L5}),
        Device("M6", "pmos", ["out", "x",  "vdd",  "vdd"],  {"W": W6,  "L": L6}),
        Device("M7", "nmos", ["out", "nbias", "0", "0"],    {"W": W7,  "L": L7}),
    ]
    if Rz:
        devs += [Device("Rz", "res", ["x", "zc"], {"value": Rz}),
                 Device("Cc", "cap", ["zc", "out"], {"value": Cc})]
    else:
        devs += [Device("Cc", "cap", ["x", "out"], {"value": Cc})]
    return Circuit("two-stage-miller-ota", devs)

def harness(c, vbias):
    full = Circuit.from_dict(copy.deepcopy(c.to_dict()))
    full.devices += [
        Device("Vdd", "vsource", ["vdd", "0"], {"dc": VDD}),
        Device("Vinp", "vsource", ["inp", "0"], {"dc": VICM, "ac": 0.5}),
        Device("Vinn", "vsource", ["inn", "0"], {"dc": VICM, "ac": -0.5}),
        Device("Vb", "vsource", ["nbias", "0"], {"dc": vbias}),
        Device("CL", "cap", ["out", "0"], {"value": CL}),
    ]
    return full

def run(tag, ckt, vbias):
    wd = f"/tmp/fx2/{tag}"
    os.makedirs(wd, exist_ok=True)
    tb = {"analysis": "acop", "sweep": "dec", "points": 30, "fstart": 1,
          "fstop": "10G", "out": "out",
          "datafile": f"{wd}/ac.dat", "opfile": f"{wd}/op.dat"}
    deck = render_netlist(harness(ckt, vbias), tb)
    res = run_ngspice(deck, workdir=wd)
    if res["returncode"] != 0:
        return {"tag": tag, "error": (res["stderr"] or res["stdout"])[-400:]}
    m = dict(measure_ac(tb["datafile"])); m.update(measure_op_current(tb["opfile"]))
    m["tag"] = tag
    return m

if __name__ == "__main__":
    trials = [
        # (tag, params..., Cc, Rz, vbias)
        ("A", dict(W1="20u", L1="1u", W34="10u", L34="1u", W5="16u", L5="1u",
                   W6="60u", L6="0.5u", W7="40u", L7="1u", Cc="1p"), 0.75),
        ("B", dict(W1="30u", L1="1u", W34="12u", L34="1u", W5="20u", L5="1u",
                   W6="100u", L6="0.5u", W7="60u", L7="1u", Cc="1.5p", Rz="1k"), 0.75),
    ]
    for tag, p, vb in trials:
        print(json.dumps(run(tag, core(**p), vb)))

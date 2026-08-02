"""Demonstrate Pillar 1 (deterministic repair) and Pillar 3 (SPICE-adjudicated
reasoning audit)."""
from ir import Circuit, Device
from render import render_netlist
from sim import run_ngspice, measure_ac
from lint import lint_and_repair
from audit import audit_causal_claim

DATA = "/tmp/alia/ac.dat"
TB_AC = {"analysis": "ac", "sweep": "dec", "points": 30,
         "fstart": 1, "fstop": "1G", "out": "out", "datafile": DATA}

print("=" * 70)
print("PILLAR 1 — deterministic repair of a broken IR")
print("=" * 70)
# Broken CS amp: M1 missing bulk (3 nodes) AND missing W; plus an unknown device.
broken = Circuit(name="broken CS amp", devices=[
    Device("Vdd", "vsource", ["vdd", "0"], {"dc": 3.3}),
    Device("Vin", "vsource", ["in", "0"], {"dc": 0.9, "ac": 1}),
    Device("RD", "res", ["vdd", "out"], {"value": "20k"}),
    Device("M1", "nmos", ["out", "in", "0"], {"L": "0.5u"}),   # no bulk, no W
    Device("Zjunk", "widget", ["a", "b"], {}),                 # unknown kind
])
repaired, actions, fatal = lint_and_repair(broken)
for a in actions:
    print(f"  [{a['severity']:5}] {a['rule']:16} {a['target']:6} "
          f"{'FIXED' if a['fixed'] else 'FLAG '} : {a['detail']}")
print("  fatal:", fatal)
res = run_ngspice(render_netlist(repaired, TB_AC))
meas = measure_ac(DATA)
print("  after repair -> ngspice rc:", res["returncode"],
      "| DC gain:", meas.get("dc_gain_db"), "dB  (repaired circuit simulates)")

print()
print("=" * 70)
print("PILLAR 3 — SPICE adjudicates the model's reasoning")
print("=" * 70)
good = Circuit(name="CS amp", devices=[
    Device("Vdd", "vsource", ["vdd", "0"], {"dc": 3.3}),
    Device("Vin", "vsource", ["in", "0"], {"dc": 0.9, "ac": 1}),
    Device("RD", "res", ["vdd", "out"], {"value": "20k"}),
    Device("M1", "nmos", ["out", "in", "0", "0"], {"W": "10u", "L": "0.5u"}),
])
# A physically SOUND claim (evidence-driven reasoning)
sound = audit_causal_claim(good, TB_AC, {
    "device": "RD", "param": "value", "new_value": "40k",
    "metric": "dc_gain_db", "predicted": "increase"})
print("  claim: 'raising R_D 20k->40k INCREASES DC gain'")
print("   ->", sound)
# A physically WRONG claim (rationalisation) — same change, wrong prediction
wrong = audit_causal_claim(good, TB_AC, {
    "device": "RD", "param": "value", "new_value": "40k",
    "metric": "dc_gain_db", "predicted": "decrease"})
print("  claim: 'raising R_D 20k->40k DECREASES DC gain'")
print("   ->", wrong)

"""Simulator-grounded reasoning-validity audit (Pillar 3).

The novel contribution: when the model states a causal design claim ("increasing
R_D will raise the DC gain"), re-simulate and let SPICE adjudicate. This
separates genuine evidence-driven reasoning (claim confirmed by physics) from
post-hoc rationalisation or lucky guessing (claim refuted / irrelevant). SPICE,
not the model and not us, is the referee.
"""
import copy
from ir import Circuit
from render import render_netlist
from sim import run_ngspice, measure_ac


def audit_causal_claim(ckt: Circuit, tb: dict, claim: dict, rel_tol: float = 0.02):
    """claim = {device, param, new_value, metric, predicted: increase|decrease}.
    Measures `metric` before vs after applying the stated change and returns a
    verdict: confirmed | refuted | negligible | unmeasurable."""
    run_ngspice(render_netlist(ckt, tb))
    before = measure_ac(tb["datafile"]).get(claim["metric"])

    c2 = Circuit.from_dict(copy.deepcopy(ckt.to_dict()))
    for d in c2.devices:
        if d.id == claim["device"] or "X" + d.id == claim["device"]:
            d.params[claim["param"]] = claim["new_value"]
    run_ngspice(render_netlist(c2, tb))
    after = measure_ac(tb["datafile"]).get(claim["metric"])

    if before is None or after is None:
        return {"verdict": "unmeasurable", "before": before, "after": after}

    delta = after - before
    if abs(delta) <= rel_tol * abs(before):
        observed = "negligible"
    else:
        observed = "increase" if delta > 0 else "decrease"
    if observed == "negligible":
        verdict = "negligible"
    else:
        verdict = "confirmed" if observed == claim["predicted"] else "refuted"
    return {"verdict": verdict, "metric": claim["metric"],
            "before": round(before, 3), "after": round(after, 3),
            "predicted": claim["predicted"], "observed": observed}

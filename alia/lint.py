"""Deterministic IR lint + repair (Pillar 1, IR side).

Targets the structural / Tier-3 failure classes catalogued in the ETECOM
baseline, but at the IR level (where fixes are deterministic and safe). Every
action is recorded {rule, severity, target, detail, fixed} so repairs can be
counted and categorised — this log is itself data for the tier-recoverability
analysis (which classes does deterministic repair recover?).
"""
import copy
from ir import Circuit

ARITY = {"nmos": 4, "pmos": 4, "res": 2, "cap": 2, "ind": 2,
         "vsource": 2, "isource": 2}
REQUIRED = {"nmos": ["W", "L"], "pmos": ["W", "L"], "res": ["value"],
            "cap": ["value"]}
DEFAULTS = {"nmos": {"W": "10u", "L": "0.5u"}, "pmos": {"W": "10u", "L": "0.5u"},
            "res": {"value": "1k"}, "cap": {"value": "1p"}}


def lint_and_repair(ckt: Circuit):
    """Return (repaired_circuit, actions, fatal)."""
    c = Circuit.from_dict(copy.deepcopy(ckt.to_dict()))
    actions = []

    def act(rule, sev, tgt, detail, fixed):
        actions.append({"rule": rule, "severity": sev, "target": tgt,
                        "detail": detail, "fixed": fixed})

    kept = []
    for d in c.devices:
        k = d.kind.lower()
        if k not in ARITY:
            act("unknown_kind", "fatal", d.id, f"kind={d.kind} (dropped)", False)
            continue
        # MOS missing bulk -> PDK-manufacturable deterministic default:
        # NMOS bulk = substrate (node 0); PMOS bulk = source (own n-well).
        # (gf180mcu nfet_03v3 sits in the common p-substrate: bulk IS VSS;
        #  bulk-to-source on an NMOS whose source floats above ground would be
        #  unmanufacturable without a deep-n-well variant and removes body effect.)
        if k in ("nmos", "pmos") and len(d.nodes) == 3:
            if k == "nmos":
                d.nodes = d.nodes + ["0"]
                act("mos_missing_bulk", "tier3", d.id,
                    "tied bulk to VSS (substrate)", True)
            else:
                d.nodes = d.nodes + [d.nodes[2]]
                act("mos_missing_bulk", "tier3", d.id,
                    "tied bulk to source (own n-well)", True)
        if len(d.nodes) != ARITY[k]:
            act("arity_mismatch", "fatal", d.id,
                f"{len(d.nodes)} nodes, need {ARITY[k]}", False)
            continue
        if any(n is None or str(n).strip() == "" for n in d.nodes):
            act("empty_node", "fatal", d.id, f"nodes={d.nodes}", False)
            continue
        # Missing REQUIRED parameter = tier-3 completeness fault: the netlist is
        # unrunnable without it. The default is a syntactic placeholder that the
        # loop subsequently sizes — not a sizing decision by the repair layer.
        for pr in REQUIRED.get(k, []):
            if pr not in d.params or d.params[pr] in (None, ""):
                d.params[pr] = DEFAULTS[k][pr]
                act("missing_param", "tier3", d.id,
                    f"defaulted {pr}={DEFAULTS[k][pr]} (completeness placeholder)", True)
        kept.append(d)
    c.devices = kept

    # connectivity checks
    pins = {}
    for d in c.devices:
        for n in d.nodes:
            pins[n] = pins.get(n, 0) + 1
    if "0" not in pins:
        act("no_ground", "fatal", "circuit", "no node '0' present", False)
    for net, cnt in pins.items():
        if net != "0" and cnt < 2:
            act("floating_net", "tier2", net, f"net on {cnt} pin only", False)

    fatal = any(a["severity"] == "fatal" for a in actions)
    return c, actions, fatal

"""Deterministic IR -> ngspice deck renderer for gf180mcu."""
from ir import Circuit, Device
import pdk

_LEAD = {"res": "R", "cap": "C", "ind": "L", "vsource": "V", "isource": "I"}


def _name(d: Device) -> str:
    """Ensure the instance name carries the correct ngspice leading letter."""
    if d.kind in ("nmos", "pmos"):
        return d.id if d.id[:1].upper() == "X" else "X" + d.id
    lead = _LEAD[d.kind]
    return d.id if d.id[:1].upper() == lead else lead + d.id


def render_device(d: Device) -> str:
    k = d.kind.lower()
    p = d.params
    if k in ("nmos", "pmos"):
        dr, g, s, b = d.nodes
        return (f"{_name(d)} {dr} {g} {s} {b} {pdk.MODEL[k]} "
                f"W={p.get('W', '10u')} L={p.get('L', '0.5u')} "
                f"nf={p.get('nf', 1)} m={p.get('m', 1)}")
    if k == "res":
        return f"{_name(d)} {d.nodes[0]} {d.nodes[1]} {p.get('value', '1k')}"
    if k == "cap":
        return f"{_name(d)} {d.nodes[0]} {d.nodes[1]} {p.get('value', '1p')}"
    if k == "vsource":
        spec = []
        if "dc" in p:
            spec.append(f"DC {p['dc']}")
        if "ac" in p:
            spec.append(f"AC {p['ac']}")
        return f"{_name(d)} {d.nodes[0]} {d.nodes[1]} {' '.join(spec) or 'DC 0'}"
    if k == "isource":
        return f"{_name(d)} {d.nodes[0]} {d.nodes[1]} DC {p.get('dc', 0)}"
    raise ValueError(f"unknown device kind: {d.kind}")


def testbench_block(tb: dict) -> str:
    """tb keys: analysis (ac|op|tran), out, datafile, + analysis params."""
    c = [".control", "set filetype=ascii"]
    a = tb["analysis"]
    if a == "ac":
        c.append(f"ac {tb.get('sweep','dec')} {tb.get('points',20)} "
                 f"{tb['fstart']} {tb['fstop']}")
        c.append(f"wrdata {tb['datafile']} vr({tb['out']}) vi({tb['out']})")
    elif a == "op":
        nodes = " ".join(f"v({n})" for n in tb.get("nodes", []))
        c.append("op")
        c.append(f"wrdata {tb['datafile']} {nodes}")
    elif a == "acop":
        # operating point (supply-current budget) + AC in one run
        c.append("op")
        c.append(f"wrdata {tb['opfile']} {tb.get('branch', 'vdd#branch')}")
        c.append(f"ac {tb.get('sweep','dec')} {tb.get('points',20)} "
                 f"{tb['fstart']} {tb['fstop']}")
        c.append(f"wrdata {tb['datafile']} vr({tb['out']}) vi({tb['out']})")
    elif a == "tran":
        c.append(f"tran {tb['tstep']} {tb['tstop']}")
        c.append(f"wrdata {tb['datafile']} v({tb['out']})")
    else:
        raise ValueError(f"unknown analysis: {a}")
    c += ["quit", ".endc"]
    return "\n".join(c)


def render_device_as_emitted(d: Device) -> str:
    """−repair ablation renderer: emit ONLY what the model provided.

    No parameter defaults (absent MOS W/L fall to the PDK subckt defaults
    inside ngspice), no arity fixes (a 3-node MOS reaches ngspice and fails
    there, verbatim). Unknown device kinds are unrenderable and raise — the
    harness surfaces that as an in-protocol verbatim error.
    """
    k = d.kind.lower()
    if k in ("nmos", "pmos"):
        parts = [_name(d)] + [str(n) for n in d.nodes] + [pdk.MODEL[k]]
        parts += [f"{key}={d.params[key]}" for key in ("W", "L", "nf", "m")
                  if d.params.get(key) not in (None, "")]
        return " ".join(parts)
    if k in ("res", "cap", "ind"):
        parts = [_name(d)] + [str(n) for n in d.nodes]
        if d.params.get("value") not in (None, ""):
            parts.append(str(d.params["value"]))
        return " ".join(parts)
    if k in ("vsource", "isource"):
        return render_device(d)          # harness-owned kinds, never model-emitted
    raise ValueError(f"unrenderable device kind: {d.kind} (id={d.id})")


def render_netlist(ckt: Circuit, tb: dict, corner: str = pdk.DEFAULT_CORNER,
                   as_emitted: bool = False) -> str:
    rd = render_device_as_emitted if as_emitted else render_device
    lines = [f"* {ckt.name}", pdk.include_lines(corner)]
    for k, v in ckt.params.items():
        lines.append(f".param {k}={v}")
    lines += [rd(d) for d in ckt.devices]
    lines.append(testbench_block(tb))
    lines.append(".end")
    return "\n".join(lines)

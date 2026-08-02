"""ALIA Phase-2 episode runner — deterministic orchestration core.

Owns ALL episode state on disk (episodes/). Builds every reasoner packet by
deterministic template-fill (the orchestrating agent invokes; it never
composes). Hash-echo contract proves packet fidelity. Audit verdicts are
WITHHELD from packets (the audit observes; it does not teach).

CLI:
  init [--episodes N] [--seed-ep k]   create episode dirs + state
  next                                emit next pending turn {episode, iter, prompt_file, sha}
                                      (idempotent: re-verifies byte-identical packet on resume)
  ingest --episode E --iter K --response FILE [--tokens N] [--model S]
  fake-turn                           built-in deterministic responder (pipeline dry-run)
  status
"""
import argparse, copy, hashlib, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ir import Circuit, Device                    # noqa: E402
from lint import lint_and_repair                  # noqa: E402
from render import render_netlist                 # noqa: E402
from sim import run_ngspice, measure_ac, measure_op_current  # noqa: E402
from spec import evaluate                         # noqa: E402

ROOT = os.path.dirname(HERE)
EPD = os.path.join(ROOT, "episodes")
MASTER = os.path.join(EPD, "episodes.jsonl")

# ---- SPEC FROZEN 2026-07-31 (author decision; exactly as pilot-validated) ----
SPEC = {"dc_gain_db": (">=", 40.0), "phase_margin_deg": (">=", 60.0),
        "gbw_hz": (">=", 20e6), "itail_ua": ("<=", 100.0)}
K_BUDGET = 7
# Phase-3 arms (2026-07-31): identical fixed template everywhere; arms differ
# ONLY in pipeline/feedback mechanics. k_budget per arm; oneshot = budget 0.
ARMS = ("full", "norepair", "passfail", "oneshot")
ARM_K = {"full": K_BUDGET, "norepair": K_BUDGET, "passfail": K_BUDGET,
         "oneshot": 0}
VDD, CL, VICM = 3.3, "5p", 1.65
METRICS = ["dc_gain_db", "gbw_hz", "phase_margin_deg", "itail_ua"]

TEMPLATE = """=== ALIA DESIGN TURN — FIXED TEMPLATE v1-pilot ===
ECHO CONTRACT: the first key of your JSON reply MUST be "echo": "{sha}"

[ROLE]
You are the design reasoner inside a closed-loop analog design harness. This
turn is stateless: everything you know about this episode is in this packet.
Do not use any tools of any kind; do not browse, execute, or read files.
Reply with EXACTLY ONE JSON object and no other text.

[TASK]
Design a five-transistor OTA (differential pair M1/M2, PMOS mirror load M3/M4
diode side on M1's drain, NMOS tail source M5) on GF180MCU 3.3 V devices.
Specification (all must pass):
  dc_gain_db        >= 40.0        (differential DC gain, dB)
  phase_margin_deg  >= 60.0
  gbw_hz            >= 20e6        (unity-gain bandwidth, Hz)
  itail_ua          <= 100.0       (total supply current, uA — power budget)

[FIXED TESTBENCH — supplied by the harness, do NOT emit these]
  VDD = 3.3 V rail node "vdd"; ground node "0".
  Differential drive: v(inp) = {vicm} V DC + 0.5 AC, v(inn) = {vicm} V DC - 0.5 AC.
  Load C_L = {cl} at node "out". Bias rail: node "nbias" driven by an ideal
  source whose DC value you choose via "vbias".

[WHAT YOU EMIT — IR schema]
JSON circuit with devices only for the OTA core (M1..M5). Node-order
conventions: nmos/pmos = [drain, gate, source, bulk]; use node names
inp, inn, out, vdd, nbias, 0, plus any internal nodes you need.
Params: W, L (strings like "10u", "0.5u"), optional nf, m.
Bulk convention on this PDK: NMOS bulk -> "0"; PMOS bulk -> its source or "vdd".
Device kinds: "nmos", "pmos" (models nfet_03v3 / pfet_03v3 are applied by the
renderer). Do not emit sources, the load, or simulation directives.

[REPLY FORMAT — one JSON object, first key echo]
{{
  "echo": "{sha}",
  "circuit": {{"name": "5t-ota", "devices": [
      {{"id": "M1", "kind": "nmos", "nodes": ["n1", "inp", "ntail", "0"],
        "params": {{"W": "…", "L": "…"}}}}, …
  ]}},
  "vbias": <number, volts>,
  "claim": {{"device": "<id; comma-list for matched pairs, e.g. \\"M1,M2\\"; or VB>",
             "param": "<W|L|value|dc>",
             "new_value": "<the value you set this turn>",
             "metric": "<one of dc_gain_db|gbw_hz|phase_margin_deg|itail_ua>",
             "predicted": "<increase|decrease>"}},
  "rationale": "<= 50 words"
}}
"claim" is REQUIRED on every revision turn (state the single causal claim
behind your main change, relative to the previous design) and MUST be omitted
on the initial turn. The claim is audited against the simulator.

[EPISODE TRACE — full history, oldest first; the harness reconstructs this
from disk every turn; there is no hidden state]
{trace}
"""


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def _mlog(rec):
    os.makedirs(EPD, exist_ok=True)
    with open(MASTER, "a") as f:
        f.write(json.dumps({"t": time.time(), **rec}, default=str) + "\n")


def _spath(ep):
    return os.path.join(EPD, ep, "state.json")


def _load(ep):
    with open(_spath(ep)) as f:
        return json.load(f)


def _save(ep, st):
    with open(_spath(ep), "w") as f:
        json.dump(st, f, indent=1, default=str)


def _trace_text(st) -> str:
    # BLINDED seeding (2026-07-31, round-3b adoption + author decision):
    # seeded-fault injections are NEVER disclosed in packets. They remain
    # logged in state/master (seeded_faults) and are disclosed to the READER.
    arm = st.get("arm", "full")
    if not st["iters"]:
        return "none yet — produce your initial design (omit \"claim\")."
    out = []
    for it in st["iters"]:
        e = [f"--- iteration {it['k']} ---"]
        e.append("emitted: " + json.dumps(it["circuit_emitted"], separators=(",", ":"))
                 + f' | vbias={it["vbias"]}')
        if it["repair_actions"]:
            e.append("repair: " + "; ".join(
                f"[{a['severity']}] {a['rule']} {a['target']}: {a['detail']}"
                for a in it["repair_actions"]))
        if it.get("parse_error"):
            e.append("your reply did not parse as a single JSON object — "
                     "error (verbatim): " + str(it["parse_error"])
                     + " — re-emit the FULL reply, one JSON object, no other text.")
        if it.get("fatal"):
            e.append("FATAL faults present — iteration invalid, no measurement.")
        if it.get("sim_error"):
            e.append("simulator error (verbatim): " + it["sim_error"][:500])
        if it.get("measured"):
            m = it["measured"]
            if arm == "passfail":
                # ablation: numeric feedback replaced by per-metric pass/fail
                e.append("spec: " + ", ".join(
                    f"{k}:{v[0]}" for k, v in it["eval"].items()))
            else:
                e.append("measured: " + ", ".join(
                    f"{k}={m.get(k)}" for k in METRICS))
                e.append("spec: " + ", ".join(
                    f"{k}:{v[0]} (got {v[1]}, need {SPEC[k][0]}{SPEC[k][1]})"
                    for k, v in it["eval"].items()))
        out.append("\n".join(e))
    out.append(f"--- now produce iteration {len(st['iters'])} (revision; include \"claim\") ---")
    return "\n".join(out)


def build_packet(ep) -> tuple:
    st = _load(ep)
    body = TEMPLATE.format(sha="{SHA}", vicm=VICM, cl=CL, trace=_trace_text(st))
    # echo hash covers everything below the contract line, with SHA slot blanked
    below = body.split("\n", 2)[2]
    sha = _sha(below)
    return body.replace("{SHA}", sha), sha, st


def _tb(ep, tag):
    wd = os.path.join(EPD, ep, "sim")
    os.makedirs(wd, exist_ok=True)
    return {"analysis": "acop", "sweep": "dec", "points": 30, "fstart": 1,
            "fstop": "10G", "out": "out",
            "datafile": os.path.join(wd, f"{tag}_ac.dat"),
            "opfile": os.path.join(wd, f"{tag}_op.dat")}, wd


def _harness_circuit(core: Circuit, vbias: float) -> Circuit:
    c = Circuit.from_dict(copy.deepcopy(core.to_dict()))
    c.devices += [
        Device("Vdd", "vsource", ["vdd", "0"], {"dc": VDD}),
        Device("Vinp", "vsource", ["inp", "0"], {"dc": VICM, "ac": 0.5}),
        Device("Vinn", "vsource", ["inn", "0"], {"dc": VICM, "ac": -0.5}),
        Device("Vb", "vsource", ["nbias", "0"], {"dc": vbias}),
        Device("CL", "cap", ["out", "0"], {"value": CL}),
    ]
    return c


def _simulate_full(ep, full: Circuit, tag: str, as_emitted: bool = False):
    tb, wd = _tb(ep, tag)
    deck = render_netlist(full, tb, as_emitted=as_emitted)
    res = run_ngspice(deck, workdir=wd)
    meas, err = {}, None
    if res["returncode"] == 0:
        meas = dict(measure_ac(tb["datafile"]))
        meas.update(measure_op_current(tb["opfile"]))
    else:
        err = (res["stderr"] or res["stdout"])[-800:]
    return meas, err, deck


def _audit(ep, prev_full: Circuit, claim, as_emitted: bool = False):
    """Re-simulate the claimed edit in isolation on the PREVIOUS (repaired,
    fully assembled) design. Verdicts are logged, never fed back."""
    ok_metrics = set(METRICS)
    if not isinstance(claim, dict) or claim.get("metric") not in ok_metrics \
            or claim.get("predicted") not in ("increase", "decrease"):
        return {"verdict": "unmeasurable", "why": "malformed or out-of-schema claim"}
    before, _err_b, _ = _simulate_full(ep, prev_full, "audit_before",
                                       as_emitted=as_emitted)
    b = before.get(claim["metric"])
    mod = Circuit.from_dict(copy.deepcopy(prev_full.to_dict()))
    # device may be a comma-list for matched pairs ("M1,M2"); VB = bias source
    targets = [t.strip() for t in str(claim.get("device", "")).split(",") if t.strip()]
    targets = ["Vb" if t in ("VB", "Vb") else t for t in targets]
    found = set()
    for d in mod.devices:
        if d.id in targets:
            par = "dc" if d.id == "Vb" else claim.get("param")
            d.params[par] = claim.get("new_value")
            found.add(d.id)
    if found != set(targets) or not targets:
        return {"verdict": "unmeasurable",
                "why": f"claim devices {targets} not all in previous design"}
    after, _err_a, _ = _simulate_full(ep, mod, "audit_after",
                                      as_emitted=as_emitted)
    a = after.get(claim["metric"])
    if b is None or a is None:
        return {"verdict": "unmeasurable", "before": b, "after": a}
    delta = a - b
    if abs(delta) <= 0.02 * max(abs(b), 1e-30):
        verdict = "negligible"
    else:
        observed = "increase" if delta > 0 else "decrease"
        verdict = "confirmed" if observed == claim["predicted"] else "refuted"
    return {"verdict": verdict, "metric": claim["metric"],
            "before": b, "after": a, "predicted": claim["predicted"]}


SEED_NOTE = ["removed bulk node of first nmos (3-node MOS)",
             "deleted required W of second MOS device",
             "injected unknown-kind device Zx"]


def _seed_faults(core: Circuit):
    nmos = [d for d in core.devices if d.kind == "nmos"]
    mos = [d for d in core.devices if d.kind in ("nmos", "pmos")]
    if nmos and len(nmos[0].nodes) == 4:
        nmos[0].nodes = nmos[0].nodes[:3]
    if len(mos) > 1:
        mos[1].params.pop("W", None)
    core.devices.append(Device("Zx", "gizmo", ["a", "b"], {}))
    return core


def cmd_init(a):
    os.makedirs(EPD, exist_ok=True)
    arm = getattr(a, "arm", "full") or "full"
    prefix = getattr(a, "prefix", "ep") or "ep"
    made = []
    for i in range(1, a.episodes + 1):
        ep = f"{prefix}{i:02d}"
        d = os.path.join(EPD, ep)
        if os.path.exists(_spath(ep)):               # never clobber existing state
            continue
        os.makedirs(d, exist_ok=True)
        seeded = bool(getattr(a, "all_seeded", False)) or (i == a.seed_ep)
        st = {"episode": ep, "arm": arm, "seeded": seeded, "status": "pending",
              "spec": {k: list(v) for k, v in SPEC.items()},
              "k_budget": ARM_K[arm],
              "iters": [], "created": time.strftime("%Y-%m-%d %H:%M:%S")}
        _save(ep, st)
        made.append(ep)
        _mlog({"ev": "init", "episode": ep, "arm": arm, "seeded": st["seeded"]})
    print(json.dumps({"ok": True, "created": made, "arm": arm}))


def _pending_eps():
    for ep in sorted(os.listdir(EPD)):
        if not ep.startswith("ep") or not os.path.isdir(os.path.join(EPD, ep)) \
                or not os.path.exists(_spath(ep)):
            continue
        st = _load(ep)
        if st["status"] in ("passed", "exhausted"):
            continue
        yield ep, st


def _emit_packet(ep, st):
    """Build/verify this episode's next packet on disk; return descriptor."""
    k = len(st["iters"])
    packet, sha, _ = build_packet(ep)
    pf = os.path.join(EPD, ep, f"turn{k}_prompt.txt")
    if os.path.exists(pf):                           # resume path: must be identical
        if open(pf).read() != packet:
            return {"error": "resume mismatch", "episode": ep, "iter": k}
        regenerated = "verified-identical"
    else:
        open(pf, "w").write(packet)
        regenerated = "fresh"
    _mlog({"ev": "packet", "episode": ep, "iter": k, "sha": sha,
           "file": pf, "resume": regenerated})
    return {"episode": ep, "iter": k, "prompt_file": pf, "sha": sha,
            "packet_state": regenerated}


def cmd_next(a):
    only = getattr(a, "episode", None)
    for ep, st in _pending_eps():
        if only and ep != only:
            continue
        print(json.dumps(_emit_packet(ep, st)))
        return
    print(json.dumps({"done": True, "msg": "no pending turns"}))


def cmd_next_all(_a):
    outs = [_emit_packet(ep, st) for ep, st in _pending_eps()]
    print(json.dumps({"n": len(outs), "pending": outs}))


def cmd_ingest(a):
    ep, k = a.episode, a.iter
    st = _load(ep)
    assert len(st["iters"]) == k, f"expected iter {len(st['iters'])}, got {k}"
    raw = open(a.response).read()
    packet = open(os.path.join(EPD, ep, f"turn{k}_prompt.txt")).read()
    sha = packet.split('"echo": "')[1].split('"')[0]
    rec = {"k": k, "model": a.model, "tokens": a.tokens,
           "t": time.strftime("%Y-%m-%d %H:%M:%S")}
    try:
        j = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError) as e:
        rec.update({"parse_error": str(e), "fatal": True, "echo_ok": False,
                    "circuit_emitted": None, "vbias": None,
                    "repair_actions": [], "eval": {}, "eval_ok": False})
        st["iters"].append(rec)
        # a reply-contract failure consumes the iteration: budget applies
        st["status"] = ("exhausted" if len(st["iters"]) >= st["k_budget"] + 1
                        else "running")
        _save(ep, st)
        _mlog({"ev": "ingest", "episode": ep, "iter": k, "parse_error": True})
        print(json.dumps({"episode": ep, "iter": k, "parse_error": str(e),
                          "status": st["status"]}))
        return
    rec["echo_ok"] = (j.get("echo") == sha)
    try:
        core = Circuit.from_dict(j["circuit"])
        vbias = float(j.get("vbias", 0.9))
    except Exception as e:          # parseable JSON but reply-schema violation:
        rec.update({"parse_error": f"reply schema violation: {e}",
                    "fatal": True, "circuit_emitted": None, "vbias": None,
                    "repair_actions": [], "eval": {}, "eval_ok": False})
        st["iters"].append(rec)
        st["status"] = ("exhausted" if len(st["iters"]) >= st["k_budget"] + 1
                        else "running")
        _save(ep, st)
        _mlog({"ev": "ingest", "episode": ep, "iter": k, "parse_error": True})
        print(json.dumps({"episode": ep, "iter": k,
                          "parse_error": rec["parse_error"],
                          "status": st["status"]}))
        return
    rec["circuit_emitted"] = j["circuit"]
    rec["vbias"] = vbias
    rec["rationale"] = j.get("rationale", "")
    rec["claim_stated"] = j.get("claim")
    arm = st.get("arm", "full")
    # fault seeding on the seeded episode's first attempt (iteration 0) only.
    # BLINDED: logged here, never surfaced in packets (round-3b adoption).
    if st["seeded"] and k == 0:
        core = _seed_faults(core)
        rec["seeded_faults"] = SEED_NOTE
        rec["circuit_emitted"] = core.to_dict()
    # lint/repair the FULL assembled circuit (core + harness testbench), so
    # interface nets (inp/inn/nbias/vdd) are seen with both sides connected
    full = _harness_circuit(core, vbias)
    if arm == "norepair":
        # ablation: repair disabled. Lint runs OBSERVE-ONLY (statistics channel,
        # stored under lint_observed, never fed back, never applied). The design
        # is rendered AS EMITTED: absent params fall to PDK subckt defaults;
        # structural faults surface as verbatim render/ngspice errors.
        _obs, obs_actions, _obs_fatal = lint_and_repair(full)
        rec["lint_observed"] = obs_actions
        rec["repair_actions"] = []
        rec["fatal"] = False
        try:
            meas, err, _deck = _simulate_full(ep, full, f"iter{k}",
                                              as_emitted=True)
        except Exception as ex:
            meas, err = {}, f"render/simulation failed (verbatim): {ex}"
        rec["measured"], rec["sim_error"] = meas, err
        ok, ev = evaluate(meas, SPEC) if meas else (False, {})
        rec["eval"], rec["eval_ok"] = ev, ok
        repaired = full
    else:
        repaired, actions, fatal = lint_and_repair(full)
        rec["repair_actions"] = actions
        rec["fatal"] = fatal
        if fatal:
            rec["measured"], rec["eval"], rec["eval_ok"] = {}, {}, False
            rec["sim_error"] = "fatal lint faults — not simulated"
        else:
            meas, err, _deck = _simulate_full(ep, repaired, f"iter{k}")
            rec["measured"], rec["sim_error"] = meas, err
            ok, ev = evaluate(meas, SPEC) if meas else (False, {})
            rec["eval"], rec["eval_ok"] = ev, ok
    # audit (revisions only, needs a previous non-fatal design) — WITHHELD from packets
    if k > 0 and j.get("claim") and st["iters"][k - 1].get("circuit_repaired") \
            and not st["iters"][k - 1].get("fatal"):
        prev_full = Circuit.from_dict(st["iters"][k - 1]["circuit_repaired"])
        try:
            rec["audit"] = _audit(ep, prev_full, j["claim"],
                                  as_emitted=(arm == "norepair"))
        except Exception as ex:
            rec["audit"] = {"verdict": "unmeasurable",
                            "why": f"audit simulation failed: {ex}"}
    elif k > 0:
        rec["audit"] = {"verdict": "unmeasurable",
                        "why": "no claim or no prior measurable design"}
    rec["circuit_repaired"] = repaired.to_dict()
    st["iters"].append(rec)
    if rec["eval_ok"]:
        st["status"] = "passed"
    elif len(st["iters"]) >= st["k_budget"] + 1:
        st["status"] = "exhausted"
    else:
        st["status"] = "running"
    _save(ep, st)
    _mlog({"ev": "ingest", "episode": ep, "iter": k, "echo_ok": rec["echo_ok"],
           "fatal": rec["fatal"], "eval_ok": rec["eval_ok"],
           "audit": rec.get("audit", {}).get("verdict"),
           "tokens": a.tokens, "model": a.model})
    if getattr(a, "quiet", False):
        print(json.dumps({"episode": ep, "iter": k, "echo_ok": rec["echo_ok"],
                          "fatal": rec["fatal"], "eval_ok": rec["eval_ok"],
                          "audit": rec.get("audit", {}).get("verdict"),
                          "status": st["status"]}, default=str))
    else:
        print(json.dumps({"episode": ep, "iter": k, "echo_ok": rec["echo_ok"],
                          "repair": [x["rule"] for x in rec["repair_actions"]],
                          "fatal": rec["fatal"],
                          "measured": rec.get("measured"),
                          "eval_ok": rec["eval_ok"],
                          "audit": rec.get("audit"), "status": st["status"]},
                         default=str))


FAKE_STEPS = [
    {"W1": "20u", "L1": "1u", "Wp": "10u", "Lp": "1u", "W5": "16u", "L5": "1u",
     "vb": 0.75},
    {"W1": "60u", "L1": "1.5u", "Wp": "20u", "Lp": "1.5u", "W5": "24u",
     "L5": "1u", "vb": 0.72},
]


def _fake_circuit(s):
    return {"name": "5t-ota", "devices": [
        {"id": "M1", "kind": "nmos", "nodes": ["n1", "inp", "ntail", "0"],
         "params": {"W": s["W1"], "L": s["L1"]}},
        {"id": "M2", "kind": "nmos", "nodes": ["out", "inn", "ntail", "0"],
         "params": {"W": s["W1"], "L": s["L1"]}},
        {"id": "M3", "kind": "pmos", "nodes": ["n1", "n1", "vdd", "vdd"],
         "params": {"W": s["Wp"], "L": s["Lp"]}},
        {"id": "M4", "kind": "pmos", "nodes": ["out", "n1", "vdd", "vdd"],
         "params": {"W": s["Wp"], "L": s["Lp"]}},
        {"id": "M5", "kind": "nmos", "nodes": ["ntail", "nbias", "0", "0"],
         "params": {"W": s["W5"], "L": s["L5"]}},
    ]}


def cmd_fake(a):
    epflag = f" --episode {a.episode}" if getattr(a, "episode", None) else ""
    out = json.loads(os.popen(
        f"python3 {os.path.join(HERE,'runner.py')} next{epflag}").read())
    if out.get("done"):
        print(json.dumps(out))
        return
    ep, k = out["episode"], out["iter"]
    sha = out["sha"]
    s = FAKE_STEPS[min(k, len(FAKE_STEPS) - 1)]
    resp = {"echo": sha, "circuit": _fake_circuit(s), "vbias": s["vb"],
            "rationale": "fake deterministic responder (dry run)"}
    if k > 0:
        resp["claim"] = {"device": "M1,M2", "param": "W", "new_value": s["W1"],
                         "metric": "gbw_hz", "predicted": "increase"}
    rf = os.path.join(EPD, ep, f"turn{k}_response.json")
    open(rf, "w").write(json.dumps(resp))
    os.system(f"python3 {os.path.join(HERE,'runner.py')} ingest --episode {ep} "
              f"--iter {k} --response {rf} --model fake --tokens 0")


def cmd_status(a):
    brief = getattr(a, "brief", False)
    for ep in sorted(os.listdir(EPD)):
        if not ep.startswith("ep") or not os.path.isdir(os.path.join(EPD, ep)) \
                or not os.path.exists(_spath(ep)):
            continue
        st = _load(ep)
        line = (f"{ep} arm={st.get('arm','full')} seeded={st['seeded']} "
                f"status={st['status']} iters={len(st['iters'])}")
        if brief:
            print(line)
            continue
        for it in st["iters"]:
            m = it.get("measured") or {}
            line += (f"\n  k={it['k']} fatal={it.get('fatal')} "
                     f"gain={m.get('dc_gain_db')} gbw={m.get('gbw_hz')} "
                     f"pm={m.get('phase_margin_deg')} itail={m.get('itail_ua')} "
                     f"pass={it.get('eval_ok')} "
                     f"audit={(it.get('audit') or {}).get('verdict')} "
                     f"echo_ok={it.get('echo_ok')} tokens={it.get('tokens')}")
        print(line)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init")
    i.add_argument("--episodes", type=int, default=2)
    i.add_argument("--seed-ep", type=int, default=0)
    i.add_argument("--arm", choices=ARMS, default="full")
    i.add_argument("--prefix", default="ep")
    i.add_argument("--all-seeded", action="store_true")
    n = sub.add_parser("next")
    n.add_argument("--episode", default=None)
    sub.add_parser("next-all")
    g = sub.add_parser("ingest")
    g.add_argument("--episode", required=True)
    g.add_argument("--iter", type=int, required=True)
    g.add_argument("--response", required=True)
    g.add_argument("--tokens", type=int, default=None)
    g.add_argument("--model", default=None)
    g.add_argument("--quiet", action="store_true")
    f = sub.add_parser("fake-turn")
    f.add_argument("--episode", default=None)
    s = sub.add_parser("status")
    s.add_argument("--brief", action="store_true")
    a = ap.parse_args()
    {"init": cmd_init, "next": cmd_next, "next-all": cmd_next_all,
     "ingest": cmd_ingest, "fake-turn": cmd_fake, "status": cmd_status}[a.cmd](a)

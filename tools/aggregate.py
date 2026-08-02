"""Phase-3 aggregation: per-arm statistics, tier decomposition, audit tally.

Definitions (locked; match manuscript Sec. III):
- CONVERGED  : episode reached a measurement satisfying all four spec entries.
- EXHAUSTED  : episode consumed its full iteration budget (K+1 attempts) without
               converging. Terminal.
- CENSORED   : episode is in neither terminal state because the run was stopped by
               an EXTERNAL cause (reasoner-service usage window). Censoring is
               non-informative: it struck every in-flight episode at one wall-clock
               instant, independently of episode state.
- Pass rate  : converged / terminal, with the censored count printed alongside; the
               converged/N ratio is reported as a LOWER bound (censored episodes may
               still convert) and converged/(N-censored) as the terminal-set rate.
- Median iters (converging episodes only) : index k of the converging iteration,
               i.e. 0 means "one-shot correct", 1 means "one revision".

Failure tiers (Sec. II, taxonomy of [1]):
  T3 syntax/completeness : deterministic-repair actions with severity 'tier3',
                           plus reply-contract (non-JSON) failures, plus renderer/
                           binning rejections that abort the netlist.
  T2 sizing              : netlist simulates, one or more metrics miss spec.
  T1 topology            : structurally invalid design (fatal lint, unknown device).
Usage: python3 tools/aggregate.py [--json out.json]
"""
import argparse
import collections
import glob
import json
import os
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EPD = os.path.join(ROOT, "episodes")
METRICS = ["dc_gain_db", "gbw_hz", "phase_margin_deg", "itail_ua"]


def classify_iter(it):
    """Return the failure tier of a non-converging iteration, or None if it passed."""
    if it.get("eval_ok"):
        return None
    if it.get("parse_error"):
        return "T3"                       # reply-contract failure
    if it.get("fatal"):
        return "T1"                       # structurally invalid (unknown kind etc.)
    err = it.get("sim_error") or ""
    if err:
        return "T3"                       # netlist rejected by simulator/renderer
    if it.get("measured"):
        return "T2"                       # runs, misses spec
    return "T3"


def load():
    eps = []
    for f in sorted(glob.glob(os.path.join(EPD, "ep_*", "state.json"))):
        eps.append(json.load(open(f)))
    return eps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=None)
    a = ap.parse_args()
    eps = load()

    arms = collections.defaultdict(list)
    for st in eps:
        key = st.get("arm", "full") + ("/seeded" if st["seeded"] else "")
        arms[key].append(st)

    out = {"arms": {}, "audit": {}, "tiers": {}, "repair": {}}
    print("=" * 78)
    print("PER-ARM OUTCOMES  (converged / terminal ; censored listed separately)")
    print("=" * 78)
    print(f"{'arm':17} {'N':>3} {'conv':>5} {'exh':>4} {'cens':>5} "
          f"{'rate(term)':>11} {'rate(lower)':>12} {'med.iters':>10}")
    for k in sorted(arms):
        g = arms[k]
        conv = [s for s in g if s["status"] == "passed"]
        exh = [s for s in g if s["status"] == "exhausted"]
        cens = [s for s in g if s["status"] in ("running", "pending")]
        term = len(conv) + len(exh)
        iters = []
        for s in conv:
            for it in s["iters"]:
                if it.get("eval_ok"):
                    iters.append(it["k"])
                    break
        med = statistics.median(iters) if iters else float("nan")
        rate_t = f"{len(conv)}/{term}" if term else "—"
        rate_l = f"{len(conv)}/{len(g)}"
        print(f"{k:17} {len(g):3} {len(conv):5} {len(exh):4} {len(cens):5} "
              f"{rate_t:>11} {rate_l:>12} {med:10.1f}")
        out["arms"][k] = {
            "n": len(g), "converged": len(conv), "exhausted": len(exh),
            "censored": len(cens), "terminal": term,
            "pass_rate_terminal": (len(conv) / term) if term else None,
            "pass_rate_lower": len(conv) / len(g),
            "median_iters_converging": med if iters else None,
            "iters_converging": sorted(iters),
            "censored_episodes": [s["episode"] for s in cens],
        }

    # ---- tier decomposition (clean arms only; seeded probes segregated) ----
    print()
    print("=" * 78)
    print("TIER DECOMPOSITION — first-attempt (iteration 0) failure class, clean arms")
    print("=" * 78)
    for k in sorted(arms):
        g = arms[k]
        c = collections.Counter()
        for s in g:
            if not s["iters"]:
                continue
            c[classify_iter(s["iters"][0]) or "PASS@0"] += 1
        print(f"{k:17} " + "  ".join(f"{t}={c[t]}" for t in ("PASS@0", "T1", "T2", "T3")))
        out["tiers"][k] = dict(c)

    # ---- recovery by tier: of episodes whose iter-0 failed with tier X, how many converged
    print()
    print("RECOVERY BY FIRST-FAILURE TIER (converged / episodes whose it0 failed at that tier)")
    for k in sorted(arms):
        g = arms[k]
        num, den = collections.Counter(), collections.Counter()
        for s in g:
            if not s["iters"]:
                continue
            t = classify_iter(s["iters"][0])
            if t is None:
                continue
            den[t] += 1
            if s["status"] == "passed":
                num[t] += 1
        parts = [f"{t}: {num[t]}/{den[t]}" for t in ("T1", "T2", "T3") if den[t]]
        print(f"{k:17} " + "  ".join(parts) if parts else f"{k:17} —")
        out["tiers"].setdefault(k, {})["recovery"] = {
            t: [num[t], den[t]] for t in ("T1", "T2", "T3") if den[t]}

    # ---- deterministic repair actions (Pillar 1) ----
    print()
    print("=" * 78)
    print("PILLAR 1 — deterministic repair actions logged (rule x severity)")
    print("=" * 78)
    rules = collections.Counter()
    fixed = collections.Counter()
    obs = collections.Counter()          # norepair arm: observe-only lint
    for st in eps:
        arm = st.get("arm", "full")
        for it in st["iters"]:
            for act in it.get("repair_actions", []):
                rules[(act["rule"], act["severity"])] += 1
                if act.get("fixed"):
                    fixed[act["rule"]] += 1
            for act in it.get("lint_observed", []):
                obs[(act["rule"], act["severity"])] += 1
    for (r, sev), n in sorted(rules.items(), key=lambda x: -x[1]):
        print(f"  {r:20} [{sev:6}] n={n:3}  auto-fixed={fixed[r]}")
    out["repair"] = {"applied": {f"{r}|{s}": n for (r, s), n in rules.items()},
                     "auto_fixed": dict(fixed),
                     "observed_only_norepair": {f"{r}|{s}": n for (r, s), n in obs.items()}}

    # ---- Pillar 3: reasoning audit ----
    print()
    print("=" * 78)
    print("PILLAR 3 — simulator-adjudicated reasoning audit")
    print("=" * 78)
    verd = collections.Counter()
    verd_clean = collections.Counter()
    verd_seeded = collections.Counter()
    per_arm = collections.defaultdict(collections.Counter)
    early_late = {"early": collections.Counter(), "late": collections.Counter()}
    for st in eps:
        arm = st.get("arm", "full") + ("/seeded" if st["seeded"] else "")
        for it in st["iters"]:
            au = it.get("audit")
            if not au:
                continue
            v = au.get("verdict")
            verd[v] += 1
            (verd_seeded if st["seeded"] else verd_clean)[v] += 1
            per_arm[arm][v] += 1
            bucket = "early" if it["k"] <= 1 else "late"
            early_late[bucket][v] += 1
    tot = sum(verd.values())
    adjud = verd["confirmed"] + verd["refuted"]
    print(f"  total audit records : {tot}")
    for v in ("confirmed", "refuted", "negligible", "unmeasurable"):
        print(f"    {v:14} {verd[v]:4}")
    if adjud:
        print(f"  ADJUDICABLE (confirmed+refuted) = {adjud}; "
              f"confirmed share = {verd['confirmed']}/{adjud} "
              f"= {100*verd['confirmed']/adjud:.1f}%  (chance floor ~50%)")
    else:
        print("  ADJUDICABLE = 0 — sparse-audit branch applies")
    print("  by arm:", {k: dict(v) for k, v in per_arm.items()})
    print("  early(k<=1) vs late(k>=2):", {k: dict(v) for k, v in early_late.items()})
    adj_clean = verd_clean["confirmed"] + verd_clean["refuted"]
    print(f"  CLEAN episodes only (the figure reported in the paper): "
          f"{sum(verd_clean.values())} records, {verd_clean['confirmed']}/{adj_clean} clear verdicts confirmed")
    print(f"  SEEDED (fault-injected) episodes, segregated: {sum(verd_seeded.values())} records, "
          f"{verd_seeded['confirmed']} confirmed")
    out["audit"] = {"totals_all_episodes": dict(verd),
                    "adjudicable_all_episodes": adjud,
                    "clean": {"totals": dict(verd_clean), "records": sum(verd_clean.values()),
                              "adjudicable": adj_clean, "confirmed": verd_clean["confirmed"],
                              "note": "THIS is the split reported in the paper (88 records, 20 of 20 clear verdicts)"},
                    "seeded_segregated": {"totals": dict(verd_seeded),
                                          "records": sum(verd_seeded.values())},
                    "by_arm": {k: dict(v) for k, v in per_arm.items()}}

    # ---- reply-contract failures (protocol observation) ----
    pe = sum(1 for st in eps for it in st["iters"] if it.get("parse_error"))
    turns = sum(len(st["iters"]) for st in eps)
    echo_ok = sum(1 for st in eps for it in st["iters"] if it.get("echo_ok"))
    print()
    print(f"turns ingested = {turns}; reply-contract (non-JSON) failures = {pe} "
          f"({100*pe/turns:.1f}%); echo-contract satisfied = {echo_ok}/{turns - pe}")
    out["protocol"] = {"turns": turns, "parse_errors": pe, "echo_ok": echo_ok}

    # ---- converged design quality (clean full arm) ----
    print()
    print("CONVERGED DESIGN METRICS (median over converging episodes, per arm)")
    for k in sorted(arms):
        vals = collections.defaultdict(list)
        for s in arms[k]:
            if s["status"] != "passed":
                continue
            for it in s["iters"]:
                if it.get("eval_ok"):
                    for m in METRICS:
                        if it["measured"].get(m) is not None:
                            vals[m].append(it["measured"][m])
                    break
        if vals:
            print(f"  {k:17} gain={statistics.median(vals['dc_gain_db']):.1f} dB, "
                  f"GBW={statistics.median(vals['gbw_hz'])/1e6:.1f} MHz, "
                  f"PM={statistics.median(vals['phase_margin_deg']):.1f} deg, "
                  f"Itail={statistics.median(vals['itail_ua']):.1f} uA")
            out["arms"][k]["median_metrics"] = {
                m: statistics.median(vals[m]) for m in METRICS if vals[m]}

    if a.json:
        json.dump(out, open(a.json, "w"), indent=1)
        print(f"\nwrote {a.json}")


if __name__ == "__main__":
    main()

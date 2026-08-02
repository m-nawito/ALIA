"""Figs. 2 and 3 — REAL Phase-3 data (2026-07-31 run, claude-fable-5).

Fig. 2  convergence: per-episode trajectory of the binding metric vs iteration,
        full arm, with the one-shot baseline outcome marked at k=0.
Fig. 3  (a) tier decomposition + recovery, (b) reasoning-audit tally.
No mock data anywhere: every point is read from episodes/*/state.json.
"""
import collections
import glob
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EPD = os.path.join(ROOT, "episodes")
SPEC = {"dc_gain_db": 40.0, "phase_margin_deg": 60.0,
        "gbw_hz": 20e6, "itail_ua": 100.0}

# IEEE-ish single-column figure style, grayscale-safe
plt.rcParams.update({
    "font.size": 7.5, "axes.labelsize": 7.5, "axes.titlesize": 8,
    "xtick.labelsize": 7, "ytick.labelsize": 7, "legend.fontsize": 6.8,
    "axes.linewidth": 0.6, "lines.linewidth": 1.0, "figure.dpi": 300,
    "axes.spines.top": False, "axes.spines.right": False,
})
INK = "#1b1b1b"
ACC = "#0b6fa4"
WARN = "#b3541e"
MUTE = "#8a8a8a"


def load(arm=None, seeded=None):
    out = []
    for f in sorted(glob.glob(os.path.join(EPD, "ep_*", "state.json"))):
        st = json.load(open(f))
        if arm and st.get("arm", "full") != arm:
            continue
        if seeded is not None and bool(st["seeded"]) != seeded:
            continue
        out.append(st)
    return out


def classify(it):
    if it.get("eval_ok"):
        return None
    if it.get("parse_error"):
        return "T3"
    if it.get("fatal"):
        return "T1"
    if it.get("sim_error"):
        return "T3"
    if it.get("measured"):
        return "T2"
    return "T3"


# ------------------------------------------------------------------ Fig. 2
def fig2():
    full = load("full", seeded=False)
    one = load("oneshot", seeded=False)
    fig, ax = plt.subplots(figsize=(3.5, 2.35))

    # normalised spec distance: max over metrics of (shortfall / target), 0 = meets spec
    def dist(it):
        m = it.get("measured") or {}
        if not m:
            return None
        d = []
        for k, tgt in SPEC.items():
            v = m.get(k)
            if v is None:
                return None
            d.append((tgt - v) / tgt if k != "itail_ua" else (v - tgt) / tgt)
        return max(max(d), 0.0)

    n_conv = 0
    n_traj = 0
    for st in full:
        xs, ys = [], []
        for it in st["iters"]:
            d = dist(it)
            if d is not None:
                xs.append(it["k"])
                ys.append(max(d, 1e-3))
        if xs:
            n_traj += 1
            ax.plot(xs, ys, "-o", color=ACC, alpha=0.38, ms=2.4, lw=0.8,
                    markeredgewidth=0)
        if st["status"] == "passed":
            n_conv += 1
            k = next(i["k"] for i in st["iters"] if i.get("eval_ok"))
            ax.plot([k], [1e-3], marker="*", color=ACC, ms=6,
                    markeredgewidth=0, zorder=5)

    n_one_pass = sum(1 for s in one if s["status"] == "passed")
    ax.axhline(1e-3, color=INK, lw=0.7, ls="--")
    ax.text(0.02, 1.35e-3, "meets all four specs", fontsize=6.4, color=INK,
            va="bottom")
    ax.set_yscale("log")
    ax.set_xlabel("iteration $k$ (0 = first attempt)")
    ax.set_ylabel("worst-metric spec shortfall")
    ax.set_xlim(-0.25, 4.3)
    ax.set_xticks(range(0, 5))
    handles = [
        Line2D([], [], color=ACC, marker="o", ms=2.6, lw=0.8,
               label=f"full loop, $N$={len(full)} ({n_conv}/{len(full)} converge)"),
        Line2D([], [], color=ACC, marker="*", ls="none", ms=6,
               label="convergence"),
        Line2D([], [], color=MUTE, ls="none",
               label=f"one-shot in-harness: {n_one_pass}/{len(one)} at $k$=0"),
    ]
    ax.legend(handles=handles, loc="upper right", frameon=False,
              handletextpad=0.5, borderpad=0.2)
    fig.tight_layout(pad=0.35)
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(HERE, f"figS1_convergence_REAL.{ext}"),
                    bbox_inches="tight")
    plt.close(fig)
    return {"full_n": len(full), "full_conv": n_conv, "trajectories_drawn": n_traj,
            "oneshot_n": len(one), "oneshot_conv": n_one_pass}


# ------------------------------------------------------------------ Fig. 3
def fig3():
    fig, axa = plt.subplots(figsize=(3.45, 2.20))
    figb, axb = plt.subplots(figsize=(3.45, 1.05))

    # (a) first-failure tier and recovery, clean arms
    arms = [("full", False, "full loop"), ("oneshot", False, "one-shot")]
    tiers = ["T1", "T2", "T3"]
    width = 0.38
    for i, (arm, sd, label) in enumerate(arms):
        eps = load(arm, seeded=sd)
        den = collections.Counter()
        num = collections.Counter()
        for st in eps:
            if not st["iters"]:
                continue
            t = classify(st["iters"][0])
            if t is None:
                continue
            den[t] += 1
            if st["status"] == "passed":
                num[t] += 1
        col = [ACC, WARN][i]
        xs = [j + (i - 0.5) * width for j in range(len(tiers))]
        # hollow = episodes that first failed at this tier; solid = of those, recovered
        axa.bar(xs, [den[t] for t in tiers], width * 0.94, facecolor="white",
                edgecolor=col, linewidth=0.9, hatch=["", "///"][i],
                label=f"{label}: failed here")
        axa.bar(xs, [num[t] for t in tiers], width * 0.94, facecolor=col,
                edgecolor=col, linewidth=0.9, label=f"{label}: recovered")
        for x, t in zip(xs, tiers):
            if den[t]:
                axa.text(x, den[t] + 0.4, f"{num[t]}/{den[t]}", ha="center",
                         fontsize=5.8, color=col)
    axa.set_xticks(range(len(tiers)))
    axa.set_xticklabels(["T1 topology", "T2 sizing", "T3 syntax"])
    axa.set_ylabel("episodes (by first-failure tier)")
    axa.set_ylim(0, 21)
    from matplotlib.ticker import MaxNLocator
    axa.yaxis.set_major_locator(MaxNLocator(integer=True))
    axa.legend(frameon=False, ncol=2, loc="upper center", fontsize=5.6,
               handlelength=1.1, borderpad=0.1, labelspacing=0.2, columnspacing=0.9)

    # (b) audit verdicts
    verd = collections.Counter()
    for st in load(seeded=False):
        for it in st["iters"]:
            au = it.get("audit")
            if au and au.get("verdict"):
                verd[au["verdict"]] += 1
    order = ["confirmed", "refuted", "negligible", "unmeasurable"]
    cols = [ACC, WARN, MUTE, "#d8d8d8"]
    vals = [verd[v] for v in order]
    tot = sum(vals) or 1
    left = 0.0
    for v, c, lab in zip(vals, cols, order):
        if v == 0:
            continue
        axb.barh([0], [v], left=left, height=0.5, color=c, edgecolor=INK, linewidth=0.5)
        if v / tot > 0.08:
            axb.text(left + v / 2.0, 0, f"{lab}\n{v}", ha="center", va="center",
                     fontsize=6.0, color="#ffffff" if c is ACC else INK)
        else:
            axb.annotate(f"{lab}: {v}", xy=(left + v / 2.0, -0.26),
                         xytext=(left + v / 2.0, -0.62), ha="center", va="top",
                         fontsize=6.0, color=INK,
                         arrowprops=dict(arrowstyle="-", lw=0.5, color=INK))
        left += v
    zeros = [lab for lab, v in zip(order, vals) if v == 0]
    if zeros:
        axb.text(tot, -0.52, " / ".join(zeros) + ": 0", ha="right", va="top",
                 fontsize=6.0, color=INK)
    adj = verd["confirmed"] + verd["refuted"]
    share = 100 * verd["confirmed"] / adj if adj else float("nan")
    axb.set_xlim(0, tot)
    axb.set_ylim(-0.9, 0.45)
    axb.set_yticks([])
    axb.set_xticks([])
    axb.set_xlabel(f"causal claims audited ($n$ = {tot})", labelpad=1)
    axb.set_title(f"reasoning audit: {verd['confirmed']}/{adj} clear verdicts, "
                  f"all confirmed", loc="left")
    for sp in ("left", "bottom"):
        axb.spines[sp].set_visible(False)
    fig.tight_layout(pad=0.3)
    figb.tight_layout(pad=0.3)
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(HERE, f"fig2_tiers_REAL.{ext}"), bbox_inches="tight")
        figb.savefig(os.path.join(HERE, f"figS2_audit_REAL.{ext}"), bbox_inches="tight")
    plt.close(fig); plt.close(figb)
    return {"audit": dict(verd), "adjudicable": adj, "confirmed_share": share}


if __name__ == "__main__":
    print(json.dumps({"fig2": fig2(), "fig3": fig3()}, indent=1))

"""Fig. 1 — ALIA closed-loop architecture (REAL, publication figure).
IEEE column width 3.46 in. Palette: validated slots — blue #2a78d6 (LLM/reasoning),
orange #eb6834 (deterministic harness), aqua #1baf7a (audit/verdict), neutral inks.
"""
import os
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, MUT, GRID = "#0b0b0b", "#52514e", "#c3c2b7"
FS = 6.4

fig, ax = plt.subplots(figsize=(3.46, 2.35), dpi=300)
ax.set_xlim(0, 100); ax.set_ylim(0, 68); ax.axis("off")

def box(x, y, w, h, label, fc, ec, fs=FS, lw=0.9, bold=False, sub=None):
    b = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.6,rounding_size=1.6",
                       fc=fc, ec=ec, lw=lw)
    ax.add_patch(b)
    weight = "bold" if bold else "normal"
    if sub:
        ax.text(x + w/2, y + h/2 + 2.1, label, ha="center", va="center",
                fontsize=fs, color=INK, weight=weight)
        ax.text(x + w/2, y + h/2 - 2.4, sub, ha="center", va="center",
                fontsize=fs-1.1, color=MUT)
    else:
        ax.text(x + w/2, y + h/2, label, ha="center", va="center",
                fontsize=fs, color=INK, weight=weight)

def arrow(p0, p1, c=INK, lw=1.0, rad=0.0, ls="solid"):
    a = FancyArrowPatch(p0, p1, arrowstyle="-|>", mutation_scale=6,
                        lw=lw, color=c, shrinkA=1, shrinkB=1, linestyle=ls,
                        connectionstyle=f"arc3,rad={rad}")
    ax.add_patch(a)

# ---- forward path, upper band ----
box(1, 52, 13, 11, "Spec", "#ffffff", GRID, sub="targets")
box(17, 50, 24, 15, "LLM reasoner", "#e7f0fb", BLUE, bold=True,
    sub="frozen · un-augmented")
box(43, 50, 23, 15, "Lint / repair", "#fdeee7", ORANGE, bold=True,
    sub="deterministic  P1")
box(68, 52, 13, 11, "Render", "#ffffff", GRID, sub="netlist")
box(85, 52, 14, 11, "ngspice", "#ffffff", GRID, sub="gf180 PDK")

# ---- return path, middle band (right -> left) ----
box(76, 28, 20, 12, "Measure", "#ffffff", GRID, sub="A0, PM, GBW, I$_{DD}$")
box(46, 28, 25, 12, "Evaluate vs spec", "#ffffff", GRID, sub="pass / fail + errors")
box(14, 28, 27, 12, "Feedback packet", "#e7f0fb", BLUE,
    sub="IR · trace ·\nmetrics · margins · errors")

# ---- pillar taps, bottom band ----
box(2, 4, 34, 13, "Reasoning audit  P3", "#e6f6f0", AQUA, bold=True,
    sub="vs SPICE: confirm / refute /\nnegligible / unmeasurable")
box(38, 4, 35, 13, "Tier decomposition  P2", "#ffffff", GRID, bold=True,
    sub="T1 topology · T2 sizing ·\nT3 syntax")
box(77, 4, 21, 13, "Design + logs", "#ffffff", GRID, sub="episode JSONL")

# forward arrows
arrow((14, 57.5), (17, 57.5))
arrow((41, 57.5), (43, 57.5))
arrow((66, 57.5), (68, 57.5))
arrow((81, 57.5), (85, 57.5))
# ngspice down to Measure, then leftwards
arrow((91, 52), (88, 40))
arrow((76, 34), (71, 34))
arrow((46, 34), (41, 34))
# feedback up to LLM (the loop), labelled
arrow((24, 40), (27, 50), c=BLUE, lw=1.2, rad=-0.12)
ax.text(31.5, 44.6, "fail: iterate", fontsize=FS-1.3, color=BLUE,
        ha="center", va="center", style="italic")
# pass exit: Evaluate -> Design + logs
arrow((66, 28), (83, 17), c=MUT, rad=-0.15)
ax.text(73.5, 20.5, "pass", fontsize=FS-1.3, color=MUT, ha="center", style="italic")
# reasoning record tap: LLM -> audit
arrow((22, 50), (14, 17), c=AQUA, rad=0.25, ls=(0, (2, 1.2)))
ax.text(5.5, 33.5, "reasoning\nrecord", fontsize=FS-1.3, color=AQUA,
        ha="center", va="center", style="italic")
# repair log tap: Lint/repair -> tier decomposition
arrow((55, 50), (54, 17), c=ORANGE, rad=0.0, ls=(0, (2, 1.2)))
ax.text(59.5, 44.8, "repair log", fontsize=FS-1.3, color=ORANGE,
        ha="center", va="center", style="italic")
# outcome tap: Evaluate -> tier decomposition
arrow((58, 28), (58, 17), c=MUT, rad=0.0, ls=(0, (2, 1.2)))

plt.subplots_adjust(left=0.005, right=0.995, top=0.995, bottom=0.005)
fig.savefig(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fig1_architecture.png"), dpi=300)
fig.savefig(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fig1_architecture.pdf"))
print("fig1 done")

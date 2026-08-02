"""Fig. S1 — 5-transistor OTA schematic (REAL: the design task handed to the
reasoner). Hand-drawn textbook-style symbols; mirror gates face inward.
"""
import matplotlib.pyplot as plt

INK, MUT = "#0b0b0b", "#52514e"
LW = 1.2
fig, ax = plt.subplots(figsize=(5.3, 4.15), dpi=300)
ax.set_xlim(0.2, 12.4); ax.set_ylim(0.2, 10.7)
ax.set_aspect("equal"); ax.axis("off")

def line(x0, y0, x1, y1, c=INK, lw=LW):
    ax.plot([x0, x1], [y0, y1], color=c, lw=lw, solid_capstyle="round", zorder=2)

def dot(x, y, open_=False):
    if open_:
        ax.plot([x], [y], marker="o", ms=4, mfc="white", mec=INK, mew=1.0, zorder=4)
    else:
        ax.plot([x], [y], marker="o", ms=3.2, color=INK, zorder=4)

def mosfet(x, y, kind="n", face="R"):
    """(x,y)=channel centre. face='R': stubs exit right, gate lead exits left;
    face='L' mirrors. Current-path column sits at x + s*0.55."""
    s = 1 if face == "R" else -1
    g_x = x - s * 0.32
    line(x, y - 0.62, x, y + 0.62)
    line(g_x, y - 0.44, g_x, y + 0.44)
    gate = (x - s * 1.0, y)
    line(g_x, y, gate[0], y)
    col = x + s * 0.55
    dtop = (col, y + 1.05); stop = (col, y - 1.05)
    line(x, y + 0.52, col, y + 0.52); line(col, y + 0.52, col, dtop[1])
    line(x, y - 0.52, col, y - 0.52); line(col, y - 0.52, col, stop[1])
    if kind == "n":
        ax.annotate("", xy=(x + s * 0.42, y - 0.52), xytext=(x, y - 0.52),
                    arrowprops=dict(arrowstyle="-|>", color=INK, lw=0, mutation_scale=9))
        drain, src = dtop, stop
    else:
        ax.annotate("", xy=(x, y + 0.52), xytext=(x + s * 0.45, y + 0.52),
                    arrowprops=dict(arrowstyle="-|>", color=INK, lw=0, mutation_scale=9))
        drain, src = stop, dtop
    return {"g": gate, "d": drain, "s": src, "col": col}

def ground(x, y):
    line(x - 0.30, y, x + 0.30, y)
    line(x - 0.19, y - 0.14, x + 0.19, y - 0.14)
    line(x - 0.08, y - 0.28, x + 0.08, y - 0.28)

XL, XR, XM = 2.6, 8.4, 5.5
Y_RAIL, Y_P, Y_N1, Y_DP, Y_TAIL, Y_M5, Y_VSS = 9.9, 8.6, 7.25, 5.9, 4.55, 3.3, 1.9

# VDD rail
line(XL - 0.9, Y_RAIL, XR + 0.9, Y_RAIL)
ax.text(XM, Y_RAIL + 0.28, "VDD = 3.3 V", fontsize=7.5, ha="center", color=INK)

# PMOS mirror, gates inward
M3 = mosfet(XL + 1.1, Y_P, "p", "L")   # column at XL+0.55
M4 = mosfet(XR - 1.1, Y_P, "p", "R")   # column at XR-0.55
line(M3["s"][0], M3["s"][1], M3["s"][0], Y_RAIL); dot(M3["s"][0], Y_RAIL)
line(M4["s"][0], M4["s"][1], M4["s"][0], Y_RAIL); dot(M4["s"][0], Y_RAIL)
line(M3["g"][0], Y_P, M4["g"][0], Y_P)                    # gate-gate, inner span
# diode connection: tap gate wire at M3 gate end, drop to n1
dot(M3["g"][0], Y_P)
line(M3["g"][0], Y_P, M3["g"][0], Y_N1)
line(M3["g"][0], Y_N1, M3["col"], Y_N1)
# drains to n1 / nout
line(M3["col"], M3["d"][1], M3["col"], Y_N1)
line(M4["col"], M4["d"][1], M4["col"], Y_N1)
n1 = (M3["col"], Y_N1); nout = (M4["col"], Y_N1)
dot(*n1)

# diff pair, gates outward
M1 = mosfet(XL, Y_DP, "n", "R")        # column XL+0.55 — aligns with M3
M2 = mosfet(XR, Y_DP, "n", "L")        # column XR-0.55 — aligns with M4
line(M1["col"], M1["d"][1], n1[0], Y_N1)
line(M2["col"], M2["d"][1], nout[0], Y_N1)
line(M1["g"][0], Y_DP, M1["g"][0] - 0.6, Y_DP); dot(M1["g"][0] - 0.6, Y_DP, open_=True)
ax.text(M1["g"][0] - 0.85, Y_DP, r"$v_{in+}$", fontsize=8, ha="right", va="center")
line(M2["g"][0], Y_DP, M2["g"][0] + 0.6, Y_DP); dot(M2["g"][0] + 0.6, Y_DP, open_=True)
ax.text(M2["g"][0] + 0.85, Y_DP, r"$v_{in-}$", fontsize=8, ha="left", va="center")
line(M1["col"], M1["s"][1], M1["col"], Y_TAIL)
line(M2["col"], M2["s"][1], M2["col"], Y_TAIL)
line(M1["col"], Y_TAIL, M2["col"], Y_TAIL)
dot(XM, Y_TAIL)

# tail device
M5 = mosfet(XM - 0.55, Y_M5, "n", "R")  # column at XM
line(M5["col"], M5["d"][1], M5["col"], Y_TAIL)
line(M5["g"][0], Y_M5, M5["g"][0] - 0.6, Y_M5); dot(M5["g"][0] - 0.6, Y_M5, open_=True)
ax.text(M5["g"][0] - 0.85, Y_M5, r"$V_{bias}$", fontsize=8, ha="right", va="center")
line(M5["col"], M5["s"][1], M5["col"], Y_VSS)
ground(M5["col"], Y_VSS)

# output net + load, kept clear of the v_in- lead
line(nout[0], Y_N1, 11.0, Y_N1); dot(*nout)
vo = (11.0, Y_N1)
dot(*vo, open_=True)
ax.text(vo[0] + 0.25, vo[1] + 0.3, r"$v_{out}$", fontsize=8, ha="left", va="center")
line(vo[0], vo[1], vo[0], vo[1] - 0.9)
line(vo[0] - 0.38, vo[1] - 0.9, vo[0] + 0.38, vo[1] - 0.9)
line(vo[0] - 0.38, vo[1] - 1.08, vo[0] + 0.38, vo[1] - 1.08)
line(vo[0], vo[1] - 1.08, vo[0], vo[1] - 1.7)
ground(vo[0], vo[1] - 1.7)
ax.text(vo[0] + 0.52, vo[1] - 1.0, r"$C_L$", fontsize=8, ha="left", va="center")

# device labels — manual, collision-free spots
ax.text(2.55, Y_P, "M3", fontsize=8, ha="right", va="center")
ax.text(9.35, Y_P, "M4", fontsize=8, ha="left", va="center")
ax.text(3.45, Y_DP + 0.62, "M1", fontsize=8, ha="left", va="center")
ax.text(7.55, Y_DP + 0.62, "M2", fontsize=8, ha="right", va="center")
ax.text(6.0, Y_M5 + 0.62, "M5", fontsize=8, ha="left", va="center")

ax.text(0.4, 1.35,
        "Design task handed to the reasoner — GF180MCU 3.3 V devices (nfet_03v3 / pfet_03v3);\n"
        "bulks (omitted for clarity): NMOS to VSS (substrate), PMOS in own n-well to source;\n"
        "free variables: all W, L, $V_{bias}$; power budget $I_{tail}$ ≤ 100 µA (proposed).\n"
        "AC testbench: differential input, $C_L$ at $v_{out}$; ngspice measures DC gain, GBW, PM.",
        fontsize=6.6, ha="left", va="top", color=MUT, linespacing=1.5)

plt.subplots_adjust(left=0.01, right=0.99, top=0.99, bottom=0.01)
fig.savefig("figS1_ota_schematic.png", dpi=300)
fig.savefig("figS1_ota_schematic.pdf")
print("figS1 done")

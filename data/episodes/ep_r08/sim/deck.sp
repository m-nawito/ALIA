* 5t-ota
.include "/home/claude/icta2026/gf180pr/models/ngspice/design.ngspice"
.lib "/home/claude/icta2026/gf180pr/models/ngspice/sm141064.ngspice" typical
XM1 n1 inp ntail 0 nfet_03v3 W=10u L=1u m=20
XM2 out inn ntail 0 nfet_03v3 W=10u L=1u m=20
XM3 n1 n1 vdd vdd pfet_03v3 W=10u L=2u m=2
XM4 out n1 vdd vdd pfet_03v3 W=10u L=2u m=2
XM5 ntail nbias 0 0 nfet_03v3 W=10u L=1u
Vdd vdd 0 DC 3.3
Vinp inp 0 DC 1.65 AC 0.5
Vinn inn 0 DC 1.65 AC -0.5
Vb nbias 0 DC 1.0
CL out 0 5p
.control
set filetype=ascii
op
wrdata /home/claude/icta2026/episodes/ep_r08/sim/iter3_op.dat vdd#branch
ac dec 30 1 10G
wrdata /home/claude/icta2026/episodes/ep_r08/sim/iter3_ac.dat vr(out) vi(out)
quit
.endc
.end
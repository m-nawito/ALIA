* 5t-ota
.include "/home/claude/icta2026/gf180pr/models/ngspice/design.ngspice"
.lib "/home/claude/icta2026/gf180pr/models/ngspice/sm141064.ngspice" typical
XM1 n1 inp ntail 0 nfet_03v3 W=200u L=1u nf=10 m=1
XM2 out inn ntail 0 nfet_03v3 W=200u L=1u nf=10 m=1
XM3 n1 n1 vdd vdd pfet_03v3 W=40u L=2u nf=4 m=1
XM4 out n1 vdd vdd pfet_03v3 W=40u L=2u nf=4 m=1
XM5 ntail nbias 0 0 nfet_03v3 W=15u L=1u nf=2 m=1
Vdd vdd 0 DC 3.3
Vinp inp 0 DC 1.65 AC 0.5
Vinn inn 0 DC 1.65 AC -0.5
Vb nbias 0 DC 0.95
CL out 0 5p
.control
set filetype=ascii
op
wrdata /home/claude/icta2026/episodes/ep_p18/sim/audit_after_op.dat vdd#branch
ac dec 30 1 10G
wrdata /home/claude/icta2026/episodes/ep_p18/sim/audit_after_ac.dat vr(out) vi(out)
quit
.endc
.end
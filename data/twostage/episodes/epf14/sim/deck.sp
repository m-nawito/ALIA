* two-stage-ota
.include "/home/claude/alia/gf180pr/models/ngspice/design.ngspice"
.lib "/home/claude/alia/gf180pr/models/ngspice/sm141064.ngspice" typical
XM1 n1 inp ntail 0 nfet_03v3 W=10u L=1u nf=1 m=1
XM2 n2 inn ntail 0 nfet_03v3 W=10u L=1u nf=1 m=1
XM3 n1 n2 vdd vdd pfet_03v3 W=10u L=1u nf=1 m=1
XM4 n2 n2 vdd vdd pfet_03v3 W=10u L=1u nf=1 m=1
XM5 ntail nbias 0 0 nfet_03v3 W=10u L=1u nf=1 m=1
XM6 out n1 vdd vdd pfet_03v3 W=24u L=1u nf=1 m=1
XM7 out nbias 0 0 nfet_03v3 W=12u L=1u nf=1 m=1
Rz n1 nz 3.3k
Cc nz out 8p
Vdd vdd 0 DC 3.3
Vinp inp 0 DC 1.65 AC 0.5
Vinn inn 0 DC 1.65 AC -0.5
Vb nbias 0 DC 0.9
CL out 0 5p
.control
set filetype=ascii
op
wrdata /home/claude/alia/episodes/epf14/sim/audit_after_op.dat vdd#branch
ac dec 30 1 10G
wrdata /home/claude/alia/episodes/epf14/sim/audit_after_ac.dat vr(out) vi(out)
quit
.endc
.end
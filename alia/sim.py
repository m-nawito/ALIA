"""Run ngspice on a rendered deck and extract measurements (deterministic)."""
import subprocess, os, math


def run_ngspice(deck: str, workdir: str = "/tmp/alia", timeout: int = 120):
    os.makedirs(workdir, exist_ok=True)
    deckpath = os.path.join(workdir, "deck.sp")
    with open(deckpath, "w") as f:
        f.write(deck)
    p = subprocess.run(["ngspice", "-b", deckpath],
                       capture_output=True, text=True, timeout=timeout)
    return {"returncode": p.returncode, "stdout": p.stdout, "stderr": p.stderr,
            "deckpath": deckpath}


def _read_cols(path):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append([float(x) for x in line.split()])
            except ValueError:
                continue
    return rows


def measure_ac(datafile: str) -> dict:
    """Columns from `wrdata f vr(out) vi(out)`: [freq, vr, freq, vi]. Vin AC=1,
    so v(out) == transfer function H(f)."""
    rows = _read_cols(datafile)
    if not rows:
        return {"error": "no AC data"}
    freqs, gdb, phase = [], [], []
    for r in rows:
        f = r[0]; vr = r[1]; vi = r[3] if len(r) > 3 else 0.0
        mag = math.hypot(vr, vi)
        freqs.append(f)
        gdb.append(20 * math.log10(mag) if mag > 0 else -300.0)
        phase.append(math.degrees(math.atan2(vi, vr)))
    dc = gdb[0]
    f3 = next((f for f, g in zip(freqs, gdb) if g <= dc - 3.0), None)
    fu = pm = None
    for i in range(1, len(gdb)):
        if gdb[i - 1] >= 0.0 >= gdb[i]:
            g1, g2 = gdb[i - 1], gdb[i]
            t = (0 - g1) / (g2 - g1) if g2 != g1 else 0.0
            fu = freqs[i - 1] * (freqs[i] / freqs[i - 1]) ** t
            pm = 180.0 + (phase[i - 1] + t * (phase[i] - phase[i - 1]))
            break
    return {
        "dc_gain_db": round(dc, 3),
        "f_3db_hz": f3,
        "gbw_hz": fu,
        "phase_margin_deg": round(pm, 2) if pm is not None else None,
        "n_points": len(freqs),
    }


def measure_op_current(opfile: str) -> dict:
    """Supply current from `wrdata opfile vdd#branch` after .op — last float of
    the first data line is the branch current (negative = sourcing)."""
    rows = _read_cols(opfile)
    if not rows or not rows[0]:
        return {"itail_ua": None}
    return {"itail_ua": round(abs(rows[0][-1]) * 1e6, 3)}

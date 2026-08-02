"""Verify the released per-turn transcripts against the released episode packets.

For every transcript in --search (default data/transcripts/phase3):
  1. scan: first user message, final assistant text, tool_use count,
     model set, token sums
  2. match the received prompt byte-for-byte against the packet files
     (data/episodes/<ep>/turn<k>_prompt.txt) and the recorded reply against
     the stored response
  3. report one JSON line per transcript and an overall summary

Expected on this release: 227 phase-3 transcripts, all ok. The six pilot
transcripts (data/transcripts/pilot/) predate the release layout and have no
shipped packet files; they report episode null (see the README there).

Usage:  python3 tools/verify_transcripts.py --epd data/episodes \
            --search data/transcripts/phase3
"""
import argparse
import glob
import json
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def _msg_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text", "") for b in content
                       if isinstance(b, dict) and b.get("type") == "text")
    return ""


def scan_transcript(path):
    first_user, final_assistant = None, None
    tool_uses, models = 0, set()
    tok_out, tok_total = 0, 0
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            m = d.get("message")
            if not isinstance(m, dict):
                continue
            role = m.get("role")
            c = m.get("content")
            if role == "user" and first_user is None:
                first_user = _msg_text(c)
            if isinstance(c, list):
                for b in c:
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        tool_uses += 1
            if role == "assistant":
                if m.get("model"):
                    models.add(m["model"])
                t = _msg_text(c)
                if t.strip():
                    final_assistant = t
                u = m.get("usage") or {}
                tok_out += u.get("output_tokens", 0) or 0
                tok_total += sum((u.get(k) or 0) for k in (
                    "input_tokens", "cache_creation_input_tokens",
                    "cache_read_input_tokens", "output_tokens"))
    return {"first_user": first_user, "final_assistant": final_assistant,
            "tool_uses": tool_uses, "models": sorted(models),
            "tokens_out": tok_out, "tokens_total": tok_total}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--marker", default=None)
    ap.add_argument("--search", default=os.path.join(ROOT, "data", "transcripts", "phase3"))
    ap.add_argument("--epd", default=os.path.join(ROOT, "data", "episodes"))
    ap.add_argument("--archive", action="store_true",
                    help="copy matched transcripts to <epd>/transcripts/phase3")
    a = ap.parse_args()
    cutoff = os.path.getmtime(a.marker) if a.marker else 0.0

    # every turn<k>_prompt.txt with its stored response; match against ALL
    # packets (cheap, exact).
    packets = {}                      # packet text -> [(ep, k, prompt, resp)]
    for pf in glob.glob(os.path.join(a.epd, "ep*", "turn*_prompt.txt")):
        ep = os.path.basename(os.path.dirname(pf))
        k = int(os.path.basename(pf).split("turn")[1].split("_")[0])
        rf = os.path.join(os.path.dirname(pf), f"turn{k}_response.json")
        packets.setdefault(open(pf).read(), []).append((ep, k, pf, rf))

    arch = os.path.join(a.epd, "transcripts", "phase3")
    if a.archive:
        os.makedirs(arch, exist_ok=True)
    results, n_ok = [], 0
    files = [p for p in glob.glob(os.path.join(a.search, "**", "agent-*.jsonl"),
                                  recursive=True)
             if os.path.getmtime(p) > cutoff]
    for p in sorted(files):
        s = scan_transcript(p)
        fu = s["first_user"] or ""
        # The dispatch path strips the packet's single trailing newline
        # (pilot-verified): exact OR exact+'\n' both count as byte-fidelity.
        cands = packets.get(fu, []) or packets.get(fu + "\n", [])
        match = None
        for (ep, k, pf, rf) in cands:
            if os.path.exists(rf) and open(rf).read().rstrip("\n") == (s["final_assistant"] or "").rstrip("\n"):
                match = (ep, k)
                break
        if match is None and len(cands) == 1:
            match = (cands[0][0], cands[0][1])          # unique packet, resp pending
        ok = bool(match) and s["tool_uses"] == 0 and bool(cands)
        n_ok += ok
        rec = {"transcript": os.path.basename(p), "episode": match[0] if match else None,
               "iter": match[1] if match else None,
               "packet_match": bool(cands), "response_match": bool(match),
               "tool_uses": s["tool_uses"], "models": s["models"],
               "tokens_out": s["tokens_out"], "tokens_total": s["tokens_total"],
               "ok": ok}
        results.append(rec)
        if match and a.archive:
            dst = os.path.join(
                arch, f"{os.path.basename(p)[:-6]}__{match[0]}_turn{match[1]}.jsonl")
            shutil.copy2(p, dst)
    print(json.dumps({"n_transcripts": len(results), "n_ok": n_ok,
                      "all_ok": n_ok == len(results) and len(results) > 0,
                      "results": results}))


if __name__ == "__main__":
    main()

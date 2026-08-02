Pilot reasoner-turn transcripts (2026-07-30) — one JSONL per turn, same line
schema as phase 3 ({type, timestamp, message}, message verbatim).
Mapping: a3f8485d=ep01/it0, a54b5747=ep01/it1, acc8377b=ep02/it0,
ac8badf3=ep02/it1, a3cbb3e0=ep02/it2, a1c20b7e=ep02/it3.
Verified at pilot time: received prompt == harness disk packet (6/6); zero
tool_use blocks (6/6); model claude-fable-5 throughout. The pilot's packet
files predate the release layout and are not shipped, so the automated
byte-identity check in tools/verify_transcripts.py covers the 227 phase-3
turns; these six report `episode: null` there by construction.

"""gf180mcu PDK configuration for the ALIA harness.

Validated 2026-07-16: include design.ngspice FIRST (sets sw_stat_mismatch,
fnoicor, etc.), then .lib the model card with a corner. Devices are subckts
with node order d g s b.
"""
import os

MODELS_DIR = os.environ.get("ALIA_GF180_MODELS",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gf180pr", "models", "ngspice"))
DESIGN_INC = os.path.join(MODELS_DIR, "design.ngspice")
LIB_FILE = os.path.join(MODELS_DIR, "sm141064.ngspice")

DEFAULT_CORNER = "typical"          # typical | ff | ss | fs | sf
DEFAULT_VDD = 3.3

# generic kind -> gf180 3.3 V device subckt (node order: d g s b)
MODEL = {"nmos": "nfet_03v3", "pmos": "pfet_03v3"}


def include_lines(corner: str = DEFAULT_CORNER) -> str:
    return f'.include "{DESIGN_INC}"\n.lib "{LIB_FILE}" {corner}'

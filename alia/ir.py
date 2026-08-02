"""Circuit intermediate representation (IR).

JSON-serialisable. This is the structured object the LLM emits (instead of raw
SPICE text); the deterministic renderer turns it into a guaranteed-well-formed
ngspice deck. Keeping generation at the IR level is what lets the repair layer
be deterministic.

Node-order conventions by kind:
  nmos / pmos : [drain, gate, source, bulk]   params: W, L, nf, m
  res         : [n1, n2]                       params: value
  cap         : [n1, n2]                       params: value
  vsource     : [plus, minus]                  params: dc, ac
  isource     : [plus, minus]                  params: dc
"""
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any


@dataclass
class Device:
    id: str
    kind: str
    nodes: List[str]
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Circuit:
    name: str
    devices: List[Device] = field(default_factory=list)
    params: Dict[str, Any] = field(default_factory=dict)  # global .param values

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Circuit":
        return Circuit(
            name=d["name"],
            devices=[Device(**x) for x in d.get("devices", [])],
            params=d.get("params", {}),
        )

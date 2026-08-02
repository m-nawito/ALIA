"""Structured JSONL logging — every attempt is auditable and replayable."""
import json, os, time


class RunLogger:
    def __init__(self, path: str):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.path = path
        self._f = open(path, "a")

    def log(self, record: dict):
        self._f.write(json.dumps({"t": time.time(), **record}, default=str) + "\n")
        self._f.flush()

    def close(self):
        self._f.close()

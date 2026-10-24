"""Offline recovery from one capture's immutable responses; never falls back to HTTP."""
import hashlib
import json
from pathlib import Path


class ArchivedApiFootballClient:
    def __init__(self, audit):
        self.last_headers = {}
        self.payloads = {}
        for value in audit["raw_files"]:
            path = Path(value)
            content = path.read_bytes()
            label, digest = path.stem.rsplit("_", 1)
            if hashlib.sha256(content).hexdigest()[:12] != digest:
                raise ValueError("archive digest mismatch")
            label = label.split("_", 1)[1]
            if label in self.payloads:
                raise ValueError("ambiguous archived request")
            self.payloads[label] = json.loads(content)

    def get(self, endpoint, params):
        if endpoint == "fixtures/lineups":
            key = "lineups_" + str(params["fixture"])
        elif endpoint in ("fixtures", "injuries"):
            key = endpoint + "_" + params["date"]
            if endpoint == "fixtures" and key not in self.payloads:
                key = "calendar_" + params["date"]
        else:
            raise ValueError("unsupported archived endpoint")
        if key not in self.payloads:
            raise ValueError("missing_archived_response:" + key)
        return self.payloads[key]

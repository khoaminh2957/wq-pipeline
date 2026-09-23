#!/usr/bin/env python3
"""5x regression test for state/funnel/stage3_example_spec.json (no API).

Verifies the example stage-3 run-spec:
  1. loads as JSON,
  2. has exactly 9 choices,
  3. every field3 exists in the model175 CHN d1 catalog (fields_per_dataset.jsonl),
  4. every field3 is same-dataset as the root (mdl175_ prefix) and NOT a used field
     (root + any stage-2 partner),
  5. every structure3 differs from its seed's structure (multiply).
"""
import json, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
SPEC = ROOT / "state/funnel/stage3_example_spec.json"
CAT = ROOT / "fetched/catalog_CHN/fields_per_dataset.jsonl"


def _d1_catalog():
    ids = set()
    for line in open(CAT):
        r = json.loads(line)
        if r.get("dataset", {}).get("id") == "model175" and r.get("_delay") == 1:
            ids.add(r["id"])
    return ids


def check():
    spec = json.load(open(SPEC))                      # (1) loads
    choices = spec["choices"]
    assert len(choices) == 9, f"expected 9 choices, got {len(choices)}"  # (2)
    d1 = _d1_catalog()
    root = spec["root_field"]
    used = set(spec["used_fields"])
    prefix = root.split("_", 1)[0]                    # mdl175
    for c in choices:
        f3 = c["field3"]
        assert f3 in d1, f"field3 {f3} not in model175 CHN d1 catalog"       # (3)
        assert f3.split("_", 1)[0] == prefix, f"{f3} not same dataset as {root}"  # (4a)
        assert f3 not in used, f"field3 {f3} is an already-used field"           # (4b)
        assert f3 != c["seed_partner"], f"field3 {f3} == seed_partner"
        assert c["structure3"] != c["seed_structure"], (                        # (5)
            f"structure3 {c['structure3']} must differ from seed structure "
            f"{c['seed_structure']}")
    return True


if __name__ == "__main__":
    for i in range(5):
        assert check()
        print(f"pass {i + 1}/5")
    print("OK 5/5")

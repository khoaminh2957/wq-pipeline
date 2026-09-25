"""Storage: one JSON file per frame under framelib/library/frames/<id>.json, plus a generated INDEX.json
that files every id under each taxonomy axis (the "systematised" view of the library).

Files are written with sorted keys and a fixed indent, so an unchanged entry rewrites byte-identically
and a diff shows only what changed. `save` refuses an invalid entry; `load` refuses a library with any
invalid entry, a file whose name is not its id, or a stale INDEX.json.

    python3 -B -m framelib.store [library dir]      validate a library, print a summary, exit 1 on errors
"""
from __future__ import annotations

import json
import pathlib
import sys

from framelib import schema as SC
from framelib import taxonomy as TX

LIBRARY = pathlib.Path(__file__).resolve().parent / "library"
INDEX_AXES = ("family",) + tuple(TX.DIMENSIONS) + ("slot_kinds",)


class LibraryError(ValueError):
    def __init__(self, problems: dict):
        self.problems = problems
        super().__init__("; ".join("%s: %s" % (k, " | ".join(v)) for k, v in sorted(problems.items()))[:2000])


def dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=False) + "\n"


def frames_dir(root=LIBRARY) -> pathlib.Path:
    return pathlib.Path(root) / "frames"


def save(entry: dict, root=LIBRARY) -> pathlib.Path:
    errs = SC.validate(entry)
    if errs:
        raise LibraryError({entry.get("id", "?"): errs})
    d = frames_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    p = d / ("%s.json" % entry["id"])
    text = dumps(entry)
    if not p.exists() or p.read_text() != text:
        p.write_text(text)
    return p


def read_all(root=LIBRARY) -> dict:
    """id -> entry, without validation (the builder reads existing entries this way)."""
    out = {}
    for p in sorted(frames_dir(root).glob("*.json")):
        out[p.stem] = json.loads(p.read_text())
    return out


def index(entries) -> dict:
    out = {ax: {} for ax in INDEX_AXES}
    for e in sorted(entries, key=lambda e: e["id"]):
        ch = e["characteristics"]
        for ax in INDEX_AXES:
            out[ax].setdefault(str(ch[ax]), []).append(e["id"])
    out["status"] = {}
    for e in sorted(entries, key=lambda e: e["id"]):
        out["status"].setdefault(e["status"], []).append(e["id"])
    return {ax: dict(sorted(v.items())) for ax, v in out.items()}


def write_index(entries, root=LIBRARY) -> pathlib.Path:
    p = pathlib.Path(root) / "INDEX.json"
    text = dumps({"taxonomy_version": TX.TAXONOMY_VERSION, "n_frames": len(entries), "index": index(entries)})
    if not p.exists() or p.read_text() != text:
        p.write_text(text)
    return p


def problems(root=LIBRARY) -> dict:
    """file name -> [errors] for the whole library (empty dict = valid)."""
    out, entries = {}, []
    for p in sorted(frames_dir(root).glob("*.json")):
        try:
            e = json.loads(p.read_text())
        except ValueError as exc:
            out[p.name] = ["not JSON: %s" % exc]
            continue
        errs = SC.validate(e)
        if e.get("id") != p.stem:
            errs.append("file name %s is not the entry id %s" % (p.stem, e.get("id")))
        if errs:
            out[p.name] = errs
        else:
            entries.append(e)
    ip = pathlib.Path(root) / "INDEX.json"
    if ip.exists() and not out:
        got = json.loads(ip.read_text())
        want = {"taxonomy_version": TX.TAXONOMY_VERSION, "n_frames": len(entries), "index": index(entries)}
        if got != want:
            out["INDEX.json"] = ["stale: does not match the entries; rebuild with framelib.build"]
    return out


def load(root=LIBRARY) -> list:
    """Every entry, validated; raises LibraryError listing every problem."""
    bad = problems(root)
    if bad:
        raise LibraryError(bad)
    return [json.loads(p.read_text()) for p in sorted(frames_dir(root).glob("*.json"))]


def select(entries, **axes) -> list:
    """Entries whose characteristics match every axis given, e.g. select(lib, combiner="SUM", horizon="YEAR")."""
    return [e for e in entries if all(e["characteristics"].get(k) == v for k, v in axes.items())]


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    root = pathlib.Path(argv[0]) if argv else LIBRARY
    bad = problems(root)
    n = len(list(frames_dir(root).glob("*.json")))
    print(json.dumps({"library": str(root), "files": n, "invalid": len(bad), "problems": bad}, indent=1, ensure_ascii=False))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())

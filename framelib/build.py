"""The builder: frame proposals + the canonical corpus -> library entries (status candidate).

    python3 -B -m framelib.build --canonical DIR [--novel FILE] [--discovery FILE ...] [--mined-min-fills K]
                                 [--out framelib/library] [--dry-run] [--now ISO]

PROPOSALS (each optional; a missing file is reported and skipped):
  --discovery FILE  repeatable. Markdown: every `backticked` span holding $1..$n inside a section whose
                    heading says "candidate" (the whole document when no heading does) is one frame.
                    CSV (e.g. quant/out/q4_candidates.csv, the list 10_frames_discovery.md section 5 points
                    to): the "frame_key" column, else the first column; rows whose "candidate" column is
                    not true are skipped; the row's other columns are kept verbatim in the source
  --novel FILE      JSON lines; the frame text under "template" ({k} placeholders, the designer's form, which
                    keeps pinned fields) or "text" / "frame" / "frame_key" ($k); when both "template" and
                    "frame" are given their canonical keys must agree. Optional "settings" {neutralization,
                    decay, truncation, universe (+ region)}, "slots" [{"slot": "$k", "role", constraint keys
                    (compat.CONSTRAINT_KEYS)}]; the designer's own descriptive keys (DESIGNER_KEPT: id, function,
                    rationale with its EX-ANTE / SPECULATION label, the slot list, ...) are kept verbatim in
                    the source record
  --mined-min-fills K   every canonical frame with >= K distinct fills (frames_summary.jsonl); off by default
EVIDENCE: --canonical DIR must hold rows_framed.jsonl (and frames_summary.jsonl for --mined-min-fills).

origin is decided by the data, not by the proposer: "mined" iff the canonical corpus holds a row of the
frame. A designer's frame that the corpus already holds is therefore "mined", with the designer kept
among its sources. An existing entry keeps its status, history, approval, notes and a measured
reliability; its version is bumped only when something besides built_at changed. Entries the build
does not produce are left untouched; nothing is ever deleted. Nothing is simulated.
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as DT
import json
import pathlib
import re

from framelib import compat as CM
from framelib import evidence as EV
from framelib import frames as FR
from framelib import schema as SC
from framelib import store as ST

BUILT_BY = "framelib.build v1"
_SPAN = re.compile(r"`([^`\n]*\$\d+[^`\n]*)`")
_HEAD = re.compile(r"^(#{1,6})\s+(.*)$")
DESIGNER_SETTINGS = ("neutralization", "decay", "truncation", "universe")
DESIGNER_KEPT = ("id", "author", "function", "family", "computes", "rationale", "platform_risk", "posthoc_refs", "slots")
NOVEL_TEXT_KEYS = ("template", "text", "frame", "frame_key")     # first present wins
_BRACE = re.compile(r"\{(\d+)\}")


def discovery_spans(text: str) -> tuple:
    """([(line number, span)], whole_document_parsed)."""
    lines = text.splitlines()
    heads = [(i, len(m.group(1)), m.group(2)) for i, l in enumerate(lines) for m in [_HEAD.match(l)] if m]
    ranges = []
    for j, (i, lvl, title) in enumerate(heads):
        if "candidate" in title.lower():
            end = next((i2 for i2, l2, _ in heads[j + 1:] if l2 <= lvl), len(lines))
            ranges.append((i + 1, end))
    whole = not ranges
    if whole:
        ranges = [(0, len(lines))]
    out = []
    for a, b in ranges:
        for i in range(a, b):
            out.extend((i + 1, m.group(1)) for m in _SPAN.finditer(lines[i]))
    return out, whole


def discovery_csv(path) -> list:
    """[(ref, frame text, the row's other columns)] from a candidates CSV: the frame is the "frame_key"
    column, else the first column; when a "candidate" column exists only its true rows are kept."""
    out = []
    with open(path, newline="") as fh:
        rd = csv.DictReader(fh)
        col = "frame_key" if "frame_key" in rd.fieldnames else rd.fieldnames[0]
        for i, r in enumerate(rd, 2):
            if "candidate" in r and str(r["candidate"]).strip().lower() not in ("true", "1", "yes"):
                continue
            out.append(("row %d" % i, r[col], {k: v for k, v in r.items() if k != col and v not in ("", None)}))
    return out


def designer_slots(slots) -> dict:
    """{source slot number: {"role", "constraints"}} from a designer line's "slots" list. Keys outside
    compat.CONSTRAINT_KEYS (notes, samples, pool sizes) stay only in the source record."""
    out = {}
    for sl in slots or []:
        m = re.fullmatch(r"\$(\d+)", str(sl.get("slot", "")))
        if not m:
            continue
        cons = {k: ([v] if isinstance(v, str) and k != "unit_eq" else v) for k, v in sl.items() if k in CM.CONSTRAINT_KEYS}
        out[int(m.group(1))] = {"role": sl.get("role"), "constraints": cons or None}
    return out


def gather(canonical=None, novel=None, discovery=None, mined_min_fills=None) -> dict:
    """Proposals -> {"frames": {id: {"text", "sources", "settings"}}, "errors": [...], "inputs": {...}}."""
    frames, errors, inputs = {}, [], {}

    def add(text, source, settings=None, slot_specs=None):
        try:
            n = FR.normalize(text)
            specs = {n.renumbered(k): v for k, v in (slot_specs or {}).items()}
            if None in specs:
                raise FR.FrameError("a slot spec names a slot the text does not have")
        except FR.FrameError as exc:
            errors.append({"source": source, "text": text[:200], "error": str(exc)})
            return
        fid = SC.frame_id(n.text)
        f = frames.setdefault(fid, {"text": n.text, "sources": [], "settings": None, "slot_specs": None})
        if source not in f["sources"]:
            f["sources"].append(source)
        if settings and f["settings"] is None:
            f["settings"] = settings
        if specs and f["slot_specs"] is None:
            f["slot_specs"] = specs

    for disc in ([discovery] if isinstance(discovery, (str, pathlib.Path)) else list(discovery or [])):
        p = pathlib.Path(disc)
        if not p.exists():
            inputs.setdefault("discovery", []).append({"path": str(p), "missing": True})
            continue
        sha = EV.sha256(p)
        if p.suffix == ".csv":
            got = discovery_csv(p)
            inputs.setdefault("discovery", []).append({"path": str(p), "candidates": len(got)})
            for ref, text, extra in got:
                add(text, {"kind": "discovery", "path": str(p), "sha256": sha, "ref": ref, "row": extra})
        else:
            spans, whole = discovery_spans(p.read_text())
            inputs.setdefault("discovery", []).append({"path": str(p), "spans": len(spans), "whole_document": whole})
            for line, span in spans:
                add(span, {"kind": "discovery", "path": str(p), "sha256": sha, "ref": "line %d" % line})
    if novel:
        p = pathlib.Path(novel)
        if p.exists():
            sha, n_lines = EV.sha256(p), 0
            for i, line in enumerate(p.read_text().splitlines(), 1):
                if not line.strip():
                    continue
                n_lines += 1
                try:
                    d = json.loads(line)
                except ValueError as exc:
                    errors.append({"source": {"kind": "novel", "ref": "line %d" % i}, "error": "not JSON: %s" % exc})
                    continue
                key = next((k for k in NOVEL_TEXT_KEYS if isinstance(d.get(k), str)), None)
                if key is None:
                    errors.append({"source": {"kind": "novel", "ref": "line %d" % i}, "error": "no %s" % " / ".join(NOVEL_TEXT_KEYS)})
                    continue
                text = _BRACE.sub(r"$\1", d[key]) if key == "template" else d[key]
                src = {"kind": "novel", "path": str(p), "sha256": sha, "ref": "line %d" % i, "field": key}
                src.update({k: d[k] for k in DESIGNER_KEPT if d.get(k)})
                if key == "template" and isinstance(d.get("frame"), str):
                    try:
                        if FR.normalize(text).key != FR.normalize(d["frame"]).key:
                            errors.append({"source": src, "text": text[:200], "error": "template and frame give different canonical keys"})
                            continue
                    except FR.FrameError:
                        pass                                    # add() below reports the template's own error
                st = d.get("settings") if isinstance(d.get("settings"), dict) else None
                st = {k: st[k] for k in DESIGNER_SETTINGS if k in st} if st else None
                if st and isinstance(st.get("universe"), str):
                    st["universe"] = {d["settings"].get("region") or "?": st["universe"]}
                add(text, src, dict(st, source="designer") if st else None, designer_slots(d.get("slots")))
            inputs["novel"] = {"path": str(p), "lines": n_lines}
        else:
            inputs["novel"] = {"path": str(p), "missing": True}
    if mined_min_fills is not None:
        p = pathlib.Path(canonical) / "frames_summary.jsonl"
        sha, n_taken = EV.sha256(p), 0
        with open(p) as fh:
            for i, line in enumerate(fh, 1):
                d = json.loads(line)
                if d["n_distinct_fills"] >= mined_min_fills:
                    n_taken += 1
                    add(d["frame_key"], {"kind": "canonical", "path": str(p), "sha256": sha,
                                         "ref": "line %d; n_distinct_fills >= %d" % (i, mined_min_fills)})
        inputs["canonical_min_fills"] = {"path": str(p), "k": mined_min_fills, "frames": n_taken}
    return {"frames": frames, "errors": errors, "inputs": inputs}


def _strip_volatile(e: dict) -> dict:
    e = json.loads(json.dumps(e))
    e["provenance"].pop("built_at", None)
    e.pop("version", None)
    return e


def build(canonical, novel=None, discovery=None, mined_min_fills=None, out=ST.LIBRARY, now=None, dry_run=False) -> dict:
    now = now or DT.datetime.now(DT.timezone.utc).replace(microsecond=0).isoformat()
    g = gather(canonical, novel, discovery, mined_min_fills)
    rows_path = pathlib.Path(canonical) / "rows_framed.jsonl"
    wanted = collections.defaultdict(list)
    normals = {fid: FR.normalize(f["text"]) for fid, f in g["frames"].items()}
    for fid, n in normals.items():
        wanted[n.key].append((fid, dict(n.pinned)))
    rows = EV.collect(rows_path, wanted) if wanted else {}
    source = {"path": str(rows_path), "sha256": EV.sha256(rows_path), "spec": "FRAME SPEC v1"} if wanted else {}
    existing = ST.read_all(out)
    report = collections.Counter()
    entries = []
    for fid, f in sorted(g["frames"].items()):
        ev = EV.block(rows[fid], source) if rows.get(fid) else None
        settings = f["settings"] or (EV.modal_settings(rows[fid]) if rows.get(fid) else None)
        e = SC.new_entry(f["text"], sources=f["sources"], built_by=BUILT_BY, built_at=now, evidence=ev, settings=settings,
                         slot_specs=f.get("slot_specs"))
        old = existing.get(fid)
        if old is not None:
            for k in ("status", "status_history", "approval", "notes"):
                e[k] = old[k]
            srcs = old["provenance"]["sources"] + [s for s in e["provenance"]["sources"] if s not in old["provenance"]["sources"]]
            e["provenance"]["sources"] = srcs
            rel = ((old.get("evidence") or {}).get("reliability") or {})
            if rel.get("verdict", "UNMEASURED") != "UNMEASURED":
                if e["evidence"] is None:
                    g["errors"].append({"source": {"kind": "library", "ref": fid},
                                        "error": "measured reliability but no canonical rows now; entry left as it was"})
                    continue
                e["evidence"]["reliability"] = rel
            if _strip_volatile(e) == _strip_volatile(old):
                e = old
                report["unchanged"] += 1
            else:
                e["version"] = old["version"] + 1
                report["updated"] += 1
        else:
            report["new"] += 1
        errs = SC.validate(e)
        if errs:
            g["errors"].append({"source": {"kind": "entry", "ref": fid}, "error": "; ".join(errs)})
            continue
        entries.append(e)
    if not dry_run:
        for e in entries:
            ST.save(e, out)
        ST.write_index(list(ST.read_all(out).values()), out)
    fam = collections.Counter(e["characteristics"]["family"] for e in entries)
    return {
        "inputs": g["inputs"], "proposals": len(g["frames"]), "entries": len(entries), "written": not dry_run,
        "out": str(out), **dict(report),
        "origin": dict(collections.Counter(e["provenance"]["origin"] for e in entries)),
        "sources_by_kind": dict(collections.Counter(s["kind"] for f in g["frames"].values() for s in f["sources"])),
        "by_axis": {ax: dict(collections.Counter(str(e["characteristics"][ax]) for e in entries).most_common())
                    for ax in ("combiner", "conditioning", "economic_function", "horizon", "turnover_class", "grouping")},
        "families_top10": dict(fam.most_common(10)),
        "errors": g["errors"],
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--canonical", required=True)
    ap.add_argument("--novel")
    ap.add_argument("--discovery", action="append",
                    help="repeatable; default docs/frames/10_frames_discovery.md")
    ap.add_argument("--mined-min-fills", type=int)
    ap.add_argument("--out", default=str(ST.LIBRARY))
    ap.add_argument("--now")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    disc = a.discovery or [str(ST.LIBRARY.parents[1] / "docs/frames/10_frames_discovery.md")]
    rep = build(a.canonical, a.novel, disc, a.mined_min_fills, pathlib.Path(a.out), a.now, a.dry_run)
    print(json.dumps(rep, indent=1, ensure_ascii=False))
    return 1 if rep["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

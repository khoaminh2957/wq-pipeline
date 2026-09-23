"""Promote audited staged mechanisms into the live library at a quota-day boundary.

Promotion mid-day changed the new arm's composition twice on ET 2026-09-09 and is recorded as that
day's confound (docs/harness5/round_1.md); this script exists so a promotion is one reviewed action
taken at the 11:00 local boundary, with the checks that decide it printed first.

Checks, all refusals (nothing is promoted unless every composite passes):
  loads          the composite and every leg it names load through forge.hypotheses
  arm            the composite is tagged `arm: new` (harness5 A/B)
  new leg        it names at least one leg that is not already live
  pair           its leg set is not already a live composite's
  combiner       a composite containing a bearish (sign -1) leg is [multiply] only -- the `gate`
                 branch leaves the gated-out half uniformly long after neutralisation (2026-09-08)
  partner        it does not sit on a leg the round's brief excludes (AVOID)
`--dry` prints the table and writes nothing. Without it, files move staged/ -> live and the count is
printed; the caller ships them to the VPS.
"""
from __future__ import annotations

import argparse
import collections
import glob
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from forge import hypotheses as H  # noqa: E402

LEGS, COMPS = ROOT / "forge/hypotheses", ROOT / "forge/composites"
# MEASURED 2026-09-09 (docs/harness5/round_2/diagnosis_ladder.md §3a, round_3/prod_vs_self.md §5):
# these legs have never cleared the IS-ladder's first window in any composite, or carry the whole
# book's PROD-correlation history. A new mechanism placed on them inherits a measured death stage.
AVOID = {"short_volume_ratio_informed", "news_ravenpack_composite_tone", "short_interest_surprise"}


def audit(legs_dir=LEGS, comps_dir=COMPS):
    """[(composite id, path, new legs, partners, refusals)] over forge/composites/staged/*.yaml."""
    lib = H.load_library(str(legs_dir))
    live_by = {h.id: h for h in lib}
    staged = {}
    for p in sorted(glob.glob(str(legs_dir / "staged/*.yaml"))):
        try:
            h = H.load_file(p)
        except Exception as exc:                       # noqa: BLE001 -- a broken leg refuses its composite
            staged[p] = exc
            continue
        staged[h.id] = (h, pathlib.Path(p))
    ids = set(live_by) | {k for k in staged if not isinstance(staged[k], Exception)}
    live_pairs = {tuple(sorted(c.legs)) for c in H.load_composites(str(comps_dir), lib)}
    out = []
    for p in sorted(glob.glob(str(comps_dir / "staged/*.yaml"))):
        path, refuse = pathlib.Path(p), []
        try:
            c = H.load_composite(p, ids)
        except Exception as exc:                       # noqa: BLE001
            out.append((path.stem, path, [], [], ["loads: %s" % exc]))
            continue
        new = [l for l in c.legs if l in staged and l not in live_by]
        partners = [l for l in c.legs if l not in new]
        if getattr(c, "arm", "current") != "new":
            refuse.append("arm != new")
        if not new:
            refuse.append("no new leg")
        if tuple(sorted(c.legs)) in live_pairs:
            refuse.append("leg set already live")
        def sign(l):
            h = live_by.get(l) or (staged.get(l) or (None,))[0]
            return getattr(h, "sign", 1) if h is not None else 1
        if any(sign(l) == -1 for l in c.legs) and "gate" in (c.combiners or []):
            refuse.append("bearish leg with gate combiner")
        bad = sorted(set(partners) & AVOID)
        if bad:
            refuse.append("partner on the avoid list: %s" % ",".join(bad))
        out.append((c.id, path, new, partners, refuse))
    return out, staged


def promote(rows, staged, dry=True) -> int:
    moved = 0
    for cid, path, new, _partners, refuse in rows:
        if refuse:
            continue
        if not dry:
            for leg in new:
                src = staged[leg][1]
                shutil.move(str(src), str(LEGS / src.name))
            shutil.move(str(path), str(COMPS / path.name))
        moved += 1
    return moved


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry", action="store_true", help="print the audit, move nothing")
    a = ap.parse_args(argv)
    rows, staged = audit()
    print("%-34s %-32s %-32s %s" % ("composite", "new leg", "partner(s)", "refusals"))
    for cid, _p, new, partners, refuse in rows:
        print("%-34s %-32s %-32s %s" % (cid[:34], (new[0] if new else "-")[:32], ",".join(partners)[:32],
                                        "; ".join(refuse) or "-"))
    ok = [r for r in rows if not r[4]]
    print("\n%d of %d promotable | partner spread %s"
          % (len(ok), len(rows), dict(collections.Counter(l for r in ok for l in r[3]))))
    n = promote(rows, staged, dry=a.dry)
    print(("DRY RUN: %d would move" if a.dry else "promoted %d composite(s) with their new legs") % n)
    return 0


if __name__ == "__main__":
    sys.exit(main())

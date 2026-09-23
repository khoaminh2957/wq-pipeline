#!/usr/bin/env python3
"""Classify every datafield by what it MEANS, using the local model, so operators can be chosen.

The existing classifier (tools/alpha_loop/strategy_lib.classify) matches keywords in the
description and returns FLOW/LEVEL/CHANGE/SENT. It is crude in a way that matters:

  * LEVEL is the DEFAULT — 12,892 of 20,307 fields are "LEVEL" mostly because nothing matched,
    so the biggest class means "unclassified", not "is a level".
  * Keywords are not meaning. `impact` is tagged SENT, but "price impact" is microstructure.
    `value` matches both "book value" and "value of the flag".
  * A field gets every label it happens to match, so `FLOW|LEVEL|SENT` can mean "rich" or
    "ambiguous" and nothing distinguishes them.

The labels here are chosen to answer ONE question: which operator is meaningful on this field.
That is what a generator actually needs.

    LEVEL      a stock/level measured at a point in time. ts_delta is meaningful.
    FLOW       a rate or per-period quantity (volume, count). Already a difference in disguise;
               ts_delta of it is an acceleration.
    CHANGE     ALREADY a difference/revision/growth. ts_delta gives a second derivative, which
               measured 1.3-3.0% zero-fail inside Model against 4.8% for LEVEL.
    RATIO      already normalised (per-share, percentage, ratio). Re-ranking is fine; re-scaling
               is redundant.
    SENTIMENT  a signed opinion or surprise measure.
    EVENT      sparse or discrete occurrences. Needs ts_backfill before anything else.
    META       describes HOW the datum was produced, not a market quantity — estimation method,
               confidence, coverage, identifier. EXCLUDE from alphas: one such field produced
               sharpe 11.18 / fitness 14.94, which is an artifact, not signal.

Batched through Ollama with strict JSON output, cached and resumable, so a 20k-field pass costs
nothing and survives interruption.

  python3 tools/classify_fields.py --limit 200          # try it
  python3 tools/classify_fields.py --all                # the whole catalogue
  python3 tools/classify_fields.py --validate 40        # sample for hand-checking
"""
import argparse, json, pathlib, sys, time, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / "breakthrough"))
OUT = ROOT / "state/field_roles.json"
OLLAMA = "http://localhost:11434/api/generate"
MODEL = "qwen2.5:7b-instruct"
LABELS = ["LEVEL", "FLOW", "CHANGE", "RATIO", "SENTIMENT", "EVENT", "META"]

SYSTEM = """You label financial datafields by what they MEASURE, so that a quant system can pick
the right operator. Use EXACTLY these labels:

LEVEL     a stock or level at a point in time (assets, price, open interest, estimate).
FLOW      a rate or per-period quantity (volume, count, number of trades, turnover).
CHANGE    ALREADY a difference: change, growth, revision, delta, momentum, acceleration.
RATIO     already normalised: a ratio, percentage, per-share, or margin.
SENTIMENT a signed opinion, surprise, or positive/negative score.
EVENT     sparse or discrete occurrences (announcement, filing, action happened).
META      describes HOW the data was produced, not a market quantity: estimation method,
          confidence, coverage, identifier, code, flag, data-source tag.

Rules:
- Give the ONE label that fits best, plus at most one secondary label if genuinely both.
- CHANGE beats LEVEL when the description says the field is itself a change or revision.
- RATIO beats LEVEL when the field is already a ratio or percentage.
- META beats everything: if it describes the data rather than the market, it is META.
- Never invent a label outside the list.

Reply with STRICT JSON only, an OBJECT with a "results" array holding ONE ENTRY PER INPUT FIELD,
in the same order. You must return exactly as many entries as there are input fields.

{"results": [{"id": "...", "label": "...", "second": "", "delta_ok": true}, ...]}

delta_ok is false when taking a time-difference of this field would be meaningless."""


# Deterministic rules for the cases a 7B model gets wrong INCONSISTENTLY. Hand-checking 18 labels
# found `actuals_value_currency_code` -> LEVEL (it is a currency code) while
# `actuals_reporting_currency` -> META correctly, and `accrued_liabilities_total` -> LEVEL while its
# near-identical twin `accrued_liabilities_total_2` -> META. Where the answer is decidable from the
# text, decide it in code; leave the model the genuinely ambiguous middle.
import re as _re
_META_RE = _re.compile(r"(currency|_code$|code\b|identifier|\bid\b|ticker|sedol|cusip|isin|"
                       r"exchange|flag|dummy|indicator variable|estimation method|confidence|"
                       r"coverage|data source|timestamp|fiscal (?:qtr|yr)|reporting currency)", _re.I)
_CHANGE_RE = _re.compile(r"\b(change|changes|growth|revision|revisions|delta|momentum|"
                         r"acceleration|year[- ]over[- ]year|quarter[- ]over[- ]quarter|"
                         r"increase in|decrease in)\b", _re.I)
_RATIO_RE = _re.compile(r"\b(ratio|percentage|percent|per share|margin|rate of|yield|"
                        r"proportion|share of)\b", _re.I)
_FLOW_RE = _re.compile(r"\b(volume|turnover|number of|count of|shares traded|trades|"
                       r"average daily volume)\b", _re.I)


def rule_label(fid, desc):
    """A label when the text decides it outright, else None."""
    t = f"{fid} {desc or ''}"
    if _META_RE.search(t):
        return "META", False
    if _CHANGE_RE.search(desc or ""):
        return "CHANGE", False          # a delta of a change is a second derivative
    if _FLOW_RE.search(desc or ""):
        return "FLOW", True
    if _RATIO_RE.search(desc or ""):
        return "RATIO", True
    return None, None


def ask(items, model, timeout=180):
    body = SYSTEM + "\n\nFIELDS:\n" + json.dumps(
        [{"id": i, "desc": (d or "")[:220]} for i, d in items], ensure_ascii=False)
    payload = json.dumps({"model": model, "prompt": body, "stream": False,
                          "format": "json", "options": {"temperature": 0}}).encode()
    req = urllib.request.Request(OLLAMA, data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = json.loads(r.read())["response"]
    j = json.loads(raw)
    # Ollama's format:json forces an OBJECT, and a 7B model asked for a bare array answers with a
    # single object for the first item only — 60 fields in, 0 labelled out. Accept every shape it
    # actually produces rather than assuming the one that was asked for.
    if isinstance(j, dict):
        lst = next((v for v in j.values() if isinstance(v, list)), None)
        if lst is not None:
            j = lst
        elif j.get("id"):
            j = [j]                       # a lone object = one classified field
        else:
            j = []
    return j if isinstance(j, list) else []


def load_catalogue():
    """id -> description, from the local crawl plus anything resolved on demand."""
    out = {}
    p = ROOT / "fetched/fields_all.jsonl"
    if p.exists():
        for line in p.open():
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("description"):
                out[d["id"]] = d["description"]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--batch", type=int, default=20)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--validate", type=int, default=0)
    args = ap.parse_args()

    cat = load_catalogue()
    try:
        done = json.load(open(OUT))
    except Exception:
        done = {}

    if args.validate:
        import random
        keys = [k for k in done if done[k].get("label")]
        random.Random(5).shuffle(keys)
        print(f"{'field':44} {'label':10} {'2nd':10} {'delta_ok':8} desc")
        for k in keys[:args.validate]:
            d = done[k]
            print(f"{k:44} {d.get('label',''):10} {d.get('second',''):10} "
                  f"{str(d.get('delta_ok','')):8} {cat.get(k,'')[:70]}")
        return

    todo = [(k, v) for k, v in cat.items() if k not in done]
    # Fields in the cells still being mined come first: a label on a field nothing uses is worth
    # nothing, and an interrupted run should have finished the useful part.
    try:
        import gen_pyramid as GP
        _full = GP.full_cells()
        want = {f for (cn, sn), pool in GP.load_fields().items()
                if GP.cell_weight(cn, sn, full=_full) > 0 for _, f, _ in pool}
        todo.sort(key=lambda kv: kv[0] not in want)
        print(f"  prioritising {sum(1 for k, _ in todo if k in want)} fields from live target cells",
              flush=True)
    except Exception:
        pass
    if not args.all:
        todo = todo[:args.limit]
    print(f"catalogue {len(cat)} fields | already labelled {len(done)} | to do {len(todo)}",
          flush=True)
    t0, n = time.time(), 0
    for i in range(0, len(todo), args.batch):
        chunk = todo[i:i + args.batch]
        # Decide everything the rules can decide BEFORE spending inference on it. 41% of fields
        # were rule-decidable yet were still being sent to the model twice, so nearly half of all
        # inference was answering questions already answered.
        ruled = {}
        rest = []
        for k, dsc in chunk:
            rl, dok = rule_label(k, dsc)
            if rl:
                ruled[k] = {"label": rl, "second": "", "delta_ok": dok, "by": "rule"}
            else:
                rest.append((k, dsc))
        done.update(ruled)
        n += len(ruled)
        if not rest:
            continue
        chunk = rest
        try:
            res = ask(chunk, args.model)
        except Exception as e:
            print(f"  batch failed ({str(e)[:60]}) — skipping", flush=True)
            continue
        got = {r.get("id"): r for r in res if isinstance(r, dict) and r.get("id")}
        # NO second opinion. It was added to catch the model contradicting itself, but measured
        # over three runs at temperature 0 on the fields the rules do NOT decide, agreement was
        # 30/30 = 100%: the model is deterministic, so a vote confirms a foregone conclusion at
        # double the cost. The inconsistency that motivated it was between two DIFFERENT
        # descriptions inside one call, which a re-run can never detect and the rules do.
        for k, dsc in chunk:
            r = got.get(k)
            if not r or r.get("label") not in LABELS:
                continue      # never guess: an unlabelled field stays unlabelled
            done[k] = {"label": r["label"],
                       "second": r.get("second") if r.get("second") in LABELS else "",
                       "delta_ok": bool(r.get("delta_ok", True)), "by": "model"}
        n += len(chunk)
        if i % (args.batch * 10) == 0:
            tmp = OUT.with_suffix(".tmp")
            json.dump(done, open(tmp, "w"))
            tmp.replace(OUT)
            rate = n / max(1e-9, time.time() - t0)
            print(f"  {len(done)} labelled | {rate:.1f} fields/s | "
                  f"{(len(todo)-n)/max(rate,1e-9)/60:.0f} min left", flush=True)
    tmp = OUT.with_suffix(".tmp")
    json.dump(done, open(tmp, "w"))
    tmp.replace(OUT)
    import collections
    print(f"\n{len(done)} fields labelled")
    for k, v in collections.Counter(d["label"] for d in done.values()).most_common():
        print(f"  {k:10} {v}")
    nod = sum(1 for d in done.values() if not d.get("delta_ok"))
    print(f"  delta meaningless on {nod} of them")


if __name__ == "__main__":
    main()

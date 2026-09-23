#!/usr/bin/env python3
"""Build OPERATORS.md — the most detailed operator reference (Khoa's directive, 2026-07-16):
RC-85 catalog + full 'show more' docs (fetched/rc/operator_docs/) + TABLE/EQUATION/IMAGE
+ SIMULATION_EXAMPLE blocks with REAL sim results (state/resim_results.jsonl, old_id=opex_*).

Khoa's rules:
- Content must match the Learn section 100% word-for-word (incl. show more), rendered as clean
  markdown (no HTML tags) — strip tags only, never change or drop a word.
- OPERATORS.md must be English-only.
- Only the clearly-marked "Simulation result" / "What the result reflects" blocks are our additions.

Re-run any time to regenerate (idempotent, local-only).
"""
import json, re, html, glob, pathlib
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent
ops = json.load(open(ROOT / "fetched/rc/operators.json"))

# ---- load detailed docs ----
docs = {}
for f in glob.glob(str(ROOT / "fetched/rc/operator_docs/*.json")):
    name = pathlib.Path(f).stem
    if not name.startswith("_"):
        docs[name] = json.load(open(f))

# ---- load example sim results (old_id -> journal row, keep last) ----
opex = {}
jf = ROOT / "state/resim_results.jsonl"
if jf.exists():
    for l in open(jf):
        try:
            j = json.loads(l)
        except Exception:
            continue
        oid = str(j.get("old_id", ""))
        if oid.startswith("opex_"):
            opex[oid] = j
targets = {t["id"]: t for t in json.load(open(ROOT / "state/opex_targets.json"))} \
    if (ROOT / "state/opex_targets.json").exists() else {}

# ---- VERBATIM TEXT: keep every word exactly as in Learn, rendered as clean markdown (tags stripped) ----
def text_verbatim(s):
    s = re.sub(r"<br\s*/?>", "\n", s)
    s = re.sub(r"</p>\s*<p>", "\n\n", s)
    s = re.sub(r"</?p[^>]*>", "\n", s)
    s = re.sub(r"<li[^>]*>", "\n- ", s); s = re.sub(r"</li>", "", s)
    s = re.sub(r"</?[uo]l[^>]*>", "\n", s)
    s = re.sub(r"<b>(.*?)</b>", r"**\1**", s, flags=re.S)
    s = re.sub(r"<strong>(.*?)</strong>", r"**\1**", s, flags=re.S)
    s = re.sub(r"<i>(.*?)</i>", r"*\1*", s, flags=re.S)
    s = re.sub(r"<em>(.*?)</em>", r"*\1*", s, flags=re.S)
    s = re.sub(r"<code[^>]*>(.*?)</code>", r"`\1`", s, flags=re.S)
    s = re.sub(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', r"[\2](\1)", s, flags=re.S)
    s = re.sub(r"<[^>]+>", "", s)          # strip any remaining tags, never touch the words
    s = html.unescape(s)
    s = re.sub(r"[ \t]{2,}", " ", s)       # collapse whitespace introduced by HTML formatting
    s = re.sub(r" +\n", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()

def table_verbatim(v):
    """TABLE -> markdown table, every cell kept 100% intact."""
    data = v.get("data") or []
    if not data:
        return ""
    out = []
    out.append("| " + " | ".join(str(c) for c in data[0]) + " |")
    out.append("|" + "---|" * len(data[0]))
    for row in data[1:]:
        out.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(out)

# ---- EXECUTOR analysis: what each sim result reflects about the operator (NOT Learn content) ----
ANALYSIS = {
 "opex_group_mean": "Alpha = inverse of the industry-mean earnings yield, so every stock in an industry receives the SAME value — this is an INDUSTRY-ROTATION bet (overweight richly-valued/growth industries). The moderate sharpe 0.53 shows group_mean turns a stock-level ratio into a GROUP-level signal; it is stronger as a group benchmark (compare each stock against its industry mean) than standing alone.",
 "opex_hump": "A 5-day price reversal wrapped in hump: sharpe 1.11, turnover 0.433. hump limits the frequency/magnitude of position changes — turnover stays high here because hump=0.00001 is far too small to bind. Takeaway: hump is a TURNOVER VALVE; it only works with a threshold large enough (default 0.01), it does not change the signal itself.",
 "opex_if_else": "Doubling a 3-day reversal signal WHEN volume > adv20: sharpe 1.58 — better than the plain reversal. Takeaway: if_else enables CONDITIONAL SCALING (regime switching) — reversals accompanied by a volume spike are more reliable; this is the canonical 'conditional leverage' pattern for if_else.",
 "opex_is_nan": "Replacing NaN in rank(sales) with a neutral 0.5: turnover 0.007 = near buy-and-hold tilt toward high-sales names. Sharpe 0.40 is weak — the lesson here is DATA HYGIENE (don't let NaN break positions), not signal generation.",
 "opex_kth_element": "Takes the most recent valid value of sales/assets within 252 days (k=1, ignoring NaN/0): a near-static operating-quality tilt, turnover 0.013 ultra-low, sharpe 0.55. Takeaway: kth_element = STALENESS-TOLERANT DATA ACCESS (sparse fundamentals across reporting periods) — it keeps the signal stable between updates.",
 "opex_max": "max(close, vwap) is just a PRICE LEVEL — sharpe 0.13 ≈ 0. Takeaway: absolute price levels carry no cross-sectional information; this example is a syntax demo, not a strategy. Use max to select between value branches inside a formula, not as a bare alpha.",
 "opex_min": "min(close, vwap) — same as max: absolute price levels carry no signal (sharpe 0.14). Syntax demo.",
 "opex_multiply": "rank(-returns) × rank(volume/adv20), filter=true: **sharpe 1.95 — the BEST of all 17 examples**, dd 0.077. Takeaway: multiply builds SIGNAL INTERACTIONS — a 1-day reversal confirmed by volume is far stronger than either leg alone (a volume spike marks trustworthy reversals). This is the classic 'signal × confirmation' pattern.",
 "opex_power_1": "The fixed version runs but sharpe −0.83, turnover 1.44, dd 3.15 = UNINVESTABLE. Takeaway: power with a DATA-DEPENDENT EXPONENT on signed returns explodes/NaNs out — positions go haywire. Lesson: power suits NORMALIZED POSITIVE inputs (rank, sigmoid, …); avoid fractional exponents on negative values.",
 "opex_power_2": "sigmoid(close) via power: sharpe 0.22 ≈ 0. Takeaway: any MONOTONE TRANSFORM of a price level (sigmoid/log/zscore…) creates no new cross-sectional information — this example demonstrates how to build math functions, not an alpha source.",
 "opex_quantile": "quantile(close, gaussian, 0.5): sharpe 0.22 ≈ 0. Takeaway: quantile is a DISTRIBUTION-NORMALIZATION tool (forces the signal into a gaussian shape) — reshaping a price level generates no information; its value is producing cleaner inputs for a REAL signal computed beforehand.",
 "opex_ts_corr": "ts_corr(vwap, close, 20): sharpe 0.26 but dd only 0.093. vwap and close are usually correlated ≈ 1; the days they diverge flag intraday buying/selling pressure. Takeaway: weak standalone but STABLE (low drawdown) — good as an INGREDIENT in composites (a microstructure-pressure gauge), not as an independent alpha.",
 "opex_ts_product": "power(ts_product(returns,10), 1/10): sharpe −0.43, dd 0.97. Takeaway: ts_product on RAW returns (~0.01) is numerically degenerate — a product of near-zero values with flipping signs. Proper compounding needs (1+returns). The docs example demonstrates syntax but is FINANCIALLY WRONG as written — use with care.",
 "opex_ts_regression": "Fixed version (beta of smoothed volume on 2-day returns, 252-day window): sharpe −0.10 ≈ 0. Takeaway: a raw regression coefficient is not a directional signal; ts_regression's power is in RESIDUALS/HEDGING (rettype variants — residualize a signal against another factor), not in using beta as the alpha.",
 "opex_ts_skewness": "ts_skewness(returns, 60): sharpe 0.18, dd 0.815, only 3 checks pass. Takeaway: going long positive-skew names = lottery preference — a thin signal with heavy tail risk; higher moments are noisy and need pairing with momentum/quality rather than standing alone.",
 "opex_vector_neut": "vector_neut(open, close): sharpe 1.45, fit 0.53 but turnover 0.902 (extreme). Takeaway: orthogonalizing open against close removes the shared price-level component, leaving OVERNIGHT-GAP STRUCTURE — a real, fast, transaction-cost-heavy signal. vector_neut = an ORTHOGONALIZATION tool (strip one variable's exposure out of a signal), the vector-space sibling of group_neutralize.",
 "opex_zscore": "zscore(close): sharpe 0.16 ≈ 0, turnover 0.012. Takeaway: a cross-sectional zscore of the PRICE LEVEL = long expensive-price stocks — no information; zscore is a NORMALIZATION step in a pipeline (bring signals onto one scale), it does not create alpha by itself.",
}

def sim_example_md(op_name, v, idx, counts):
    tid = f"opex_{op_name}" + (f"_{idx}" if counts > 1 or op_name == "power" else "")
    st = v.get("settings", {})
    lines = []
    lines.append("**⚗️ SIMULATION EXAMPLE (from the docs — actually simulated on our account):**")
    lines.append("```")
    lines.append(v.get("regular", ""))
    lines.append("```")
    lines.append(f"Settings: region={st.get('region')} · universe={st.get('universe')} · delay={st.get('delay')} · "
                 f"decay={st.get('decay')} · neut={st.get('neutralization')} · trunc={st.get('truncation')} · nan={st.get('nanHandling')}")
    t = targets.get(tid, {})
    notes = []
    if t.get("_fixed_brackets"):
        notes.append("docs are missing a closing parenthesis — fixed before simulating")
    if t.get("_fixed_truncation"):
        notes.append("docs specify truncation>1 (API requires ≤1) — simulated with 1.0")
    if t.get("_fixed_case"):
        notes.append('docs define "Event" but call "event" (case mismatch; kills the whole multi-sim) — fixed before simulating')
    if notes:
        lines.append(f"> ⚠ Platform docs bug: {'; '.join(notes)}")
    r = opex.get(tid)
    if r and r.get("alpha"):
        ck = r.get("checks") or []
        lines.append(f"**Simulation result (sid `{r['alpha']}`):** sharpe **{r.get('sharpe')}** · fitness **{r.get('fitness')}** · "
                     f"turnover {r.get('turnover')} · returns {r.get('returns')} · drawdown {r.get('drawdown')}")
        lines.append(f"Checks PASS: {', '.join(ck) if ck else '(none)'}")
        if r.get("message"):
            lines.append(f"Platform message: {str(r['message']).strip()}")
        if ANALYSIS.get(tid):
            lines.append("")
            lines.append(f"**📊 What the result reflects** *(EXECUTOR analysis, not Learn content)*: {ANALYSIS[tid]}")
    elif r:
        msg = r.get("message") or r.get("status") or r.get("error")
        lines.append(f"**Simulation result: ERROR (docs bug — the verbatim example fails)** — `{str(msg)[:250]}`")
        fx = opex.get(tid + "_fixed"); ft = targets.get(tid + "_fixed", {})
        if fx and fx.get("alpha"):
            ck = fx.get("checks") or []
            lines.append("")
            lines.append(f"**🔧 Fixed version** ({ft.get('_fixed_note','')}):")
            lines.append("```")
            lines.append(ft.get("formula", ""))
            lines.append("```")
            lines.append(f"**Fixed-version result (sid `{fx['alpha']}`):** sharpe **{fx.get('sharpe')}** · fitness **{fx.get('fitness')}** · "
                         f"turnover {fx.get('turnover')} · returns {fx.get('returns')} · drawdown {fx.get('drawdown')}")
            lines.append(f"Checks PASS: {', '.join(ck) if ck else '(none)'}")
            if ANALYSIS.get(tid):
                lines.append("")
                lines.append(f"**📊 What the result reflects** *(EXECUTOR analysis, not Learn content)*: {ANALYSIS[tid]}")
    else:
        lines.append("*(not yet simulated / result not in journal)*")
    return "\n".join(lines)

# ---- fixed-note translations (targets file stores Vietnamese notes; render English) ----
FIXED_NOTES_EN = {
    "opex_power_1_fixed": "dropped the leading bare statement (docs bug: unused expressions)",
    "opex_ts_regression_fixed": "replaced ts_returns (operator does not exist in RC-85) with (close - ts_delay(close, 2))/ts_delay(close, 2)",
}
for k, v in FIXED_NOTES_EN.items():
    if k in targets:
        targets[k]["_fixed_note"] = v

# ---- assemble ----
bycat = defaultdict(list)
for o in ops:
    bycat[o.get("category", "Other")].append(o)
order = ["Arithmetic", "Logical", "Time Series", "Cross Sectional", "Vector", "Transformational", "Group", "Special"]
cats = sorted(bycat, key=lambda c: (order.index(c) if c in order else 99, c))

L = []
L.append("# WQ BRAIN — Exhaustive Operators Reference (Learn section, full 'show more')")
L.append("")
L.append("> **MANDATORY: read this file FIRST every time you build an alpha** (Khoa's directive, 2026-07-16).")
L.append("> Sources: RC-85 allowlist (`fetched/rc/operators.json`) + each operator's detailed docs page")
L.append("> (`GET /operators/{name}` → `fetched/rc/operator_docs/`) + **17 SIMULATION_EXAMPLEs actually simulated** (journal `state/resim_results.jsonl`).")
L.append("> **Docs content is kept 100% word-for-word identical to the Learn section (incl. show more)**, rendered as clean markdown (no HTML tags); only the 'Simulation result' / 'What the result reflects' blocks are our additions.")
n_doc = sum(1 for o in ops if o["name"] in docs)
L.append(f"> Total: **{len(ops)} operators** / {len(cats)} categories · {n_doc} with detailed docs ('show more') · {len(ops)-n_doc} without a dedicated page (404 'No Reference') · {sum(1 for k in opex if not k.endswith('_fixed'))} examples simulated.")
L.append("> Only operators listed here are usable (anything else → 400 reject). Regenerate: `python tools/build_operators_md.py`.")
L.append("")
L.append("## Quick index (by category)")
for c in cats:
    names = ", ".join(f"`{o['name']}`" + ("†" if o["name"] in docs else "") for o in sorted(bycat[c], key=lambda x: x["name"]))
    L.append(f"- **{c}** ({len(bycat[c])}): {names}")
L.append("")
L.append("† = detailed docs below")
L.append("")
L.append("---")

for c in cats:
    L.append("")
    L.append(f"## {c}")
    for o in sorted(bycat[c], key=lambda x: x["name"]):
        name = o["name"]
        L.append("")
        L.append(f"### `{name}`")
        if (o.get("definition") or "").strip():
            L.append("```")
            L.append(o["definition"].strip())
            L.append("```")
        if (o.get("description") or "").strip():
            L.append(o["description"].strip())
        meta = []
        if o.get("level"):
            meta.append(f"level={o['level']}")
        if o.get("scope"):
            meta.append(f"scope={','.join(o['scope'])}")
        L.append(f"<sub>{' · '.join(meta)}</sub>")
        d = docs.get(name)
        if not d:
            L.append("")
            L.append("*(no dedicated detailed-docs page on the platform — 404 'No Reference')*")
            continue
        L.append("")
        L.append("<details open><summary><b>📖 Detailed docs (show more)</b></summary>")
        L.append("")
        sim_idx = 0
        sim_count = sum(1 for x in d.get("content", []) if x.get("type") == "SIMULATION_EXAMPLE")
        for blk in d.get("content", []):
            t = blk.get("type"); v = blk.get("value")
            if t == "TEXT" and isinstance(v, str):
                L.append(text_verbatim(v)); L.append("")     # verbatim Learn wording — 100%
            elif t == "TABLE" and isinstance(v, dict):
                L.append(table_verbatim(v)); L.append("")
            elif t == "EQUATION":
                if isinstance(v, str):
                    L.append(text_verbatim(v))               # verbatim
                else:
                    L.append("```json"); L.append(json.dumps(v, ensure_ascii=False)); L.append("```")
                L.append("")
            elif t == "IMAGE" and isinstance(v, dict):
                L.append(f"🖼 Image: [{v.get('title','image')}]({v.get('url','')}) ({v.get('width')}×{v.get('height')})"); L.append("")
            elif t == "SIMULATION_EXAMPLE" and isinstance(v, dict):
                sim_idx += 1
                L.append(sim_example_md(name, v, sim_idx, sim_count)); L.append("")
        L.append("</details>")

out = ROOT / "OPERATORS.md"
out.write_text("\n".join(L))
print(f"OPERATORS.md rebuilt (English-only): {len(L)} lines · {len(ops)} ops · {n_doc} detailed · {len(opex)} sim results embedded")

"""The author loop: a hosted model proposes a mechanism, the machine grades it, the model repairs.

RULE 1 holds: nothing here simulates or spends platform quota. It writes YAML into the STAGED
library (`forge/*/staged/`), which the live loader cannot see (its glob is non-recursive), so the
running loop is untouched -- Khoa's tick, 2026-09-19: "Tác giả ngoại tuyến, loop giữ nguyên tất định".

The accuracy mechanisms, each aimed at a failure a small model actually makes:
  invents field ids          -> every id is RETRIEVED into the prompt; verify() checks it exists
  mis-states units / kinds   -> forge.typed judges the rendered formula (the live pre-sim gate)
  writes a sign from nothing -> the label file's own reading of the field is checked against it
  re-proposes a sibling      -> the family pairs already in the library are listed and checked
  writes vague economics     -> the 8 hard gates of fetched/hypothesis_standard.md
  cannot self-correct        -> it never grades itself; verify()'s report is fed back verbatim
                               ("LLMs cannot self-correct", vetted in docs/harness5/papers_harness.md)

The model is a parameter. Ollama is the default host because it is already installed; any OpenAI-
compatible endpoint works by pointing --host at it.
"""
from __future__ import annotations

import argparse
from concurrent import futures
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from forge.llm import retrieve as RT  # noqa: E402
from forge.llm import verify as V  # noqa: E402

STAGED_LEGS = ROOT / "forge/hypotheses/staged"
STAGED_COMPS = ROOT / "forge/composites/staged"
DEFAULT_HOST = "http://localhost:11434"

SYSTEM = """You write ONE economic mechanism for a quantitative equity alpha, as two YAML files.

What matters is the ECONOMICS, not the formula. A formula that expresses no force is worthless: a
random formula generator was run against a hand-written library for five live rounds and lost every
one (0.1% of its alphas reached the Sharpe bar against 2.6%). So state a real force, name who is on
the other side of the trade, and say which way it predicts and why.

HARD RULES. A machine checks every one of these before anything is simulated. Breaking one wastes
the whole proposal, so read them as constraints, not advice.
1. Every field id you write MUST be copied exactly from the FIELDS table below. Never invent one.
2. The partner leg id MUST be copied exactly from the PARTNERS table below.
3. Your two families MUST NOT form a pair already listed in USED PAIRS.
4. The leg's `sign` must agree with the field's sign in the FIELDS table. If you believe the table
   is wrong, you may disagree, but then the `notes` block must say so and why.
5. A field with cadence `quarterly` or `annual` MUST be wrapped in ts_backfill in the template.
6. A field with cov below 0.50 MUST declare a density rule (`zero` for a count or score where a gap
   means "no event", `backfill` for a level where a gap means "no change").
7. Never divide or subtract across different units. Rank-bound both operands before multiplying.
8. `mechanism` must be over 25 words, must not merely restate the composite's own name, and must
   describe the middle link: why does this quantity move the price LATER?
9. `counterparty` must name a concrete agent class: retail investors, index funds, pension funds,
   mandate-driven institutions, market makers, dealers, short sellers, sell-side analysts, ...
10. `source` must start with "EX-ANTE — " and contain a dated citation (author year).
11. `regimes` must carry all four keys with a sign each, reasoned for THIS conjunction.

EVERY KEY BELOW IS MANDATORY. The leg is rejected outright if `template` is missing -- that single
omission was 32 of 83 rejections on 2026-09-19. `template` is the expression skeleton: it uses the
literal placeholders {signal}, {w} and {group}, which the compiler substitutes; you do NOT write a
field id into it.

WORKED EXAMPLE of an accepted leg (copy this shape, change the economics):

```yaml leg
id: news_ravenpack_composite_tone
family: tone_composite
category: News
title: RavenPack composite sentiment predicts short-horizon drift
mechanism: >
  The mean composite sentiment score summarises the tone of a firm's news flow on a 0-100 scale, and
  positive tone diffuses into prices slowly because the investors who read the feed are not the ones
  setting the marginal price that week, so the most positively covered names keep drifting up.
counterparty: retail holders who react to headlines with a lag
sign: 1
source: "EX-ANTE — Tetlock 2007, negative media tone predicts downward pressure on prices"
datasets: [news46]
signal:
  fields: [mws46_ravenpack_mean_ssc, mws46_ravenpack_mean_ssc_fast_d1]
  density: backfill
  density_window: 5
template: "group_rank(ts_mean({signal}, {w}), {group})"
params:
  w: [5, 10, 20]
  group: [subindustry, industry, sector]
settings:
  neutralization: [STATISTICAL, INDUSTRY, SUBINDUSTRY]
  decay: [4, 8]
  truncation: 0.08
regions: [USA]
delays: [1]
notes: >
  a 0-100 score, so a day with no news is "no change" and backfills rather than reading as the most
  negative value.
```

A bearish leg (sign: -1) starts its template with a minus:
  template: "-group_rank(ts_mean({signal} / {signal2}, {w}), {group})"

OUTPUT FORMAT. Exactly two fenced blocks, nothing else, no commentary:

```yaml leg
id: <snake_case_id>
family: <one word, e.g. accruals, profitability, tone, insider, options, short>
category: <the pyramid category from the FIELDS table, e.g. Fundamental>
title: <one line>
mechanism: >
  <2-4 sentences: the force, and why the price moves later>
counterparty: <concrete agent class>
sign: <1 or -1>
source: "EX-ANTE — <Author Year>, <what they showed>"
datasets: [<dataset id from the table>]
signal:
  fields: [<field ids copied from the table>]
template: "<expression using {signal} {w} {group}>"
params:
  w: [5, 20, 60]
  group: [subindustry, industry, sector]
settings:
  neutralization: [SUBINDUSTRY, INDUSTRY, STATISTICAL]
  decay: [4, 8]
  truncation: 0.08
regions: [USA]
delays: [1]
notes: >
  <any override of the FIELDS table, and why>
```

```yaml composite
id: <snake_case_id>
title: <one line>
arm: new
legs: [<your new leg id>, <a partner leg id from the table>]
families: [<your family>, <the partner's family>]
combiners: [multiply]
mechanism: >
  <why the CONJUNCTION predicts returns -- not a paraphrase of either leg>
counterparty: <concrete agent class>
source: "EX-ANTE — <Author Year>, <what they showed>"
regimes: {value_winter_2014_2020: "+", momentum_crash_2016: "0", covid_2020: "+", rate_shock_2022: "-"}
strongest_in: <where the effect is largest>
weakens_when: <what breaks it>
settings:
  neutralization: [SUBINDUSTRY, INDUSTRY, STATISTICAL]
  decay: [4, 8]
  truncation: 0.08
notes: >
  <reason each regime sign for THIS conjunction>
```"""

TASK = """CATEGORY must be copied EXACTLY from this list -- it is the pyramid cell your leg fills, and a
category outside it renders nothing at all:
{categories}

FIELDS you may use (dataset {dataset}, {region}, fewest users first -- uncrowded is the point):
{fields}

PARTNERS you may combine with:
{partners}

USED PAIRS (a proposal repeating one of these is a sibling of something already running, and
siblings read production correlation 0.79-0.85, which is over the submit line):
{pairs}

Write one leg and one composite now. Both fenced blocks, nothing else."""

REPAIR = """Your proposal was rejected by the machine checker. Every line below is a fact about your
YAML, not an opinion. Fix exactly these and output both blocks again, complete, nothing else.

{report}"""

BLOCK = re.compile(r"```(?:yaml)?[ \t]*(leg|composite)[ \t]*\n(.*?)```", re.S | re.I)
# A reasoning model emits its scratchpad first. vLLM's `--reasoning-parser qwen3` moves that into
# `reasoning_content` and leaves `content` clean, but the server is a rented box someone else
# configured, so strip it here too rather than trust a flag we cannot see.
THINK = re.compile(r"<(think|thinking|reasoning)>.*?</\1>", re.S | re.I)


class Model:
    """Whatever is hosting the weights, local or rented.

    Two wire formats, because the host is a rented box and its server is not our choice:
      openai  POST /v1/chat/completions  -- vLLM, SGLang, TGI, llama.cpp --api-server, and any
              commercial endpoint. This is what a vast.ai vLLM image serves.
      ollama  POST /api/chat             -- an ollama host.
    Nothing else about the pipeline depends on which one is in use.

    MEASURED 2026-09-19, and the reason the host moved off the laptop: qwen2.5:7b-instruct, given
    the retrieved fields, the exact category list and three repair rounds, kept 0 of 3 mechanisms.
    Its failures were capability, not information -- it invented template syntax
    ("{signal.<field id>}" for "{signal}"), left a citation placeholder ("<NAME> (2023)"), and wrote
    mechanisms that restate the signal instead of naming the middle link. A larger model is the
    lever; the checks below it do not change.
    """

    def __init__(self, name: str, host: str = DEFAULT_HOST, temperature: float = 0.8, timeout: int = 600,
                 api: str = "openai", api_key: str = "", max_tokens: int = 4000, thinking: bool = False):
        self.name, self.host, self.temperature = name, host.rstrip("/"), temperature
        self.timeout, self.api, self.api_key, self.max_tokens = timeout, api, api_key, max_tokens
        self.thinking = thinking

    def chat(self, messages: list, schema: dict | None = None) -> str:
        """`schema` turns on vLLM constrained decoding (`guided_json`, xgrammar backend): invalid
        tokens are masked at sampling time, so the reply CANNOT violate the schema.

        This is the difference between catching a failure and making it impossible. The dominant
        small-model failure here is an invented field id; put the retrieved ids in the schema as an
        `enum` and the model is unable to emit anything else -- no repair round, no wasted tokens.
        Only the openai wire carries it; an ollama host ignores the key and the output checks still
        run, so nothing depends on the server honouring it.
        """
        headers = {"Content-Type": "application/json"}
        if self.api == "ollama":
            url = self.host + "/api/chat"
            body = {"model": self.name, "messages": messages, "stream": False,
                    "options": {"temperature": self.temperature, "num_ctx": 16384}}
        else:
            url = self.host + "/v1/chat/completions"
            body = {"model": self.name, "messages": messages, "stream": False,
                    "temperature": self.temperature, "max_tokens": self.max_tokens}
            if not self.thinking:
                # MEASURED 2026-09-19 against Qwen3.8-27B-FP8: on the real 3,353-token prompt the
                # model spent ALL 8,000 completion tokens on reasoning and returned content of
                # length ZERO -- finish_reason "length", reasoning_tokens 8000. Twelve mechanisms
                # in a row failed on "format" for that reason alone, at ~358 s each. Filling a
                # template needs no chain of thought, so it is switched off at the chat template.
                body["chat_template_kwargs"] = {"enable_thinking": False}
            if schema:
                body["guided_json"] = schema
                body["guided_decoding_backend"] = "xgrammar"
            if self.api_key:
                headers["Authorization"] = "Bearer " + self.api_key
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            payload = json.loads(r.read())
        if self.api == "ollama":
            return payload["message"]["content"]
        return payload["choices"][0]["message"]["content"]


def parse(text: str) -> tuple:
    """(leg_yaml, composite_yaml) from the model's reply; (None, None) when it did not comply."""
    found = {kind.lower(): body.strip() for kind, body in BLOCK.findall(THINK.sub("", text or ""))}
    return found.get("leg"), found.get("composite")


def _ids(leg_yaml: str, comp_yaml: str) -> tuple:
    def first_id(t):
        m = re.search(r"^id:\s*([A-Za-z0-9_]+)", t or "", re.M)
        return m.group(1) if m else None
    return first_id(leg_yaml), first_id(comp_yaml)


def propose(ctx, model: Model, dataset: str, tries: int = 3, n_fields: int = 24, seed_note: str = "") -> dict:
    """One mechanism: generate, grade, repair, and keep it staged only if it finally passes."""
    rows = RT.shortlist(ctx, dataset=dataset, n=n_fields)
    if not rows:
        return {"ok": False, "dataset": dataset, "why": "no signed fields in this dataset at %s" % ctx.key}
    task = TASK.format(dataset=dataset, region=ctx.key, fields=RT.fields_block(rows),
                       categories=", ".join(sorted({c.category for c in ctx.cells})),
                       partners=RT.partners_block(RT.partners(ctx)), pairs=RT.pairs_block(RT.used_pairs(ctx)))
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": task + seed_note}]
    STAGED_LEGS.mkdir(parents=True, exist_ok=True)
    STAGED_COMPS.mkdir(parents=True, exist_ok=True)
    history = []
    for attempt in range(1, tries + 1):
        t0 = time.time()
        try:
            reply = model.chat(messages)
        except (urllib.error.URLError, OSError, KeyError) as exc:
            return {"ok": False, "dataset": dataset, "why": "model call failed: %s" % exc, "attempts": attempt}
        leg_y, comp_y = parse(reply)
        if not leg_y or not comp_y:
            history.append({"attempt": attempt, "failed": ["format"], "s": round(time.time() - t0, 1)})
            messages += [{"role": "assistant", "content": reply},
                         {"role": "user", "content": REPAIR.format(report="You did not output both fenced blocks "
                                                                   "(```yaml leg and ```yaml composite).")}]
            continue
        leg_id, comp_id = _ids(leg_y, comp_y)
        if not leg_id or not comp_id:
            history.append({"attempt": attempt, "failed": ["no-id"], "s": round(time.time() - t0, 1)})
            messages += [{"role": "assistant", "content": reply},
                         {"role": "user", "content": REPAIR.format(report="A block has no `id:` line.")}]
            continue
        lp, cp = STAGED_LEGS / ("%s.yaml" % leg_id), STAGED_COMPS / ("%s.yaml" % comp_id)
        lp.write_text(leg_y + "\n")
        cp.write_text(comp_y + "\n")
        v = V.verify(lp, cp, ctx)
        history.append({"attempt": attempt, "failed": v.get("failed", []), "s": round(time.time() - t0, 1),
                        "leg": leg_id, "composite": comp_id})
        if v["ok"]:
            return {"ok": True, "dataset": dataset, "leg": leg_id, "composite": comp_id,
                    "attempts": attempt, "history": history, "verify": v}
        lp.unlink(missing_ok=True)
        cp.unlink(missing_ok=True)
        messages += [{"role": "assistant", "content": reply},
                     {"role": "user", "content": REPAIR.format(report=V.report(v))}]
    return {"ok": False, "dataset": dataset, "why": "failed after %d attempts" % tries, "history": history}


def propose_many(ctx, model: Model, datasets: list, tries: int = 3, concurrency: int = 16,
                 on_done=None) -> list:
    """Every mechanism in flight at once, because a rented GPU is billed by the second.

    WHY, and it is the difference between $1 and $0.10 a batch: generating a token requires reading
    the WHOLE model out of VRAM, and that one read serves every request in the batch. One request in
    flight pays the full bandwidth cost for one token; thirty-two in flight pay it for thirty-two.
    vLLM does the batching server-side (continuous batching), so all this side has to do is keep the
    endpoint fed. The repair loop inside one mechanism stays sequential -- attempt 2 needs attempt
    1's verdict -- but different mechanisms are independent and run together.

    `concurrency` is bounded by the server's KV-cache budget, not by this side: past it, vLLM queues
    rather than fails, so a too-high value costs latency, never correctness.
    """
    _ = ctx.burned                              # force the lazy scan before threads touch it
    out = []
    with futures.ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        pending = {pool.submit(propose, ctx, model, ds, tries): ds for ds in datasets}
        for fut in futures.as_completed(pending):
            ds = pending[fut]
            try:
                r = fut.result()
            except Exception as exc:            # noqa: BLE001 -- one bad dataset must not kill the batch
                r = {"ok": False, "dataset": ds, "why": "%s: %s" % (type(exc).__name__, exc)}
            out.append(r)
            if on_done:
                on_done(r, len(out), len(datasets))
    return out


def probe(model: Model) -> int:
    """First contact with a rented box: is it up, does it obey the output format, how fast is it?

    Worth its own mode because a rented GPU bills by the second: find out that the endpoint is
    wrong, or that the model ignores fenced blocks, before paying for a batch.
    """
    ask = ("Reply with exactly two fenced blocks and nothing else:\n"
           "```yaml leg\nid: probe_leg\n```\n```yaml composite\nid: probe_comp\n```")
    t0 = time.time()
    try:
        reply = model.chat([{"role": "system", "content": "You follow output formats exactly."},
                            {"role": "user", "content": ask}])
    except Exception as exc:                                    # noqa: BLE001 -- any transport failure is the answer
        print("endpoint %s (%s api) UNREACHABLE: %s: %s" % (model.host, model.api, type(exc).__name__, exc))
        return 2
    dt = time.time() - t0
    leg, comp = parse(reply)
    words = len(reply.split())
    print("endpoint  %s (%s api)" % (model.host, model.api))
    print("model     %s" % model.name)
    print("latency   %.1fs for ~%d words  (~%.0f words/s)" % (dt, words, words / max(dt, 1e-6)))
    print("format    %s" % ("obeys fenced blocks" if (leg and comp) else "DOES NOT obey fenced blocks -- the loop will burn repair rounds"))
    if not (leg and comp):
        print("reply     %s" % reply[:300].replace("\n", " "))
    return 0 if (leg and comp) else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", default="Qwen/Qwen3.8-27B-FP8",
                    help="MEASURED 2026-09-19: this one keeps 18%% of proposals through all 8 checks; "
                         "Bonsai-2-27B kept 0 of 20 on the same prompt and datasets")
    ap.add_argument("--host", default=DEFAULT_HOST, help="e.g. http://<vast-ip>:8000 for a rented vLLM box")
    ap.add_argument("--api", choices=("openai", "ollama"), default="openai")
    ap.add_argument("--api-key", default="", help="bearer token if the rented endpoint sets one")
    ap.add_argument("--n", type=int, default=3, help="how many mechanisms to attempt")
    ap.add_argument("--tries", type=int, default=3, help="repair rounds per mechanism")
    ap.add_argument("--datasets", default="", help="comma list; default = signed datasets, most material first")
    ap.add_argument("--max-users", type=int, default=None,
                    help="optional crowding cap. OFF by default since 2026-09-20: crowding was measured "
                         "not to predict correlation (r=-0.001) while capping it cost ~0.4 Sharpe")
    ap.add_argument("--temperature", type=float, default=0.8)
    ap.add_argument("--concurrency", type=int, default=16,
                    help="mechanisms in flight at once; a rented GPU batches them server-side")
    ap.add_argument("--probe", action="store_true", help="check the endpoint and measure it, spend nothing else")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    if a.probe:
        return probe(Model(a.model, a.host, a.temperature, api=a.api, api_key=a.api_key))

    ctx = V.Context()
    if a.datasets:
        pool = [d.strip() for d in a.datasets.split(",") if d.strip()]
    else:
        pool = [d["dataset"] for d in RT.datasets_for_author(ctx, max_users=a.max_users)][: a.n * 3]
    if not pool:
        print("no candidate datasets%s" % ("" if a.max_users is None else " under %d users" % a.max_users))
        return 2
    model = Model(a.model, a.host, a.temperature, api=a.api, api_key=a.api_key)
    t0 = time.time()

    def show(r, done, total):
        if a.json:
            return
        print("%-4s [%3d/%3d] %-26s %s" % ("KEPT" if r["ok"] else "drop", done, total, r["dataset"],
                                           r.get("composite") or r.get("why", "")))
        for h in r.get("history", []):
            print("            attempt %d  %5.1fs  %s" % (h["attempt"], h["s"],
                                                          ", ".join(h["failed"]) or "all checks pass"))

    results = propose_many(ctx, model, pool[: a.n], tries=a.tries, concurrency=a.concurrency, on_done=show)
    kept = [r for r in results if r["ok"]]
    if a.json:
        print(json.dumps({"kept": len(kept), "tried": len(results), "results": results}, indent=1, default=str))
    else:
        dt = time.time() - t0
        print("\n%d/%d kept in staged/ after %.0fs  (%d in flight, %.1f mechanisms/min)"
              % (len(kept), len(results), dt, a.concurrency, 60.0 * len(results) / max(dt, 1e-6)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

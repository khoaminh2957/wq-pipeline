# What a submission 403 actually is (measured 2026-09-22, at Khoa's instruction "tìm hiểu triệt để")

The question that prompted this: Khoa's no-repeat rule (D18) blocks the structures of alphas "đã được
nộp". A 403 refusal is ambiguous — did the alpha enter the book or not? The answer decides whether its
structure is spent. Everything below is read from the logs; nothing is inferred from documentation.

## 1. Where the 403s are, and are not

| log | POST rows | 403s |
|---|---|---|
| `state/forge/submitted.jsonl` (the current submitter) | 4 accepted + 5 unknown | **0** |
| `state/climb/submitted.jsonl` | included above | **0** |
| `state/funnel/submit_log.jsonl` (the older funnel pipeline) | 141 | **13**, over 12 distinct alphas |
| `state/submit_budget.jsonl` | reservations only | 0 |

**The forge era has never drawn a 403.** All 13 belong to the funnel pipeline that preceded it, and
they are recorded under a `status` key, not `http` — which is why a scan of `http` values finds none
and why the count differs between the VPS (0) and this MacBook (13). Anyone quoting "twelve 403s"
without naming the log is quoting a different pipeline's history.

## 2. A 403 is not one thing. It is a refusal whose REASON lives in the body.

| body says | count | did the alpha enter the book? |
|---|---|---|
| `ALREADY_SUBMITTED: FAIL` | 3 | **Yes** — the platform is telling us it is already in the book |
| `PROD_CORRELATION: ERROR` | 2 | **No** — the platform's own check errored; nothing was adjudicated |
| truncated, reason destroyed | 8 | **UNKNOWN** — see §3 |

So the status code alone cannot answer the question. `ALREADY_SUBMITTED` means the structure is spent;
an `ERROR` means the platform failed to evaluate and nothing happened; a genuine check FAIL would mean
the alpha was judged and refused, so nothing entered the book either.

## 3. Eight of the thirteen reasons were destroyed by our own logger

The bodies come in three lengths: 64 and 83 characters (the short `ALREADY_SUBMITTED` and
`PROD_CORRELATION` payloads, which parse) and **exactly 400** (which do not — the JSON is cut
mid-string). Only 5 of 13 bodies parse at all.

The truncation is ours: `tools/auto_submit.py:486` writes `"body": body[:400]` and
`tools/submit_alphas.py:612` writes `"body": r.text[:400]`. The platform sends the full check set; the
first 400 characters are the PASSing checks, so the cut lands exactly on the failing one. Note that
`tools/submit_alphas.py:640` already had the right idea — `keep = body if r.status_code not in (200,
201) else body[:400]` — and the other two call sites did not follow it.

**The current submitter does not have this defect.** `tools/climb_submit.py:218` returns
`(r.status_code, r.text or "")` and `forge/submit.py:248` writes `"body": body` whole. Nothing needs
fixing on the live path; the eight lost reasons stay lost.

## 4. A memory entry this corrects

`submit-403-spends-the-post` records "a 403 = platform adjudicated; G6 slot gone forever; only 408/429
are retryable". On this evidence that is **too strong as a general rule**: a 403 carrying
`PROD_CORRELATION: ERROR` adjudicated nothing, and 2 of the 5 readable cases are exactly that. The
conservative *operational* half of the memory — do not blindly retry a 403 — remains right, because a
retry after `ALREADY_SUBMITTED` is wasted and a retry after a real FAIL is a second refusal. What is
wrong is the claim that every 403 spent something.

## 5. What this means for D18, as a rule a machine can run

Decide by the body, not by the status code:

| observed | treat the structure as |
|---|---|
| http 200/201 | **submitted** — register it |
| 403 whose body contains `ALREADY_SUBMITTED` | **submitted** — the platform says it is in the book |
| 403 with any other readable reason (a check FAIL, an ERROR) | **not submitted** — it may be retried |
| 403 with an unreadable or truncated body | **unknown** — hold and surface it; never guess |
| http None (the POST raised, outcome unrecorded) | **unknown** — 5 such rows exist in the forge logs |

The last row is the live gap: the forge logs hold **5 POSTs whose outcome nobody recorded**, against 4
accepted. `tools/climb_submit.py:216` already writes the honest string "OUTCOME UNKNOWN, the POST may
have been adjudicated" into the body for those. Only `GET /alphas/{id}` can settle each one, and until
it does, their structures are of unknown status — which is why `forge/novelty.py` registers neither.

## 6. Not established

- Why the 8 truncated 403s were refused. The evidence was destroyed at write time and cannot be
  recovered from the logs; the platform may still know, via `GET /alphas/{id}`.
- Whether an `ALREADY_SUBMITTED` 403 means *we* submitted it earlier or the platform matched it to
  someone else's book. The body does not say, and no experiment here distinguishes them.

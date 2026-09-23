import json, copy
s=json.load(open('/tmp/harness/spec_r4.json'))
nodes={n['id']:n for n in s['nodes']}

def setlabel(nid,label):
    nodes[nid]['label']=label

def edge(src,dst):
    for e in s['edges']:
        if e['src']==src and e['dst']==dst: return e
    raise KeyError((src,dst))

# --- title: drop overclaim "verified complete" ---
s['title']="WQ Alpha Pipeline - design spec (VERIFY-live items tagged)"

# --- Vietnamese -> English (E4->C1, OOS->C1) + discriminator on E4->C1 ---
edge('E4','C1')['label']="dup -> new thesis (no mutate)"
edge('OOS','C1')['label']="per-alpha marginal drift -> relabel"

# --- E2->E4 control -> data feed ---
e=edge('E2','E4'); e['label']="PnL IS (data for corr)"; e['kind']="fwd"

# --- A4->A7 back -> fwd ---
edge('A4','A7')['kind']="fwd"

# --- C0->B4 back -> fwd (forward config-key dependency) ---
e=edge('C0','B4'); e['kind']="fwd"; e['label']="config key (region,universe,delay)"

# --- B1->B5 relabel: not operator catalog ---
edge('B1','B5')['label']="field catalog (op-feasibility)"

# --- B5->FEAS: expose allowlist ---
edge('B5','FEAS')['label']="allowlist op-classes (+ blocklist)"

# --- B5->D1 back -> fwd (reference dependency) ---
edge('B5','D1')['kind']="fwd"

# --- E5->C1 retag VERIFY (stale 7/7+403) ---
edge('E5','C1')['label']="partial-pass -> API reject, recycle (count/status VERIFY live)"

# --- C0->PART relabel: explain WHY partition (not config dims as key) ---
edge('C0','PART')['label']="shared immutable config (identical across acc -> clone-farm risk)"

# --- TRIALCNT->E3 / ->E3b disambiguate two counts ---
edge('TRIALCNT','E3')['label']="N_attempted (deflation) + N_simulated (Var[SR])"
edge('TRIALCNT','E3b')['label']="N_simulated (cohort)"

# --- E3->E3b guard label ---
edge('E3','E3b')['label']="cohort N>=K"

# --- D2->E1 pass label ---
edge('D2','E1')['label']="unique -> simulate"

# --- D1->C3 trim verbose ---
edge('D1','C3')['label']="invalid expr -> regenerate"

# --- E4->D2 + E4->C1 discriminators (redundancy reviewer) ---
edge('E4','D2')['label']="PnL dup (same struct missed) -> tighten fingerprint"
# E4->C1 already set above to dup -> new thesis (no mutate)

# === NODE LABEL EDITS ===

# A8: explicit 1-to-many multi-label cardinality
setlabel('A8',"Idea pool (idea carries thesis)|multi-label: each idea -> 1+ of B1 9 categories|same idea may seed multiple category arms (C1)")

# A7: allow A3 figure/table caption grounding
setlabel('A7',"3-LLM consensus + cite supporting paper span OR A3 figure/table caption|grounding / anti-hallucination (NOT novelty)|unsupported -> re-extract")

# B1: drop dangling slash + mark 9-cat verified (live 2026-06-16)
setlabel('B1',"Scrape fields (name / desc / coverage / category)|9 cat: Model/Fundamental/Analyst/News/Earnings|Option/PV/Social/Sentiment (USA equity, verified 2026-06-16)")

# B4: name the result-filter cutoff distinctly
setlabel('B4',"Vector DB keyed (region, universe, delay)|COV_PROBE (<50% VERIFY) -> ts_backfill|results filtered if coverage < COV_MIN (COV_MIN != COV_PROBE, VERIFY live)")

# B5: split confirmed vs to-verify blocks; allowlist authoritative
setlabel('B5',"Operator allowlist (authoritative) / blocklist (tier-derived); enum CLOSED for frozen tier|vector_neut, hump_decay BLOCK (hard); tail, regression_neut BLOCK (tier, VERIFY live)|mult deprecated -> use multiply(.,.,filter=false) (VERIFY live)")

# C0: assert eligibility at config birth (incl TOP1000, verified)
setlabel('C0',"C0: IMMUTABLE config|(region, universe, delay) chosen ONCE|threaded read-only; no node may mutate; eligibility asserted at birth (Neut!=NONE, universe in {TOP500/1000/2000/3000})")

# FEAS: receive allowlist not just blocklist (matches edge edit)
setlabel('FEAS',"Feasibility gate (per config)|>=1 field/category coverage >= FEAS_MIN (config; VERIFY live)|thesis realizable by >=1 allowlist op-class (else infeasible -> drop arm)")

# C1: reward = uncorrelated marginal drift; hierarchical fingerprint credit
setlabel('C1',"Bandit: pick (category, thesis); reward credited at structural-fingerprint sub-arm|yield-weighted + exploration floor (arms + UNSEEN fingerprint)|reward = OOS per-alpha marginal drift x (1 - max_corr_to_book); pre-sim gates = penalty (VERIFY live)")

# C3: TOP1000 added (verified); Neut from eligible enum; universe asserted not chosen
setlabel('C3',"Generate alpha (Fast Expression + settings)|operators = enum-CONSTRAINED to B5 closed allowlist (hard; +arity, +alias)|settings inherit C0 (universe in {TOP500/1000/2000/3000} assert; Neut enum != NONE)")

# D1: TOP1000 added; eligibility = C0 invariant assert; pure AST otherwise
setlabel('D1',"Validator schema/operator/field (AST)|block non-allowlist op, wrong-config field, bad arity|eligibility ASSERT (C0 invariant): Neut!=NONE; universe in {TOP500/1000/2000/3000} (VERIFY live)")

# D2: fingerprint excludes settings; exempt before F1 decrement; idempotent; primary corr defense
setlabel('D2',"Dup detector (no mutate, idempotent); GLOBAL/structural mask; PRIMARY corr defense (E4 = PnL backstop)|fingerprint: field-set + AST + group (+ thesis); EXCLUDES settings (F1 re-tune = fingerprint-identical)|same lineage EXEMPT while retune_count <= F1 cap (eval BEFORE decrement); mask on pass + reject")

# E3: add soft path-rank; clarify DSR independence + K-ratio/R2 = path not selection
setlabel('E3',"Robust per-alpha (IS-only)|WQ-native: sub-universe Sharpe + IS checks (VERIFY live)|OUR (off-platform): DSR (deflation N=N_attempted; Var[SR] from candidate IS series); K-ratio + R2 = path consistency; soft path-rank (non-gating)")

# E3b: gates submit ONLY when N>=K; cohort-level PBO; define K
setlabel('E3b',"OUR: Cohort PBO via CSCV (N configs x T time matrix; partition TIME, S even >=4)|param sweep of one thesis; needs N>=K (K>=2 min, ~10 stable); cohort-level prob, NOT per-alpha|gates submit ONLY when N>=K (N<K bypass via E3->E4, PBO-unassessed)")

# TRIALCNT: fix N semantics; dups not new hypotheses; remove Var[SR]/matrix from counter
setlabel('TRIALCNT',"Trial counter (two counts)|N_simulated = trials w/ Sharpe -> cohort size (E3b); Var[SR] is per-candidate (not from counter)|N_attempted = distinct hypotheses (D1 invalid + F1; D2 dups de-duplicated) -> DSR deflation N")

# E5: 7/7 strict verified-threshold; only HTTP status VERIFY
setlabel('E5',"SUBMIT (requires 7/7 IS checks PASS - strict)|API reject if <7/7 (status code VERIFY live)")

# F1: cap decrements on ADMITTED retry (after D1/D2 pass); dual entry shares one cap
setlabel('F1',"Re-tune settings (capped)|Neut (eligible, !=NONE)/decay/trunc only; region/universe/delay LOCKED|entry: E2-fail OR E5-settings-near-miss; cap decrements on ADMITTED retry (after D1/D2 pass); ONE shared E1 cap")

# E1: plan-against-default note
setlabel('E1',"Simulate (CONCURRENT slot-gated, NOT req/min); mutex per account_id|slots ~3 non-consultant / ~10 consultant in-flight (VERIFY live)|HARD sim/idea cap (incl F1 re-tune); plan against ~3 default")

# TEAMCORR: defer != discard
setlabel('TEAMCORR',"Team / merged-IQC corr gate|vs teammate SUBMITTED PnL only (live re-fetch); serialize submit|merged PnL AGGREGATE only; partition-overlap excluded (VERIFY live); defer != discard (alpha retained)")

# === ADD EDGES ===
# FEAS reject path -> C1 (drop + bandit mask)
s['edges'].append({"src":"FEAS","dst":"C1","label":"infeasible -> drop arm + bandit mask","kind":"back"})
# D1 validator-reject penalty -> C1
s['edges'].append({"src":"D1","dst":"C1","label":"validator-reject penalty (arm)","kind":"back"})
# PART -> E1 account_id provenance
s['edges'].append({"src":"PART","dst":"E1","label":"account_id (per-acc sim mutex + slots)","kind":"fwd"})
# E3b -> E5 cohort gate (submit only after CSCV pass)
s['edges'].append({"src":"E3b","dst":"E5","label":"cohort PBO PASS (N>=K) -> release submit","kind":"fwd"})

# === REMOVE E4->D2 ? No, keep (redundancy reviewer wanted discriminator, applied above) ===

json.dump(s, open('/tmp/harness/spec_r5.json','w'))
print("title:",s['title'])
print("edges:",len(s['edges']))
print("nodes:",len(s['nodes']))

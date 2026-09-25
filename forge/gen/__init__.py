"""forge.gen -- the pass-first generator (docs/evalharness/04_passfirst_design.md, stage 2 of §7).

STATUS UNDER RULE 2. Every mechanism here is a PROPOSAL built under Khoa's ticks D34 (the reward), D35
(uniform priors, the §2.3 exclusions, a 20 % exploration floor reaching TIER_U), D36 (the spending rules
re-keyed on his fingerprint family), D37 (the repair queue with a coin per trigger), D38 (the DSR pool is
the family x cell x category) and D51 (two one-setting neighbours per generated harvest-pass). None of it
has passed gates 3-4; D47 is the proof design (rounds randomised 50/50 within each ET day between the
incumbent and this branch; D54: the round is the unit and only meta.gen_route "fresh" enters the estimand).
The caller is forge/runner.py's `fill_gen` (`--mode gen`, design stage 4, the runner owner's; read
2026-09-24); whether a live round runs it is forge.env's (D50), not this package's.

EVERY FUNCTION IS PURE except `state.load`, which only READS files. No module simulates, posts, writes a
journal or opens a socket, so every behaviour is testable offline without spending a simulation (RULE 1).

Modules:
  productions  the §2.2 grammar as data; one seeded draw, typed so it passes the structural gate by
               construction; the exclusions
  posterior    y (D34), harvest-pass (§0), the levels a row used, the Beta counts, one round's weights
  families     Khoa's fingerprint family of a formula (root fingerprint.py), nearest-member assignment
  spend        the D36 rules per family: DEAD_SIMS, LADDER_DEAD, PASSED_BLOCK, the PnL stop, plan-time D18
  repair       the D37 trigger, coin and settings grid; the D51 neighbours
  state        the loop's state as a pure function of the journal, the submit logs and the cached curves,
               and its sha (meta.gen_state, §3.2)
  propose      one round: neighbours, then repairs, then draws, each through every rule above, each
               stamped meta.gen_route "neighbour" / "repair" / "fresh" (propose.ROUTES)
"""

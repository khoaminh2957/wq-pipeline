"""framelib.loop -- the frames loop that replaces the incumbent forge loop (docs/frames/00_decisions.md F5-F9).

Per round the driver calls, in order (shared interface, 2026-09-24):
  evidence      python -m framelib.loop.evidence --update      the evidence ledger state/frames/evidence.jsonl,
                                                              and used_fields(frame_id) for freshness
  newframes     python -m framelib.loop.newframes --n 25       once per ET day: new candidate frames (F8)
  plan          python -m framelib.loop.plan --n 300 --seed S --out P
                                                              the round's constructions (this package's planner); it
                                                              first refreshes state/frames/unit_blacklist.json
  availability  (imported by plan)                            today's datasets; the field library pruned to them; the
                                                              (field, operator) inputs rejected with "Incompatible unit"
  dispatch      framelib/experiments/vps/dispatch_round.py --abc P ... --experiment FRAMES-LOOP --live
  submit        python -m framelib.loop.submit --submit        the only code that POSTs

Nothing in plan or availability simulates, submits or talks to the network (RULE 1).
"""

"""framelib -- a library of alpha FRAMES (Khoa 2026-09-24: "thư viện khung").

A frame is a FASTEXPR formula with typed slots ($1..$n) and optional fixed fields; filling its
slots with compatible fields gives formulas. Modules:

  frames    normal form of a frame text (FRAME SPEC v1) and the facts derived from the text
  taxonomy  the classification axes, defined in code
  fields    the field library (field_labels.jsonl + the catalogues), one typed record per field and cell
  compat    the slot-compatibility rule (which fields may fill which slot)
  filler    frame x compatible fields -> formulas + settings, seeded, gated by structurally_ok
  evidence  per-cell observed rates of a frame in the canonical corpus (POST-HOC, never a verdict)
  schema    the library entry: fields, derivations, status rules, validator
  store     JSON storage under framelib/library/, loader, index
  build     the builder: canonical corpus + designer frames + discovery list -> library entries

Nothing in this package simulates, submits or talks to the network (RULE 1).
"""

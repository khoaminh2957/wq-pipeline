#!/usr/bin/env python3
"""5x regression suite for gate_lib.py vs hand-computed expectations.

Fixtures: state/benchmark/fixtures/gate_lib_fixtures.json
  - 7 gate_status rows: CHN-d0 full rows, JPN-d0 (different check set, 1 FAIL),
    USA-d1 grandfathered-WARNING (+PENDING), bare PASS-name list, short-form
    fails, fail-count-only (S10-25: fail>0 must block), and the fetch_gates
    dict-form {name:result} checks shape.
  - 9 region_delay_bar cells (all 5 ground-truth bars + unknown/coercion/invalid).
  - 3 cycle_metrics scenarios: the n_good==0 & all-gated-fail => robustness 0.0
    invariant, a fully hand-computed mixed batch, and a fail-count + dict-form
    batch.

Usage: python3 tools/funnel/test_gate_lib.py   (single run; prints PASS/FAIL)
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gate_lib

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        '..', '..', 'state', 'benchmark', 'fixtures',
                        'gate_lib_fixtures.json')

TOL = 1e-9


def _eq(got, want):
    if isinstance(want, float) and isinstance(got, (int, float)):
        return abs(got - want) <= TOL
    return got == want


def check(label, got, want, errors):
    for k, w in want.items():
        g = got.get(k, '<MISSING>')
        if not _eq(g, w):
            errors.append(f'{label}.{k}: got {g!r}, want {w!r}')


def main():
    with open(FIXTURES) as f:
        fx = json.load(f)
    errors = []

    for case in fx['gate_status_cases']:
        got = gate_lib.gate_status(case['row'])
        check(case['name'], got, case['expect'], errors)

    for i, case in enumerate(fx['region_delay_bar_cases']):
        got = gate_lib.region_delay_bar(case['region'], case['delay'])
        if not _eq(got, case['expect']):
            errors.append(f"bar[{i}] ({case['region']},{case['delay']}): "
                          f"got {got!r}, want {case['expect']!r}")

    for case in fx['cycle_metrics_cases']:
        got = gate_lib.cycle_metrics(case['rows'], case['wall_min'])
        check(case['name'], got, case['expect'], errors)
        # S8 contract: emitted signal set includes every named quality signal
        for key in ('n_gated', 'n_good', 'gate_pass_rate',
                    'robust_univ_pass_rate', 'spread', 'dd_score',
                    'good_per_min', 'robustness'):
            if key not in got:
                errors.append(f"{case['name']}: missing S8 signal '{key}'")

    # determinism: same input -> byte-identical output
    row = fx['gate_status_cases'][0]['row']
    if json.dumps(gate_lib.gate_status(row), sort_keys=True) != \
       json.dumps(gate_lib.gate_status(row), sort_keys=True):
        errors.append('gate_status not deterministic')
    cm = fx['cycle_metrics_cases'][1]
    if json.dumps(gate_lib.cycle_metrics(cm['rows'], cm['wall_min']), sort_keys=True) != \
       json.dumps(gate_lib.cycle_metrics(cm['rows'], cm['wall_min']), sort_keys=True):
        errors.append('cycle_metrics not deterministic')

    n_checks = (len(fx['gate_status_cases']) + len(fx['region_delay_bar_cases'])
                + len(fx['cycle_metrics_cases']) + 2)
    if errors:
        print(f'FAIL ({len(errors)} mismatches over {n_checks} cases)')
        for e in errors:
            print('  ' + e)
        return 1
    print(f'PASS ({n_checks} cases, all hand-computed expectations matched)')
    return 0


if __name__ == '__main__':
    sys.exit(main())

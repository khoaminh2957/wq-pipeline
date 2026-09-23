import shutil

import pytest
import yaml

from forge.offline import promote_staged as PS

LEG = {"id": "new_leg", "family": "f", "category": "Insiders", "title": "t", "mechanism": "Insiders buy ahead of news that outsiders have not priced, and a profitable firm turns that private information into earnings that persist rather than into a story, so the product of the two ranks keeps the names where an informed buyer and a cash-generating business agree, and the drift comes from holders who read neither the filings nor the income statement.",
       "counterparty": "retail holders who do not read filings", "sign": 1, "source": "EX-ANTE — x", "datasets": ["d"],
       "signal": {"fields": ["fld"]}, "template": "group_rank(ts_mean({signal}, {w}), {group})",
       "params": {"w": [5], "group": ["industry"]},
       "settings": {"neutralization": ["INDUSTRY"], "decay": [8], "truncation": 0.08},
       "regions": ["USA"], "delays": [1]}
COMP = {"id": "new_x_partner", "title": "t", "arm": "new", "legs": ["new_leg", "partner_leg"],
        "families": ["f", "g"], "combiners": ["multiply"], "mechanism": "Insiders buy ahead of news that outsiders have not priced, and a profitable firm turns that private information into earnings that persist rather than into a story, so the product of the two ranks keeps the names where an informed buyer and a cash-generating business agree, and the drift comes from holders who read neither the filings nor the income statement.",
        "counterparty": "retail holders who do not read filings",
        "source": "EX-ANTE — x",
        "regimes": {"value_winter_2014_2020": "+", "momentum_crash_2016": "0", "covid_2020": "+", "rate_shock_2022": "-"}, "strongest_in": "mid caps with a reported income statement and rare insider purchases",
        "weakens_when": "insider buying is programmatic under a 10b5-1 plan",
        "settings": {"neutralization": ["INDUSTRY"], "decay": [8], "truncation": 0.08}}


@pytest.fixture
def repo(tmp_path, monkeypatch):
    legs, comps = tmp_path / "hypotheses", tmp_path / "composites"
    (legs / "staged").mkdir(parents=True)
    (comps / "staged").mkdir(parents=True)
    partner = dict(LEG, id="partner_leg", family="g", category="Fundamental", sign=-1)
    (legs / "partner_leg.yaml").write_text(yaml.safe_dump(partner))
    monkeypatch.setattr(PS, "LEGS", legs)
    monkeypatch.setattr(PS, "COMPS", comps)
    return legs, comps


def _write(repo, leg=None, comp=None):
    legs, comps = repo
    (legs / "staged/new_leg.yaml").write_text(yaml.safe_dump({**LEG, **(leg or {})}))
    (comps / "staged/new_x_partner.yaml").write_text(yaml.safe_dump({**COMP, **(comp or {})}))


def test_a_clean_staged_pair_promotes_and_the_files_move(repo):
    legs, comps = repo
    _write(repo)
    rows, staged = PS.audit(legs, comps)
    assert [r[4] for r in rows] == [[]]
    assert rows[0][2] == ["new_leg"] and rows[0][3] == ["partner_leg"]
    assert PS.promote(rows, staged, dry=True) == 1 and (comps / "staged/new_x_partner.yaml").exists()
    assert PS.promote(rows, staged, dry=False) == 1
    assert (comps / "new_x_partner.yaml").exists() and (legs / "new_leg.yaml").exists()
    assert not (comps / "staged/new_x_partner.yaml").exists()


@pytest.mark.parametrize("comp,leg,why", [
    ({"arm": "current"}, None, "arm != new"),
    ({"combiners": ["multiply", "gate"]}, None, "bearish leg with gate combiner"),
    ({"legs": ["new_leg", "short_volume_ratio_informed"]}, None, "avoid list"),
])
def test_refusals_keep_the_files_in_staged(repo, comp, leg, why):
    legs, comps = repo
    if comp.get("legs"):                      # the avoid-list case needs that partner to exist
        (legs / "short_volume_ratio_informed.yaml").write_text(
            yaml.safe_dump(dict(LEG, id="short_volume_ratio_informed", family="short", sign=-1)))
    _write(repo, leg, comp)
    rows, staged = PS.audit(legs, comps)
    assert any(why in r for r in rows[0][4]), rows[0][4]
    assert PS.promote(rows, staged, dry=False) == 0
    assert (comps / "staged/new_x_partner.yaml").exists()


def test_a_leg_set_already_live_is_refused(repo):
    legs, comps = repo
    _write(repo)
    rows, staged = PS.audit(legs, comps)
    PS.promote(rows, staged, dry=False)                     # first promotion succeeds
    shutil.copy(legs / "new_leg.yaml", legs / "staged/new_leg.yaml")
    (comps / "staged/new_x_partner.yaml").write_text(yaml.safe_dump(dict(COMP, id="same_pair_again")))
    rows, staged = PS.audit(legs, comps)
    assert any("already live" in r or "no new leg" in r for r in rows[0][4]), rows[0][4]

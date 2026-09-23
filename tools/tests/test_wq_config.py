"""Suite for tools/wq_config.py — the one per-account config surface.

WHAT THIS SUITE IS ACTUALLY FOR. Not "does the loader parse JSON". The failure worth a test is the
one that is SILENT: account 2 appending to account 1's `submit_budget.jsonl`, `banned_fields.json`
or `auto_submit_journal.jsonl` because some path resolved to account 1's `state/`. A crash is
noticed the same minute; a shared ledger is noticed after four submits are spent. So every test
below asserts a REFUSAL or an ISOLATION, and `test_second_account_cannot_write_into_first_accounts_
ledgers` is the one this file exists for.

OFFLINE AND OFF-REPO BY CONSTRUCTION. `_no_network` makes any socket a failure. `_no_repo_config`
clears $WQ_CONFIG so the search order is deterministic, and no test calls `load()` in a way that
could claim the REAL `state/` — every config points at a tmp_path.
"""

import json
import socket
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import wq_config  # noqa: E402


# ------------------------------------------------------------------------------------- fixtures

@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("a test opened a socket; this suite must be fully offline")
    monkeypatch.setattr(socket, "socket", _boom)
    monkeypatch.setattr(socket, "create_connection", _boom)


@pytest.fixture(autouse=True)
def _no_repo_config(monkeypatch):
    monkeypatch.delenv("WQ_CONFIG", raising=False)


def write_cfg(dirpath: Path, name: str, d: dict) -> Path:
    p = dirpath / name
    p.write_text(json.dumps(d))
    return p


# ------------------------------------------------- 1. two configs -> two independent state dirs

def test_two_configs_produce_two_independent_state_dirs(tmp_path):
    a = write_cfg(tmp_path, "acc1.json",
                  {"account_id": "acc1", "state_dir": str(tmp_path / "s1")})
    b = write_cfg(tmp_path, "acc2.json",
                  {"account_id": "acc2", "state_dir": str(tmp_path / "s2")})
    c1, c2 = wq_config.load(str(a)), wq_config.load(str(b))

    assert c1.state_dir != c2.state_dir
    assert c1.cookie_path != c2.cookie_path
    # Every per-account ledger named in the audit must land in its own tree.
    for ledger in ("banned_fields.json", "prod_corr_measured.json", "submit_budget.jsonl",
                   "auto_submit_journal.jsonl", "resim_results.jsonl", "funnel/winners.csv"):
        p1, p2 = c1.state(ledger), c2.state(ledger)
        assert p1 != p2
        assert not str(p1).startswith(str(c2.state_dir))
        assert not str(p2).startswith(str(c1.state_dir))


def test_cookie_jar_is_per_account_and_not_a_shared_default(tmp_path):
    """`tools/layered_sim.py:61` falls back to /opt/wq/state/wq_cookies.pkl when the local jar is
    absent — a second checkout would then authenticate AS ACCOUNT 1 while writing account 2's
    journal. The config surface names exactly one jar, derived from that account's state dir."""
    a = wq_config.load(str(write_cfg(tmp_path, "a.json",
                                     {"account_id": "acc1", "state_dir": str(tmp_path / "s1")})))
    b = wq_config.load(str(write_cfg(tmp_path, "b.json",
                                     {"account_id": "acc2", "state_dir": str(tmp_path / "s2")})))
    assert a.cookie_path == tmp_path / "s1" / "wq_cookies.pkl"
    assert b.cookie_path == tmp_path / "s2" / "wq_cookies.pkl"
    assert wq_config.WQConfig(account_id="x", state_dir=tmp_path / "z").cookie_path.parent == \
        tmp_path / "z"


# ---------------------------------------------------------- 2. THE dangerous failure, head-on

def test_second_account_cannot_write_into_first_accounts_ledgers(tmp_path):
    """acc2 misconfigured at acc1's state directory. This must REFUSE, not append."""
    shared = tmp_path / "state"
    shared.mkdir()
    c1 = wq_config.load(str(write_cfg(tmp_path, "acc1.json",
                                      {"account_id": "acc1", "state_dir": str(shared)})))
    assert (shared / wq_config.CLAIM_FILE).read_text().strip() == "acc1"

    with pytest.raises(wq_config.ConfigError) as e:
        wq_config.load(str(write_cfg(tmp_path, "acc2.json",
                                     {"account_id": "acc2", "state_dir": str(shared)})))
    msg = str(e.value)
    assert "acc1" in msg and "acc2" in msg
    assert "submit_budget.jsonl" in msg          # the error names what would have been corrupted
    # and acc1's claim is untouched
    assert (shared / wq_config.CLAIM_FILE).read_text().strip() == "acc1"
    assert c1.account_id == "acc1"


def test_reloading_the_same_account_on_a_claimed_dir_is_fine(tmp_path):
    shared = tmp_path / "state"
    p = write_cfg(tmp_path, "acc1.json", {"account_id": "acc1", "state_dir": str(shared)})
    shared.mkdir()
    wq_config.load(str(p))
    wq_config.load(str(p))                        # idempotent, no refusal
    assert (shared / wq_config.CLAIM_FILE).read_text().strip() == "acc1"


def test_claim_is_skipped_when_the_state_dir_does_not_exist_yet(tmp_path):
    """A config may legitimately name a directory that has not been created. Refusing there would
    make bootstrapping impossible, and claiming it would create state/ as a side effect of a read."""
    c = wq_config.load(str(write_cfg(tmp_path, "a.json",
                                     {"account_id": "acc9", "state_dir": str(tmp_path / "nope")})))
    assert not (tmp_path / "nope").exists()
    assert c.account_id == "acc9"


# ------------------------------------------------------------------- 3. missing config FAILS CLOSED

def test_missing_config_fails_closed_and_names_what_it_searched(tmp_path, monkeypatch):
    monkeypatch.setattr(wq_config, "REPO_ROOT", tmp_path)          # no wq_account.json here
    with pytest.raises(wq_config.ConfigError) as e:
        wq_config.load()
    msg = str(e.value)
    assert str(tmp_path / wq_config.DEFAULT_CONFIG_NAME) in msg
    assert "WQ_CONFIG" in msg


def test_missing_config_does_not_fall_back_to_the_repo_state_dir(tmp_path, monkeypatch):
    """The whole point. An unconfigured process must not inherit account 1's paths."""
    monkeypatch.setattr(wq_config, "REPO_ROOT", tmp_path)
    with pytest.raises(wq_config.ConfigError):
        wq_config.load()
    with pytest.raises(wq_config.ConfigError):
        wq_config.load(str(tmp_path / "does_not_exist.json"))


def test_explicit_path_that_does_not_exist_does_not_silently_use_env_or_default(tmp_path,
                                                                                monkeypatch):
    good = write_cfg(tmp_path, "env.json", {"account_id": "envacct",
                                            "state_dir": str(tmp_path / "envstate")})
    monkeypatch.setenv("WQ_CONFIG", str(good))
    assert wq_config.load().account_id == "envacct"
    with pytest.raises(wq_config.ConfigError):
        wq_config.load(str(tmp_path / "typo.json"))   # explicit wins; no fallback to $WQ_CONFIG


def test_malformed_json_is_a_refusal_not_a_default(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json")
    with pytest.raises(wq_config.ConfigError) as e:
        wq_config.load(str(p))
    assert "not valid JSON" in str(e.value)


# --------------------------------------------------------- 4. identity and typos fail closed

def test_config_without_account_id_is_refused(tmp_path):
    p = write_cfg(tmp_path, "anon.json", {"state_dir": str(tmp_path / "s")})
    with pytest.raises(wq_config.ConfigError) as e:
        wq_config.load(str(p))
    assert "account_id" in str(e.value)


def test_empty_account_id_is_refused(tmp_path):
    p = write_cfg(tmp_path, "empty.json", {"account_id": "  ", "state_dir": str(tmp_path / "s")})
    with pytest.raises(wq_config.ConfigError):
        wq_config.load(str(p))


def test_unknown_key_is_refused_because_a_typo_would_leave_account_1s_path(tmp_path):
    """`statedir` is not `state_dir`. Accepting it would leave state_dir at its default, which on
    a shared checkout is the FIRST account's directory — the silent case this suite guards."""
    p = write_cfg(tmp_path, "typo.json", {"account_id": "acc2", "statedir": str(tmp_path / "s2")})
    with pytest.raises(wq_config.ConfigError) as e:
        wq_config.load(str(p))
    assert "statedir" in str(e.value)


# --------------------------------------------------- 5. defaults reproduce TODAY's behaviour

def test_defaults_reproduce_todays_constants():
    """If one of these drifts, a migrated module changes behaviour for account 1. Each value is
    sourced on its line in wq_config.py; the module it came from is the truth."""
    c = wq_config.WQConfig(account_id="acc1")
    assert c.api_host == "https://api.worldquantbrain.com"
    assert (c.region, c.delay, c.universe, c.instrument_type) == ("USA", 1, "TOP3000", "EQUITY")
    assert c.settings() == {"instrumentType": "EQUITY", "region": "USA",
                            "universe": "TOP3000", "delay": 1}
    assert c.daily_submit_quota == 4          # tools/auto_submit.py:67
    assert c.max_alphas_per_run == 4          # tools/auto_submit.py:68
    assert c.max_decisions_per_run == 8       # tools/auto_submit.py:81
    assert c.quota_timezone == "America/New_York"
    assert c.auth_daily_reset_utc_hour == 4   # tools/auth_backoff.py:75
    assert c.state_dir == wq_config.REPO_ROOT / "state"
    assert c.cookie_path == wq_config.REPO_ROOT / "state" / "wq_cookies.pkl"


def test_shipped_acc1_config_reproduces_todays_paths_exactly():
    """The repo's own wq_account.json must describe account 1 as it runs today, so the migration
    changes nothing for it."""
    p = wq_config.REPO_ROOT / wq_config.DEFAULT_CONFIG_NAME
    assert p.is_file(), "wq_account.json is the documented default for account 1"
    c = wq_config.from_dict(json.loads(p.read_text()), source_path=str(p))
    assert c.account_id == "acc1"
    assert c.state_dir == wq_config.REPO_ROOT / "state"
    assert c.cookie_path == wq_config.REPO_ROOT / "state" / "wq_cookies.pkl"
    assert c.settings() == {"instrumentType": "EQUITY", "region": "USA",
                            "universe": "TOP3000", "delay": 1}


def test_a_second_region_is_a_config_change_not_a_code_change(tmp_path):
    """28 files under tools/ carry region/universe/delay as a literal. One config, one edit."""
    c = wq_config.load(str(write_cfg(tmp_path, "chn.json",
                                     {"account_id": "acc2", "state_dir": str(tmp_path / "s"),
                                      "region": "CHN", "delay": 0, "universe": "TOP2000U"})))
    assert c.settings() == {"instrumentType": "EQUITY", "region": "CHN",
                            "universe": "TOP2000U", "delay": 0}


def test_a_second_vps_is_a_config_change(tmp_path):
    """harness13/ops/deploy.sh hardcodes /opt/wq and documents one --host."""
    c = wq_config.load(str(write_cfg(tmp_path, "vps2.json",
                                     {"account_id": "acc3", "state_dir": str(tmp_path / "s"),
                                      "vps_host": "root@10.0.0.9", "vps_root": "/opt/wq2"})))
    assert c.vps_host == "root@10.0.0.9"
    assert c.vps_root == Path("/opt/wq2")


def test_paths_expand_user(tmp_path):
    c = wq_config.from_dict({"account_id": "acc4", "state_dir": str(tmp_path),
                             "creds_path": "~/.wqbrain_creds_acc4"})
    assert "~" not in str(c.creds_path)
    assert c.creds_path == Path.home() / ".wqbrain_creds_acc4"


# ---------------------------------------------------------------- 6. this round changes nothing

def test_no_existing_module_imports_wq_config_yet():
    """Round 1 builds the surface only; the migration is a later round's work and would collide
    with the other agents. If this fails, someone migrated a module early — that is the thing to
    check, not this assertion."""
    root = wq_config.REPO_ROOT
    hits = []
    for p in list((root / "tools").rglob("*.py")) + list((root / "harness13").rglob("*.py")):
        if p.name in ("wq_config.py", "test_wq_config.py") or "/archive/" in str(p):
            continue
        try:
            src = p.read_text(errors="ignore")
        except OSError:
            continue
        if "import wq_config" in src or "from wq_config" in src:
            hits.append(str(p))
    assert hits == [], "modules already import wq_config: %s" % hits

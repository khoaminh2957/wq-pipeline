#!/usr/bin/env python3
"""ONE config surface for everything that is per-ACCOUNT, per-REGION, per-PATH or per-QUOTA.

WHY THIS EXISTS. Khoa's stated end state (SOP "Packaging"): perfect this one account, package it,
then scale to many accounts and many VPSs. Today 121 modules under `tools/` derive their state
directory from `pathlib.Path(__file__).resolve().parent.parent`, i.e. from WHERE THE CODE LIVES.
Two accounts sharing one checkout therefore share one `state/`, one `wq_cookies.pkl`, one
`banned_fields.json` and one submit ledger. That is not a crash; it is silent cross-account
corruption. This module gives every such constant a single place to come from.

**NOTHING IMPORTS THIS YET.** Round 1 builds the surface and the inventory only; the migration of
existing modules is proposed in `harness13/massgen/experiments/PACKAGING_P1R1.md` and is a later
round's work. So account 1's behaviour this round is unchanged BY CONSTRUCTION, not by argument.

THE DEFAULTS REPRODUCE TODAY. Every value in `DEFAULTS` was read out of the module that owns it
today; the source is named on the line. If a default here disagrees with the live module, the
module is the truth and this file is the bug.

FAIL-CLOSED, AND WHERE. The dangerous failure is not a crash, it is account 2 quietly writing into
account 1's ledgers. Four separate refusals guard that, each with its own test:

  1. NO config file found            -> `ConfigError` naming every path searched. There is no
                                        "fall back to the repo's own state/".
  2. `account_id` missing            -> `ConfigError`. There is no default account id, ever.
  3. an UNKNOWN key in the file      -> `ConfigError`. A typo (`statedir` for `state_dir`) would
                                        otherwise leave the default in place, which for account 2
                                        means account 1's directory.
  4. the state dir is already CLAIMED by a different account -> `ConfigError`. `load()` writes
                                        `<state_dir>/.wq_account` the first time it sees a
                                        directory and refuses to hand out a config whose
                                        `account_id` disagrees with the marker already there.

Resolution order for the config file, first hit wins:

    explicit path argument  ->  $WQ_CONFIG  ->  <repo_root>/wq_account.json

USAGE:

    import wq_config
    cfg = wq_config.load()                       # or load("accounts/acc2.json")
    jar = cfg.cookie_path
    ledger = cfg.state("submit_budget.jsonl")
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_NAME = "wq_account.json"
CLAIM_FILE = ".wq_account"


class ConfigError(RuntimeError):
    """Raised for every refusal above. Never returns a usable config."""


@dataclass(frozen=True)
class WQConfig:
    # ---- identity: the ONE field with no default -------------------------------------------
    account_id: str

    # ---- paths ------------------------------------------------------------------------------
    #: repo checkout. Today every module computes this itself from __file__.
    repo_root: Path = REPO_ROOT
    #: per-account state. TODAY: <repo_root>/state, shared by 121 modules in tools/.
    state_dir: Optional[Path] = None                    # None -> repo_root/state
    #: TODAY: tools/*.py read ROOT/"state/wq_cookies.pkl"; config.py:15 reads
    #: Path.home()/"wq_pipeline"/"state"/"wq_cookies.pkl". Those are the same file on this box
    #: and different files on any other.
    cookie_path: Optional[Path] = None                  # None -> state_dir/wq_cookies.pkl
    #: TODAY: config.py:14, tools/auth_only.py:20 -> Path.home()/".wqbrain_creds"
    creds_path: Path = Path.home() / ".wqbrain_creds"

    # ---- platform endpoint -------------------------------------------------------------------
    #: TODAY: literal in 49 files under tools/ and harness13/.
    api_host: str = "https://api.worldquantbrain.com"

    # ---- simulation settings ------------------------------------------------------------------
    #: TODAY: tools/layered_sim.py:36, tools/pyramid_gate.py:55-56, tools/decide_submits.py:57,
    #: and the "region":"USA","universe":"TOP3000","delay":1 literal in 28 files under tools/.
    region: str = "USA"
    delay: int = 1
    universe: str = "TOP3000"
    instrument_type: str = "EQUITY"

    # ---- per-account quotas --------------------------------------------------------------------
    #: TODAY: tools/auto_submit.py:67,68,81. Platform REGULAR_SUBMISSION limit, resets 00:00 ET.
    daily_submit_quota: int = 4
    max_alphas_per_run: int = 4
    max_decisions_per_run: int = 8
    #: OPERATOR-STATED (memory `platform-quotas-reset-midnight-et`), mirrored at
    #: harness13/massgen/experiments/poll_cadence.py:473. Not measured by this module.
    daily_sim_quota: int = 5000
    #: OPERATOR-STATED (Khoa 2026-08-12, SOP "Simulation shape"): 8 multisims x 10 children.
    #: NOT measured here.
    sim_max_concurrent: int = 80
    #: OPERATOR-STATED (Khoa 2026-08-13, SIM_CEILING.md L269). The counter itself lives on the VPS
    #: daemon (`state/auth_mint_budget.json`), not in this repo's code.
    auth_mint_budget: int = 25

    # ---- quota clock ---------------------------------------------------------------------------
    #: TODAY: tools/submit_budget.py:71, tools/daily_budget.py:53, run_report.py:145.
    quota_timezone: str = "America/New_York"
    #: TODAY: tools/auth_backoff.py:75. Kept SEPARATE from quota_timezone because it is a fixed UTC
    #: hour that matches the VPS daemon and is NOT DST-correct — under EST the true boundary is
    #: 05:00Z and this releases an hour early. Carried here as-is so the two do not silently
    #: diverge; see that module's docstring.
    auth_daily_reset_utc_hour: int = 4

    # ---- deployment target ----------------------------------------------------------------------
    #: TODAY: harness13/ops/deploy.sh:19 (the --host example) and /opt/wq literal in deploy.sh
    #: plus tools/layered_sim.py:61.
    vps_host: Optional[str] = "root@160.25.88.163"
    vps_root: Path = Path("/opt/wq")

    #: where this config was read from; "" when built in-process.
    source_path: str = ""

    def __post_init__(self):
        if not self.account_id or not str(self.account_id).strip():
            raise ConfigError("account_id is empty; there is no default account id")
        object.__setattr__(self, "repo_root", Path(self.repo_root))
        if self.state_dir is None:
            object.__setattr__(self, "state_dir", Path(self.repo_root) / "state")
        else:
            object.__setattr__(self, "state_dir", Path(self.state_dir))
        if self.cookie_path is None:
            object.__setattr__(self, "cookie_path", self.state_dir / "wq_cookies.pkl")
        else:
            object.__setattr__(self, "cookie_path", Path(self.cookie_path))
        object.__setattr__(self, "creds_path", Path(self.creds_path))
        object.__setattr__(self, "vps_root", Path(self.vps_root))

    def state(self, *parts: str) -> Path:
        """A path under THIS account's state directory. Every per-account ledger goes through here:
        banned_fields.json, prod_corr_measured.json, submit_budget.jsonl, resim_results.jsonl,
        auto_submit_journal.jsonl, funnel/winners.csv."""
        return self.state_dir.joinpath(*parts)

    def settings(self) -> dict:
        """The simulation settings block, in the shape the API takes. Only the four fields this
        config owns; decay/neutralization/truncation stay with the module that varies them."""
        return {"instrumentType": self.instrument_type, "region": self.region,
                "universe": self.universe, "delay": self.delay}


_FIELD_NAMES = {f.name for f in fields(WQConfig)}
_PATH_FIELDS = {"repo_root", "state_dir", "cookie_path", "creds_path", "vps_root"}


def search_paths(explicit: Optional[str] = None) -> list[Path]:
    """Every path `load()` will try, in order. Reported verbatim in the not-found error."""
    if explicit:
        return [Path(explicit)]
    out = []
    env = os.environ.get("WQ_CONFIG")
    if env:
        out.append(Path(env))
    out.append(REPO_ROOT / DEFAULT_CONFIG_NAME)
    return out


def from_dict(d: dict, source_path: str = "") -> WQConfig:
    """Build a config from a plain dict. Unknown keys are a REFUSAL, not a warning: a mistyped key
    leaves the default in place, and for a second account the default is the FIRST account's path."""
    if not isinstance(d, dict):
        raise ConfigError("config must be a JSON object, got %s" % type(d).__name__)
    unknown = sorted(set(d) - _FIELD_NAMES - {"source_path"})
    if unknown:
        raise ConfigError(
            "unknown config key(s) %s. A typo would silently leave the DEFAULT in place, which for "
            "a second account is the first account's path. Known keys: %s"
            % (", ".join(unknown), ", ".join(sorted(_FIELD_NAMES - {"source_path"}))))
    if "account_id" not in d:
        raise ConfigError("config %s has no `account_id`. There is no default account id — two "
                          "accounts must never be distinguishable only by which file was loaded."
                          % (source_path or "<in-process>"))
    kw: dict[str, Any] = {k: v for k, v in d.items() if k in _FIELD_NAMES}
    for k in _PATH_FIELDS:
        if kw.get(k) is not None:
            kw[k] = Path(str(kw[k])).expanduser()
    kw["source_path"] = source_path
    return WQConfig(**kw)


def claim_state_dir(cfg: WQConfig) -> None:
    """Write `<state_dir>/.wq_account`, or refuse if a DIFFERENT account already claimed it.

    This is the guard for the failure that matters: account 2 configured — by typo, by a copied
    file, by a relative path resolved from the wrong cwd — at account 1's state directory, and
    quietly appending to account 1's submit ledger. The marker makes that a refusal at load time
    instead of a corrupted ledger discovered later."""
    if not cfg.state_dir.exists():
        return
    marker = cfg.state_dir / CLAIM_FILE
    if marker.exists():
        owner = marker.read_text().strip()
        if owner and owner != cfg.account_id:
            raise ConfigError(
                "state dir %s is claimed by account %r but this config is account %r. REFUSING: "
                "sharing a state directory means one account appends to the other's ledgers "
                "(submit_budget.jsonl, banned_fields.json, auto_submit_journal.jsonl). Point "
                "`state_dir` at a directory of its own, or delete %s if the claim is stale."
                % (cfg.state_dir, owner, cfg.account_id, marker))
        return
    tmp = marker.with_suffix(".tmp")
    tmp.write_text(cfg.account_id + "\n")
    os.replace(tmp, marker)


def load(path: Optional[str] = None, claim: bool = True) -> WQConfig:
    """Load the one config. Fails CLOSED — see the module docstring for all four refusals."""
    tried = search_paths(path)
    for p in tried:
        if p.is_file():
            try:
                d = json.loads(p.read_text())
            except json.JSONDecodeError as e:
                raise ConfigError("config %s is not valid JSON: %s" % (p, e)) from e
            cfg = from_dict(d, source_path=str(p))
            if claim:
                claim_state_dir(cfg)
            return cfg
    raise ConfigError(
        "no account config found. Searched, in order: %s. Set $WQ_CONFIG or create %s. "
        "This does NOT fall back to %s — an unconfigured process must not inherit another "
        "account's state directory."
        % (", ".join(str(p) for p in tried), REPO_ROOT / DEFAULT_CONFIG_NAME, REPO_ROOT / "state"))


if __name__ == "__main__":
    import sys
    c = load(sys.argv[1] if len(sys.argv) > 1 else None)
    print(json.dumps({f.name: str(getattr(c, f.name)) for f in fields(c)}, indent=2))

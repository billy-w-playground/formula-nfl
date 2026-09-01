"""Betting splits + the 'Formula' signal — OddsCrowd edition.

DATA SOURCE: api.oddscrowd.com — a clean REST API discovered via HAR
capture of the odds-comparison page (Sep 2026). League filtering is
explicit (sport_slug=amer-football&league_slug=nfl); per-book odds ride
event_teams.odds_total / odds_spread; index 1 = home team.

IMPORTANT STATUS: as of preseason 2026 the API sends NO bets/money/opener
fields — the site's Bets/Money columns render dashes because the data
does not exist yet. Lines parse today; the Formula signals stay dormant
until OddsCrowd starts sending split percentages (re-capture a HAR then
and match _PCT_KEYS below to the real field names).

The Formula itself is unchanged and source-agnostic:
  signal on side S when bets%(S) < 50, money%(S)-bets%(S) >= threshold,
  and the line moved toward S versus opening.
"""
from __future__ import annotations
import time
from dataclasses import dataclass

import requests

from ..teams import resolve

API = "https://api.oddscrowd.com/events"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"),
    "Accept": "application/json",
    "Origin": "https://oddscrowd.com",
    "Referer": "https://oddscrowd.com/",
}
# candidate field names for split percentages, checked when they appear
_PCT_KEYS = ("bets_percent", "bet_percent", "tickets_percent", "bets_pct",
             "money_percent", "money_pct", "handle_percent")


@dataclass
class Splits:
    away: str
    home: str
    open_home_spread: float | None = None
    cur_home_spread: float | None = None
    home_bets_pct: float | None = None
    home_money_pct: float | None = None
    open_total: float | None = None
    cur_total: float | None = None
    over_bets_pct: float | None = None
    over_money_pct: float | None = None


def _median(xs):
    xs = sorted(x for x in xs if x is not None)
    return xs[len(xs) // 2] if xs else None


def _params(bet_type: str, include: str, page: int) -> list[tuple[str, str]]:
    return [
        ("from", str(int(time.time()) - 6 * 3600)),
        ("per_page", "50"), ("order_by", "datetime"),
        ("with[]", "league"), ("with[]", "league.sport"),
        ("with[]", f"event_teams.{include}.bookmaker.image"),
        ("with[]", f"event_teams.{include}.bet_type"),
        ("sport_slug", "amer-football"), ("league_slug", "nfl"),
        ("bet_type", bet_type), ("page", str(page)),
    ]


def _fetch_events(bet_type: str, include: str, timeout: int) -> list[dict]:
    events, page = [], 1
    while page <= 5:
        r = requests.get(API, params=_params(bet_type, include, page),
                         headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        events.extend(data.get("data", []))
        if not data.get("next_page_url"):
            break
        page += 1
    return events


def _team_split_pcts(et: dict) -> tuple[float | None, float | None]:
    """Scan an event_team (and its odds rows) for split percentage fields."""
    pools = [et] + list(et.get("odds_spread") or []) + list(et.get("odds_total") or [])
    bets = money = None
    for node in pools:
        if not isinstance(node, dict):
            continue
        for k, v in node.items():
            kl = k.lower()
            if not isinstance(v, (int, float)):
                continue
            if bets is None and any(t in kl for t in ("bets", "bet_", "ticket")) and "pct" in kl + "percent" and ("percent" in kl or "pct" in kl):
                bets = float(v)
            if money is None and ("money" in kl or "handle" in kl) and ("percent" in kl or "pct" in kl):
                money = float(v)
    return bets, money


def fetch(endpoint_url: str | None = None, timeout: int = 20
          ) -> dict[tuple[str, str], Splits]:
    """Fetch NFL spread + total data. endpoint_url optionally overrides the
    spread call entirely (paste a captured URL to pin behavior)."""
    out: dict[tuple[str, str], Splits] = {}

    def ingest(events: list[dict], kind: str):
        for ev in events:
            if (ev.get("league") or {}).get("slug") != "nfl":
                continue
            ets = sorted(ev.get("event_teams", []), key=lambda e: e.get("index", 9))
            if len(ets) < 2:
                continue
            home_et = next((e for e in ets if e.get("index") == 1), ets[0])
            away_et = next((e for e in ets if e.get("index") == 2), ets[-1])
            ht, at = home_et.get("team") or {}, away_et.get("team") or {}
            home = resolve(ht.get("name", "")) or resolve(ht.get("abbrv") or "")
            away = resolve(at.get("name", "")) or resolve(at.get("abbrv") or "")
            if not home or not away:
                continue
            s = out.setdefault((away, home), Splits(away=away, home=home))
            if kind == "spread":
                rows = home_et.get("odds_spread") or []
                s.cur_home_spread = _median([r.get("market_argument") for r in rows])
                b, m = _team_split_pcts(home_et)
                s.home_bets_pct, s.home_money_pct = b, m
            else:
                over_rows = [r for r in (home_et.get("odds_total") or [])
                             if str(r.get("name", "")).lower() == "over"]                     or (home_et.get("odds_total") or [])
                s.cur_total = _median([r.get("market_argument") for r in over_rows])
                b, m = _team_split_pcts(home_et)
                s.over_bets_pct, s.over_money_pct = b, m

    if endpoint_url and endpoint_url.startswith("http"):
        r = requests.get(endpoint_url, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        ingest(r.json().get("data", []), "spread")
    else:
        try:
            ingest(_fetch_events("AH_OT", "odds_spread", timeout), "spread")
        except Exception:
            pass  # spread include name is inferred; totals call is verified
    ingest(_fetch_events("OU_OT", "odds_total", timeout), "total")

    if not out:
        raise ValueError("OddsCrowd returned no NFL events")
    return out


@dataclass
class FormulaSignal:
    market: str          # "spread" or "total"
    side: str            # team abbr, or "Over"/"Under"
    bets_pct: float
    money_pct: float
    differential: float
    line_move: float     # movement toward the side, in points
    strength: str        # "Strong" / "Lean"


def spread_signal(s: Splits, diff_threshold: float = 5.0,
                  move_threshold: float = 0.5) -> FormulaSignal | None:
    if None in (s.open_home_spread, s.cur_home_spread,
                s.home_bets_pct, s.home_money_pct):
        return None
    move_home = s.open_home_spread - s.cur_home_spread  # + = toward home
    for side, bets, money, move in (
        (s.home, s.home_bets_pct, s.home_money_pct, move_home),
        (s.away, 100 - s.home_bets_pct, 100 - s.home_money_pct, -move_home),
    ):
        diff = money - bets
        if bets < 50 and diff >= diff_threshold and move >= move_threshold:
            strength = "Strong" if (diff >= 15 or move >= 1.5) else "Lean"
            return FormulaSignal("spread", side, round(bets, 1),
                                 round(money, 1), round(diff, 1),
                                 round(move, 2), strength)
    return None


def total_signal(s: Splits, diff_threshold: float = 5.0,
                 move_threshold: float = 0.5) -> FormulaSignal | None:
    if None in (s.open_total, s.cur_total, s.over_bets_pct, s.over_money_pct):
        return None
    move_over = s.cur_total - s.open_total  # + = toward Over
    for side, bets, money, move in (
        ("Over", s.over_bets_pct, s.over_money_pct, move_over),
        ("Under", 100 - s.over_bets_pct, 100 - s.over_money_pct, -move_over),
    ):
        diff = money - bets
        if bets < 50 and diff >= diff_threshold and move >= move_threshold:
            strength = "Strong" if (diff >= 15 or move >= 1.5) else "Lean"
            return FormulaSignal("total", side, round(bets, 1),
                                 round(money, 1), round(diff, 1),
                                 round(move, 2), strength)
    return None

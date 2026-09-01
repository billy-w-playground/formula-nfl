"""Public betting splits and the 'Formula' signal — OddsCrowd edition.

DATA SOURCE: oddscrowd.com. Their odds-comparison pages carry Bets / Money /
Opener columns, but those cells are filled client-side by JavaScript — the
static HTML serves dashes. fetch() therefore requires the site's internal
data endpoint URL, captured once via browser DevTools (Network tab ->
Fetch/XHR -> the request whose response contains bets/money percentages).
Paste that URL into the app sidebar. The parser below is written tolerantly
against common shapes and will need one round of adjustment against the
first real payload.

The Formula (user's method) is unchanged and source-agnostic:
  A signal fires on side S when, versus opening:
    1. Ticket minority: bets% on S < 50
    2. Sharp differential: money%(S) - bets%(S) >= diff_threshold
    3. Reverse line movement toward S >= move_threshold
"""
from __future__ import annotations
from dataclasses import dataclass

import requests

from ..teams import resolve

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"),
    "Accept": "application/json",
    "Referer": "https://oddscrowd.com/odds-comparison/amer-football/leagues/nfl/bet-types/spread-fullgame",
}


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


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _walk_games(obj):
    """Yield dict nodes that look like game objects anywhere in the JSON."""
    if isinstance(obj, dict):
        keys = {k.lower() for k in obj}
        if ({"hometeam", "awayteam"} & keys or {"home_team", "away_team"} & keys
                or {"home", "away"} & keys):
            yield obj
        for v in obj.values():
            yield from _walk_games(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_games(v)


def _get(d, *names):
    for n in names:
        for k, v in d.items():
            if k.lower().replace("_", "") == n.lower().replace("_", ""):
                return v
    return None


def fetch(endpoint_url: str, timeout: int = 20) -> dict[tuple[str, str], Splits]:
    """Fetch splits from the OddsCrowd internal endpoint (see module doc)."""
    if not endpoint_url or not endpoint_url.startswith("http"):
        raise ValueError("No OddsCrowd endpoint URL configured — grab it via "
                         "DevTools (Network -> Fetch/XHR) and paste it in the sidebar")
    r = requests.get(endpoint_url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    out: dict[tuple[str, str], Splits] = {}
    for g in _walk_games(data):
        home_raw = _get(g, "homeTeam", "home")
        away_raw = _get(g, "awayTeam", "away")
        if isinstance(home_raw, dict):
            home_raw = _get(home_raw, "name", "fullName", "teamName")
        if isinstance(away_raw, dict):
            away_raw = _get(away_raw, "name", "fullName", "teamName")
        home, away = resolve(str(home_raw or "")), resolve(str(away_raw or ""))
        if not home or not away:
            continue
        s = Splits(away=away, home=home)
        s.cur_home_spread = _num(_get(g, "homeSpread", "spreadHome", "spread"))
        s.open_home_spread = _num(_get(g, "homeSpreadOpen", "spreadHomeOpen",
                                       "openingSpread", "openerSpread"))
        s.home_bets_pct = _num(_get(g, "homeSpreadBetsPct", "homeBetsPct",
                                    "spreadBetsHome", "betsHome"))
        s.home_money_pct = _num(_get(g, "homeSpreadMoneyPct", "homeMoneyPct",
                                     "spreadMoneyHome", "moneyHome"))
        s.cur_total = _num(_get(g, "total", "overUnder", "totalPoints"))
        s.open_total = _num(_get(g, "totalOpen", "openingTotal", "openerTotal"))
        s.over_bets_pct = _num(_get(g, "overBetsPct", "totalBetsOver", "betsOver"))
        s.over_money_pct = _num(_get(g, "overMoneyPct", "totalMoneyOver", "moneyOver"))
        out[(away, home)] = s
    if not out:
        raise ValueError("OddsCrowd payload parsed to zero games — send the "
                         "raw JSON so the parser can be matched to it")
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

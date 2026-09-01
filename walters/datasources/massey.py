"""Massey Ratings for the NFL.

CAUTION: masseyratings.com/nfl/ratings renders via JavaScript — there is no
static HTML table to scrape. The page is fed by Massey's JSON backend
(model export). This module tries the JSON endpoint the site uses; if
Massey changes it, fetch() raises and the app falls back to CSV paste
(the same 'Massey CSV Paste' workflow as the original spreadsheet, but
optional rather than mandatory).

CSV fallback format (from Massey's Export feature or hand-built):
    Team,Rating
    Detroit Lions,88.0
"""
from __future__ import annotations
import csv
import io
import requests

from ..teams import resolve

# The JSON endpoint pattern used by Massey's ratings pages. `sub` values
# have historically been stable per league; NFL uses the argument below.
# If this 404s, use the CSV fallback in the app.
JSON_URL = "https://masseyratings.com/json/rate.php"
PARAMS = {"s": "nfl", "dt": 0}


def fetch(timeout: int = 20) -> dict[str, float]:
    r = requests.get(JSON_URL, params=PARAMS, timeout=timeout,
                     headers={"User-Agent": "Mozilla/5.0 (walters-model)"})
    r.raise_for_status()
    data = r.json()
    out: dict[str, float] = {}
    # Massey's JSON is a table: data['DI'] describes columns, data['DT'] rows.
    cols = [c.get("name", "").lower() for c in data.get("DI", [])]
    try:
        team_i = next(i for i, c in enumerate(cols) if "team" in c)
        rat_i = next(i for i, c in enumerate(cols) if c.startswith("rat"))
    except StopIteration:
        raise ValueError("Massey JSON schema changed; use CSV fallback")
    for row in data.get("DT", []):
        cell = row[team_i]
        name = cell[0] if isinstance(cell, list) else cell
        rcell = row[rat_i]
        rating = rcell[0] if isinstance(rcell, list) else rcell
        abbr = resolve(str(name))
        if abbr:
            out[abbr] = float(rating)
    if len(out) < 20:
        raise ValueError("Massey parse produced too few teams; use CSV fallback")
    return out


def parse_csv(text: str) -> dict[str, float]:
    """Fallback: parse a pasted Team,Rating CSV."""
    out: dict[str, float] = {}
    reader = csv.reader(io.StringIO(text.strip()))
    for row in reader:
        if len(row) < 2:
            continue
        abbr = resolve(row[0])
        try:
            rating = float(row[-1])
        except ValueError:
            continue  # header row
        if abbr:
            out[abbr] = rating
    return out

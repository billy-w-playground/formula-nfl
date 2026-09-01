"""Massey Ratings via their JSON backend, with the value cipher decoded.

Massey's ratings pages load data from /json/rate.php?argv=... and obfuscate
numeric cells with a running LCG: seed = (0x1fb9*seed + 0x4d2) % 1024,
stepped once per cell down each encoded column (columns flagged gfac in CI).
gfac==1 cells (ranks) subtract the seed; gfac==2 cells (values) divide by
seed+1. The page seeds from an inline stamp value, but the seed space is
only 1024, so we brute-force the anchor using the constraint that rank
columns must decode to integers in [1, n_teams]. Validated against the
site's rendered table (2026 preseason).

Returned rating: the 'Pwr' (Power rating) column — point-spread scale.
If Massey rotates the argv token or changes the scheme, fetch() raises and
the app falls back to the sidebar CSV paste.
"""
from __future__ import annotations
import csv
import io
import requests

from ..teams import resolve

ARGV = ("slxlZrMjujc7FOv1L0Uz63MgeaeaNkKU2F2E3ka5MNriHAi2dOle1IC5qgO8qd_8"
        "5DDs1oEFwKaVPcmxJb566hfFVCBM97M3SuJj_UJh_Ko.")
JSON_URL = "https://masseyratings.com/json/rate.php"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Referer": "https://masseyratings.com/nfl/ratings",
    "X-Requested-With": "XMLHttpRequest",
}


def _decode_table(CI: list, DI: list) -> list | None:
    """Brute-force the LCG anchor; return decoded rows or None."""
    gcols = [i for i, c in enumerate(CI) if c.get("gfac")]
    n = len(DI)
    if not gcols or not n:
        return DI
    for seed0 in range(1024):
        seed, first, ok = seed0, True, True
        out = [row[:] for row in DI]
        for col in gcols:
            g = CI[col]["gfac"]
            for r in range(n):
                if first:
                    first = False
                else:
                    seed = (0x1FB9 * seed + 0x4D2) % 1024
                v = out[r][col]
                is_arr = isinstance(v, list)
                x = v[0] if is_arr else v
                if x is None:
                    continue
                if g == 1:
                    x -= seed
                    if not (isinstance(x, int) and 1 <= x <= n):
                        ok = False
                        break
                elif g == 2:
                    x /= (seed + 1)
                out[r][col] = ([x] + v[1:]) if is_arr else x
            if not ok:
                break
        if ok:
            return out
    return None


def parse_payload(data: dict) -> dict[str, float]:
    """Decode a rate.php JSON payload -> {abbr: power_rating}."""
    CI, DI = data.get("CI", []), data.get("DI", [])
    table = _decode_table(CI, DI)
    if table is None:
        raise ValueError("Massey decode failed (cipher may have changed) — "
                         "use CSV fallback")
    # find the value column following the 'Power rating' rank column
    val_col = None
    for i, c in enumerate(CI):
        if "power rating" in str(c.get("key", "")).lower():
            val_col = i + 1 if i + 1 < len(CI) and not CI[i + 1].get("title") else i
            if c.get("gfac") == 2:  # column itself holds the value
                val_col = i
            break
    if val_col is None:
        for i, c in enumerate(CI):
            if "overall strength" in str(c.get("key", "")).lower():
                val_col = i + 1
                break
    if val_col is None:
        raise ValueError("Massey schema changed: no power column — use CSV fallback")
    out: dict[str, float] = {}
    for row in table:
        name_cell = row[0]
        name = name_cell[0] if isinstance(name_cell, list) else name_cell
        abbr = resolve(str(name))
        val = row[val_col]
        if isinstance(val, list):
            val = val[0]
        if abbr and isinstance(val, (int, float)):
            out[abbr] = float(val)
    if len(out) < 20:
        raise ValueError(f"Massey parse got only {len(out)} teams — use CSV fallback")
    return out


def fetch(timeout: int = 20) -> dict[str, float]:
    r = requests.get(JSON_URL, params={"argv": ARGV}, headers=HEADERS,
                     timeout=timeout)
    r.raise_for_status()
    return parse_payload(r.json())


def parse_csv(text: str) -> dict[str, float]:
    """Fallback paste parser. Accepts either a simple Team,Rating CSV or
    Massey's own Export file (header row: Team,,Rec,,Rat,,Pwr,... where the
    power VALUE sits one column after the 'Pwr' rank column)."""
    text = text.lstrip("\ufeff").strip()
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return {}
    val_idx = None  # None => simple mode (last column)
    header = [c.strip().lower() for c in rows[0]]
    if "pwr" in header:
        val_idx = header.index("pwr") + 1
        rows = rows[1:]
    elif "team" in header:
        rows = rows[1:]
    out: dict[str, float] = {}
    for row in rows:
        if len(row) < 2:
            continue
        abbr = resolve(row[0])
        if not abbr:
            continue
        try:
            rating = float(row[val_idx] if val_idx is not None else row[-1])
        except (ValueError, IndexError):
            continue
        out[abbr] = rating
    return out

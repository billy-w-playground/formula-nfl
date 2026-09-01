"""Billy Walters NFL model + Formula splits — Streamlit app.

Tabs: Walters | Formula Spreads | Walters x Formula | Formula O/U
Run:  streamlit run app.py
"""
import datetime as dt

import pandas as pd
import streamlit as st

from walters.pipeline import run_week
from walters.scoring import BOOK_FACTOR_SCALE
from walters.datasources import (sonnymoore, massey, odds as odds_api,
                                 injuries as inj_api, oddscrowd as splits_api)

st.set_page_config(page_title="Walters NFL Model", page_icon="🏈", layout="wide")

BOARD_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=VT323&family=IBM+Plex+Mono:wght@500;700&display=swap');
html, body, [data-testid="stAppViewContainer"] { background: #000 !important; }
h1 { font-family: 'VT323', monospace !important; color: #ffbf00 !important;
     letter-spacing: 2px; font-size: 3rem !important; }
[data-testid="stMetricValue"] { font-family: 'VT323', monospace;
     color: #00e63c; font-size: 2.6rem; }
[data-testid="stMetricLabel"] { color: #7a7a7a; }
button[data-baseweb="tab"] { font-family: 'VT323', monospace;
     font-size: 1.3rem; color: #00e63c; }
button[data-baseweb="tab"][aria-selected="true"] { color: #ffbf00; }
.board { width: 100%; border-collapse: collapse;
     font-family: 'IBM Plex Mono', monospace; font-size: 0.86rem;
     background: #000; }
.board th { color: #7a7a7a; text-align: left; font-weight: 500;
     border-bottom: 1px solid #262626; padding: 4px 10px;
     font-size: 0.72rem; }
.board td { padding: 5px 10px; border-bottom: 1px solid #141414;
     color: #ffbf00; font-weight: 700; white-space: nowrap; }
.board td.team { color: #00e63c; }
.board td.neg { color: #ff3b30; }
.board td.sig { color: #00e63c; }
.board td.dim { color: #555; font-weight: 500; }
.board tr:hover td { background: #0d0d0d; }
</style>
"""
st.markdown(BOARD_CSS, unsafe_allow_html=True)


def board_table(df, team_cols=(), signal_cols=(), dim_cols=()):
    """Render a dataframe as a Vegas-board HTML table."""
    import html as _html
    head = "".join(f"<th>{_html.escape(str(c))}</th>" for c in df.columns)
    rows = []
    for _, row in df.iterrows():
        cells = []
        for c in df.columns:
            v = row[c]
            txt = "" if v is None or (isinstance(v, float) and pd.isna(v)) else v
            if isinstance(txt, float):
                txt = f"{txt:+.1f}" if c not in ("Injuries",) else f"{txt:.0f}"
            txt = _html.escape(str(txt))
            cls = ""
            if c in team_cols:
                cls = "team"
            elif c in signal_cols and str(v).strip():
                cls = "sig"
            elif c in dim_cols:
                cls = "dim"
            elif isinstance(v, (int, float)) and not isinstance(v, bool) and v < 0:
                cls = "neg"
            cells.append(f'<td class="{cls}">{txt}</td>')
        rows.append("<tr>" + "".join(cells) + "</tr>")
    st.markdown(f'<table class="board"><thead><tr>{head}</tr></thead>'
                f'<tbody>{"".join(rows)}</tbody></table>',
                unsafe_allow_html=True)


st.title("🏈 BILLY WALTERS NFL BOARD")

with st.sidebar:
    st.header("Run settings")
    today = dt.date.today()
    default_season = today.year if today.month >= 8 else today.year - 1
    season = st.number_input("Season", 2020, 2035, default_season)
    week = st.number_input("Week", 1, 18, 1)
    hfa = st.slider("Home field advantage (pts)", 0.0, 4.0, 1.9, 0.1)
    scale = st.radio("Factor weighting",
                     ["Book spec (units ÷ 5)", "Legacy raw (spreadsheet)"])
    factor_scale = BOOK_FACTOR_SCALE if scale.startswith("Book") else 1.0

    st.divider()
    st.header("Formula thresholds")
    diff_thr = st.slider("Money−Bets differential ≥", 1.0, 25.0, 5.0, 0.5)
    move_thr = st.slider("Reverse line move ≥ (pts)", 0.0, 3.0, 0.5, 0.5)

    st.divider()
    st.header("Super Bowl carryover")
    from walters.teams import TEAMS as _T
    _opts = ["(none)"] + sorted(_T)
    sb_winner = st.selectbox("Last SB winner", _opts, index=0)
    sb_loser = st.selectbox("Last SB loser", _opts, index=0)
    sb_winner = "" if sb_winner == "(none)" else sb_winner
    sb_loser = "" if sb_loser == "(none)" else sb_loser

    st.divider()
    st.header("Data sources")
    use_sonny = st.checkbox("Use Sonny Moore ratings", True,
        help="Uncheck early season if his page is still last year's final ratings")
    use_massey = st.checkbox("Use Massey ratings", True)
    use_weather = st.checkbox("Fetch weather (Open-Meteo)", True)
    use_injuries = st.checkbox("Fetch injury reports (ESPN)", True)
    use_splits = st.checkbox("Fetch betting splits (OddsCrowd)", True)
    oc_url = st.text_input(
        "OddsCrowd data endpoint URL",
        help="One-time DevTools grab: Network -> Fetch/XHR on the NFL "
             "spread page, copy the request URL whose response holds "
             "bets/money percentages.")
    odds_key = st.text_input("The Odds API key (optional)", type="password")
    massey_csv = st.text_area("Massey CSV fallback (Team,Rating)", height=100)

run = st.button("▶ Run model", type="primary", use_container_width=True)

if not run:
    st.info("Set the week and hit **Run model**. No keys needed for the "
            "defaults; The Odds API key improves market lines.")
    st.stop()

prog = st.progress(0, "Power ratings…")
warnings = []

sonny_r = massey_r = None
if use_sonny:
    try:
        sonny_r = sonnymoore.fetch()
    except Exception as e:
        warnings.append(f"Sonny Moore fetch failed: {e}")
if use_massey:
    if massey_csv.strip():
        massey_r = massey.parse_csv(massey_csv)
    else:
        try:
            massey_r = massey.fetch()
        except Exception as e:
            warnings.append(f"Massey auto-fetch failed ({e}) — CSV fallback available in sidebar.")
prog.progress(20, "Odds…")

odds_lookup = None
if odds_key.strip():
    try:
        odds_lookup = odds_api.fetch(odds_key.strip())
    except Exception as e:
        warnings.append(f"Odds API failed: {e} — using ESPN lines.")
prog.progress(35, "Injuries…")

injuries = {}
if use_injuries:
    injuries = inj_api.fetch()
    if not injuries:
        warnings.append("Injury fetch returned nothing — reports unavailable.")
prog.progress(50, "Betting splits…")

splits = {}
if use_splits:
    try:
        splits = splits_api.fetch(oc_url.strip())
    except Exception as e:
        warnings.append(f"Betting splits failed ({e}). Formula tabs will be "
                        "empty until the OddsCrowd endpoint is configured.")
prog.progress(65, "Schedule, weather, scoring…")

if not sonny_r and not massey_r:
    st.error("No ratings source available. Paste a Massey CSV or retry.")
    st.stop()

try:
    results = run_week(int(season), int(week), massey_r, sonny_r,
                       odds_lookup=odds_lookup, hfa=hfa,
                       factor_scale=factor_scale,
                       sb_winner=sb_winner.strip().upper() or None,
                       sb_loser=sb_loser.strip().upper() or None,
                       fetch_weather=use_weather, injuries=injuries)
except Exception as e:
    st.error(f"Pipeline failed: {e}")
    st.stop()
prog.progress(100, "Done")

for w in warnings:
    st.warning(w)
unknown_venues = [r["venue"] for r in results
                  if r["neutral_site"] and not r.get("venue_recognized", True)]
if unknown_venues:
    st.warning("Unrecognized international venue(s) — travel factors "
               "skipped: " + ", ".join(sorted(set(unknown_venues))) +
               ". Add coordinates to INTL_VENUES in walters/teams.py.")
if not results:
    st.info("No games found for that season/week.")
    st.stop()

# --- derive Formula signals -------------------------------------------------
spread_sigs, total_sigs = {}, {}
for key, s in splits.items():
    sig = splits_api.spread_signal(s, diff_thr, move_thr)
    if sig:
        spread_sigs[key] = (sig, s)
    tsig = splits_api.total_signal(s, diff_thr, move_thr)
    if tsig:
        total_sigs[key] = (tsig, s)

tab_w, tab_fs, tab_wx, tab_ou = st.tabs(
    ["🏈 Walters", "📈 Formula Spreads", "🎯 Walters × Formula", "⬆️⬇️ Formula O/U"])

# --- Tab 1: Walters ----------------------------------------------------------
with tab_w:
    rows = []
    for r in results:
        flags = []
        if r["qb_flag"]:
            flags.append("🚑 QB")
        if r["neutral_site"]:
            flags.append("🌍 INTL")
            if not r.get("venue_recognized", True):
                flags.append("⚠️ VENUE?")
        rows.append({
            "Away": r["away"], "Home": r["home"], "Day": r["game_day"],
            "Walters (Home)": r["walters_home_line"],
            "Market (Home)": r["market_home_spread"],
            "Edge": r["edge"], "Bet": r["bet_side"],
            "Flags": " ".join(flags),
            "Injuries": r["injury_count"],
        })
    df = pd.DataFrame(rows)
    df["_absedge"] = df["Edge"].abs()
    df = df.sort_values("_absedge", ascending=False,
                        na_position="last").drop(columns="_absedge")
    hide_qb = st.checkbox("High-confidence only (hide QB-injury games)", False)
    view = df[~df["Flags"].str.contains("QB")] if hide_qb else df
    c1, c2, c3 = st.columns(3)
    c1.metric("Games", len(df))
    c2.metric("Edges ≥ 1 pt", int((df["Bet"] != "").sum()))
    c3.metric("QB-flagged", int(df["Flags"].str.contains("QB").sum()))
    board_table(view, team_cols=("Away", "Home", "Bet"),
                signal_cols=("Bet",), dim_cols=("Day", "Flags"))

    st.subheader("Game detail")
    for r in sorted(results, key=lambda x: -(abs(x["edge"]) if x["edge"] is not None else -1)):
        label = f"{r['away']} @ {r['home']} — Walters {r['walters_home_line']:+.1f}"
        if r["bet_side"]:
            label += f" → BET {r['bet_side']} ({r['edge']:+.1f})"
        if r["qb_flag"]:
            label += "  🚑"
        with st.expander(label):
            if r["factors"]:
                st.table(pd.DataFrame(r["factors"],
                                      columns=["Factor", "Units", "Credits"]))
            for side, plist in (("Home", r["injuries_home"]),
                                ("Away", r["injuries_away"])):
                if plist:
                    st.caption(f"{side} injuries: " + "; ".join(
                        f"{p['name']} ({p['position']}, {p['status']})"
                        for p in plist))

# --- Tab 2: Formula Spreads --------------------------------------------------
with tab_fs:
    if not splits:
        st.info("No splits data this run.")
    else:
        rows = []
        for (a, h), s in splits.items():
            sig = spread_sigs.get((a, h))
            rows.append({
                "Away": a, "Home": h,
                "Open": s.open_home_spread, "Now": s.cur_home_spread,
                "Home Bets%": s.home_bets_pct, "Home Money%": s.home_money_pct,
                "Signal": sig[0].side if sig else "",
                "Diff": sig[0].differential if sig else None,
                "RLM": sig[0].line_move if sig else None,
                "Strength": sig[0].strength if sig else "",
            })
        board_table(pd.DataFrame(rows), team_cols=("Away", "Home"),
                    signal_cols=("Signal",), dim_cols=("Strength",))

# --- Tab 3: Walters × Formula ------------------------------------------------
with tab_wx:
    combos = []
    for r in results:
        key = (r["away"], r["home"])
        sig = spread_sigs.get(key)
        if r["bet_side"] and sig and sig[0].side == r["bet_side"]:
            combos.append({
                "Away": r["away"], "Home": r["home"], "Side": r["bet_side"],
                "Walters Edge": r["edge"],
                "Formula Diff": sig[0].differential,
                "RLM": sig[0].line_move, "Strength": sig[0].strength,
                "QB Flag": "🚑" if r["qb_flag"] else "",
            })
    if combos:
        st.success(f"{len(combos)} game(s) where Walters and the Formula "
                   "agree on the same side.")
        board_table(pd.DataFrame(combos), team_cols=("Away", "Home", "Side"),
                    signal_cols=("Side",), dim_cols=("Strength",))
    else:
        st.info("No Walters × Formula agreement this run.")

# --- Tab 4: Formula O/U ------------------------------------------------------
with tab_ou:
    if not splits:
        st.info("No splits data this run.")
    else:
        rows = []
        for (a, h), s in splits.items():
            sig = total_sigs.get((a, h))
            rows.append({
                "Away": a, "Home": h,
                "Open Total": s.open_total, "Now": s.cur_total,
                "Over Bets%": s.over_bets_pct, "Over Money%": s.over_money_pct,
                "Signal": sig[0].side if sig else "",
                "Diff": sig[0].differential if sig else None,
                "Move": sig[0].line_move if sig else None,
                "Strength": sig[0].strength if sig else "",
            })
        board_table(pd.DataFrame(rows), team_cols=("Away", "Home"),
                    signal_cols=("Signal",), dim_cols=("Strength",))

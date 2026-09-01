# Billy Walters NFL Model (Streamlit)

Rebuild of the Walters power-rating + game-factor model, per the book chapter.
Hit **Run model** and get Walters lines vs the market for every game that week.

## Data pipes
| Source | What | Key needed | Fragility |
|---|---|---|---|
| ESPN scoreboard (unofficial JSON) | Schedule, results, day/time, embedded lines | No | Low — stable for years, but unofficial |
| Open-Meteo | Kickoff temp/rain at stadium lat/lon | No | Low. Forecasts only ~16 days out |
| Sonny Moore | Power ratings (spread-equivalent) | No | Medium — HTML scrape of a hand-maintained page |
| Massey Ratings | Power ratings | No | **High** — page is JS-rendered; auto-fetch targets their JSON backend and may break. CSV-paste fallback built into the sidebar |
| The Odds API | Consensus market lines | Optional (free tier 500/mo) | Low |

## The model
1. **Power**: each ratings source centered at league mean (→ point-spread units,
   avg team = 0 per the book), then averaged across sources.
2. **Factors**: the book's full factor table (turf, division/conference,
   primetime, Monday-night hangover, OT hangover, byes by team quality,
   Super Bowl carryover, 3rd-away-in-4, consecutive 2+ TZ trips, travel 2000+,
   proximity, body-clock kickoff penalties, blowout bounce-back, warm-to-cold
   and dome-to-cold weather ramps).
3. **Scale**: factor units × **0.2** — the book's "each number is worth
   one-fifth of a point." The legacy spreadsheet applied units raw (5×
   overweight); that mode is available as a toggle for comparison only.
4. **Line**: home margin = ΔPower + HFA (default 1.9, Sonny Moore's number)
   + scaled factors. Walters home line = −margin. Edge = market − Walters.

## Tabs
- **Walters** — model lines vs market, edges, QB-injury flag (🚑), international flag (🌍), high-confidence filter, per-game factor and injury detail.
- **Formula Spreads** — the reverse-line-movement method: signal when ticket minority + money>bets differential + line moved toward that side.
- **Walters × Formula** — games where both methods land on the same side.
- **Formula O/U** — the same method applied to totals.

## Betting splits (OddsCrowd)
Formula tabs use oddscrowd.com. Their Bets/Money/Opener columns load via
JavaScript, so the app needs the site's internal data endpoint URL —
a one-time DevTools grab (Network -> Fetch/XHR on the NFL spread page,
copy the request URL whose response contains bets/money percentages) pasted
into the sidebar. The parser is tolerant but expects one adjustment round
against the first real payload. Unofficial endpoint: can change without
notice; Formula tabs degrade gracefully, model tabs unaffected.

## Known gaps (deliberate)
- **Injuries**: reports are pulled and QB-flagged, but NOT valued in points — the model line ignores them. Use the 🚑 flag to skip games, per your workflow.
- **OT detection**: ESPN's summary feed doesn't flag OT in this endpoint; OT-hangover factors only fire if enriched manually.
- **Super Bowl winner/loser**: set manually in the sidebar each season.

## Run
```
pip install -r requirements.txt
streamlit run app.py
```
Deploy free: push to GitHub → share.streamlit.io → point at `app.py`.

## Tests
```
python tests/test_scoring.py
```

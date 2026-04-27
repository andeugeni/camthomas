# CAMTHOMAS

**Career Arc Model for Tracking Historical Outputs, Mapping Athletic Statistics**

A fantasy basketball projection system inspired by Basketball Reference's Simple Projection System and FiveThirtyEight's discontinued CARMELO model. Live at [**camthomas.vercel.app**](https://camthomas.vercel.app/). It’s an expanded, visualized version of my draft guide EXCEL builder developed on [kaggle.com/andrewsonicoeugenio](http://kaggle.com/andrewsonicoeugenio) that led me to two (2) fantasy basketball championships.

---

## Overview

CAMTHOMAS projects NBA player fantasy performance using two complementary systems:

1. **SPS Layer** — A fixed-formula, weighted 3-year regression toward the league mean with age adjustment, extended 5 years forward by iterating each projection as the next year's input.
2. **Similarity Layer** — A career-arc comparison engine that finds the 10 most historically similar players at the same age and uses their future trajectories to generate probabilistic projections.

The combination mirrors the original CARMELO architecture: SPS provides the statistical baseline, similarity scoring provides the career-shape context.

---

## Architecture

```
nba_api / Basketball Reference
        │
        ▼
  src/data/fetch.py
  ┌─────────────────────────────────┐
  │  player_totals_{year}.csv       │
  │  player_advanced_{year}.csv     │
  │  player_bio.csv                 │
  │  draft_positions.csv            │
  └─────────────────────────────────┘
        │
        ▼
  src/data/pipeline.py
  ┌─────────────────────────────────────────────────────┐
  │  historical_sps_projections.csv  (1980 – present)   │
  │  historical_actuals.csv          (1980 – present)   │
  └─────────────────────────────────────────────────────┘
        │
        ├──────────────────────────────┐
        ▼                              ▼
  src/models/projections.py    src/models/compute_similarities.py
  ┌──────────────────────┐     ┌──────────────────────────────┐
  │  projections_2026.csv│     │  similarities.json           │
  │  (per-36 → per-game) │     │  (top 10 comps per player)   │
  └──────────────────────┘     └──────────────────────────────┘
        │                              │
        └──────────────┬───────────────┘
                       ▼
         src/data/build_player_cards.py
         ┌──────────────────────────────┐
         │  player_cards_2026.csv       │
         │  (single flat file for UI)   │
         └──────────────────────────────┘
                       │
                       ▼
              app/ (Next.js / Vercel)
```

---

## Projection Methodology

### SPS Formula (Year 1)

For each counting stat, CAMTHOMAS applies a weighted 3-year regression toward the league mean:

$$\text{per36} = \frac{W_\text{player} + W_\text{league_avg_1000min}}{W_\text{minutes} + 1000} \times 36$$

where weights are **6 / 3 / 1** for the most recent three seasons respectively. Missing seasons are skipped and remaining weights renormalized.

**Age adjustment** is then applied:

| Age | Direction | Rate |
| --- | --- | --- |
| < 28 | Improvement | +0.4% per year from 28 |
| > 28 | Decline | −0.2% per year from 28 |
| tov | Inverted | same rates, opposite sign |

**Minutes projection** uses the same weighted average with an additional young-player boost for sub-30 mpg players under age 28.

### SPS Iteration (Years 2–5)

Each projection year is fed back as the new "current season" (weight 6 only) to produce the next year's projection. This propagates both the statistical trajectory and the minutes curve forward across five seasons.

### Similarity Engine

Players are represented as weighted feature vectors across five buckets:

| Bucket | Features | Weight Range |
| --- | --- | --- |
| Physical / Draft | position, height, weight, log(draft pick) | 1.0 – 3.5 |
| Volume / Role | career mp, mpg, total mp, usg% | 1.5 – 6.0 |
| Shooting Efficiency | ts%, ft%, ft-freq, adj 3p-freq | 1.5 – 5.0 |
| Playmaking | ast%, tov% | 1.5 – 4.0 |
| Defense / Rebounding | trb%, blk%, stl%, dbpm, bpm | 2.0 – 5.0 |

Vectors are z-scored across the candidate pool, weights are reapplied, and Euclidean distance is computed. Similarity is scaled to 0–100 via `100 × exp(−dist / k)` where `k` is the median distance in the pool — a typical comparable scores ~61, a strong one scores 80+.

Age-matching constrains candidates to ±1 year of the target player's current age.

### Fantasy Scoring

All projections are converted to the fantasy point scoring of my friend Stephen’s league:

| Stat | Weight |
| --- | --- |
| 2PM | +1.5 |
| 3PM | +2.25 |
| FTM | +0.75 |
| REB | +1.25 |
| AST | +1.5 |
| STL | +2.0 |
| BLK | +2.0 |
| TOV | −1.0 |

---

## Data Pipeline

### Fetch (`src/data/fetch.py`)

Pulls from Basketball Reference via `basketball_reference_web_scraper` and the BallDontLie API:

- **Totals** — counting stats for every player-season from 1980 onward
- **Advanced** — BPM, DBPM, TS%, USG%, TRB%, AST%, STL%, BLK%, TOV%, VORP, WS/48, PER
- **Bio** — height, weight, and draft position via BallDontLie (name-matched to BR slugs)
- **Draft** — overall pick number scraped from BR draft pages (one-shot, all-time)

Multi-team players: the combined "TOT" row is kept and individual team rows are dropped.

### Pipeline (`src/data/pipeline.py`)

Builds two parallel historical tables covering every player-snapshot from 1980–2025:

- `historical_sps_projections.csv` — what SPS predicted at each snapshot age, extended 5 years forward
- `historical_actuals.csv` — what actually happened in the same ±year windows

Both share a common schema: `player_id, player, snapshot_year, snapshot_age` plus lookback columns `{stat}_ym2/_ym1/_y0` and forward columns `{stat}_y1` through `{stat}_y5`.

### Projections (`src/models/projections.py`)

Performs “pipeline” historical SPS projection, but for “current” players. “Current” in this instance means any player with >1 minute played within the last 3 years.

### Compute Similarities (`src/models/compute_similarities.py`)

Generates the top 10 similar comparisons using weights listed above.

### Carmelo Adjust (`src/models/carmelo_adjust.py.py`)

Adjusts SPS per-game fantasy point projections using a CARMELO-style
comparable-player delta approach. For each comparison above a certain similarity threshold, compute how much they beat their own SPS baseline projection and aggregate them, weighted by similarity, to the current player’s SPS projection.

### Player Cards (`src/data/build_player_cards.py`)

Assembles the single flat file consumed by the frontend:

- SPS projections (per-game + fantasy pts, years 1–5)
- Historical actuals arc (≤7 years back)
- Bio and advanced stats
- Shooting tendency columns (3p-freq, ft-freq)
- Percentile ranks against the full historical distribution
- Similarity comps with sparkline trajectories
- CAMTHOMAS-adjusted SPS projections

### Integrate Cards (`src/data/integrate_cards.py`)

- Adds CARMELO-style predictive adjustments to the player cards for use in frontend.

---

## Known Bugs Fixed (vs. Original Notebook)

The original Kaggle SPS notebook contained three bugs that are corrected throughout this codebase:

1. **`inf` projections** for players with zero minutes in the most recent season — fixed by skipping years with `mp == 0` and renormalizing weights.
2. **Copy-paste rate bug** — `proj_trb`, `proj_ast`, `proj_stl`, `proj_blk`, and `proj_tov` all used the FT league rate as their denominator. Each now uses its own stat's league rate.
3. **Wrong numerator in `proj_tov`** — the original used `weighted_blk` instead of `weighted_tov`. Fixed.

---

## Roadmap

- [x]  Data ingestion pipeline (`fetch.py`)
- [x]  Historical table builder (`pipeline.py`)
- [x]  SPS projection engine (`projections.py`)
- [x]  Similarity engine (`compute_similarities.py`)
- [x]  Player card assembler (`build_player_cards.py`)
- [x]  Frontend (Next.js, deployed on Vercel)
- [ ]  Backtesting framework — run 2024 projections on 2021–2023 data, and 2025 projections on 2022-2024 data, validate against actuals vs. SPS.
- [ ]  Accuracy reporting — RMSE per stat, fantasy points MAE, similarity comp accuracy

---

## Tech Stack

| Layer | Technology |
| --- | --- |
| Data ingestion | `basketball_reference_web_scraper`, BallDontLie API, BeautifulSoup |
| Data processing | Python, pandas, NumPy, scikit-learn |
| Local storage | CSV files in-project |
| Frontend | Next.js, Vercel |
| Scheduling | GitHub Actions (planned) |

---

## References

- [Basketball Reference Simple Projection System](https://www.basketball-reference.com/about/projections.html)
- [FiveThirtyEight CARMELO (archived)](https://projects.fivethirtyeight.com/carmelo/)
- [Basketball Reference League Totals](https://www.basketball-reference.com/leagues/NBA_stats_totals.html)

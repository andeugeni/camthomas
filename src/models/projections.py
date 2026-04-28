"""
projections.py
--------------
Basketball Reference Simple Projection System (SPS).

Output shape (one row per player)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  Identity     — player_id, player, age

  Actuals      — last 3 seasons of per-game stats + fantasy_pts
                 columns: {stat}_pg_{year}  /  fantasy_pts_{year}

  Projections  — next 5 seasons of per-game stats + fantasy_pts
                 columns: {stat}_pg_y{1..5}  /  fantasy_pts_y{1..5}
                 plus:    proj_mpg_y{1..5}

Year 1 is a full 3-season weighted SPS projection.
Years 2–5 iterate forward using each prior projection as input (weight 6 only),
via pipeline.iterate_projection.

Only players with mp > 1 in at least one of the three most recent seasons
are included — no historical ghosts.

Weights: most-recent=6, one-prior=3, two-prior=1.  Missing seasons are skipped
and remaining weights normalised automatically.

Bugs fixed vs. original Kaggle notebook
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
1. Division-by-zero (inf) for players with zero recent-season minutes.
2. proj_trb/ast/stl/blk/tov all used FT league rates — each now uses its own.
3. proj_tov used weighted_blk in its numerator — fixed to weighted_tov.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STATS = ["x2p", "x3p", "ft", "trb", "ast", "stl", "blk", "tov"]

DEFAULT_WEIGHTS = (6, 3, 1)

# DraftKings scoring
FANTASY_WEIGHTS: dict[str, float] = {
    "x2p":  1.5,
    "x3p":  2.25,
    "ft":   0.75,
    "trb":  1.25,
    "ast":  1.5,
    "stl":  2.0,
    "blk":  2.0,
    "tov": -1.0,
}

MIN_MP       = 1
FUTURE_YEARS = 5
PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"


# ---------------------------------------------------------------------------
# Fantasy pts helper (works on per-game columns)
# ---------------------------------------------------------------------------

def _fantasy_pts(df: pd.DataFrame, suffix: str) -> pd.Series:
    """
    Compute fantasy points from per-game stat columns named {stat}_pg{suffix}.
    suffix examples: '_2023'  or  '_y1'
    """
    total = pd.Series(0.0, index=df.index)
    for stat, w in FANTASY_WEIGHTS.items():
        col = f"{stat}_pg{suffix}"
        if col in df.columns:
            total += df[col].fillna(0) * w
    return total


# ---------------------------------------------------------------------------
# SPS year-1 projection helpers
# ---------------------------------------------------------------------------

def _age_adjustment(per36: pd.Series, age: pd.Series, stat: str) -> pd.Series:
    sign = -1.0 if stat == "tov" else 1.0
    rate = np.where(age < 28, 0.004, 0.002)
    return per36 * (1.0 + sign * (28 - age) * rate)


def _project_mpg(
    mpg_cols: list[pd.Series],
    mp_cols:  list[pd.Series],
    age:      pd.Series,
    weights:  tuple[int, ...] = DEFAULT_WEIGHTS,
) -> pd.Series:
    numerator    = pd.Series(0.0, index=age.index)
    total_weight = pd.Series(0.0, index=age.index)

    for w, mpg_s, mp_s in zip(weights, mpg_cols, mp_cols):
        played = mp_s > 0
        numerator    += played * w * mpg_s
        total_weight += played.astype(float) * w

    with np.errstate(divide="ignore", invalid="ignore"):
        proj = np.where(total_weight > 0, numerator / total_weight, 0.0)

    proj = pd.Series(proj, index=age.index)
    young_boost = (age < 28) & (proj < 30)
    return pd.Series(
        np.where(
            young_boost,
            np.minimum(proj * (1 + (28 - age) * 0.02), 36),
            np.where(age > 28, proj * (1 + (28 - age) * 0.01), proj),
        ),
        index=age.index,
    )


def _project_stat_per36(
    stat_cols:    list[pd.Series],
    mp_cols:      list[pd.Series],
    league_stats: list[pd.Series],
    league_mps:   list[pd.Series],
    age:          pd.Series,
    stat:         str,
    weights:      tuple[int, ...] = DEFAULT_WEIGHTS,
    regression_mp: float = 1000.0,
) -> pd.Series:
    idx          = age.index
    weighted_val = pd.Series(0.0, index=idx)
    weighted_mp  = pd.Series(0.0, index=idx)
    league_num   = pd.Series(0.0, index=idx)

    for w, s, mp, lg_s, lg_mp in zip(weights, stat_cols, mp_cols, league_stats, league_mps):
        played    = mp > 0
        safe_lgmp = lg_mp.where(lg_mp > 0, 1.0)
        weighted_val += played * w * s
        weighted_mp  += played.astype(float) * w * mp
        league_num   += played.astype(float) * w * mp * (lg_s / safe_lgmp)

    with np.errstate(divide="ignore", invalid="ignore"):
        league_term = np.where(weighted_mp > 0, league_num / weighted_mp * regression_mp, 0.0)
        per36 = np.where(
            weighted_mp > 0,
            (weighted_val + league_term) / (weighted_mp + regression_mp) * 36,
            np.nan,
        )

    return _age_adjustment(pd.Series(per36, index=idx), age, stat)


# ---------------------------------------------------------------------------
# Build wide table (actuals)
# ---------------------------------------------------------------------------

def _build_wide_table(
    all_totals: pd.DataFrame,
    years: list[int],
) -> pd.DataFrame:
    """
    Pivot long-format totals into one row per player.
    Keeps only players with mp > MIN_MP in at least one of the given years.
    Also attaches per-game actual columns: {stat}_pg_{year}, fantasy_pts_{year}.
    """
    frames: dict[int, pd.DataFrame] = {}
    for year in years:
        season_df = all_totals[all_totals["season"] == year].copy()
        season_df = season_df[season_df["mp"] > MIN_MP]
        if "mpg" not in season_df.columns:
            season_df["mpg"] = season_df["mp"] / season_df["g"].replace(0, np.nan)
        frames[year] = season_df

    active_ids = set()
    for df in frames.values():
        active_ids |= set(df["player_id"].unique())

    if not active_ids:
        raise RuntimeError(
            f"No players found with mp > {MIN_MP} in years {years}. "
            "Has fetch.py been run for these seasons?"
        )

    # Identity: name + age from most recent season
    identity_rows = []
    for pid in active_ids:
        for year in sorted(years, reverse=True):
            if year in frames and pid in frames[year]["player_id"].values:
                row = frames[year][frames[year]["player_id"] == pid].iloc[0]
                identity_rows.append({
                    "player_id": pid,
                    "player":    row["player"],
                    "age":       float(row["age"]) if pd.notna(row.get("age")) else np.nan,
                })
                break

    wide = pd.DataFrame(identity_rows)

    # Attach totals + per-game actuals per year
    for year in years:
        if year not in frames:
            continue
        yr = frames[year][["player_id", "mp", "mpg", "g"] + STATS].copy()
        yr = yr.rename(columns={
            "mp":  f"mp_{year}",
            "mpg": f"mpg_{year}",
            "g":   f"g_{year}",
            **{s: f"{s}_{year}" for s in STATS},
        })
        wide = wide.merge(yr, on="player_id", how="left")

    # Fill missing and compute per-game actuals + fantasy pts per year
    for year in years:
        mp_col = f"mp_{year}"
        g_col  = f"g_{year}"
        for col in [mp_col, f"mpg_{year}", g_col] + [f"{s}_{year}" for s in STATS]:
            if col in wide.columns:
                wide[col] = wide[col].fillna(0)
            else:
                wide[col] = 0.0

        g = wide[g_col].replace(0, np.nan)
        for stat in STATS:
            wide[f"{stat}_pg_{year}"] = wide[f"{stat}_{year}"] / g

        wide[f"fantasy_pts_{year}"] = _fantasy_pts(wide, f"_{year}")

    log.info("Wide table: %d players active in %s.", len(wide), years)
    return wide.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Year-1 SPS projection (vectorised)
# ---------------------------------------------------------------------------

def _project_year1(
    wide: pd.DataFrame,
    league_totals: dict[int, dict[str, float]],
    base_year: int,
    weights: tuple[int, ...] = DEFAULT_WEIGHTS,
    regression_mp: float = 1000.0,
) -> pd.DataFrame:
    """
    Compute year-1 (next season) per-36 projections for every player.
    Returns wide with added columns: proj_{stat}_per36_y1, proj_mpg_y1.
    """
    years    = [base_year, base_year - 1, base_year - 2]
    age      = wide["age"].fillna(28).astype(float)
    proj_age = age + 1

    def _col(prefix: str, year: int) -> pd.Series:
        c = f"{prefix}_{year}"
        return wide[c].fillna(0) if c in wide.columns else pd.Series(0.0, index=wide.index)

    mp_cols  = [_col("mp",  y) for y in years]
    mpg_cols = [_col("mpg", y) for y in years]

    wide["proj_mpg_y1"] = _project_mpg(mpg_cols, mp_cols, proj_age, weights)

    for stat in STATS:
        stat_cols = [_col(stat, y) for y in years]
        lg_stats  = [
            pd.Series(float(league_totals.get(y, {}).get(stat, 0.0)), index=wide.index)
            for y in years
        ]
        lg_mps    = [
            pd.Series(float(league_totals.get(y, {}).get("mp", 1.0)) or 1.0, index=wide.index)
            for y in years
        ]
        wide[f"proj_{stat}_per36_y1"] = _project_stat_per36(
            stat_cols, mp_cols, lg_stats, lg_mps,
            proj_age, stat, weights, regression_mp,
        )

    return wide


# ---------------------------------------------------------------------------
# Years 2-5: iterate via pipeline.iterate_projection (row-by-row)
# ---------------------------------------------------------------------------

def _project_years_2_to_5(
    wide: pd.DataFrame,
    league_df: pd.DataFrame,
    base_year: int,
) -> pd.DataFrame:
    """
    For each player, call pipeline.iterate_projection starting from their
    year-1 projection to produce years 2–5.

    Adds columns: proj_{stat}_per36_y{2..5}, proj_mpg_y{2..5}
    """
    from src.data.pipeline import iterate_projection, SPS_STATS

    for future_year in range(2, FUTURE_YEARS + 1):
        for stat in STATS:
            wide[f"proj_{stat}_per36_y{future_year}"] = np.nan
        wide[f"proj_mpg_y{future_year}"] = np.nan

    for idx, row in wide.iterrows():
        # Build the base_proj dict that iterate_projection expects:
        # { stat: per36_value, 'proj_mpg': mpg }
        base_proj = {"proj_mpg": row["proj_mpg_y1"]}
        for stat in SPS_STATS:
            base_proj[stat] = row.get(f"proj_{stat}_per36_y1", 0.0)

        base_age = float(row["age"]) + 1  # age in y1

        all_projs = iterate_projection(base_proj, base_age, league_df, base_year)
        # all_projs is a list of 5 dicts: [y1, y2, y3, y4, y5]
        # We already have y1; take y2–y5
        for future_year, proj in enumerate(all_projs[1:], start=2):
            wide.at[idx, f"proj_mpg_y{future_year}"] = proj["proj_mpg"]
            for stat in SPS_STATS:
                wide.at[idx, f"proj_{stat}_per36_y{future_year}"] = proj.get(stat, 0.0)

    return wide


# ---------------------------------------------------------------------------
# Convert per-36 projections → per-game + fantasy pts for all 5 years
# ---------------------------------------------------------------------------

def _per36_to_per_game(wide: pd.DataFrame) -> pd.DataFrame:
    """
    For each projection year 1–5, convert per-36 columns to per-game
    using that year's projected mpg, then compute fantasy_pts.
    """
    for y in range(1, FUTURE_YEARS + 1):
        mpg = wide[f"proj_mpg_y{y}"].fillna(0)
        for stat in STATS:
            per36_col = f"proj_{stat}_per36_y{y}"
            pg_col    = f"{stat}_pg_y{y}"
            if per36_col in wide.columns:
                wide[pg_col] = wide[per36_col].fillna(0) / 36 * mpg
            else:
                wide[pg_col] = 0.0

        wide[f"fantasy_pts_y{y}"] = _fantasy_pts(wide, f"_y{y}")

    return wide


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run(base_year: int = 2026) -> pd.DataFrame:
    """
    Build the full projection table:
      - 3 years of per-game actuals  ({stat}_pg_{year}, fantasy_pts_{year})
      - 5 years of per-game projections  ({stat}_pg_y{1..5}, fantasy_pts_y{1..5})

    Parameters
    ----------
    base_year : int
        Most recent completed season.  Default 2025 → projects 2025-26 onward.
    """
    from src.data.pipeline import load_all_totals, compute_league_totals_by_season

    years      = [base_year, base_year - 1, base_year - 2]
    all_totals = load_all_totals(min(years), max(years))
    league_df  = compute_league_totals_by_season(all_totals)

    league_totals = {
        int(row["season"]): {col: float(row[col]) for col in league_df.columns if col != "season"}
        for _, row in league_df.iterrows()
    }

    wide = _build_wide_table(all_totals, years)
    wide = _project_year1(wide, league_totals, base_year)
    wide = _project_years_2_to_5(wide, league_df, base_year)
    wide = _per36_to_per_game(wide)

    # Drop intermediate per-36 and raw totals — frontend only needs per-game
    drop_cols = (
        [f"proj_{stat}_per36_y{y}" for stat in STATS for y in range(1, FUTURE_YEARS + 1)]
        + [f"{stat}_{year}" for stat in STATS for year in years]
        + [f"mp_{year}"  for year in years]
        + [f"g_{year}"   for year in years]
    )
    wide = wide.drop(columns=[c for c in drop_cols if c in wide.columns])

    wide = wide.dropna(subset=["fantasy_pts_y1"])
    wide = wide.sort_values("fantasy_pts_y1", ascending=False).reset_index(drop=True)

    log.info(
        "Projections complete — %d players. Top 5 by Y1 fantasy pts:\n%s",
        len(wide),
        wide[["player", "proj_mpg_y1", "fantasy_pts_y1"]].head(5).to_string(index=False),
    )
    return wide


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

SAVE_COLS_IDENTITY = ["player_id", "player", "age"]

SAVE_COLS_ACTUALS = [
    f"{stat}_pg_{year}"
    for year in [2026, 2025, 2024]
    for stat in STATS
] + [f"fantasy_pts_{year}" for year in [2026, 2025, 2024]]

SAVE_COLS_PROJECTIONS = [
    col
    for y in range(1, FUTURE_YEARS + 1)
    for col in (
        [f"proj_mpg_y{y}"]
        + [f"{stat}_pg_y{y}" for stat in STATS]
        + [f"fantasy_pts_y{y}"]
    )
]


def save(results: pd.DataFrame, base_year: int) -> Path:
    """
    Write to data/processed/projections_{base_year}.csv.

    Column order: identity → 3yr actuals → 5yr projections.
    Sorted by fantasy_pts_y1 descending.
    """
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / f"projections_{base_year}.csv"

    desired = SAVE_COLS_IDENTITY + SAVE_COLS_ACTUALS + SAVE_COLS_PROJECTIONS
    present = [c for c in desired if c in results.columns]

    results[present].to_csv(out_path, index=False)
    log.info("Saved %d rows -> %s", len(results), out_path)
    return out_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    base    = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
    results = run(base)
    save(results, base)

    # Print a readable summary
    display = (
        ["player", "age"]
        + [f"fantasy_pts_{y}" for y in [base - 2, base - 1, base]]
        + [f"fantasy_pts_y{y}" for y in range(1, FUTURE_YEARS + 1)]
    )
    present = [c for c in display if c in results.columns]
    print(results[present].head(30).to_string(index=False))
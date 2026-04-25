"""
pipeline.py
--------------------------
Builds two parallel tables over all historical player-seasons (1980–2024):

  data/processed/historical_sps_projections.csv
      What SPS predicted for each player at each snapshot age,
      extended 5 years forward by iterating the formula.

  data/processed/historical_actuals.csv
      What actually happened in those same ±year windows.
      Missing seasons (injury, retirement, never played) = 0.

Both tables share the same outer shape:
  player_id, player, snapshot_year, snapshot_age,
  {stat}_ym2, {stat}_ym1, {stat}_y0,   <- lookback window
  {stat}_y1 .. {stat}_y5                <- forward window

Usage
~~~~~
    python -m src.data.pipeline
    python -m src.data.pipeline --start-year 1984 --end-year 2024
"""

import argparse
import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

RAW_DIR       = Path(__file__).resolve().parents[2] / "data" / "raw"
PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"

# Stats the SPS formula operates on
SPS_STATS = ["x2p", "x3p", "ft", "trb", "ast", "stl", "blk", "tov"]

# SPS year weights: most-recent=6, one-prior=3, two-prior=1
WEIGHTS = [6, 3, 1]

# Projection horizon
FUTURE_YEARS = 5

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_all_totals(start_year: int, end_year: int) -> pd.DataFrame:
    """
    Load and concatenate all player_totals_{year}.csv files.
    Expects columns: player_id, player, season, age, mp, g,
                     x2p, x3p, ft, trb, ast, stl, blk, tov
    Adds mpg and derived x2p/x2pa if missing.
    Returns one row per player per season (multi-team players already
    deduplicated by fetch.py).
    """
    frames = []
    for year in range(start_year, end_year + 1):
        path = RAW_DIR / f"player_totals_{year}.csv"
        if not path.exists():
            log.warning("Missing totals for %d — skipping.", year)
            continue
        df = pd.read_csv(path)
        df["season"] = year  # ensure season column is present
        frames.append(df)

    if not frames:
        raise RuntimeError(f"No totals CSVs found in {RAW_DIR}")

    all_totals = pd.concat(frames, ignore_index=True)

    # Derived columns
    if "x2p" not in all_totals.columns and "fg" in all_totals.columns:
        all_totals["x2p"] = all_totals["fg"] - all_totals.get("x3p", 0)
    if "mpg" not in all_totals.columns:
        all_totals["mpg"] = all_totals["mp"] / all_totals["g"].replace(0, np.nan)

    all_totals["age"] = pd.to_numeric(all_totals["age"], errors="coerce")

    log.info(
        "Loaded %d player-seasons across %d–%d.",
        len(all_totals), start_year, end_year,
    )
    return all_totals


def compute_league_totals_by_season(all_totals: pd.DataFrame) -> pd.DataFrame:
    """
    Sum counting stats across all players for each season.
    Returns one row per season with columns: season, mp, x2p, x3p, ft,
    trb, ast, stl, blk, tov.
    """
    stat_cols = ["mp"] + SPS_STATS
    present   = [c for c in stat_cols if c in all_totals.columns]
    league    = all_totals.groupby("season")[present].sum().reset_index()
    log.info("League totals computed for %d seasons.", len(league))
    return league


# ---------------------------------------------------------------------------
# SPS core
# ---------------------------------------------------------------------------

def _age_factor(age: float, stat: str) -> float:
    """
    Age adjustment multiplier.
    Positive stats: young players get a boost, older get a penalty.
    tov is inverted (lower is better).
    """
    if age < 28:
        delta = (28 - age) * 0.004
    else:
        delta = (28 - age) * 0.002   # negative for age > 28

    if stat == "tov":
        return 1 - delta
    return 1 + delta


def sps_project_one_stat(
    player_vals: list[float],   # [y0, ym1, ym2]  (most-recent first)
    player_mps:  list[float],   # minutes matching each val
    league_vals: list[float],   # league totals for same seasons
    league_mps:  list[float],   # league mp for same seasons
    age:         float,
    stat:        str,
) -> float:
    """
    Basketball-Reference SPS formula for a single stat, adapted for
    1-, 2-, or 3-year history depending on how many non-zero mp entries exist.

    Returns the projected per-36 value before converting to per-game.
    Returns 0.0 if the player has no minutes at all.
    """
    # Determine which years have data (mp > 0)
    full_weights = WEIGHTS[: len(player_vals)]
    active = [(w, pv, pm, lv, lm)
              for w, pv, pm, lv, lm
              in zip(full_weights, player_vals, player_mps, league_vals, league_mps)
              if pm > 0]

    if not active:
        return 0.0

    weights    = [a[0] for a in active]
    p_vals     = [a[1] for a in active]
    p_mps      = [a[2] for a in active]
    l_vals     = [a[3] for a in active]
    l_mps      = [a[4] for a in active]

    weighted_mp  = sum(w * pm for w, pm in zip(weights, p_mps))
    weighted_val = sum(w * pv for w, pv in zip(weights, p_vals))

    # League-average term scaled to 1000 minutes
    league_term = sum(
        w * pm * (lv / lm) if lm > 0 else 0
        for w, pm, lv, lm in zip(weights, p_mps, l_vals, l_mps)
    )
    league_avg_1000 = (league_term / weighted_mp * 1000) if weighted_mp > 0 else 0

    per36 = (weighted_val + league_avg_1000) / (weighted_mp + 1000) * 36
    return per36 * _age_factor(age, stat)


def sps_project_minutes(
    mpg_vals:    list[float],   # [y0, ym1, ym2] most-recent first
    player_mps:  list[float],
    age:         float,
) -> float:
    """
    Weighted average of minutes-per-game, with age adjustment for sub-30-mpg
    players under 28.
    """
    full_weights = WEIGHTS[: len(mpg_vals)]
    active = [(w, mpg, mp)
              for w, mpg, mp in zip(full_weights, mpg_vals, player_mps)
              if mp > 0]

    if not active:
        return 0.0

    total_w   = sum(a[0] for a in active)
    weighted  = sum(a[0] * a[1] for a in active) / total_w

    # Minutes adjustment mirrors BR's approach
    if age < 28 and weighted < 30:
        weighted = min(weighted * (1 + (28 - age) * 0.02), 36)
    elif age >= 28:
        weighted = weighted * (1 + (28 - age) * 0.01)

    return max(weighted, 0.0)


# ---------------------------------------------------------------------------
# Single-player snapshot projection
# ---------------------------------------------------------------------------

def project_snapshot(
    y0_row:  pd.Series,
    ym1_row: Optional[pd.Series],
    ym2_row: Optional[pd.Series],
    league:  pd.DataFrame,        # all league totals
    proj_age: float,              # age in the projection year
) -> dict:
    """
    Given a player's most-recent season row and up to two prior seasons,
    compute SPS per-36 projections for each stat and projected mpg.
    Returns a flat dict of {stat: per36_value, 'proj_mpg': mpg}.
    """

    def _get(row, col):
        if row is None:
            return 0.0
        return float(row[col]) if col in row.index and pd.notna(row[col]) else 0.0

    def _league(season, col):
        row = league[league["season"] == season]
        if row.empty or col not in row.columns:
            return 0.0, 0.0
        return float(row[col].iloc[0]), float(row["mp"].iloc[0])

    # Build per-season arrays (most-recent first)
    rows     = [r for r in [y0_row, ym1_row, ym2_row] if r is not None]
    seasons  = [int(_get(r, "season")) for r in rows]
    mp_vals  = [_get(r, "mp")  for r in rows]
    mpg_vals = [_get(r, "mpg") if "mpg" in r.index else (_get(r, "mp") / _get(r, "g") if _get(r, "g") > 0 else 0.0)
                for r in rows]

    result = {"proj_mpg": sps_project_minutes(mpg_vals, mp_vals, proj_age)}

    for stat in SPS_STATS:
        p_vals  = [_get(r, stat) for r in rows]
        l_vals, l_mps = zip(*[_league(s, stat) for s in seasons]) if seasons else ([], [])
        result[stat] = sps_project_one_stat(
            p_vals, mp_vals,
            list(l_vals), list(l_mps),
            proj_age, stat,
        )

    return result


# ---------------------------------------------------------------------------
# Iterate projection 5 years forward
# ---------------------------------------------------------------------------

def iterate_projection(
    base_proj:    dict,           # projection for y+1 (per-36 stats + proj_mpg)
    base_age:     float,          # age at y+1
    league:       pd.DataFrame,
    reference_season: int,        # y0 season, used to pick a nearby league average
) -> list[dict]:
    """
    Starting from base_proj (y+1), iterate to produce y+2 .. y+5.
    Each iteration uses the previous projection as the "current season"
    with weight 6 only (no prior history — we're projecting into the unknown).

    Returns a list of 5 dicts (y+1 through y+5).
    """
    projections = [base_proj]

    # Use the most recent available league season as the denominator
    avail_seasons = league["season"].sort_values()
    ref_season    = avail_seasons[avail_seasons <= reference_season].max()
    if pd.isna(ref_season):
        ref_season = avail_seasons.max()

    def _league_val(col):
        row = league[league["season"] == ref_season]
        if row.empty or col not in row.columns:
            return 0.0, 0.0
        return float(row[col].iloc[0]), float(row["mp"].iloc[0])

    for step in range(1, FUTURE_YEARS):   # y+2 .. y+5
        prev  = projections[-1]
        age   = base_age + step
        # Convert prev per-36 back to totals using prev projected mpg
        prev_mpg = prev["proj_mpg"]
        prev_mp  = prev_mpg * 82           # approximate season minutes

        new_proj = {"proj_mpg": sps_project_minutes([prev_mpg], [prev_mp], age)}

        for stat in SPS_STATS:
            prev_total = prev[stat] / 36 * prev_mp   # per-36 → season total
            lv, lm     = _league_val(stat)
            new_proj[stat] = sps_project_one_stat(
                [prev_total], [prev_mp],
                [lv], [lm],
                age, stat,
            )

        projections.append(new_proj)

    return projections   # list of 5 dicts (y+1 .. y+5)


# ---------------------------------------------------------------------------
# Build row for one player-snapshot
# ---------------------------------------------------------------------------

def _stat_cols(suffix: str) -> list[str]:
    return [f"{s}_{suffix}" for s in SPS_STATS] + [f"mpg_{suffix}"]


def build_snapshot_row(
    player_id:   str,
    player_name: str,
    snapshot_year: int,
    snapshot_age:  float,
    y0_row:   pd.Series,
    ym1_row:  Optional[pd.Series],
    ym2_row:  Optional[pd.Series],
    all_data: pd.DataFrame,
    league:   pd.DataFrame,
) -> tuple[dict, dict]:
    """
    Returns (proj_row, actual_row) for this player-snapshot.
    """
    base = {
        "player_id":    player_id,
        "player":       player_name,
        "snapshot_year": snapshot_year,
        "snapshot_age":  snapshot_age,
    }

    # ---- Lookback window (same for both tables) ----
    def _fill_lookback(row, suffix):
        d = {}
        for stat in SPS_STATS:
            d[f"{stat}_{suffix}"] = float(row[stat]) if (row is not None and stat in row.index and pd.notna(row[stat])) else 0.0
        mpg = (float(row["mpg"]) if "mpg" in row.index and pd.notna(row["mpg"])
               else (float(row["mp"]) / float(row["g"]) if row is not None and float(row.get("g", 0)) > 0 else 0.0)) if row is not None else 0.0
        d[f"mpg_{suffix}"] = mpg

        d[f"g_{suffix}"] = float(row["g"]) if (row is not None and "g" in row.index and pd.notna(row["g"])) else 0.0
        
        return d

    lookback = {}
    lookback.update(_fill_lookback(y0_row,  "y0"))
    lookback.update(_fill_lookback(ym1_row, "ym1"))
    lookback.update(_fill_lookback(ym2_row, "ym2"))

    # ---- SPS projections (y+1 .. y+5) ----
    proj_age    = snapshot_age + 1
    base_proj   = project_snapshot(y0_row, ym1_row, ym2_row, league, proj_age)
    all_projs   = iterate_projection(base_proj, proj_age, league, snapshot_year)

    proj_forward = {}
    for i, proj in enumerate(all_projs, start=1):
        for stat in SPS_STATS:
            proj_forward[f"{stat}_y{i}"] = proj[stat]
        proj_forward[f"mpg_y{i}"] = proj["proj_mpg"]

    # ---- Actuals (y+1 .. y+5) ----
    actual_forward = {}
    for i in range(1, FUTURE_YEARS + 1):
        future_season = snapshot_year + i
        fut = all_data[
            (all_data["player_id"] == player_id) &
            (all_data["season"]    == future_season)
        ]
        for stat in SPS_STATS:
            actual_forward[f"{stat}_y{i}"] = float(fut[stat].iloc[0]) if (not fut.empty and stat in fut.columns) else 0.0
        if not fut.empty and "g" in fut.columns:
            actual_forward[f"g_y{i}"] = float(fut["g"].iloc[0])
        else:
            actual_forward[f"g_y{i}"] = 0.0
        
        if not fut.empty and "mpg" in fut.columns:
            actual_forward[f"mpg_y{i}"] = float(fut["mpg"].iloc[0])
        elif not fut.empty and "mp" in fut.columns and "g" in fut.columns and float(fut["g"].iloc[0]) > 0:
            actual_forward[f"mpg_y{i}"] = float(fut["mp"].iloc[0]) / float(fut["g"].iloc[0])
        else:
            actual_forward[f"mpg_y{i}"] = 0.0


        

    proj_row   = {**base, **lookback, **proj_forward}
    actual_row = {**base, **lookback, **actual_forward}
    return proj_row, actual_row


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_historical_tables(
    start_year: int = 1980,
    end_year:   int = 2024,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Iterate over every player-season from start_year to end_year and build
    one projection row and one actuals row per snapshot.

    start_year=1980 means the first snapshot is for season 1980 (rookie
    season); prior years will simply be absent (treated as 0).
    """
    all_totals = load_all_totals(start_year, end_year)
    league     = compute_league_totals_by_season(all_totals)

    # Ensure player_id is string for consistent joining
    all_totals["player_id"] = all_totals["player_id"].astype(str)

    proj_rows   = []
    actual_rows = []

    players = all_totals[["player_id", "player"]].drop_duplicates()
    log.info("Processing %d unique players.", len(players))

    for _, prow in players.iterrows():
        pid   = str(prow["player_id"])
        pname = prow["player"]

        player_data = all_totals[all_totals["player_id"] == pid].sort_values("season")

        for _, season_row in player_data.iterrows():
            snapshot_year = int(season_row["season"])
            snapshot_age  = float(season_row["age"]) if pd.notna(season_row["age"]) else 0.0

            y0_row  = season_row

            ym1_data = player_data[player_data["season"] == snapshot_year - 1]
            ym1_row  = ym1_data.iloc[0] if not ym1_data.empty else None

            ym2_data = player_data[player_data["season"] == snapshot_year - 2]
            ym2_row  = ym2_data.iloc[0] if not ym2_data.empty else None

            proj_row, actual_row = build_snapshot_row(
                pid, pname,
                snapshot_year, snapshot_age,
                y0_row, ym1_row, ym2_row,
                all_totals, league,
            )
            proj_rows.append(proj_row)
            actual_rows.append(actual_row)

    proj_df   = pd.DataFrame(proj_rows)
    actual_df = pd.DataFrame(actual_rows)

    log.info("Built %d snapshot rows.", len(proj_df))
    return proj_df, actual_df


# ---------------------------------------------------------------------------
# Save + main
# ---------------------------------------------------------------------------

def save_tables(proj_df: pd.DataFrame, actual_df: pd.DataFrame) -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    proj_path   = PROCESSED_DIR / "historical_sps_projections.csv"
    actual_path = PROCESSED_DIR / "historical_actuals.csv"

    proj_df.to_csv(proj_path,   index=False)
    actual_df.to_csv(actual_path, index=False)

    log.info("Saved -> %s", proj_path)
    log.info("Saved -> %s", actual_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build historical SPS projection and actuals tables")
    parser.add_argument("--start-year", type=int, default=1980)
    parser.add_argument("--end-year",   type=int, default=2024)
    args = parser.parse_args()

    proj_df, actual_df = build_historical_tables(args.start_year, args.end_year)
    save_tables(proj_df, actual_df)

    # Sanity check: print a few rows for a known player
    sample = proj_df[proj_df["player"] == "LeBron James"].head(3)
    if not sample.empty:
        print("\nSample — LeBron James projections:")
        print(sample[["player", "snapshot_year", "snapshot_age", "pts_y1", "pts_y2", "mpg_y1"]].to_string())

    # UNCOMMENT IF YOU WANT TO TEST IF YOUR DATA MAKES SENSE
    # proj_df = pd.read_csv(PROCESSED_DIR / "historical_sps_projections.csv")

    # sample = proj_df[proj_df["player"] == "LeBron James"].head(3)
    # if not sample.empty:
    #     print("\nSample — LeBron James projections:")
    #     print(sample[[
    #         "player", "snapshot_year", "snapshot_age",
    #         "ast_y1", "trb_y1", "mpg_y1",
    #         "ast_y2", "trb_y2", "mpg_y2",
    #     ]].to_string())
    # else:
    #     print("LeBron not found — check player name or CSV path.")
    #     print("Available columns:", proj_df.columns.tolist())
    #     print("Sample players:", proj_df["player"].unique()[:10])


if __name__ == "__main__":
    main()
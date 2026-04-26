"""
build_player_cards.py
---------------------
Produces data/processed/player_cards_2025.csv — the single flat file
consumed by the frontend player card UI.

Run:
    python src/data/build_player_cards.py
    python src/data/build_player_cards.py --base-year 2025

Requires (all in data/raw/ unless noted):
    player_totals_2025.csv           <- most recent season totals
    advanced_2025.csv                <- TS%, USG%, AST%, TOV%, TRB%, BLK%, STL% etc.
    player_bio_*.csv                 <- height, weight, draft_pick  (any year glob)
    data/processed/historical_sps_projections.csv
    data/processed/historical_actuals.csv

All column names follow camthomas conventions (x3p, x2p, x3pa, etc.).
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT          = Path(__file__).resolve().parents[2]
RAW_DIR       = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
OUT_PATH      = PROCESSED_DIR / "player_cards_2026.csv"

# ---------------------------------------------------------------------------
# Fantasy scoring (DraftKings default — must match projections.py)
# ---------------------------------------------------------------------------

DK_WEIGHTS: dict[str, float] = {
    "x2p":  2.0,
    "x3p":  3.0,
    "ft":   1.0,
    "trb":  1.25,
    "ast":  1.5,
    "stl":  2.0,
    "blk":  2.0,
    "tov": -0.5,
}

PROJ_STATS = list(DK_WEIGHTS.keys())   # ["x2p","x3p","ft","trb","ast","stl","blk","tov"]

# Per-game display stats tracked in arc (actual + projected)
# pts = (x2p*2 + x3p*3 + ft) / g, but we store components so we can compute
ARC_DISPLAY_STATS = ["pts", "trb", "ast", "stl", "blk", "tov"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_read(path: Path, **kwargs) -> pd.DataFrame:
    if not path.exists():
        log.warning("File not found, returning empty df: %s", path)
        return pd.DataFrame()
    return pd.read_csv(path, **kwargs)


def _percentile_rank(series: pd.Series, ref: pd.Series) -> pd.Series:
    ref_arr = ref.dropna().to_numpy()
    if len(ref_arr) == 0:
        return pd.Series(50, index=series.index)

    def _pct(v):
        if pd.isna(v):
            return np.nan
        return float(np.mean(ref_arr <= v) * 100)

    return series.map(_pct)


def _fantasy_pts_from_row(df: pd.DataFrame, suffix: str = "") -> pd.Series:
    total = pd.Series(0.0, index=df.index)
    for stat, w in DK_WEIGHTS.items():
        col = f"{stat}{suffix}"
        if col in df.columns:
            total += df[col].fillna(0) * w
    return total


def _fantasy_pts_per_game(df: pd.DataFrame, suffix: str = "", g_col: str = "g") -> pd.Series:
    raw = _fantasy_pts_from_row(df, suffix)
    if g_col in df.columns:
        g = df[g_col].replace(0, np.nan)
        return raw / g
    return raw


def _pts_from_components(x2p: pd.Series, x3p: pd.Series, ft: pd.Series) -> pd.Series:
    """Compute total points from made shot components."""
    return x2p * 2 + x3p * 3 + ft


# ---------------------------------------------------------------------------
# Step 1 — Load 2025 projections output + totals
# ---------------------------------------------------------------------------

def load_2025_projections(base_year: int) -> pd.DataFrame:
    proj_cache = PROCESSED_DIR / f"sps_projections_{base_year}.csv"
    if proj_cache.exists():
        log.info("Loading cached projections: %s", proj_cache)
        return pd.read_csv(proj_cache)

    log.info("No cached projections found — running project_season().")
    try:
        import sys
        sys.path.insert(0, str(ROOT / "src"))
        from models.projections import project_season
        from data.pipeline import build_3yr_table, compute_league_totals

        df     = build_3yr_table(base_year)
        league = compute_league_totals(base_year)
        proj   = project_season(df, league, base_year)
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        proj.to_csv(proj_cache, index=False)
        log.info("Projections saved -> %s", proj_cache)
        return proj
    except Exception as exc:
        log.warning("Could not run projections (%s). Will try raw totals only.", exc)
        return pd.DataFrame()


def load_raw_totals(base_year: int) -> pd.DataFrame:
    path = RAW_DIR / f"player_totals_{base_year}.csv"
    df = _safe_read(path)
    if df.empty:
        return df
    if "mpg" not in df.columns and "mp" in df.columns and "g" in df.columns:
        df["mpg"] = df["mp"] / df["g"].replace(0, np.nan)
    return df


# ---------------------------------------------------------------------------
# Step 2 — Load bio data
# ---------------------------------------------------------------------------

def load_bio(base_year: int) -> pd.DataFrame:
    path = RAW_DIR / "player_bio.csv"
    bio = _safe_read(path)

    if bio.empty:
        log.warning("player_bio.csv not found in %s", RAW_DIR)
        return pd.DataFrame(columns=["player_id", "ht_inches", "wt", "draft_pick"])

    bio = bio.drop_duplicates(subset="player_id", keep="first")
    keep = [c for c in ["player_id", "ht_inches", "wt", "draft_pick"] if c in bio.columns]
    return bio[keep].copy()


# ---------------------------------------------------------------------------
# Step 3 — Load advanced stats
# ---------------------------------------------------------------------------

def load_advanced(base_year: int) -> pd.DataFrame:
    path = RAW_DIR / f"player_advanced_{base_year}.csv"
    df = _safe_read(path)
    if df.empty:
        return df

    rename_map = {
        "ts%": "ts_pct", "ts_percent": "ts_pct",
        "usg%": "usg_pct", "usg_percent": "usg_pct",
        "ast%": "ast_pct", "ast_percent": "ast_pct",
        "tov%": "tov_pct", "tov_percent": "tov_pct",
        "trb%": "trb_pct", "trb_percent": "trb_pct",
        "blk%": "blk_pct", "blk_percent": "blk_pct",
        "stl%": "stl_pct", "stl_percent": "stl_pct",
        "bpm": "bpm", "dbpm": "dbpm", "vorp": "vorp",
        "ws/48": "ws_per48", "per": "per",
    }
    df.columns = [rename_map.get(c.lower(), c.lower()) for c in df.columns]

    if "tm" in df.columns:
        combined = df[df["tm"].str.upper().isin(["TOT", "2TM", "3TM"])]
        others   = df[~df["player_id"].isin(combined["player_id"])]
        df = pd.concat([combined, others], ignore_index=True)
    df = df.drop_duplicates(subset="player_id", keep="first")

    return df


# ---------------------------------------------------------------------------
# Step 4 — Compute shooting tendency columns
# ---------------------------------------------------------------------------

def add_tendency_cols(df: pd.DataFrame, year: int) -> pd.DataFrame:
    def _col(name: str) -> pd.Series:
        for candidate in [f"{name}_{year}", name]:
            if candidate in df.columns:
                return df[candidate].fillna(0)
        return pd.Series(0.0, index=df.index)

    fga  = _col("fga").replace(0, np.nan)
    x3pa = _col("x3pa")
    fta  = _col("fta")

    df["x3_freq"] = x3pa / fga
    df["ft_freq"]  = fta  / fga
    return df


# ---------------------------------------------------------------------------
# Step 5 — Historical actuals arc
# ---------------------------------------------------------------------------

def build_actuals_arc(
    current_player_ids: pd.Series,
    base_year: int,
    n_back: int = 7,
) -> pd.DataFrame:
    """
    Return wide table: player_id, plus for each year in [base_year-n_back .. base_year]:
        actual_fpts_{year}   — DK fantasy pts per game
        actual_pts_{year}    — points per game
        actual_trb_{year}    — rebounds per game
        actual_ast_{year}    — assists per game
        actual_stl_{year}    — steals per game
        actual_blk_{year}    — blocks per game
        actual_tov_{year}    — turnovers per game
    Missing seasons = NaN.
    """
    years = list(range(base_year - n_back, base_year + 1))
    print("YEARS: ", years)

    path = PROCESSED_DIR / "historical_actuals.csv"
    stat_cols_y0 = [f"{s}_y0" for s in PROJ_STATS]

    if path.exists():
        actuals = pd.read_csv(path)
        if all(c in actuals.columns for c in stat_cols_y0):
            arc = actuals[actuals["player_id"].isin(current_player_ids)].copy()
            arc = arc[["player_id", "snapshot_year"] +
                      [c for c in actuals.columns if c.endswith("_y0")]].drop_duplicates(
                          subset=["player_id", "snapshot_year"])

            g_col = "g_y0"
            has_g = g_col in arc.columns

            # Compute per-game stats from y0 columns
            arc["fpts_pg"] = _fantasy_pts_from_row(arc, "_y0")
            if has_g:
                g = arc[g_col].replace(0, np.nan)
                arc["fpts_pg"] = arc["fpts_pg"] / g
                for stat in ["trb", "ast", "stl", "blk", "tov"]:
                    col = f"{stat}_y0"
                    arc[f"{stat}_pg"] = arc[col].fillna(0) / g if col in arc.columns else np.nan
                # pts = x2p*2 + x3p*3 + ft
                x2p = arc.get("x2p_y0", pd.Series(0.0, index=arc.index)).fillna(0)
                x3p = arc.get("x3p_y0", pd.Series(0.0, index=arc.index)).fillna(0)
                ft  = arc.get("ft_y0",  pd.Series(0.0, index=arc.index)).fillna(0)
                arc["pts_pg"] = _pts_from_components(x2p, x3p, ft) / g
            else:
                for stat in ["pts", "trb", "ast", "stl", "blk", "tov"]:
                    arc[f"{stat}_pg"] = np.nan

            # Pivot each metric wide
            result = arc[["player_id"]].drop_duplicates()
            for metric in ["fpts", "pts", "trb", "ast", "stl", "blk", "tov"]:
                pg_col = f"{metric}_pg"
                pivot = arc.pivot(index="player_id", columns="snapshot_year", values=pg_col)
                pivot.columns = [f"actual_{metric}_{int(c)}" for c in pivot.columns]
                # Keep only target years
                keep = [f"actual_{metric}_{y}" for y in years if f"actual_{metric}_{y}" in pivot.columns]
                pivot = pivot[keep]
                result = result.merge(pivot.reset_index(), on="player_id", how="left")

            # Fill missing year columns
            for y in years:
                for metric in ["fpts", "pts", "trb", "ast", "stl", "blk", "tov"]:
                    col = f"actual_{metric}_{y}"
                    if col not in result.columns:
                        result[col] = np.nan

            return result

    # Fallback: load raw totals year by year
    log.warning("historical_actuals.csv missing or incomplete — loading raw totals per year.")
    all_frames = {}
    for y in years:
        print(y)
        raw = _safe_read(RAW_DIR / f"player_totals_{y}.csv")
        if raw.empty or "player_id" not in raw.columns:
            continue
        raw = raw[raw["player_id"].isin(current_player_ids)].copy()
        g = raw["g"].replace(0, np.nan) if "g" in raw.columns else pd.Series(np.nan, index=raw.index)

        raw[f"actual_fpts_{y}"] = _fantasy_pts_from_row(raw) / g
        x2p = raw.get("x2p", pd.Series(0.0, index=raw.index)).fillna(0)
        x3p = raw.get("x3p", pd.Series(0.0, index=raw.index)).fillna(0)
        ft  = raw.get("ft",  pd.Series(0.0, index=raw.index)).fillna(0)
        raw[f"actual_pts_{y}"] = _pts_from_components(x2p, x3p, ft) / g
        for stat in ["trb", "ast", "stl", "blk", "tov"]:
            raw[f"actual_{stat}_{y}"] = raw[stat].fillna(0) / g if stat in raw.columns else np.nan

        keep_cols = ["player_id"] + [f"actual_{m}_{y}" for m in ["fpts", "pts", "trb", "ast", "stl", "blk", "tov"]]
        keep_cols = [c for c in keep_cols if c in raw.columns]
        all_frames[y] = raw[keep_cols].set_index("player_id")

    if not all_frames:
        result = pd.DataFrame({"player_id": current_player_ids})
        for y in years:
            for metric in ["fpts", "pts", "trb", "ast", "stl", "blk", "tov"]:
                result[f"actual_{metric}_{y}"] = np.nan
        return result

    merged = pd.concat(all_frames.values(), axis=1).reset_index()
    merged.columns.name = None
    return merged


# ---------------------------------------------------------------------------
# Step 6 — SPS projected arc (y1–y5)
# ---------------------------------------------------------------------------

def build_projection_arc(
    current_player_ids: pd.Series,
    base_year: int,
    n_future: int = 5,
) -> pd.DataFrame:
    """
    Pull proj_y1..proj_y5 for current players. For each future year produces:
        proj_fpts_y{i}  — DK fantasy pts per game
        proj_pts_y{i}   — points per game
        proj_trb_y{i}   — rebounds per game
        proj_ast_y{i}   — assists per game
        proj_stl_y{i}   — steals per game
        proj_blk_y{i}   — blocks per game
        proj_tov_y{i}   — turnovers per game
        ci_lo_y{i}, ci_hi_y{i}  — ±20% CI on fpts
    """
    path = PROCESSED_DIR / "projections_2026.csv"

    all_cols = []
    for i in range(1, n_future + 1):
        all_cols += [f"proj_fpts_y{i}", f"proj_pts_y{i}"]
        all_cols += [f"proj_{s}_y{i}" for s in ["trb", "ast", "stl", "blk", "tov"]]
        all_cols += [f"ci_lo_y{i}", f"ci_hi_y{i}"]

    if not path.exists():
        log.warning("projections_2026.csv not found — arc will be stub.")
        df_empty = pd.DataFrame({"player_id": current_player_ids})
        for c in all_cols:
            df_empty[c] = np.nan
        return df_empty

    proj_hist = pd.read_csv(path)

    subset = pd.DataFrame()
    for snap_yr in [base_year, base_year - 1]:
        subset = proj_hist[
            (proj_hist["player_id"].isin(current_player_ids))
        ]
        if not subset.empty:
            log.info("Using snapshot_year=%d for projection arc.", snap_yr)
            break

    if subset.empty:
        log.warning("No matching snapshot rows — arc will be empty.")
        df_empty = pd.DataFrame({"player_id": current_player_ids})
        for c in all_cols:
            df_empty[c] = np.nan
        return df_empty

    result = subset[["player_id"]].copy().reset_index(drop=True)

    for i in range(1, n_future + 1):
        # projections.py saves per-game columns as {stat}_pg_y{i} and proj_mpg_y{i}
        mpg_col = f"proj_mpg_y{i}"
        mpg = subset[mpg_col].fillna(0) if mpg_col in subset.columns else pd.Series(0.0, index=subset.index)

        # Fantasy pts — columns are already per-game
        fpts = pd.Series(0.0, index=subset.index)
        for stat, w in DK_WEIGHTS.items():
            col = f"{stat}_pg_y{i}"
            if col in subset.columns:
                fpts += subset[col].fillna(0) * w
        result[f"proj_fpts_y{i}"] = fpts.values
        result[f"ci_lo_y{i}"]     = (fpts * 0.80).values
        result[f"ci_hi_y{i}"]     = (fpts * 1.20).values

        # Points per game from per-game components
        x2p = subset.get(f"x2p_pg_y{i}", pd.Series(0.0, index=subset.index)).fillna(0)
        x3p = subset.get(f"x3p_pg_y{i}", pd.Series(0.0, index=subset.index)).fillna(0)
        ft  = subset.get(f"ft_pg_y{i}",  pd.Series(0.0, index=subset.index)).fillna(0)
        result[f"proj_pts_y{i}"] = _pts_from_components(x2p, x3p, ft).values

        # Other per-game stats — already per-game, no conversion needed
        for stat in ["trb", "ast", "stl", "blk", "tov"]:
            col = f"{stat}_pg_y{i}"
            if col in subset.columns:
                result[f"proj_{stat}_y{i}"] = subset[col].fillna(0).values
            else:
                result[f"proj_{stat}_y{i}"] = np.nan

    return result.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Step 7 — Percentile computation
# ---------------------------------------------------------------------------

PCTILE_STATS = {
    "ht_inches":  ("ht_pct",       False),
    "wt":         ("wt_pct",       False),
    "draft_pick": ("draft_pct",    True),
    "ts_pct":     ("ts_pct_rank",  False),
    "ft_pct":     ("ft_pct_rank",  False),
    "usg_pct":    ("usg_pct_rank", False),
    "x3_freq":    ("x3_freq_rank", False),
    "ft_freq":    ("ft_freq_rank", False),
    "ast_pct":    ("ast_pct_rank", False),
    "tov_pct":    ("tov_pct_rank", True),
    "trb_pct":    ("trb_pct_rank", False),
    "blk_pct":    ("blk_pct_rank", False),
    "stl_pct":    ("stl_pct_rank", False),
}

PROJ_PG_PCTILE = [
    ("proj_x2p_pg", "proj_x2p_pct",  False),
    ("proj_x3p_pg", "proj_x3p_pct",  False),
    ("proj_ft_pg",  "proj_ft_pct",   False),
    ("proj_trb_pg", "proj_trb_pct",  False),
    ("proj_ast_pg", "proj_ast_pct",  False),
    ("proj_stl_pg", "proj_stl_pct",  False),
    ("proj_blk_pg", "proj_blk_pct",  False),
    ("proj_tov_pg", "proj_tov_pct",  True),
    ("fantasy_pts", "fantasy_pct",   False),
]


def add_percentiles(
    df: pd.DataFrame,
    hist_ref: pd.DataFrame | None,
) -> pd.DataFrame:
    def _pct_series(values: pd.Series, ref_values: pd.Series, invert: bool) -> pd.Series:
        if invert:
            values     = -values
            ref_values = -ref_values.dropna()
        else:
            ref_values = ref_values.dropna()

        ref_arr = ref_values.to_numpy()
        if len(ref_arr) == 0:
            return pd.Series(50, index=values.index, dtype=int)

        pct = values.map(
            lambda v: int(np.mean(ref_arr <= v) * 100) if pd.notna(v) else np.nan
        )
        return pct

    for col, (out_col, invert) in PCTILE_STATS.items():
        if col not in df.columns:
            continue
        ref = hist_ref[col].dropna() if (hist_ref is not None and col in hist_ref.columns) else df[col]
        df[out_col] = _pct_series(df[col], ref, invert)

    for col, out_col, invert in PROJ_PG_PCTILE:
        if col not in df.columns:
            continue
        ref = df[col]
        df[out_col] = _pct_series(df[col], ref, invert)

    return df


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _get_master_player_list(base_year: int) -> pd.DataFrame:
    """Collects unique player IDs and names from the last 3 seasons."""
    frames = []
    # Check current year + last 2 years
    for y in [base_year, base_year - 1, base_year - 2]:
        path = RAW_DIR / f"player_totals_{y}.csv"
        if path.exists():
            df = pd.read_csv(path, usecols=["player_id", "player"])
            frames.append(df)
    
    if not frames:
        return pd.DataFrame(columns=["player_id", "player"])
    
    # Combine and keep the most recent name/entry for each ID
    master = pd.concat(frames, ignore_index=True)
    master["player_id"] = master["player_id"].astype(str)
    return master.drop_duplicates(subset="player_id", keep="first")

def build(base_year: int = 2026) -> pd.DataFrame:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    # ── 1. Create the Master List (2024, 2025, 2026) ─────────────────────
    # This ensures players from previous years are not excluded.
    base = _get_master_player_list(base_year)
    log.info("Master player list built: %d players identified from 3-year window.", len(base))

    # ── 2. Load Projections and Current Totals ──────────────────────────
    proj = load_2025_projections(base_year)
    raw  = load_raw_totals(base_year)

    # Merge current stats onto our master list
    if not proj.empty:
        proj["player_id"] = proj["player_id"].astype(str)
        # We use outer here just in case projections has a rookie not in totals yet
        base = base.merge(proj, on="player_id", how="outer", suffixes=("", "_proj"))
    
    if not raw.empty:
        raw["player_id"] = raw["player_id"].astype(str)
        # Merge raw totals for the base year (2026)
        base = base.merge(raw, on="player_id", how="left", suffixes=("", "_raw"))

    # If 'player' column ended up duplicated or missing from merge, clean it up
    if "player_proj" in base.columns:
        base["player"] = base["player"].fillna(base["player_proj"])
        base.drop(columns=["player_proj"], inplace=True)

    # Re-calculate projected PG stats if missing
    for stat in PROJ_STATS:
        pg_col    = f"proj_{stat}_pg"
        per36_col = f"proj_{stat}"
        mpg_col   = "proj_mpg"
        if pg_col not in base.columns and per36_col in base.columns and mpg_col in base.columns:
            base[pg_col] = base[per36_col] / 36 * base[mpg_col]

    # ── 3. Bio data ───────────────────────────────────────────────────────
    bio = load_bio(base_year)
    if not bio.empty:
        bio["player_id"] = bio["player_id"].astype(str)
        base = base.merge(bio, on="player_id", how="left")
    else:
        for c in ["ht_inches", "wt", "draft_pick"]:
            base[c] = np.nan

    # ── 4. Advanced stats (Base Year) ─────────────────────────────────────
    adv = load_advanced(base_year)
    if not adv.empty:
        adv["player_id"] = adv["player_id"].astype(str)
        adv_cols = [c for c in adv.columns
                    if c in ["player_id", "ts_pct", "usg_pct", "ast_pct",
                             "tov_pct", "trb_pct", "blk_pct", "stl_pct",
                             "ft_pct", "bpm", "dbpm", "vorp", "per", "ws_per48"]]
        base = base.merge(adv[adv_cols], on="player_id", how="left")

    # ── 5. Shooting tendency / Historical Arc / Projected Arc ──────────────
    # These functions already handle their own year-logic, so we just pass our expanded 'base'
    base = add_tendency_cols(base, base_year)
    
    arc_actual = build_actuals_arc(base["player_id"], base_year)
    arc_actual["player_id"] = arc_actual["player_id"].astype(str)
    base = base.merge(arc_actual, on="player_id", how="left")

    arc_proj = build_projection_arc(base["player_id"], base_year)
    arc_proj["player_id"] = arc_proj["player_id"].astype(str)
    base = base.merge(arc_proj, on="player_id", how="left")

    # ── 6. Percentiles & Schema ──────────────────────────────────────────
    hist_ref = None
    hist_path = PROCESSED_DIR / "historical_sps_projections.csv"
    if hist_path.exists():
        hist_ref = pd.read_csv(hist_path, usecols=lambda c: not c.startswith("proj"))

    base = add_percentiles(base, hist_ref)

    # ── 7. Percentiles ────────────────────────────────────────────────────
    hist_ref = None
    hist_path = PROCESSED_DIR / "historical_sps_projections.csv"
    if hist_path.exists():
        hist_ref = pd.read_csv(hist_path, usecols=lambda c: not c.startswith("proj"))

    base = add_percentiles(base, hist_ref)

    # ── 8. Clean up and enforce schema order ─────────────────────────────
    id_cols      = ["player_id", "player", "age", "team", "pos"]
    bio_cols     = ["ht_inches", "wt", "draft_pick"]
    proj_main    = ["proj_mpg", "fantasy_pts"]
    proj_pg_cols = [f"proj_{s}_pg" for s in PROJ_STATS]
    adv_display  = ["ts_pct", "ft_pct", "usg_pct", "x3_freq", "ft_freq",
                    "ast_pct", "tov_pct", "trb_pct", "blk_pct", "stl_pct"]
    pct_cols     = (
        [v[0] for v in PCTILE_STATS.values()] +
        [x[1] for x in PROJ_PG_PCTILE]
    )

    # Arc columns: actual_{metric}_{year} and proj_{metric}_y{i} / ci bands
    actual_cols = sorted([c for c in base.columns if c.startswith("actual_")])
    arc_cols    = sorted(
        [c for c in base.columns
         if c.startswith("proj_fpts_y") or c.startswith("proj_pts_y") or
            any(c.startswith(f"proj_{s}_y") for s in ["trb", "ast", "stl", "blk", "tov"]) or
            c.startswith("ci_lo") or c.startswith("ci_hi")]
    )

    ordered = []
    for col in (id_cols + bio_cols + proj_main + proj_pg_cols +
                adv_display + pct_cols + actual_cols + arc_cols):
        if col in base.columns and col not in ordered:
            ordered.append(col)

    remainder = [c for c in base.columns if c not in ordered]
    final = base[ordered + remainder]

    # ── 9. Export ─────────────────────────────────────────────────────────
    final.to_csv(OUT_PATH, index=False)
    log.info(
        "player_cards_%d.csv written: %d players × %d columns → %s",
        base_year, len(final), len(final.columns), OUT_PATH,
    )

    if "fantasy_pts" in final.columns and "player" in final.columns:
        top5 = final.nlargest(5, "fantasy_pts")[["player", "age", "proj_mpg", "fantasy_pts"]]
        log.info("Top 5 by fantasy_pts:\n%s", top5.to_string(index=False))
    
    return final # (Assuming you keep the rest of your original schema logic)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build player_cards_{year}.csv")
    parser.add_argument("--base-year", type=int, default=2026,
                        help="Most recent completed season (default: 2026)")
    args = parser.parse_args()
    build(args.base_year)
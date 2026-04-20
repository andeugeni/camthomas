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
OUT_PATH      = PROCESSED_DIR / "player_cards_2025.csv"

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
    """
    For each value in `series`, compute what percentile it falls at
    within `ref` (the reference distribution). Returns 0–100 integers.
    Higher = better (inversion handled separately for tov/draft_pick).
    """
    ref_arr = ref.dropna().to_numpy()
    if len(ref_arr) == 0:
        return pd.Series(50, index=series.index)

    def _pct(v):
        if pd.isna(v):
            return np.nan
        return float(np.mean(ref_arr <= v) * 100)

    return series.map(_pct)


def _fantasy_pts_from_row(df: pd.DataFrame, suffix: str = "") -> pd.Series:
    """Compute DK fantasy pts from totals columns with optional suffix."""
    total = pd.Series(0.0, index=df.index)
    for stat, w in DK_WEIGHTS.items():
        col = f"{stat}{suffix}"
        if col in df.columns:
            total += df[col].fillna(0) * w
    return total


def _fantasy_pts_per_game(df: pd.DataFrame, suffix: str = "", g_col: str = "g") -> pd.Series:
    """Season-total DK pts divided by games played."""
    raw = _fantasy_pts_from_row(df, suffix)
    if g_col in df.columns:
        g = df[g_col].replace(0, np.nan)
        return raw / g
    return raw


# ---------------------------------------------------------------------------
# Step 1 — Load 2025 projections output + totals
# ---------------------------------------------------------------------------

def load_2025_projections(base_year: int) -> pd.DataFrame:
    """
    Attempt to load the SPS projection output for base_year.
    Falls back to building it on the fly from raw totals if not cached.
    """
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
    # Compute mpg if missing
    if "mpg" not in df.columns and "mp" in df.columns and "g" in df.columns:
        df["mpg"] = df["mp"] / df["g"].replace(0, np.nan)
    return df


# ---------------------------------------------------------------------------
# Step 2 — Load bio data (height, weight, draft position)
# ---------------------------------------------------------------------------

def load_bio(base_year: int) -> pd.DataFrame:
    """
    Load player_bio.csv — a single file containing all players.
    Expected columns: player_id, ht_inches, wt, draft_pick.
    """
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
    path = RAW_DIR / f"advanced_{base_year}.csv"
    df = _safe_read(path)
    if df.empty:
        return df

    # Normalise common column aliases
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

    # Dedup multi-team players (keep TOT / combined row)
    if "tm" in df.columns:
        combined = df[df["tm"].str.upper().isin(["TOT", "2TM", "3TM"])]
        others   = df[~df["player_id"].isin(combined["player_id"])]
        df = pd.concat([combined, others], ignore_index=True)
    df = df.drop_duplicates(subset="player_id", keep="first")

    return df


# ---------------------------------------------------------------------------
# Step 4 — Compute shooting tendency columns from totals
# ---------------------------------------------------------------------------

def add_tendency_cols(df: pd.DataFrame, year: int) -> pd.DataFrame:
    """Add x3_freq and ft_freq from raw attempt columns."""
    # Column names may be absolute-year or plain depending on schema
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
# Step 5 — Historical actuals arc (fantasy_pts per season, wide)
# ---------------------------------------------------------------------------

def build_actuals_arc(
    current_player_ids: pd.Series,
    base_year: int,
    n_back: int = 7,
) -> pd.DataFrame:
    """
    Return wide table: player_id, actual_{year} for base_year-n_back..base_year.
    Missing seasons = NaN.
    """
    path = PROCESSED_DIR / "historical_actuals.csv"
    if not path.exists():
        log.warning("historical_actuals.csv not found — arc chart will be empty.")
        cols = {f"actual_{y}": pd.Series(np.nan, index=current_player_ids.index)
                for y in range(base_year - n_back, base_year + 1)}
        return pd.DataFrame({"player_id": current_player_ids, **cols})

    actuals = pd.read_csv(path)

    # Compute fantasy pts per season using SPS stat columns (season totals)
    # actuals has {stat}_y0 etc. but we need per-season absolute values.
    # Fall back to raw totals if actuals stores season totals differently.
    years = list(range(base_year - n_back, base_year + 1))

    # Build arc: for each player_id+snapshot_year combo, derive fpts
    # snapshot_year = the season whose y0 stats are recorded
    stat_cols_y0 = [f"{s}_y0" for s in PROJ_STATS]
    if all(c in actuals.columns for c in stat_cols_y0):
        # Each snapshot_year row has actual y0 totals — compute season fpts
        actuals["fpts_season"] = _fantasy_pts_from_row(actuals, "_y0")
        # Compute per-game if g_y0 is available
        if "g_y0" in actuals.columns:
            actuals["fpts_season"] = actuals["fpts_season"] / actuals["g_y0"].replace(0, np.nan)
        elif "mpg_y0" in actuals.columns:
            # proxy: fpts per 36 scaled by mpg
            pass   # leave as totals; frontend can normalise

        arc = actuals[actuals["player_id"].isin(current_player_ids)].copy()
        arc = arc[["player_id", "snapshot_year", "fpts_season"]].drop_duplicates()
        wide = arc.pivot(index="player_id", columns="snapshot_year", values="fpts_season")
        wide.columns = [f"actual_{int(c)}" for c in wide.columns]
        wide = wide.reset_index()

        # Keep only target years
        keep = ["player_id"] + [f"actual_{y}" for y in years if f"actual_{y}" in wide.columns]
        wide = wide[keep]
        # Fill missing year columns with NaN
        for y in years:
            col = f"actual_{y}"
            if col not in wide.columns:
                wide[col] = np.nan
        return wide
    else:
        # Fallback: try loading raw totals year by year
        rows = {}
        for y in years:
            raw = _safe_read(RAW_DIR / f"player_totals_{y}.csv")
            if raw.empty or "player_id" not in raw.columns:
                continue
            raw = raw[raw["player_id"].isin(current_player_ids)]
            fpts = _fantasy_pts_from_row(raw)
            if "g" in raw.columns:
                fpts = fpts / raw["g"].replace(0, np.nan)
            rows[y] = raw.set_index("player_id")[[]].assign(**{f"actual_{y}": fpts})

        if not rows:
            cols = {f"actual_{y}": np.nan for y in years}
            return pd.DataFrame({"player_id": current_player_ids, **cols})

        arc = pd.concat(rows.values(), axis=1).reset_index()
        arc.columns = ["player_id"] + [f"actual_{y}" for y in rows]
        return arc


# ---------------------------------------------------------------------------
# Step 6 — SPS projected arc (y1–y5 from historical_sps_projections.csv)
# ---------------------------------------------------------------------------

def build_projection_arc(
    current_player_ids: pd.Series,
    base_year: int,
    n_future: int = 5,
) -> pd.DataFrame:
    """
    Pull proj_y1..proj_y5 and CI bands for current players from the
    historical SPS projections table (snapshot_year == base_year).
    """
    path = PROCESSED_DIR / "historical_sps_projections.csv"
    empty_cols = (
        [f"proj_y{i}" for i in range(1, n_future + 1)] +
        [f"ci_lo_y{i}" for i in range(1, n_future + 1)] +
        [f"ci_hi_y{i}" for i in range(1, n_future + 1)]
    )

    if not path.exists():
        log.warning("historical_sps_projections.csv not found — arc will be stub.")
        df_empty = pd.DataFrame({"player_id": current_player_ids})
        for c in empty_cols:
            df_empty[c] = np.nan
        return df_empty

    proj_hist = pd.read_csv(path)

    # Filter to current players at the most recent snapshot year available
    # (ideally snapshot_year == base_year, but allow base_year-1 if missing)
    for snap_yr in [base_year, base_year - 1]:
        subset = proj_hist[
            (proj_hist["player_id"].isin(current_player_ids)) &
            (proj_hist["snapshot_year"] == snap_yr)
        ]
        if not subset.empty:
            log.info("Using snapshot_year=%d for projection arc.", snap_yr)
            break

    if subset.empty:
        log.warning("No matching snapshot rows — arc will be empty.")
        df_empty = pd.DataFrame({"player_id": current_player_ids})
        for c in empty_cols:
            df_empty[c] = np.nan
        return df_empty

    # Compute fantasy pts for each future year from {stat}_y{i} columns
    result = subset[["player_id"]].copy()

    for i in range(1, n_future + 1):
        stat_cols = {f"{s}_y{i}": f"{s}" for s in PROJ_STATS}
        available = {out_stat: col for col, out_stat in stat_cols.items()
                     if col in subset.columns}

        if available:
            fpts = pd.Series(0.0, index=subset.index)
            for out_stat, col in available.items():
                fpts += subset[col].fillna(0) * DK_WEIGHTS.get(out_stat, 0)
            # Divide by games if mpg available (approximate: mpg * 82 / 36)
            mpg_col = f"mpg_y{i}"
            if mpg_col in subset.columns:
                games = 82  # season game count assumption
                fpts = fpts / 36 * subset[mpg_col].fillna(0)
            result[f"proj_y{i}"] = fpts.values
        else:
            result[f"proj_y{i}"] = np.nan

        # Stub CI bands: ±20% of projection
        result[f"ci_lo_y{i}"] = result[f"proj_y{i}"] * 0.80
        result[f"ci_hi_y{i}"] = result[f"proj_y{i}"] * 1.20

    return result.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Step 7 — Percentile computation
# ---------------------------------------------------------------------------

PCTILE_STATS = {
    # (column_in_merged, output_name, invert)
    "ht_inches":  ("ht_pct",       False),
    "wt":         ("wt_pct",       False),
    "draft_pick": ("draft_pct",    True),   # pick 1 → 99th
    "ts_pct":     ("ts_pct_rank",  False),
    "ft_pct":     ("ft_pct_rank",  False),
    "usg_pct":    ("usg_pct_rank", False),
    "x3_freq":    ("x3_freq_rank", False),
    "ft_freq":    ("ft_freq_rank", False),
    "ast_pct":    ("ast_pct_rank", False),
    "tov_pct":    ("tov_pct_rank", True),   # lower tov% is better
    "trb_pct":    ("trb_pct_rank", False),
    "blk_pct":    ("blk_pct_rank", False),
    "stl_pct":    ("stl_pct_rank", False),
}

# Also compute percentiles for the projected per-game stats
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
    """
    For each stat, compute within-dataset percentile rank (0–100 integer).
    If hist_ref is provided, use it as the reference distribution per age band.
    Otherwise use the current df itself.
    """
    def _pct_series(values: pd.Series, ref_values: pd.Series, invert: bool) -> pd.Series:
        if invert:
            values   = -values
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
        ref = df[col]  # rank within current season
        df[out_col] = _pct_series(df[col], ref, invert)

    return df


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build(base_year: int = 2025) -> pd.DataFrame:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    # ── 1. SPS projections ────────────────────────────────────────────────
    proj = load_2025_projections(base_year)
    raw  = load_raw_totals(base_year)

    if proj.empty and raw.empty:
        raise RuntimeError(
            f"No projection data or raw totals for {base_year}. "
            "Run fetch.py and pipeline.py first."
        )

    # Use projections as the base; fall back to raw if projections are empty
    base = proj if not proj.empty else raw.copy()

    # Ensure player_id is string throughout
    base["player_id"] = base["player_id"].astype(str)

    # Add per-game projected columns if they exist from projections.py output
    for stat in PROJ_STATS:
        pg_col = f"proj_{stat}_pg"
        per36_col = f"proj_{stat}"
        mpg_col   = "proj_mpg"
        if pg_col not in base.columns and per36_col in base.columns and mpg_col in base.columns:
            base[pg_col] = base[per36_col] / 36 * base[mpg_col]

    # ── 2. Bio data ───────────────────────────────────────────────────────
    bio = load_bio(base_year)
    if not bio.empty:
        bio["player_id"] = bio["player_id"].astype(str)
        base = base.merge(bio, on="player_id", how="left")
    else:
        for c in ["ht_inches", "wt", "draft_pick"]:
            base[c] = np.nan

    # ── 3. Advanced stats ─────────────────────────────────────────────────
    adv = load_advanced(base_year)
    if not adv.empty:
        adv["player_id"] = adv["player_id"].astype(str)
        adv_cols = [c for c in adv.columns
                    if c in ["player_id", "ts_pct", "usg_pct", "ast_pct",
                             "tov_pct", "trb_pct", "blk_pct", "stl_pct",
                             "ft_pct", "bpm", "dbpm", "vorp", "per", "ws_per48"]]
        base = base.merge(adv[adv_cols], on="player_id", how="left")

    # Ensure advanced cols exist even if merge produced nothing
    for col in ["ts_pct", "usg_pct", "ast_pct", "tov_pct",
                "trb_pct", "blk_pct", "stl_pct", "ft_pct"]:
        if col not in base.columns:
            base[col] = np.nan

    # ── 4. Shooting tendency columns ──────────────────────────────────────
    base = add_tendency_cols(base, base_year)

    # ── 5. Historical actuals arc ─────────────────────────────────────────
    arc_actual = build_actuals_arc(base["player_id"], base_year)
    arc_actual["player_id"] = arc_actual["player_id"].astype(str)
    base = base.merge(arc_actual, on="player_id", how="left")

    # ── 6. SPS projected arc (y1–y5) ─────────────────────────────────────
    arc_proj = build_projection_arc(base["player_id"], base_year)
    arc_proj["player_id"] = arc_proj["player_id"].astype(str)
    base = base.merge(arc_proj, on="player_id", how="left")

    # ── 7. Percentiles ────────────────────────────────────────────────────
    # Load historical ref for age-normed percentiles (optional)
    hist_ref = None
    hist_path = PROCESSED_DIR / "historical_sps_projections.csv"
    if hist_path.exists():
        hist_ref = pd.read_csv(hist_path, usecols=lambda c: not c.startswith("proj"))

    base = add_percentiles(base, hist_ref)

    # ── 8. Clean up and enforce schema order ─────────────────────────────
    id_cols = ["player_id", "player", "age", "team", "pos"]
    bio_cols = ["ht_inches", "wt", "draft_pick"]
    proj_main = ["proj_mpg", "fantasy_pts"]
    proj_pg_cols = [f"proj_{s}_pg" for s in PROJ_STATS]
    adv_display  = ["ts_pct", "ft_pct", "usg_pct", "x3_freq", "ft_freq",
                    "ast_pct", "tov_pct", "trb_pct", "blk_pct", "stl_pct"]
    pct_cols = (
        [v[0] for v in PCTILE_STATS.values()] +
        [x[1] for x in PROJ_PG_PCTILE]
    )
    actual_cols = sorted([c for c in base.columns if c.startswith("actual_")])
    arc_cols    = sorted(
        [c for c in base.columns if c.startswith("proj_y") or
         c.startswith("ci_lo") or c.startswith("ci_hi")]
    )

    ordered = []
    for col in (id_cols + bio_cols + proj_main + proj_pg_cols +
                adv_display + pct_cols + actual_cols + arc_cols):
        if col in base.columns and col not in ordered:
            ordered.append(col)

    # Append any remaining columns not in the explicit ordering
    remainder = [c for c in base.columns if c not in ordered]
    final = base[ordered + remainder]

    # ── 9. Export ─────────────────────────────────────────────────────────
    final.to_csv(OUT_PATH, index=False)
    log.info(
        "player_cards_%d.csv written: %d players × %d columns → %s",
        base_year, len(final), len(final.columns), OUT_PATH,
    )

    # Quick sanity print
    if "fantasy_pts" in final.columns and "player" in final.columns:
        top5 = final.nlargest(5, "fantasy_pts")[["player", "age", "proj_mpg", "fantasy_pts"]]
        log.info("Top 5 by fantasy_pts:\n%s", top5.to_string(index=False))

    return final


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build player_cards_{year}.csv")
    parser.add_argument("--base-year", type=int, default=2025,
                        help="Most recent completed season (default: 2025)")
    args = parser.parse_args()
    build(args.base_year)
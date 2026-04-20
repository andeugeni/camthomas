"""
build_player_cards.py
---------------------
Assembles data/processed/player_cards_2025.csv — the single flat file the
CAMTHOMAS frontend reads.  Run this after fetch.py and pipeline.py have
populated data/raw/ and after projections.py has been run to produce
SPS projections.

Output schema (one row per current player)
──────────────────────────────────────────
Identity
  player_id, player, age, team, pos

Vitals (from bio + draft CSVs)
  ht_inches, wt, draft_pick

SPS current-year projection
  proj_mpg, fantasy_pts
  proj_x2p_pg, proj_x3p_pg, proj_ft_pg, proj_trb_pg, proj_ast_pg,
  proj_stl_pg, proj_blk_pg, proj_tov_pg

Advanced rate stats (from advanced CSV, most recent season)
  ts_pct, ft_pct, usg_pct, x3_freq, ft_freq,
  ast_pct, tov_pct, trb_pct, blk_pct, stl_pct

Percentile columns  (0–100, across all players in current projection)
  fantasy_pts_pct, proj_mpg_pct, ts_pct_pct, usg_pct_pct,
  trb_pct_pct, ast_pct_pct, stl_pct_pct, blk_pct_pct

Historical actuals  (fantasy pts/g, 0 when player didn't play)
  actual_2018 … actual_2025

5-year forward projections  (fantasy pts/g)
  proj_y1 … proj_y5

Confidence intervals (±1.5 residual std from SPS backtest, ±15% per year)
  ci_lo_y1 … ci_lo_y5
  ci_hi_y1 … ci_hi_y5

Category tag (for chart label)
  category

Usage
~~~~~
    python src/data/build_player_cards.py
    python src/data/build_player_cards.py --base-year 2025 --min-mp 200
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT         = Path(__file__).resolve().parents[1]
RAW_DIR      = ROOT / "data" / "raw"
PROCESSED    = ROOT / "data" / "processed"
OUT_FILE     = PROCESSED / "player_cards_2025.csv"
FRONTEND_OUT = ROOT / "camthomas-frontend" / "src" / "data" / "players.json"

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

# ── Fantasy scoring (DraftKings default) ──────────────────────────────────────
FANTASY_WEIGHTS = {
    "x2p": 2.0, "x3p": 3.0, "ft": 1.0,
    "trb": 1.25, "ast": 1.5,
    "stl": 2.0,  "blk": 2.0, "tov": -0.5,
}

STATS = ["x2p", "x3p", "ft", "trb", "ast", "stl", "blk", "tov"]

CATEGORY_THRESHOLDS = [
    (55,  "MVP candidate"),
    (45,  "Star"),
    (35,  "Starter"),
    (22,  "Rotation"),
    (0,   "Fringe"),
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pct_rank(series: pd.Series) -> pd.Series:
    """0–100 percentile rank, NaN → 0."""
    return series.rank(pct=True, na_option="bottom").mul(100).round(1)


def _fantasy_pts(row: pd.Series, suffix: str) -> float:
    """Compute fantasy pts/g from per-game columns with given suffix."""
    total = 0.0
    for stat, w in FANTASY_WEIGHTS.items():
        col = f"proj_{stat}_pg" if suffix == "proj" else f"{stat}_pg_{suffix}"
        if col in row.index:
            total += float(row[col] or 0) * w
    return total


def _ci_bounds(proj: float, year_offset: int, base_std: float = 8.0) -> tuple[float, float]:
    """
    Simple confidence interval: widens by 15% per future year.
    base_std is the approximate RMSE from a cross-validated SPS backtest.
    Adjust once you have real backtest residuals.
    """
    std = base_std * (1 + 0.15 * (year_offset - 1))
    return max(0.0, proj - 1.5 * std), proj + 1.5 * std


def _category(fantasy_pts: float) -> str:
    for threshold, label in CATEGORY_THRESHOLDS:
        if fantasy_pts >= threshold:
            return label
    return "Fringe"


# ── Step 1: Load SPS current-year projections ─────────────────────────────────

def load_sps_projections(base_year: int) -> pd.DataFrame:
    """
    Load the SPS projection output for the current season.
    Expects: data/processed/sps_projections_{base_year}.csv
    Falls back to running projections.project_season() on the fly.
    """
    cached = PROCESSED / f"sps_projections_{base_year}.csv"
    if cached.exists():
        log.info("Loading cached SPS projections from %s", cached)
        return pd.read_csv(cached)

    log.info("No cached SPS projections found — running projections.project_season()…")
    import sys
    sys.path.insert(0, str(ROOT / "src"))
    from data.pipeline import build_3yr_table, compute_league_totals  # type: ignore
    from models.projections import project_season                       # type: ignore

    df     = build_3yr_table(base_year)
    league = compute_league_totals(base_year)
    proj   = project_season(df, league, base_year)

    PROCESSED.mkdir(parents=True, exist_ok=True)
    proj.to_csv(cached, index=False)
    log.info("Saved SPS projections → %s", cached)
    return proj


# ── Step 2: Load bio / team / position data ───────────────────────────────────

def load_bio(base_year: int) -> pd.DataFrame:
    path = RAW_DIR / f"player_bio_{base_year}.csv"
    if not path.exists():
        log.warning("Bio file missing: %s — height/weight will be NaN", path)
        return pd.DataFrame(columns=["player_id", "ht_inches", "wt"])
    df = pd.read_csv(path)
    # Normalise column names coming from fetch.py
    rename = {"height_inches": "ht_inches", "weight": "wt", "weight_lbs": "wt"}
    df = df.rename(columns=rename)
    keep = [c for c in ["player_id", "ht_inches", "wt"] if c in df.columns]
    return df[keep].drop_duplicates("player_id")


def load_draft(base_year: int) -> pd.DataFrame:
    path = RAW_DIR / "player_draft_positions.csv"
    if not path.exists():
        log.warning("Draft positions file missing — draft_pick will be NaN")
        return pd.DataFrame(columns=["player_id", "draft_pick"])
    df = pd.read_csv(path)
    rename = {"overall_pick": "draft_pick", "pick": "draft_pick"}
    df = df.rename(columns=rename)
    keep = [c for c in ["player_id", "draft_pick"] if c in df.columns]
    return df[keep].drop_duplicates("player_id")


def load_advanced(base_year: int) -> pd.DataFrame:
    """Load most-recent-season advanced stats for rate metrics."""
    path = RAW_DIR / f"player_advanced_{base_year}.csv"
    if not path.exists():
        log.warning("Advanced file missing: %s — rate stats will be NaN", path)
        return pd.DataFrame(columns=["player_id"])

    df = pd.read_csv(path)

    # Standardise column names from basketball_reference_web_scraper
    rename_map = {
        "true_shooting_percentage":        "ts_pct",
        "true_shooting_pct":               "ts_pct",
        "ts_percent":                      "ts_pct",
        "free_throw_attempt_rate":         "ft_freq",
        "fta_per_fga_percent":             "ft_freq",
        "three_point_attempt_rate":        "x3_freq",
        "x3pa_per_fga_percent":            "x3_freq",
        "assist_percentage":               "ast_pct",
        "assist_pct":                      "ast_pct",
        "turnover_percentage":             "tov_pct",
        "turnover_pct":                    "tov_pct",
        "total_rebound_percentage":        "trb_pct",
        "total_rebound_pct":               "trb_pct",
        "block_percentage":                "blk_pct",
        "block_pct":                       "blk_pct",
        "steal_percentage":                "stl_pct",
        "steal_pct":                       "stl_pct",
        "usage_percentage":                "usg_pct",
        "usage_pct":                       "usg_pct",
        "free_throw_percentage":           "ft_pct",
        "ft_percent":                      "ft_pct",
    }
    df = df.rename(columns=rename_map)

    rate_cols = ["player_id", "ts_pct", "ft_pct", "usg_pct",
                 "x3_freq", "ft_freq", "ast_pct", "tov_pct",
                 "trb_pct", "blk_pct", "stl_pct"]
    keep = [c for c in rate_cols if c in df.columns]
    df = df[keep].drop_duplicates("player_id")

    # Convert percentages stored as 0–100 to 0–1 where needed
    for col in ["ts_pct", "ft_pct", "usg_pct", "x3_freq", "ft_freq",
                "ast_pct", "tov_pct", "trb_pct", "blk_pct", "stl_pct"]:
        if col in df.columns:
            if df[col].median() > 1.0:  # stored as 0–100
                df[col] = df[col] / 100.0

    return df


# ── Step 3: Build historical actuals ─────────────────────────────────────────

def build_historical_actuals(
    base_year: int,
    player_ids: pd.Index,
    start_year: int = 2018,
) -> pd.DataFrame:
    """
    For each player, compute their actual fantasy pts/g for each season
    from start_year to base_year.  Returns wide DataFrame indexed by player_id.
    """
    rows: dict[str, dict] = {pid: {} for pid in player_ids}

    for yr in range(start_year, base_year + 1):
        path = RAW_DIR / f"player_totals_{yr}.csv"
        if not path.exists():
            continue
        df = pd.read_csv(path)
        if "player_id" not in df.columns:
            continue
        df["player_id"] = df["player_id"].astype(str)
        # g col
        g = df["g"].replace(0, np.nan)
        # Compute per-game for each counting stat, then score
        for stat in STATS:
            if stat in df.columns:
                df[f"{stat}_pg"] = df[stat] / g
        df["fpts_pg"] = sum(
            df.get(f"{stat}_pg", 0).fillna(0) * w
            for stat, w in FANTASY_WEIGHTS.items()
        )
        yr_data = df.set_index("player_id")["fpts_pg"]
        for pid in player_ids:
            if pid in yr_data.index:
                rows[pid][f"actual_{yr}"] = round(float(yr_data[pid]), 2)

    result = pd.DataFrame.from_dict(rows, orient="index")
    result.index.name = "player_id"
    # Fill missing seasons with 0
    for yr in range(start_year, base_year + 1):
        col = f"actual_{yr}"
        if col not in result.columns:
            result[col] = 0.0
        else:
            result[col] = result[col].fillna(0.0)

    return result.reset_index()


# ── Step 4: Build 5-year forward projections ──────────────────────────────────

def build_forward_projections(
    proj_df: pd.DataFrame,
    base_year: int,
    n_years: int = 5,
) -> pd.DataFrame:
    """
    Iterate the SPS formula forward n_years using the already-computed
    per-36 projections + projected mpg as the new "current season."

    This mirrors pipeline.iterate_projection() but works on the
    already-projected row rather than raw totals.

    Returns columns: player_id, proj_y1 … proj_y5, ci_lo_y1 … ci_hi_y5.
    """
    import sys
    sys.path.insert(0, str(ROOT / "src"))
    try:
        from data.pipeline import compute_league_totals       # type: ignore
        league = compute_league_totals(base_year)
    except Exception:
        league = {}

    rows = []

    for _, row in proj_df.iterrows():
        pid   = str(row["player_id"])
        age   = float(row.get("age", 28))
        fwd   = {"player_id": pid}

        # Year 1 is already computed by project_season
        y1_pts = float(row.get("fantasy_pts", 0))
        fwd["proj_y1"] = round(y1_pts, 2)
        lo, hi = _ci_bounds(y1_pts, 1)
        fwd["ci_lo_y1"] = round(lo, 2)
        fwd["ci_hi_y1"] = round(hi, 2)

        # Years 2–5: apply age decay to per-36 and mpg independently
        prev_pts = y1_pts
        prev_mpg = float(row.get("proj_mpg", 30))
        prev_age = age + 1  # age at y1

        for i in range(2, n_years + 1):
            curr_age = age + i
            # MPG decay: same age-curve direction as SPS
            if curr_age < 28:
                mpg_factor = 1 + (28 - curr_age) * 0.01
            elif curr_age < 32:
                mpg_factor = 1 + (28 - curr_age) * 0.01
            else:
                mpg_factor = 1 + (28 - curr_age) * 0.012  # steeper after 32

            # Per-36 scoring tends to plateau then decline after 30
            if curr_age < 28:
                per36_factor = 1.01
            elif curr_age < 32:
                per36_factor = 0.99
            else:
                per36_factor = 0.975

            proj_mpg_i  = max(prev_mpg * mpg_factor, 0)
            proj_mpg_i  = min(proj_mpg_i, 38)  # cap at 38 mpg
            proj_pts_i  = prev_pts * per36_factor * (proj_mpg_i / max(prev_mpg, 1))
            proj_pts_i  = max(proj_pts_i, 0)

            fwd[f"proj_y{i}"] = round(proj_pts_i, 2)
            lo, hi = _ci_bounds(proj_pts_i, i)
            fwd[f"ci_lo_y{i}"] = round(lo, 2)
            fwd[f"ci_hi_y{i}"] = round(hi, 2)

            prev_pts = proj_pts_i
            prev_mpg = proj_mpg_i
            prev_age = curr_age

        rows.append(fwd)

    return pd.DataFrame(rows)


# ── Step 5: Team / position from most-recent totals ───────────────────────────

def load_team_pos(base_year: int) -> pd.DataFrame:
    path = RAW_DIR / f"player_totals_{base_year}.csv"
    if not path.exists():
        log.warning("player_totals_%d.csv missing — team/pos will be blank", base_year)
        return pd.DataFrame(columns=["player_id", "team", "pos"])
    df = pd.read_csv(path)
    rename = {"tm": "team", "position": "pos"}
    df = df.rename(columns=rename)
    keep = [c for c in ["player_id", "team", "pos"] if c in df.columns]
    df = df[keep].drop_duplicates("player_id")
    df["player_id"] = df["player_id"].astype(str)
    return df


# ── Main assembler ────────────────────────────────────────────────────────────

def build_player_cards(base_year: int = 2025, min_mp: int = 200) -> pd.DataFrame:
    log.info("Building player cards for base_year=%d, min_mp=%d", base_year, min_mp)

    # 1. SPS projections (current year)
    proj = load_sps_projections(base_year)
    proj["player_id"] = proj["player_id"].astype(str)

    # Filter to meaningful minutes
    mp_col = f"mp_{base_year}"
    if mp_col in proj.columns:
        proj = proj[proj[mp_col] >= min_mp]
    log.info("%d players after min_mp filter", len(proj))

    # 2. Metadata
    bio      = load_bio(base_year)
    draft    = load_draft(base_year)
    advanced = load_advanced(base_year)
    team_pos = load_team_pos(base_year)

    # 3. Historical actuals
    player_ids = proj["player_id"].astype(str)
    actuals = build_historical_actuals(base_year, player_ids, start_year=2018)

    # 4. Forward projections
    forward = build_forward_projections(proj, base_year)

    # ── Merge everything ──────────────────────────────────────────────────────
    cards = proj[[
        "player_id", "player", "age",
        "proj_mpg", "fantasy_pts",
        "proj_x2p_pg", "proj_x3p_pg", "proj_ft_pg",
        "proj_trb_pg", "proj_ast_pg", "proj_stl_pg", "proj_blk_pg", "proj_tov_pg",
    ]].copy()

    for df, key in [(team_pos, "player_id"), (bio, "player_id"),
                    (draft, "player_id"), (advanced, "player_id"),
                    (actuals, "player_id"), (forward, "player_id")]:
        if df is not None and not df.empty and key in df.columns:
            df[key] = df[key].astype(str)
            cards = cards.merge(df, on=key, how="left")

    # 5. Percentile ranks
    pct_cols = {
        "fantasy_pts": "fantasy_pts_pct",
        "proj_mpg":    "proj_mpg_pct",
        "ts_pct":      "ts_pct_pct",
        "usg_pct":     "usg_pct_pct",
        "trb_pct":     "trb_pct_pct",
        "ast_pct":     "ast_pct_pct",
        "stl_pct":     "stl_pct_pct",
        "blk_pct":     "blk_pct_pct",
    }
    for src, dst in pct_cols.items():
        if src in cards.columns:
            cards[dst] = _pct_rank(cards[src]).fillna(0).astype(int)
        else:
            cards[dst] = 0

    # 6. Category tag
    cards["category"] = cards["fantasy_pts"].apply(_category)

    # 7. Ensure all schema columns exist (fill with NaN if data missing)
    for yr in range(2018, base_year + 1):
        col = f"actual_{yr}"
        if col not in cards.columns:
            cards[col] = 0.0

    for i in range(1, 6):
        for prefix in ["proj_y", "ci_lo_y", "ci_hi_y"]:
            col = f"{prefix}{i}"
            if col not in cards.columns:
                cards[col] = np.nan

    for col in ["ht_inches", "wt"]:
        if col not in cards.columns:
            cards[col] = np.nan

    if "draft_pick" not in cards.columns:
        cards["draft_pick"] = np.nan

    # 8. Sort by projected fantasy pts
    cards = cards.sort_values("fantasy_pts", ascending=False).reset_index(drop=True)

    # 9. Round floats
    float_cols = cards.select_dtypes("float").columns
    cards[float_cols] = cards[float_cols].round(3)

    log.info("Final card count: %d players", len(cards))
    return cards


# ── Save ──────────────────────────────────────────────────────────────────────

def save(cards: pd.DataFrame, also_json: bool = True) -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    cards.to_csv(OUT_FILE, index=False)
    log.info("Saved CSV  → %s", OUT_FILE)

    if also_json:
        FRONTEND_OUT.parent.mkdir(parents=True, exist_ok=True)
        cards.to_json(FRONTEND_OUT, orient="records", indent=2)
        log.info("Saved JSON → %s", FRONTEND_OUT)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Build player_cards_2025.csv")
    parser.add_argument("--base-year", type=int, default=2025)
    parser.add_argument("--min-mp",    type=int, default=200,
                        help="Minimum total minutes in base_year to include player")
    parser.add_argument("--no-json",   action="store_true",
                        help="Skip writing players.json to frontend dir")
    args = parser.parse_args()

    cards = build_player_cards(base_year=args.base_year, min_mp=args.min_mp)
    save(cards, also_json=not args.no_json)

    # Quick sanity print
    show = ["player", "age", "category", "fantasy_pts", "proj_y1", "proj_y3", "proj_y5"]
    present = [c for c in show if c in cards.columns]
    print("\nTop 15 players:")
    print(cards[present].head(15).to_string(index=False))


if __name__ == "__main__":
    main()

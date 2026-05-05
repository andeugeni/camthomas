"""
backtest.py
-----------
Compares SPS vs four camthomas similarity variants across historical snapshot
years 1990-2025.

Methods
~~~~~~~
  SPS             — raw projection, no adjustment
  camthomas-linear  — exponential decay similarity, linear weighting
  camthomas-squared — exponential decay similarity, squared weighting
  538-linear      — FiveThirtyEight deviance formula, linear weighting
  538-squared     — FiveThirtyEight deviance formula, squared weighting

538 similarity
~~~~~~~~~~~~~~
  Z-score each feature against the eligible comp pool for that test year.
  deviance   = sqrt( sum_k( proportion_k * (z_curr_k - z_comp_k)^2 ) )
  similarity = 100 * (1.25 - deviance) / 1.25
  Drop any comp with similarity <= 0 (deviance >= 1.25).

camthomas similarity
~~~~~~~~~~~~~~~~~~
  Z-score globally (all years), exponential decay:
  similarity = 100 * exp(-dist / k)  where k = median pairwise dist in pool
  Drop any comp below MIN_SIM = 45.

Weighting variants
~~~~~~~~~~~~~~~~~~
  linear  — sim_j / sum(sim_j)
  squared — sim_j^2 / sum(sim_j^2)

Output breakdowns
~~~~~~~~~~~~~~~~~
  - By horizon (y1-y5)
  - By age bucket (<=23, 24-27, 28-31, 32-35, 36+)
  - Combined (method x horizon x age_bucket)

Saved to
~~~~~~~~
  data/processed/backtest_results.csv   — one row per (player, year, horizon)
  data/processed/backtest_summary.csv   — RMSE/MAE/bias by (method, horizon, age_bucket)
  data/processed/backtest_aggregate.csv — collapsed across years

Usage
~~~~~
    python backtest.py
    python backtest.py --start-year 1990 --end-year 2020 --min-g 20
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ROOT          = Path(__file__).resolve().parent.parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"
RAW_DIR       = ROOT / "data" / "raw"

FUTURE_YEARS    = 5
MIN_G_DEFAULT   = 20
AGE_WINDOW      = 1
MIN_SIM_CURRENT = 45.0
COMP_LOOKBACK   = 4         # comp snapshot_year <= test_year - COMP_LOOKBACK

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

SPS_STATS = ["x2p", "x3p", "ft", "trb", "ast", "stl", "blk", "tov"]

FEATURE_WEIGHTS: dict[str, float] = {
    "pos_numeric":    3.0,
    "height_in":      3.5,
    "weight_lb":      1.0,
    "log_draft_pick": 2.5,
    "career_mp":      1.5,
    "mpg":            3.5,
    "mp":             6.0,
    "usg_pct":        5.0,
    "ts_pct":         5.0,
    "ft_pct":         2.5,
    "ft_freq":        1.5,
    "x3p_freq_adj":   2.5,
    "ast_pct":        4.0,
    "tov_pct":        1.5,
    "trb_pct":        4.0,
    "blk_pct":        2.0,
    "stl_pct":        2.5,
    "dbpm":           2.0,
    "bpm":            5.0,
}
FEAT_COLS    = list(FEATURE_WEIGHTS.keys())
WEIGHT_TOTAL = sum(FEATURE_WEIGHTS.values())
WEIGHT_PROPS = np.array([FEATURE_WEIGHTS[c] / WEIGHT_TOTAL for c in FEAT_COLS])
WEIGHT_ARR   = np.array([FEATURE_WEIGHTS[c] for c in FEAT_COLS])

AGE_BUCKETS = [
    ("<=23",  0,  23),
    ("24-27", 24, 27),
    ("28-31", 28, 31),
    ("32-35", 32, 35),
    ("36+",   36, 99),
]

METHODS = ["SPS", "camthomas-linear", "camthomas-squared", "538-linear", "538-squared"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Feature engineering helpers
# ---------------------------------------------------------------------------

def _encode_pos(pos_str) -> float:
    _MAP = {
        "PG": 1.0, "SG": 2.0, "SF": 3.0, "PF": 4.0, "C": 5.0,
        "G": 1.5, "G-F": 2.5, "F-G": 2.5, "F": 3.5, "F-C": 4.5, "C-F": 4.5,
    }
    if pd.isna(pos_str) or str(pos_str).strip() == "":
        return 3.0
    return float(np.mean([_MAP.get(p.strip(), 3.0) for p in str(pos_str).split("-")]))


def _log_draft_pick(pick) -> float:
    if pd.isna(pick) or pick == 0:
        return np.log(90)
    return np.log(max(float(pick), 1.0))


def _age_bucket(age: float) -> str:
    for label, lo, hi in AGE_BUCKETS:
        if lo <= age <= hi:
            return label
    return "36+"


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_tables() -> tuple[pd.DataFrame, pd.DataFrame]:
    proj_path   = PROCESSED_DIR / "historical_sps_projections.csv"
    actual_path = PROCESSED_DIR / "historical_actuals.csv"
    if not proj_path.exists() or not actual_path.exists():
        raise RuntimeError("Run pipeline.py first to generate historical tables.")
    proj   = pd.read_csv(proj_path)
    actual = pd.read_csv(actual_path)
    proj["player_id"]   = proj["player_id"].astype(str).str.strip()
    actual["player_id"] = actual["player_id"].astype(str).str.strip()
    return proj, actual


def load_feature_matrix() -> pd.DataFrame:
    frames = []
    for p in sorted(RAW_DIR.glob("player_totals_*.csv")):
        year = int(p.stem.split("_")[-1])
        df = pd.read_csv(p)
        df["season"] = year
        frames.append(df)
    if not frames:
        raise RuntimeError("No player_totals_*.csv in data/raw/")

    totals = pd.concat(frames, ignore_index=True)
    totals["age"]       = pd.to_numeric(totals["age"], errors="coerce")
    totals["season"]    = pd.to_numeric(totals["season"], errors="coerce").astype(int)
    totals["player_id"] = totals["player_id"].astype(str).str.strip()

    g = totals["g"].replace(0, np.nan)
    totals["mpg"]       = totals["mp"] / g
    totals["career_mp"] = totals.groupby("player_id")["mp"].cumsum()

    if "x3pa" in totals.columns and "fga" in totals.columns:
        lg = totals.groupby("season")[["x3pa", "fga"]].sum()
        lg["lg_x3p_freq"] = lg["x3pa"] / lg["fga"].replace(0, np.nan)
        totals = totals.join(lg["lg_x3p_freq"], on="season")
        totals["x3p_freq"]     = totals["x3pa"] / totals["fga"].replace(0, np.nan)
        totals["x3p_freq_adj"] = totals["x3p_freq"] - totals["lg_x3p_freq"]
    else:
        totals["x3p_freq_adj"] = 0.0

    totals["ft_freq"] = (
        totals["fta"] / totals["fga"].replace(0, np.nan)
        if "fta" in totals.columns and "fga" in totals.columns else 0.0
    )

    adv_frames = []
    for p in sorted(RAW_DIR.glob("player_advanced_*.csv")):
        year = int(p.stem.split("_")[-1])
        df = pd.read_csv(p)
        df["season"] = year
        adv_frames.append(df)
    if adv_frames:
        adv = pd.concat(adv_frames, ignore_index=True)
        adv["player_id"] = adv["player_id"].astype(str).str.strip()
        adv_cols = ["player_id", "season"] + [
            c for c in ["bpm", "dbpm", "ts_pct", "usg_pct", "ast_pct",
                        "tov_pct", "trb_pct", "blk_pct", "stl_pct", "ft_pct"]
            if c in adv.columns
        ]
        totals = totals.merge(
            adv[adv_cols].drop_duplicates(["player_id", "season"]),
            on=["player_id", "season"], how="left",
        )

    bio_path = RAW_DIR / "player_bio.csv"
    if bio_path.exists():
        bio = pd.read_csv(bio_path)
        bio["player_id"] = bio["player_id"].astype(str).str.strip()
        bio_cols = ["player_id"] + [
            c for c in ["height_in", "weight_lb", "pos"] if c in bio.columns
        ]
        totals = totals.merge(
            bio[bio_cols].drop_duplicates("player_id"), on="player_id", how="left"
        )

    for name in ["draft_positions.csv", "player_draft.csv"]:
        dp = RAW_DIR / name
        if dp.exists():
            draft = pd.read_csv(dp)
            draft["player_id"] = draft["player_id"].astype(str).str.strip()
            totals = totals.merge(
                draft[["player_id", "draft_pick"]].drop_duplicates("player_id"),
                on="player_id", how="left",
            )
            break

    totals["pos_numeric"]    = totals["pos"].apply(_encode_pos) if "pos" in totals.columns else 3.0
    totals["log_draft_pick"] = totals["draft_pick"].apply(_log_draft_pick) if "draft_pick" in totals.columns else np.log(90)

    for col in FEAT_COLS:
        if col not in totals.columns:
            totals[col] = 0.0

    return totals.fillna(0.0)


# ---------------------------------------------------------------------------
# Pre-compute global scaled vectors (for current method)
# ---------------------------------------------------------------------------

def build_global_vectors(feat_df: pd.DataFrame) -> tuple[np.ndarray, pd.DataFrame]:
    feat_df = feat_df.sort_values(["player_id", "season"]).reset_index(drop=True)
    raw = feat_df[FEAT_COLS].to_numpy(dtype=float)
    scaler = StandardScaler()
    scaled = scaler.fit_transform(raw)
    return scaled * WEIGHT_ARR, feat_df


# ---------------------------------------------------------------------------
# SPS / actual fpts helpers
# ---------------------------------------------------------------------------

def sps_fpts_per_game(df: pd.DataFrame, horizon: int) -> pd.Series:
    mpg_col = f"mpg_y{horizon}"
    mpg = df[mpg_col].fillna(0) if mpg_col in df.columns else pd.Series(0.0, index=df.index)
    fpts = pd.Series(0.0, index=df.index)
    for stat, w in FANTASY_WEIGHTS.items():
        col = f"{stat}_y{horizon}"
        if col in df.columns:
            fpts += df[col].fillna(0) / 36.0 * mpg * w
    return fpts


def actual_fpts_per_game(df: pd.DataFrame, horizon: int) -> pd.Series:
    g_col = f"g_y{horizon}"
    g = df[g_col].replace(0, np.nan) if g_col in df.columns else pd.Series(np.nan, index=df.index)
    fpts = pd.Series(0.0, index=df.index)
    for stat, w in FANTASY_WEIGHTS.items():
        col = f"{stat}_y{horizon}"
        if col in df.columns:
            fpts += df[col].fillna(0) * w
    return fpts / g


# ---------------------------------------------------------------------------
# Pre-compute all SPS deltas across all history
# ---------------------------------------------------------------------------

def compute_all_deltas(proj: pd.DataFrame, actual: pd.DataFrame) -> pd.DataFrame:
    merge_keys  = ["player_id", "snapshot_year"]
    proj_cols   = merge_keys + ["player", "snapshot_age"] + \
                  [f"{s}_y{i}" for s in SPS_STATS for i in range(1, FUTURE_YEARS+1)] + \
                  [f"mpg_y{i}" for i in range(1, FUTURE_YEARS+1)]
    actual_cols = merge_keys + \
                  [f"{s}_y{i}" for s in SPS_STATS for i in range(1, FUTURE_YEARS+1)] + \
                  [f"g_y{i}"   for i in range(1, FUTURE_YEARS+1)]

    merged = proj[[c for c in proj_cols if c in proj.columns]].merge(
        actual[[c for c in actual_cols if c in actual.columns]],
        on=merge_keys,
        suffixes=("_proj", "_actual"),
        how="inner",
    )

    for i in range(1, FUTURE_YEARS + 1):
        mpg_col  = f"mpg_y{i}_proj" if f"mpg_y{i}_proj" in merged.columns else f"mpg_y{i}"
        mpg_proj = merged[mpg_col].fillna(0)

        sps_fpts = pd.Series(0.0, index=merged.index)
        for stat, w in FANTASY_WEIGHTS.items():
            col = f"{stat}_y{i}_proj" if f"{stat}_y{i}_proj" in merged.columns else f"{stat}_y{i}"
            if col in merged.columns:
                sps_fpts += merged[col].fillna(0) / 36.0 * mpg_proj * w

        g_col = f"g_y{i}_actual" if f"g_y{i}_actual" in merged.columns else f"g_y{i}"
        g = merged[g_col].replace(0, np.nan) if g_col in merged.columns else pd.Series(np.nan, index=merged.index)

        actual_fpts = pd.Series(0.0, index=merged.index)
        for stat, w in FANTASY_WEIGHTS.items():
            col = f"{stat}_y{i}_actual" if f"{stat}_y{i}_actual" in merged.columns else f"{stat}_y{i}"
            if col in merged.columns:
                actual_fpts += merged[col].fillna(0) * w
        actual_fpts_pg = actual_fpts / g

        merged[f"sps_fpts_y{i}"]    = sps_fpts
        merged[f"actual_fpts_y{i}"] = actual_fpts_pg
        merged[f"delta_y{i}"]       = actual_fpts_pg - sps_fpts

    keep = (
        ["player_id", "player", "snapshot_year", "snapshot_age"]
        + [f"delta_y{i}"    for i in range(1, FUTURE_YEARS + 1)]
        + [f"sps_fpts_y{i}" for i in range(1, FUTURE_YEARS + 1)]
    )
    return merged[[c for c in keep if c in merged.columns]].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Similarity computation
# ---------------------------------------------------------------------------

def _apply_delta(
    sps_val:   float,
    deltas:    np.ndarray,
    sims:      np.ndarray,
    weighting: str,
) -> float:
    """Apply weighted comp delta to sps_val. weighting: 'linear' or 'squared'."""
    if len(sims) == 0 or np.isnan(sps_val):
        return sps_val
    w = sims ** 2 if weighting == "squared" else sims
    total_w = w.sum()
    if total_w == 0:
        return sps_val
    return sps_val + float(np.sum(w * deltas) / total_w)


def _current_sims(
    curr_vec:  np.ndarray,
    comp_vecs: np.ndarray,
    comp_ages: np.ndarray,
    curr_age:  float,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Exponential decay similarity against globally scaled+weighted vectors.
    Returns (sims, age_mask). Comps below MIN_SIM_CURRENT zeroed.
    """
    age_mask = np.abs(comp_ages - curr_age) <= AGE_WINDOW
    if age_mask.sum() == 0:
        return np.array([]), np.zeros(len(comp_ages), dtype=bool)

    pool = comp_vecs[age_mask]
    dists = np.sqrt(np.sum((curr_vec[None, :] - pool) ** 2, axis=1))

    sample_n = min(len(pool), 400)
    rng = np.random.default_rng(42)
    idx = rng.choice(len(pool), size=sample_n, replace=False)
    sample = pool[idx]
    pw = sample[:, None, :] - sample[None, :, :]
    pw_dists = np.sqrt(np.sum(pw ** 2, axis=2))
    k = float(np.median(pw_dists[pw_dists > 0])) or 1.0

    sims = 100.0 * np.exp(-dists / k)
    sims[sims < MIN_SIM_CURRENT] = 0.0
    return sims, age_mask


def _538_sims(
    curr_raw:  np.ndarray,
    comp_raws: np.ndarray,
    comp_ages: np.ndarray,
    curr_age:  float,
) -> tuple[np.ndarray, np.ndarray]:
    """
    FiveThirtyEight deviance formula. Z-scores computed against the eligible
    comp pool for this test year (pool-relative, not global).
    Returns (sims, age_mask). Comps with sim <= 0 zeroed.
    """
    age_mask = np.abs(comp_ages - curr_age) <= AGE_WINDOW
    if age_mask.sum() == 0:
        return np.array([]), np.zeros(len(comp_ages), dtype=bool)

    pool_raw = comp_raws[age_mask]

    # Z-score against pool + current player combined for stability
    combined = np.vstack([pool_raw, curr_raw[None, :]])
    mu  = combined.mean(axis=0)
    std = combined.std(axis=0)
    std[std == 0] = 1.0

    z_pool = (pool_raw    - mu) / std
    z_curr = (curr_raw    - mu) / std

    diff_sq  = (z_curr[None, :] - z_pool) ** 2          # (n_pool, n_feat)
    deviance = np.sqrt(np.sum(WEIGHT_PROPS[None, :] * diff_sq, axis=1))

    sims = 100.0 * (1.25 - deviance) / 1.25
    sims[sims <= 0] = 0.0
    return sims, age_mask


# ---------------------------------------------------------------------------
# Adjust one snapshot year — all 4 camthomas variants
# ---------------------------------------------------------------------------

def adjust_one_year(
    test_year:   int,
    snap_df:     pd.DataFrame,
    hist_deltas: pd.DataFrame,
    feat_df:     pd.DataFrame,
    global_vecs: np.ndarray,
) -> pd.DataFrame:
    eligible_year = test_year - COMP_LOOKBACK

    hist_sub = hist_deltas[hist_deltas["snapshot_year"] <= eligible_year].copy()
    delta_cols_present = [f"delta_y{i}" for i in range(1, FUTURE_YEARS+1)
                          if f"delta_y{i}" in hist_sub.columns]

    def _fallback(df):
        for method in ["camthomas-linear", "camthomas-squared", "538-linear", "538-squared"]:
            for i in range(1, FUTURE_YEARS + 1):
                df[f"{method}_fpts_y{i}"] = df[f"sps_fpts_y{i}"]
        return df

    if hist_sub.empty:
        return _fallback(snap_df.copy())

    comp_feat = feat_df[feat_df["season"] <= eligible_year].merge(
        hist_sub[["player_id", "snapshot_year"] + delta_cols_present],
        left_on=["player_id", "season"],
        right_on=["player_id", "snapshot_year"],
        how="inner",
    )

    if comp_feat.empty:
        return _fallback(snap_df.copy())

    comp_global = global_vecs[comp_feat.index.to_numpy()]
    comp_raw    = comp_feat[FEAT_COLS].to_numpy(dtype=float)
    comp_ages   = comp_feat["age"].fillna(0).to_numpy(dtype=float)
    comp_pids   = comp_feat["player_id"].to_numpy()

    delta_arrays = {
        i: comp_feat[f"delta_y{i}"].to_numpy(dtype=float)
        for i in range(1, FUTURE_YEARS + 1)
        if f"delta_y{i}" in comp_feat.columns
    }

    # Current player feature lookup
    curr_feat = (
        feat_df[
            feat_df["season"].between(test_year - 3, test_year - 1) &
            feat_df["player_id"].isin(snap_df["player_id"])
        ]
        .sort_values("season")
        .drop_duplicates("player_id", keep="last")
        .copy()
    )
    curr_feat["age_in_test"] = curr_feat["age"] + (test_year - curr_feat["season"])

    curr_global_lk: dict[str, np.ndarray] = {}
    curr_raw_lk:    dict[str, np.ndarray] = {}
    curr_age_lk:    dict[str, float]      = {}
    for row_idx, row in curr_feat.iterrows():
        pid = row["player_id"]
        curr_global_lk[pid] = global_vecs[row_idx]
        curr_raw_lk[pid]    = row[FEAT_COLS].to_numpy(dtype=float)
        curr_age_lk[pid]    = float(row["age_in_test"])

    # Accumulate results
    variant_results: dict[str, list] = {
        f"{m}_fpts_y{i}": []
        for m in ["camthomas-linear", "camthomas-squared", "538-linear", "538-squared"]
        for i in range(1, FUTURE_YEARS + 1)
    }

    for _, snap_row in snap_df.iterrows():
        pid      = snap_row["player_id"]
        curr_age = curr_age_lk.get(pid, float(snap_row.get("snapshot_age", 28)))
        sps_vals = {i: float(snap_row.get(f"sps_fpts_y{i}", np.nan))
                    for i in range(1, FUTURE_YEARS + 1)}

        has_feat = pid in curr_global_lk
        not_self = comp_pids != pid

        if has_feat:
            sims_curr, amask_curr = _current_sims(
                curr_global_lk[pid], comp_global[not_self], comp_ages[not_self], curr_age
            )
            sims_538, amask_538 = _538_sims(
                curr_raw_lk[pid], comp_raw[not_self], comp_ages[not_self], curr_age
            )
        else:
            sims_curr, amask_curr = np.array([]), np.zeros(not_self.sum(), dtype=bool)
            sims_538,  amask_538  = np.array([]), np.zeros(not_self.sum(), dtype=bool)

        for i in range(1, FUTURE_YEARS + 1):
            sps_val = sps_vals[i]

            if i in delta_arrays:
                d_all = delta_arrays[i][not_self]
            else:
                d_all = np.array([])

            # current variants
            for weighting, tag in [("linear", "camthomas-linear"), ("squared", "camthomas-squared")]:
                col = f"{tag}_fpts_y{i}"
                if len(sims_curr) == 0 or len(d_all) == 0:
                    variant_results[col].append(sps_val)
                    continue
                d_sub   = d_all[amask_curr]
                valid   = (sims_curr > 0) & ~np.isnan(d_sub)
                if valid.sum() == 0:
                    variant_results[col].append(sps_val)
                else:
                    variant_results[col].append(
                        _apply_delta(sps_val, d_sub[valid], sims_curr[valid], weighting)
                    )

            # 538 variants
            for weighting, tag in [("linear", "538-linear"), ("squared", "538-squared")]:
                col = f"{tag}_fpts_y{i}"
                if len(sims_538) == 0 or len(d_all) == 0:
                    variant_results[col].append(sps_val)
                    continue
                d_sub   = d_all[amask_538]
                valid   = (sims_538 > 0) & ~np.isnan(d_sub)
                if valid.sum() == 0:
                    variant_results[col].append(sps_val)
                else:
                    variant_results[col].append(
                        _apply_delta(sps_val, d_sub[valid], sims_538[valid], weighting)
                    )

    out = snap_df.copy().reset_index(drop=True)
    for col, vals in variant_results.items():
        out[col] = vals
    return out


# ---------------------------------------------------------------------------
# Main backtest loop
# ---------------------------------------------------------------------------

def run_backtest(
    start_year: int = 1990,
    end_year:   int = 2020,
    min_g:      int = MIN_G_DEFAULT,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:

    proj, actual = load_tables()
    log.info("Loading feature matrix...")
    feat_df = load_feature_matrix()
    log.info("Building global vectors...")
    global_vecs, feat_df = build_global_vectors(feat_df)

    log.info("Pre-computing historical SPS deltas...")
    hist_deltas = compute_all_deltas(proj, actual)

    all_detail_rows = []

    for test_year in range(start_year, end_year + 1):
        snap = proj[proj["snapshot_year"] == test_year].copy().reset_index(drop=True)
        act  = actual[actual["snapshot_year"] == test_year].copy()

        if snap.empty:
            continue

        for i in range(1, FUTURE_YEARS + 1):
            snap[f"sps_fpts_y{i}"] = sps_fpts_per_game(snap, i)

        act_fpts: dict[int, dict] = {}
        act_g:    dict[int, dict] = {}
        for i in range(1, FUTURE_YEARS + 1):
            act[f"actual_fpts_y{i}"] = actual_fpts_per_game(act, i)
            act_fpts[i] = act.set_index("player_id")[f"actual_fpts_y{i}"].to_dict()
            g_col = f"g_y{i}"
            act_g[i] = act.set_index("player_id")[g_col].to_dict() if g_col in act.columns else {}

        snap = adjust_one_year(test_year, snap, hist_deltas, feat_df, global_vecs)

        for _, snap_row in snap.iterrows():
            pid      = snap_row["player_id"]
            snap_age = float(snap_row.get("snapshot_age", np.nan))
            age_bkt  = _age_bucket(snap_age) if not np.isnan(snap_age) else "unknown"

            for i in range(1, FUTURE_YEARS + 1):
                actual_val = act_fpts[i].get(pid, np.nan)
                g_val      = act_g[i].get(pid, 0)

                if np.isnan(actual_val) or g_val < min_g:
                    continue

                row = {
                    "player_id":     pid,
                    "player":        snap_row.get("player", ""),
                    "snapshot_year": test_year,
                    "snapshot_age":  snap_age,
                    "age_bucket":    age_bkt,
                    "horizon":       i,
                    "actual_fpts":   actual_val,
                }

                for method in METHODS:
                    if method == "SPS":
                        pred = snap_row.get(f"sps_fpts_y{i}", np.nan)
                    else:
                        pred = snap_row.get(f"{method}_fpts_y{i}", np.nan)
                    row[f"{method}_pred"]  = pred
                    row[f"{method}_error"] = pred - actual_val if not np.isnan(pred) else np.nan

                all_detail_rows.append(row)

        log.info("Year %d done — %d detail rows so far.", test_year, len(all_detail_rows))

    detail = pd.DataFrame(all_detail_rows)

    # ---------------------------------------------------------------------------
    # Summary: RMSE / MAE / bias by (method, horizon, age_bucket, snapshot_year)
    # ---------------------------------------------------------------------------
    summary_rows = []
    for (yr, h, ab), grp in detail.groupby(["snapshot_year", "horizon", "age_bucket"]):
        for method in METHODS:
            err = grp[f"{method}_error"].dropna()
            if len(err) < 5:
                continue
            summary_rows.append({
                "method":        method,
                "snapshot_year": yr,
                "horizon":       h,
                "age_bucket":    ab,
                "n":             len(err),
                "rmse":          float(np.sqrt(np.mean(err ** 2))),
                "mae":           float(np.mean(np.abs(err))),
                "bias":          float(np.mean(err)),
                "std":           float(np.std(err)),
            })

    summary = pd.DataFrame(summary_rows)

    # ---------------------------------------------------------------------------
    # Aggregate: collapse snapshot_year, keep (method x horizon x age_bucket)
    # ---------------------------------------------------------------------------
    agg_rows = []
    for (method, h, ab), grp in summary.groupby(["method", "horizon", "age_bucket"]):
        total_n = grp["n"].sum()
        if total_n == 0:
            continue
        agg_rows.append({
            "method":     method,
            "horizon":    h,
            "age_bucket": ab,
            "n_total":    total_n,
            "rmse":       float(np.sqrt(np.average(grp["rmse"] ** 2, weights=grp["n"]))),
            "mae":        float(np.average(grp["mae"],  weights=grp["n"])),
            "bias":       float(np.average(grp["bias"], weights=grp["n"])),
        })
    agg = pd.DataFrame(agg_rows)

    # Overall (no age bucket split) for headline table
    overall_rows = []
    for (method, h), grp in summary.groupby(["method", "horizon"]):
        total_n = grp["n"].sum()
        if total_n == 0:
            continue
        overall_rows.append({
            "method":  method,
            "horizon": h,
            "n_total": total_n,
            "rmse":    float(np.sqrt(np.average(grp["rmse"] ** 2, weights=grp["n"]))),
            "mae":     float(np.average(grp["mae"],  weights=grp["n"])),
            "bias":    float(np.average(grp["bias"], weights=grp["n"])),
        })
    overall = pd.DataFrame(overall_rows).sort_values(["horizon", "method"])

    # ---------------------------------------------------------------------------
    # Print results
    # ---------------------------------------------------------------------------
    print("\n=== AGGREGATE ACCURACY (all ages) ===")
    print(overall.to_string(index=False))

    print("\n=== RMSE DELTA vs SPS (negative = method beats SPS) ===")
    pivot = overall.pivot(index="horizon", columns="method", values="rmse")
    for method in METHODS[1:]:
        if method in pivot.columns and "SPS" in pivot.columns:
            pivot[f"{method}_delta"] = pivot[method] - pivot["SPS"]
    delta_cols = [c for c in pivot.columns if c.endswith("_delta")]
    if delta_cols:
        print(pivot[delta_cols].round(4).to_string())

    print("\n=== RMSE BY AGE BUCKET — HORIZON Y1 ===")
    y1_rmse = agg[agg["horizon"] == 1].pivot_table(
        index="age_bucket", columns="method", values="rmse"
    )
    bucket_order = ["<=23", "24-27", "28-31", "32-35", "36+"]
    y1_rmse = y1_rmse.reindex([b for b in bucket_order if b in y1_rmse.index])
    print(y1_rmse.round(4).to_string())

    print("\n=== BIAS BY AGE BUCKET — HORIZON Y1 ===")
    y1_bias = agg[agg["horizon"] == 1].pivot_table(
        index="age_bucket", columns="method", values="bias"
    )
    y1_bias = y1_bias.reindex([b for b in bucket_order if b in y1_bias.index])
    print(y1_bias.round(4).to_string())

    return detail, summary, agg


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest SPS vs 4 camthomas variants")
    parser.add_argument("--start-year", type=int, default=1990)
    parser.add_argument("--end-year",   type=int, default=2020)
    parser.add_argument("--min-g",      type=int, default=MIN_G_DEFAULT)
    args = parser.parse_args()

    detail, summary, agg = run_backtest(args.start_year, args.end_year, args.min_g)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    detail.to_csv(PROCESSED_DIR / "backtest_results.csv",   index=False)
    summary.to_csv(PROCESSED_DIR / "backtest_summary.csv",  index=False)
    agg.to_csv(PROCESSED_DIR / "backtest_aggregate.csv",    index=False)
    log.info("Saved backtest_results.csv, backtest_summary.csv, backtest_aggregate.csv")


if __name__ == "__main__":
    main()
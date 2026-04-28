"""
carmelo_adjust.py
-----------------
Adjusts SPS per-game fantasy point projections using a CARMELO-style
comparable-player delta approach.

The key insight (from FiveThirtyEight's methodology):
  - For each comparable player j, compute how much they BEAT OR MISSED
    *their own* SPS baseline projection, not the current player's projection.
  - Apply that baseline-relative delta, weighted by similarity, to the
    current player's SPS projection.

This corrects for "poor man's" comps — a player who was stylistically
similar but statistically inferior still provides signal: if he beat his
own projection by 3 pts/game, that's a real pattern regardless of his
absolute level.

Algorithm
~~~~~~~~~
  comp_baseline_y{i}  = SPS projected fpts/game for comp j at that age
  comp_actual_y{i}    = what comp j actually produced
  comp_delta_y{i}     = comp_actual - comp_baseline   (baseline-relative)

  current_adjustment  = Σ(sim_j * comp_delta_y{i}) / Σ(sim_j)
  carmelo_y{i}        = current_sps_y{i} + current_adjustment

Output columns
~~~~~~~~~~~~~~
  player_id, player, age,
  sps_fpts_y{1..5},      <- raw SPS fantasy pts/game
  carmelo_fpts_y{1..5},  <- similarity-adjusted fantasy pts/game
  delta_applied_y{1..5}, <- adjustment actually added (for inspection)
  n_comps_y{1..5},       <- comps with actuals for that year
  sum_sim_y{1..5}        <- total similarity weight (quality signal)

Usage
~~~~~
    python src/models/carmelo_adjust.py
    python src/models/carmelo_adjust.py --base-year 2026 --min-sim 20
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

ROOT          = Path(__file__).resolve().parents[2]
RAW_DIR       = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"

FUTURE_YEARS           = 5
MIN_SIMILARITY_DEFAULT = 45.0   # higher = fewer but stronger comps
AGE_WINDOW             = 1      # comps within ±2 years of current player's age
BASE_YEAR_DEFAULT      = 2026

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

FEAT_COLS = list(FEATURE_WEIGHTS.keys())
SPS_STATS = ["x2p", "x3p", "ft", "trb", "ast", "stl", "blk", "tov"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Step 1 — Load historical deltas (baseline-relative: actual - comp's own SPS)
# ---------------------------------------------------------------------------

def load_historical_deltas(base_year: int) -> pd.DataFrame:
    """
    For every historical player-snapshot, compute:
        delta_y{i} = actual_fpts_pg_y{i} - comp_own_sps_fpts_pg_y{i}

    This is the BASELINE-RELATIVE delta — how much the comp beat or missed
    *their own* SPS projection. This is what gets applied to the current
    player's SPS baseline.

    Returns one row per (player_id, snapshot_year) with columns:
        player_id, player, snapshot_year, snapshot_age,
        sps_fpts_y{1..5},    <- comp's own SPS projection
        actual_fpts_y{1..5}, <- comp's actual production
        delta_y{1..5}        <- actual - own SPS  (NaN if player didn't play)
    """
    proj_path   = PROCESSED_DIR / "historical_sps_projections.csv"
    actual_path = PROCESSED_DIR / "historical_actuals.csv"

    if not proj_path.exists() or not actual_path.exists():
        raise RuntimeError(
            "Run pipeline.py first to generate historical_sps_projections.csv "
            "and historical_actuals.csv."
        )

    proj   = pd.read_csv(proj_path)
    actual = pd.read_csv(actual_path)

    # Only use snapshots where actuals are fully available
    proj   = proj[proj["snapshot_year"] < base_year - 1].copy()
    actual = actual[actual["snapshot_year"] < base_year - 1].copy()

    # Both CSVs share identical column names ({stat}_y{i}, g_y{i}, mpg_y{i}).
    # Merge separately so we can reference proj and actual columns unambiguously.
    merge_keys = ["player_id", "snapshot_year"]
    # Only keep the forward-window columns from each to avoid collision
    proj_fwd_cols   = [f"{s}_y{i}" for s in SPS_STATS for i in range(1, FUTURE_YEARS+1)] +                       [f"mpg_y{i}" for i in range(1, FUTURE_YEARS+1)]
    actual_fwd_cols = proj_fwd_cols + [f"g_y{i}" for i in range(1, FUTURE_YEARS+1)]

    proj_keep   = merge_keys + ["player", "snapshot_age"] +                   [c for c in proj_fwd_cols if c in proj.columns]
    actual_keep = merge_keys + [c for c in actual_fwd_cols if c in actual.columns]

    merged = proj[proj_keep].merge(
        actual[actual_keep],
        on=merge_keys,
        suffixes=("_proj", "_actual"),
        how="inner",
    )

    for i in range(1, FUTURE_YEARS + 1):
        # Comp's OWN SPS projection (per-36 -> per-game)
        mpg_col = f"mpg_y{i}_proj" if f"mpg_y{i}_proj" in merged.columns else f"mpg_y{i}"
        mpg_proj = merged[mpg_col].fillna(0) if mpg_col in merged.columns else pd.Series(0.0, index=merged.index)
        sps_fpts = pd.Series(0.0, index=merged.index)
        for stat, w in FANTASY_WEIGHTS.items():
            col = f"{stat}_y{i}_proj" if f"{stat}_y{i}_proj" in merged.columns else f"{stat}_y{i}"
            if col in merged.columns:
                sps_fpts += merged[col].fillna(0) / 36.0 * mpg_proj * w

        # Comp's actual production (season totals -> per-game)
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
        + [f"sps_fpts_y{i}"    for i in range(1, FUTURE_YEARS + 1)]
        + [f"actual_fpts_y{i}" for i in range(1, FUTURE_YEARS + 1)]
        + [f"delta_y{i}"       for i in range(1, FUTURE_YEARS + 1)]
    )
    result = merged[[c for c in keep if c in merged.columns]].reset_index(drop=True)

    # Diagnostic: show delta distribution
    for i in range(1, 3):
        d = result[f"delta_y{i}"].dropna()
        log.info(
            "delta_y%d: mean=%.2f  std=%.2f  median=%.2f  p10=%.2f  p90=%.2f  (n=%d)",
            i, d.mean(), d.std(), d.median(),
            d.quantile(0.10), d.quantile(0.90), len(d),
        )

    log.info("Historical deltas: %d snapshots.", len(result))
    return result


# ---------------------------------------------------------------------------
# Step 2 — Feature matrix
# ---------------------------------------------------------------------------

def _encode_pos(pos_str) -> float:
    _POS_MAP = {
        "PG": 1.0, "SG": 2.0, "SF": 3.0, "PF": 4.0, "C": 5.0,
        "G": 1.5, "G-F": 2.5, "F-G": 2.5, "F": 3.5, "F-C": 4.5, "C-F": 4.5,
    }
    if pd.isna(pos_str) or str(pos_str).strip() == "":
        return 3.0
    parts = str(pos_str).split("-")
    return float(np.mean([_POS_MAP.get(p.strip(), 3.0) for p in parts]))


def _log_draft_pick(pick, last_pick: int = 60) -> float:
    if pd.isna(pick) or pick == 0:
        return np.log(last_pick + 30)
    return np.log(max(float(pick), 1.0))


def _build_features(raw_dir: Path, start_year: int, end_year: int) -> pd.DataFrame:
    """Load totals + advanced + bio + draft and engineer feature columns."""
    frames = []
    for year in range(start_year, end_year + 1):
        p = raw_dir / f"player_totals_{year}.csv"
        if p.exists():
            df = pd.read_csv(p)
            df["season"] = year
            frames.append(df)
    if not frames:
        raise RuntimeError(f"No player_totals_*.csv found in {raw_dir}")

    totals = pd.concat(frames, ignore_index=True)
    totals["age"] = pd.to_numeric(totals["age"], errors="coerce")

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
        if "fta" in totals.columns and "fga" in totals.columns
        else 0.0
    )

    # Advanced
    adv_frames = []
    for year in range(start_year, end_year + 1):
        p = raw_dir / f"player_advanced_{year}.csv"
        if p.exists():
            df = pd.read_csv(p)
            df["season"] = year
            adv_frames.append(df)
    if adv_frames:
        adv = pd.concat(adv_frames, ignore_index=True)
        adv_cols = ["player_id", "season"] + [
            c for c in ["bpm", "dbpm", "ts_pct", "usg_pct", "ast_pct",
                        "tov_pct", "trb_pct", "blk_pct", "stl_pct", "ft_pct"]
            if c in adv.columns
        ]
        totals = totals.merge(
            adv[adv_cols].drop_duplicates(["player_id", "season"]),
            on=["player_id", "season"], how="left",
        )

    # Bio
    bio_path = raw_dir / "player_bio.csv"
    if bio_path.exists():
        bio = pd.read_csv(bio_path)
        bio_cols = ["player_id"] + [
            c for c in ["height_in", "weight_lb", "pos"] if c in bio.columns
        ]
        totals = totals.merge(bio[bio_cols].drop_duplicates("player_id"), on="player_id", how="left")

    # Draft
    for name in ["draft_positions.csv", "player_draft.csv"]:
        dp = raw_dir / name
        if dp.exists():
            draft = pd.read_csv(dp)
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
# Step 3 — Main adjustment
# ---------------------------------------------------------------------------

def adjust_projections(
    base_year:      int   = BASE_YEAR_DEFAULT,
    min_similarity: float = MIN_SIMILARITY_DEFAULT,
    age_window:     int   = AGE_WINDOW,
    raw_dir:        Path  = RAW_DIR,
) -> pd.DataFrame:

    # ── Load SPS projections for current players ──────────────────────────
    sps_path = PROCESSED_DIR / f"projections_{base_year}.csv"
    if not sps_path.exists():
        raise RuntimeError(f"Run projections.py first: missing {sps_path}")
    sps = pd.read_csv(sps_path)
    sps["player_id"] = sps["player_id"].astype(str)

    # Recompute SPS fpts/game from per-game stat columns already in the file
    for i in range(1, FUTURE_YEARS + 1):
        fpts = pd.Series(0.0, index=sps.index)
        for stat, w in FANTASY_WEIGHTS.items():
            col = f"{stat}_pg_y{i}"
            if col in sps.columns:
                fpts += sps[col].fillna(0) * w
        sps[f"sps_fpts_y{i}"] = fpts

    # ── Historical baseline-relative deltas ───────────────────────────────
    hist_deltas = load_historical_deltas(base_year)
    # ── Diagnostic: show what actually came back from load_historical_deltas ──
    log.info("hist_deltas columns: %s", hist_deltas.columns.tolist())
    log.info("hist_deltas shape: %s", hist_deltas.shape)
    if "delta_y1" in hist_deltas.columns:
        d = hist_deltas["delta_y1"].dropna()
        log.info("delta_y1 non-null BEFORE merge: %d/%d  mean=%.2f", len(d), len(hist_deltas), d.mean() if len(d) else float("nan"))
    else:
        log.warning("delta_y1 not in hist_deltas at all")
    if "sps_fpts_y1" in hist_deltas.columns:
        s = hist_deltas["sps_fpts_y1"].dropna()
        log.info("sps_fpts_y1 non-null: %d/%d  mean=%.2f", len(s), len(hist_deltas), s.mean() if len(s) else float("nan"))
    if "actual_fpts_y1" in hist_deltas.columns:
        a = hist_deltas["actual_fpts_y1"].dropna()
        log.info("actual_fpts_y1 non-null: %d/%d  mean=%.2f", len(a), len(hist_deltas), a.mean() if len(a) else float("nan"))
    hist_deltas["player_id"] = hist_deltas["player_id"].astype(str)

    # ── Feature matrix ────────────────────────────────────────────────────
    log.info("Building feature matrix 1980-%d...", base_year - 1)
    feat_df = _build_features(raw_dir, 1980, base_year - 1)
    feat_df["player_id"] = feat_df["player_id"].astype(str).str.strip()
    feat_df["age"]       = pd.to_numeric(feat_df["age"], errors="coerce")
    feat_df["season"]    = pd.to_numeric(feat_df["season"], errors="coerce").astype(int)

    hist_deltas["player_id"]     = hist_deltas["player_id"].astype(str).str.strip()
    hist_deltas["snapshot_year"] = pd.to_numeric(hist_deltas["snapshot_year"], errors="coerce").astype(int)

    # Diagnostic: surface ID format mismatch before merge
    feat_ids  = set(feat_df["player_id"].unique())
    delta_ids = set(hist_deltas["player_id"].unique())
    overlap   = feat_ids & delta_ids
    log.info(
        "player_id overlap: feat_df=%d  hist_deltas=%d  overlap=%d",
        len(feat_ids), len(delta_ids), len(overlap),
    )
    if not overlap:
        log.warning(
            "ZERO overlap — IDs are in different formats.\n"
            "  feat_df sample:     %s\n"
            "  hist_deltas sample: %s",
            list(feat_ids)[:5], list(delta_ids)[:5],
        )

    # Historical feature rows: join to delta table on (player_id, season=snapshot_year)
    hist_feat = feat_df[feat_df["season"] < base_year].copy()
    delta_cols_present = [
        f"delta_y{i}" for i in range(1, FUTURE_YEARS + 1)
        if f"delta_y{i}" in hist_deltas.columns
    ]
    hist_feat = hist_feat.merge(
        hist_deltas[["player_id", "snapshot_year"] + delta_cols_present],
        left_on=["player_id", "season"],
        right_on=["player_id", "snapshot_year"],
        how="inner",
    )

    # Diagnostic: verify deltas survived the merge
    if len(hist_feat) > 0 and "delta_y1" in hist_feat.columns:
        non_null = hist_feat["delta_y1"].notna().sum()
        log.info(
            "After merge: %d hist rows, delta_y1 non-null=%d (%.1f%%)",
            len(hist_feat), non_null, 100 * non_null / len(hist_feat),
        )
        log.info("delta_y1 stats: %s", hist_feat["delta_y1"].describe().to_dict())
    else:
        log.warning("hist_feat empty after merge or delta_y1 missing — check ID format above.")

    # Current player feature rows: most recent season within last 3 years
    curr_feat = (
        feat_df[
            feat_df["season"].between(base_year - 3, base_year - 1) &
            feat_df["player_id"].isin(sps["player_id"])
        ]
        .sort_values("season")
        .drop_duplicates(subset="player_id", keep="last")
        .copy()
    )
    curr_feat["age_in_base"] = (
        pd.to_numeric(curr_feat["age"], errors="coerce") + (base_year - curr_feat["season"])
    )

    log.info("Hist snapshots: %d  |  Current players: %d", len(hist_feat), len(curr_feat))

    # ── Build scaled + weighted feature vectors ───────────────────────────
    all_feat_raw = pd.concat(
        [hist_feat[FEAT_COLS], curr_feat[FEAT_COLS]], ignore_index=True
    ).fillna(0.0).to_numpy(dtype=float)

    scaler     = StandardScaler()
    all_scaled = scaler.fit_transform(all_feat_raw)
    weight_arr = np.array([FEATURE_WEIGHTS[c] for c in FEAT_COLS])
    all_vec    = all_scaled * weight_arr

    n_hist       = len(hist_feat)
    hist_vec     = all_vec[:n_hist]
    curr_vec_arr = all_vec[n_hist:]

    # Global k from a sample of historical pairwise distances
    sample_size = min(n_hist, 600)
    rng         = np.random.default_rng(42)
    idx         = rng.choice(n_hist, size=sample_size, replace=False)
    sample      = hist_vec[idx]
    pw_diff     = sample[:, None, :] - sample[None, :, :]
    pw_dists    = np.sqrt(np.sum(pw_diff ** 2, axis=2))
    global_k    = float(np.median(pw_dists[pw_dists > 0]))
    log.info("Global k = %.4f", global_k)

    # Preload delta arrays as numpy for speed
    delta_arrays = {
        i: hist_feat[f"delta_y{i}"].to_numpy(dtype=float)
        for i in range(1, FUTURE_YEARS + 1)
        if f"delta_y{i}" in hist_feat.columns
    }
    hist_ages       = hist_feat["age"].fillna(0).to_numpy(dtype=float)
    hist_player_ids = hist_feat["player_id"].to_numpy()
    curr_player_ids = curr_feat["player_id"].to_numpy()
    curr_ages       = curr_feat["age_in_base"].fillna(28).to_numpy(dtype=float)

    # ── Per-player adjustment ─────────────────────────────────────────────
    rows = []
    for ci, pid in enumerate(curr_player_ids):
        curr_age = curr_ages[ci]
        cv       = curr_vec_arr[ci]

        age_mask = np.abs(hist_ages - curr_age) <= age_window
        pid_mask = hist_player_ids != pid
        mask     = age_mask & pid_mask

        sps_row = sps[sps["player_id"] == pid]
        if sps_row.empty:
            continue
        sps_row = sps_row.iloc[0]

        if mask.sum() == 0:
            rows.append(_sps_only_row(pid, sps_row))
            continue

        cand_vec  = hist_vec[mask]
        dists     = np.sqrt(np.sum((cv[None, :] - cand_vec) ** 2, axis=1))
        sims      = 100.0 * np.exp(-dists / global_k)
        sim_mask  = sims >= min_similarity

        if sim_mask.sum() == 0:
            rows.append(_sps_only_row(pid, sps_row))
            continue

        sims_filt    = sims[sim_mask]
        weights_filt = sims_filt ** 2
        cand_indices = np.where(mask)[0][sim_mask]

        result_row = {
            "player_id":     pid,
            "player":        sps_row.get("player", ""),
            "age":           sps_row.get("age", np.nan),
            "n_comps_total": int(sim_mask.sum()),
        }

        for i in range(1, FUTURE_YEARS + 1):
            sps_fpts = float(sps_row.get(f"sps_fpts_y{i}", np.nan))
            result_row[f"sps_fpts_y{i}"] = sps_fpts

            if i not in delta_arrays:
                result_row[f"carmelo_fpts_y{i}"]  = sps_fpts
                result_row[f"delta_applied_y{i}"] = 0.0
                result_row[f"n_comps_y{i}"]        = 0
                result_row[f"sum_sim_y{i}"]         = 0.0
                continue

            delta_arr = delta_arrays[i][cand_indices]
            valid     = ~np.isnan(delta_arr)

            result_row[f"n_comps_y{i}"] = int(valid.sum())
            result_row[f"sum_sim_y{i}"] = float(weights_filt[valid].sum())

            if valid.sum() == 0 or np.isnan(sps_fpts):
                result_row[f"carmelo_fpts_y{i}"]  = sps_fpts
                result_row[f"delta_applied_y{i}"] = 0.0
            else:
                w_delta = float(
                    np.sum(weights_filt[valid] * delta_arr[valid]) / weights_filt[valid].sum()
                )
                result_row[f"delta_applied_y{i}"]  = w_delta
                result_row[f"carmelo_fpts_y{i}"]   = sps_fpts + w_delta

        rows.append(result_row)

    out = pd.DataFrame(rows).sort_values("carmelo_fpts_y1", ascending=False).reset_index(drop=True)

    # Diagnostic: how large are the adjustments?
    for i in range(1, 3):
        col = f"delta_applied_y{i}"
        if col in out.columns:
            d = out[col].dropna()
            log.info(
                "Adjustment applied y%d: mean=%.2f  std=%.2f  "
                "min=%.2f  max=%.2f  |delta|>1: %d/%d players",
                i, d.mean(), d.std(), d.min(), d.max(),
                (d.abs() > 1).sum(), len(d),
            )

    log.info(
        "Done — %d players.\n%s",
        len(out),
        out[["player", "age", "sps_fpts_y1", "carmelo_fpts_y1", "delta_applied_y1"]]
        .head(10).to_string(index=False),
    )
    return out


def _sps_only_row(pid: str, sps_row: pd.Series) -> dict:
    row = {
        "player_id":     pid,
        "player":        sps_row.get("player", ""),
        "age":           sps_row.get("age", np.nan),
        "n_comps_total": 0,
    }
    for i in range(1, FUTURE_YEARS + 1):
        v = float(sps_row.get(f"sps_fpts_y{i}", np.nan))
        row[f"sps_fpts_y{i}"]     = v
        row[f"carmelo_fpts_y{i}"] = v
        row[f"delta_applied_y{i}"] = 0.0
        row[f"n_comps_y{i}"]       = 0
        row[f"sum_sim_y{i}"]       = 0.0
    return row


# ---------------------------------------------------------------------------
# Save + CLI
# ---------------------------------------------------------------------------

def save(results: pd.DataFrame, base_year: int) -> Path:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / f"carmelo_projections_{base_year}.csv"
    col_order = (
        ["player_id", "player", "age", "n_comps_total"]
        + [c for i in range(1, FUTURE_YEARS + 1)
           for c in [f"sps_fpts_y{i}", f"carmelo_fpts_y{i}",
                     f"delta_applied_y{i}", f"n_comps_y{i}", f"sum_sim_y{i}"]]
    )
    results[[c for c in col_order if c in results.columns]].to_csv(out_path, index=False)
    log.info("Saved %d rows -> %s", len(results), out_path)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="CARMELO-style projection adjustment")
    parser.add_argument("--base-year",  type=int,   default=BASE_YEAR_DEFAULT)
    parser.add_argument("--min-sim",    type=float,  default=MIN_SIMILARITY_DEFAULT)
    parser.add_argument("--age-window", type=int,   default=AGE_WINDOW)
    parser.add_argument("--raw-dir",    default=str(RAW_DIR))
    args = parser.parse_args()

    results = adjust_projections(
        base_year=args.base_year,
        min_similarity=args.min_sim,
        age_window=args.age_window,
        raw_dir=Path(args.raw_dir),
    )
    save(results, args.base_year)

    print("\nTop 20 by CARMELO Y1:")
    cols = ["player", "age", "n_comps_total",
            "sps_fpts_y1", "carmelo_fpts_y1", "delta_applied_y1",
            "sps_fpts_y3", "carmelo_fpts_y3", "delta_applied_y3"]
    print(results[[c for c in cols if c in results.columns]].head(20).to_string(index=False))


if __name__ == "__main__":
    main()
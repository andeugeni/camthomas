"""
compute_similarities.py
-----------------------
Finds the top 10 most similar historical players for every current NBA player.

Feature weights approximate CARMELO's five 20%-buckets:
  - Physical / draft context  (position, height, weight, draft pick)
  - Volume / role             (career mp, mpg, usg%)
  - Shooting efficiency       (ts%, ft%, ft-freq, 3p-freq)
  - Playmaking / ball-handling (ast%, tov%)
  - Defense / rebounding      (reb%, blk%, stl%, dbpm, bpm)

Data sources (all expected as columns in the wide pipeline CSV or SQLite):
  player_totals_{year}.csv  — mp, g, x2p/x3p/ft/trb/ast/stl/blk/tov
  player_advanced_{year}.csv — bpm, dbpm, ts_pct, usg_pct, ast_pct,
                                tov_pct, trb_pct, blk_pct, stl_pct
  player_bio_{year}.csv     — height_in, weight_lb, pos
  player_draft.csv          — draft_pick, draft_year  (one row per player)

Falls back gracefully when columns are absent (zero-fills that feature).

Output: data/processed/similarities.json
  {
    "jamesle01": {
      "player": "LeBron James",
      "age": 40,
      "comps": [
        {
          "rank": 1,
          "player": "Chris Paul",
          "player_id": "paulch01",
          "comp_year": 2013,
          "comp_age": 27,
          "similarity": 87.4,
          "trajectory": [null, 14.2, 16.8, 18.1, 17.3, 15.9, null]
          //              ym3   ym2   ym1   y0    y1    y2    y3
        }, ...
      ]
    }
  }

Usage
~~~~~
    python src/data/compute_similarities.py
    python src/data/compute_similarities.py --base-year 2025 --raw-dir data/raw --out data/processed/similarities.json
"""

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Feature weights
# ---------------------------------------------------------------------------

_POS_MAP = {
    "PG": 1.0, "SG": 2.0, "SF": 3.0, "PF": 4.0, "C": 5.0,
    "G": 1.5, "G-F": 2.5, "F-G": 2.5, "F": 3.5, "F-C": 4.5, "C-F": 4.5,
}

FEATURE_WEIGHTS: dict[str, float] = {
    # Physical / draft
    "pos_numeric":    3.0,
    "height_in":      3.5,
    "weight_lb":      1.0,
    "log_draft_pick": 2.5,
    # Volume / role
    "career_mp":      1.5,
    "mpg":            3.5,
    "mp":             6.0,
    "usg_pct":        5.0,
    # Shooting efficiency
    "ts_pct":         5.0,
    "ft_pct":         2.5,
    "ft_freq":        1.5,
    "x3p_freq_adj":   2.5,
    # Playmaking
    "ast_pct":        4.0,
    "tov_pct":        1.5,
    # Defense / rebounding
    "trb_pct":        4.0,
    "blk_pct":        2.0,
    "stl_pct":        2.5,
    "dbpm":           2.0,
    "bpm":            5.0,
}

FANTASY_WEIGHTS = {
    "x2p_pg": 2.0, "x3p_pg": 3.0, "ft_pg": 1.0,
    "trb_pg": 1.25, "ast_pg": 1.5, "stl_pg": 2.0, "blk_pg": 2.0, "tov_pg": -0.5,
}

TRAJ_OFFSETS = [-3, -2, -1, 0, 1, 2, 3]
BASE_YEAR_DEFAULT = 2025


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_totals(raw_dir: Path, start_year: int, end_year: int) -> pd.DataFrame:
    frames = []
    for year in range(start_year, end_year + 1):
        for prefix in ["player_totals", "totals"]:
            p = raw_dir / f"{prefix}_{year}.csv"
            if p.exists():
                df = pd.read_csv(p)
                df["season"] = year
                frames.append(df)
                break
    if not frames:
        raise RuntimeError(f"No totals CSVs in {raw_dir}")
    out = pd.concat(frames, ignore_index=True)
    out["age"] = pd.to_numeric(out["age"], errors="coerce")
    return out


def load_advanced(raw_dir: Path, start_year: int, end_year: int) -> pd.DataFrame:
    frames = []
    for year in range(start_year, end_year + 1):
        for prefix in ["player_advanced", "advanced"]:
            p = raw_dir / f"{prefix}_{year}.csv"
            if p.exists():
                df = pd.read_csv(p)
                df["season"] = year
                frames.append(df)
                break
    if not frames:
        log.warning("No advanced CSVs found — advanced features will be zero-filled.")
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def load_bio(raw_dir: Path, start_year: int, end_year: int) -> pd.DataFrame:
    single = raw_dir / "player_bio.csv"
    if single.exists():
        return pd.read_csv(single)
    frames = []
    for year in range(start_year, end_year + 1):
        for prefix in ["player_bio", "bio"]:
            p = raw_dir / f"{prefix}_{year}.csv"
            if p.exists():
                df = pd.read_csv(p)
                df["season"] = year
                frames.append(df)
                break
    if not frames:
        log.warning("No bio CSVs found — height/weight/pos will be zero-filled.")
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def load_draft(raw_dir: Path) -> pd.DataFrame:
    for name in ["player_draft.csv", "draft.csv", "draft_positions.csv"]:
        p = raw_dir / name
        if p.exists():
            return pd.read_csv(p)
    log.warning("No draft CSV found — draft_pick will be zero-filled.")
    return pd.DataFrame()


# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------

def _encode_pos(pos_str) -> float:
    if pd.isna(pos_str) or str(pos_str).strip() == "":
        return 3.0
    parts = str(pos_str).split("-")
    vals = [_POS_MAP.get(p.strip(), 3.0) for p in parts]
    return float(np.mean(vals))


def _log_draft_pick(pick, last_pick=60) -> float:
    if pd.isna(pick) or pick == 0:
        return np.log(last_pick + 30)
    return np.log(max(float(pick), 1.0))


def build_feature_matrix(
    totals: pd.DataFrame,
    advanced: pd.DataFrame,
    bio: pd.DataFrame,
    draft: pd.DataFrame,
) -> pd.DataFrame:
    df = totals.copy()

    # Per-game counting stats for sparkline
    g = df["g"].replace(0, np.nan)
    for stat in ["x2p", "x3p", "ft", "trb", "ast", "stl", "blk", "tov", "mp"]:
        if stat in df.columns:
            df[f"{stat}_pg"] = df[stat] / g

    # Career mp (cumulative)
    df = df.sort_values(["player_id", "season"])
    df["career_mp"] = df.groupby("player_id")["mp"].cumsum()

    # mpg
    df["mpg"] = df["mp"] / g

    # 3p freq adjusted for league average
    if "x3pa" in df.columns and "fga" in df.columns:
        lg = df.groupby("season")[["x3pa", "fga"]].sum()
        lg["lg_x3p_freq"] = lg["x3pa"] / lg["fga"].replace(0, np.nan)
        df = df.join(lg["lg_x3p_freq"], on="season")
        df["x3p_freq"] = df["x3pa"] / df["fga"].replace(0, np.nan)
        df["x3p_freq_adj"] = df["x3p_freq"] - df["lg_x3p_freq"]
    else:
        df["x3p_freq_adj"] = 0.0

    if "fta" in df.columns and "fga" in df.columns:
        df["ft_freq"] = df["fta"] / df["fga"].replace(0, np.nan)
    else:
        df["ft_freq"] = 0.0

    # Merge advanced
    if not advanced.empty:
        adv_cols = ["player_id", "season"] + [
            c for c in ["bpm", "dbpm", "ts_pct", "usg_pct", "ast_pct",
                        "tov_pct", "trb_pct", "blk_pct", "stl_pct", "ft_pct"]
            if c in advanced.columns
        ]
        df = df.merge(
            advanced[adv_cols].drop_duplicates(["player_id", "season"]),
            on=["player_id", "season"], how="left"
        )

    # Merge bio
    if not bio.empty:
        bio_cols = ["player_id"] + [c for c in ["height_in", "weight_lb", "pos"] if c in bio.columns]
        if "season" in bio.columns:
            bio_cols.append("season")
            df = df.merge(
                bio[bio_cols].drop_duplicates(["player_id", "season"]),
                on=["player_id", "season"], how="left"
            )
        else:
            df = df.merge(
                bio[bio_cols].drop_duplicates("player_id"),
                on="player_id", how="left"
            )

    # Merge draft
    if not draft.empty:
        draft_cols = ["player_id"] + [c for c in ["draft_pick", "draft_year"] if c in draft.columns]
        df = df.merge(
            draft[draft_cols].drop_duplicates("player_id"),
            on="player_id", how="left"
        )

    # Derived categorical features
    df["pos_numeric"] = df["pos"].apply(_encode_pos) if "pos" in df.columns else 3.0
    df["log_draft_pick"] = df["draft_pick"].apply(_log_draft_pick) if "draft_pick" in df.columns else np.log(90)

    # Ensure all feature cols exist
    for col in FEATURE_WEIGHTS:
        if col not in df.columns:
            df[col] = 0.0

    return df.fillna(0.0)


# ---------------------------------------------------------------------------
# Vector builders
# ---------------------------------------------------------------------------

FEAT_COLS = list(FEATURE_WEIGHTS.keys())
VEC_COLS  = [f"f_{c}" for c in FEAT_COLS]


def _fpts_row(row) -> float | None:
    total = 0.0
    for stat, w in FANTASY_WEIGHTS.items():
        v = row.get(stat, 0.0)
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return None
        total += float(v) * w
    return round(total, 2)


def build_historical_vectors(feat_df: pd.DataFrame, last_season: int, feat_df_full: pd.DataFrame = None) -> pd.DataFrame:
    # Snapshot anchors only up to last_season (prevents current players as their own comps)
    df = feat_df[feat_df["season"] <= last_season].drop_duplicates(["player_id", "season"]).copy()
    df["fpts_pg"] = df.apply(_fpts_row, axis=1)

    # Trajectory lookup uses full dataset so sparklines extend through present
    traj_source = (feat_df_full if feat_df_full is not None else feat_df).drop_duplicates(["player_id", "season"]).copy()
    traj_source["fpts_pg"] = traj_source.apply(_fpts_row, axis=1)

    fpts_lookup: dict[str, dict] = {}
    for _, row in traj_source[["player_id", "season", "fpts_pg"]].iterrows():
        fpts_lookup.setdefault(str(row["player_id"]), {})[int(row["season"])] = row["fpts_pg"]

    rows = []
    for _, row in df.iterrows():
        pid    = str(row["player_id"])
        season = int(row["season"])
        age    = int(row["age"]) if row["age"] > 0 else None
        if age is None:
            continue
        rec = {
            "player_id":     pid,
            "player":        row.get("player", ""),
            "age":           age,
            "snapshot_year": season,
        }
        for c in FEAT_COLS:
            rec[f"f_{c}"] = float(row.get(c, 0.0)) * FEATURE_WEIGHTS[c]
        player_fpts = fpts_lookup.get(pid, {})
        for rel in TRAJ_OFFSETS:
            v = player_fpts.get(season + rel)
            rec[f"traj_{rel}"] = v
        rows.append(rec)

    result = pd.DataFrame(rows)
    log.info("Historical vectors: %d rows", len(result))
    return result


def build_current_vectors(feat_df: pd.DataFrame, base_year: int) -> pd.DataFrame:
    # Use most recent season available per player within last 3 years
    recent = feat_df[feat_df["season"].between(base_year - 3, base_year - 1)].copy()
    recent = (
        recent.sort_values("season")
        .drop_duplicates(subset=["player_id"], keep="last")
    )

    rows = []
    for _, row in recent.iterrows():
        pid     = str(row["player_id"])
        season  = int(row["season"])
        age_raw = row["age"]
        age_in_base = int(age_raw) + (base_year - season) if age_raw > 0 else None
        if age_in_base is None:
            continue
        rec = {
            "player_id":     pid,
            "player":        row.get("player", ""),
            "age":           age_in_base,
            "snapshot_year": base_year,
        }
        for c in FEAT_COLS:
            rec[f"f_{c}"] = float(row.get(c, 0.0)) * FEATURE_WEIGHTS[c]
        rows.append(rec)

    result = pd.DataFrame(rows)
    log.info("Current player vectors: %d players", len(result))
    return result


# ---------------------------------------------------------------------------
# Similarity
# ---------------------------------------------------------------------------

def find_top10_comps(
    current_row: pd.Series,
    hist_vecs: pd.DataFrame,
    age_window: int = 1,
    n: int = 10,
) -> list[dict]:
    pid = current_row["player_id"]
    age = int(current_row["age"])

    candidates = hist_vecs[
        (hist_vecs["player_id"] != pid) &
        (hist_vecs["age"].between(age - age_window, age + age_window))
    ].copy()

    if candidates.empty:
        return []

    feat_cols = [c for c in VEC_COLS if c in candidates.columns]
    if not feat_cols:
        return []

    # Rebuild raw (pre-weighted) values from f_ cols by dividing out weights
    hist_raw_matrix = np.array([
        [float(candidates.iloc[i][fc]) / FEATURE_WEIGHTS[fc[2:]]
         if FEATURE_WEIGHTS.get(fc[2:], 0) != 0 else 0.0
         for fc in feat_cols]
        for i in range(len(candidates))
    ])
    curr_raw_vector = np.array([
        float(current_row.get(fc, 0.0)) / FEATURE_WEIGHTS[fc[2:]]
        if FEATURE_WEIGHTS.get(fc[2:], 0) != 0 else 0.0
        for fc in feat_cols
    ]).reshape(1, -1)

    # 1. Z-score on raw values across candidate pool + current player
    scaler = StandardScaler()
    all_raw = np.vstack([hist_raw_matrix, curr_raw_vector])
    all_scaled = scaler.fit_transform(all_raw)
    hist_scaled = all_scaled[:-1]
    curr_scaled = all_scaled[-1:]

    # 2. Apply weights after z-scoring
    weight_arr = np.array([FEATURE_WEIGHTS.get(fc[2:], 1.0) for fc in feat_cols])
    hist_weighted = hist_scaled * weight_arr
    curr_weighted = curr_scaled * weight_arr

    dists = np.sqrt(np.sum((hist_weighted - curr_weighted) ** 2, axis=1))
    candidates["_dist"] = dists

    # Absolute similarity scale: 100 * exp(-dist / k)
    # k is the median distance in the pool — so a typical comp scores ~61,
    # a great comp scores 80+, a bad one scores well below 50.
    k = np.median(dists) if np.median(dists) > 0 else 1.0
    candidates["_sim"] = 100 * np.exp(-dists / k)

    best = (
        candidates
        .sort_values("_dist")
        .drop_duplicates(subset="player_id", keep="first")
        .head(n)
        .reset_index(drop=True)
    )

    comps = []
    for rank, (_, crow) in enumerate(best.iterrows(), 1):
        trajectory = []
        for rel in TRAJ_OFFSETS:
            v = crow.get(f"traj_{rel}", None)
            trajectory.append(
                None if (v is None or (isinstance(v, float) and np.isnan(v))) else float(v)
            )
        comps.append({
            "rank":       rank,
            "player":     crow["player"],
            "player_id":  crow["player_id"],
            "comp_year":  int(crow["snapshot_year"]),
            "comp_age":   int(crow["age"]),
            "similarity": round(float(crow["_sim"]), 1),
            "trajectory": trajectory,
        })

    return comps


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-year",  type=int, default=BASE_YEAR_DEFAULT)
    parser.add_argument("--raw-dir",    default="data/raw")
    parser.add_argument("--out",        default="data/processed/similarities.json")
    parser.add_argument("--start-year", type=int, default=1980)
    parser.add_argument("--age-window", type=int, default=1)
    args = parser.parse_args()

    raw_dir  = Path(args.raw_dir)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    log.info("Loading data...")
    totals   = load_totals(raw_dir, args.start_year, args.base_year - 1)
    advanced = load_advanced(raw_dir, args.start_year, args.base_year - 1)
    bio      = load_bio(raw_dir, args.start_year, args.base_year - 1)
    draft    = load_draft(raw_dir)

    log.info("Building feature matrix...")
    feat_df = build_feature_matrix(totals, advanced, bio, draft)

    log.info("Building vectors...")
    hist_vecs = build_historical_vectors(feat_df, last_season=args.base_year - 4, feat_df_full=feat_df)
    curr_vecs = build_current_vectors(feat_df, base_year=args.base_year)

    log.info("Computing similarities for %d players...", len(curr_vecs))
    output = {}
    for i, (_, row) in enumerate(curr_vecs.iterrows()):
        pid   = row["player_id"]
        comps = find_top10_comps(row, hist_vecs, age_window=args.age_window)
        output[pid] = {
            "player": row["player"],
            "age":    int(row["age"]),
            "comps":  comps,
        }
        if (i + 1) % 100 == 0:
            log.info("  %d / %d done", i + 1, len(curr_vecs))

    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)

    log.info("Wrote %d player entries -> %s", len(output), out_path)


if __name__ == "__main__":
    main()
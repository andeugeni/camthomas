"""
similarity.py
-------------
CARMELO-style player similarity engine.

Given a current player at a specific age, finds the N most similar historical
players at that same age (±1 year) based on their trailing 3-year per-game
stats, then uses the *rest of those players' careers* to project the current
player's next 1–4 seasons.

This completes the "LaMelo Brunson" notebook — the notebook had three distance
functions implemented but left the weighted projection step as a stub.

Architecture
~~~~~~~~~~~~
1. build_historical_vectors(df_all_seasons)
      → DataFrame where each row is (player, age, stat_year-3, stat_year-2,
         stat_year-1, stat_year0) — a snapshot of a player at a given age.

2. build_current_vectors(recent_seasons, base_year)
      → Same shape, but for current NBA players (past 3 seasons relative to
         base_year).

3. find_similar_players(current_player, current_vec, historical_vecs, n, method)
      → Top-N similar historical players with similarity scores.

4. project_from_comps(current_player, current_age, similar_rows, historical_vecs, n_future)
      → Weighted average of what similar players did in their next 1–4 seasons.

5. project_all(current_vecs, historical_vecs, n_comps, n_future, method)
      → Run steps 3–4 for every current player.

Similarity methods
~~~~~~~~~~~~~~~~~~
  'cosine'    — best for relative profile matching (direction, not magnitude).
                Ignores players with very different usage but similar ratios.
  'euclidean' — penalises magnitude differences; better for same-role comps.
  'manhattan' — similar to Euclidean but less sensitive to outliers.

Default: 'euclidean' (matches the notebook's best-performing method for
per-game stats where magnitude matters — a 35 mpg player is not comparable
to a 15 mpg player even if their per-minute rates are identical).
"""

import logging
from typing import Literal

import numpy as np
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import StandardScaler
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stats used for similarity matching
# ---------------------------------------------------------------------------

# Per-game stats, 3 trailing seasons (year-3, year-2, year-1 relative to age)
_SIM_STATS = [
    "mp_per_game",
    "x2p_per_game", "x3p_per_game", "ft_per_game",
    "trb_per_game", "ast_per_game",
    "stl_per_game", "blk_per_game", "tov_per_game",
]
_TRAILING = [-3, -2, -1]
_FUTURE   = [1, 2, 3, 4]

SIM_COLS = [f"{s}_year{y}" for s in _SIM_STATS for y in _TRAILING]

# ---------------------------------------------------------------------------
# Vector builders
# ---------------------------------------------------------------------------


def build_historical_vectors(
    df_per_game: pd.DataFrame,
    first_season: int = 1980,
    last_season: int = 2021,  # exclude recent seasons used for current players
) -> pd.DataFrame:
    """
    Build a (player, age) → trailing-stats vector table from historical data.

    Parameters
    ----------
    df_per_game : pd.DataFrame
        Per-game stats with columns: season, player, age, mp_per_game,
        x2p_per_game, x3p_per_game, ft_per_game, trb_per_game, ast_per_game,
        stl_per_game, blk_per_game, tov_per_game.
    first_season, last_season : int
        Season range (inclusive) to include as historical reference.

    Returns
    -------
    pd.DataFrame
        One row per (player, age) with columns player, age, {sim_cols},
        plus future year cols {stat}_year{1..4} for projection use.
    """
    df = df_per_game[
        (df_per_game["season"] >= first_season) &
        (df_per_game["season"] <= last_season)
    ].drop_duplicates(subset=["player", "age"]).copy()

    rows = []
    for _, row in df.iterrows():
        player = row["player"]
        age    = int(row["age"])
        rows.append(_build_vector_row(player, age, df, include_future=True))

    result = pd.DataFrame(rows)
    log.info("Historical vectors: %d rows (player-age pairs)", len(result))
    return result


def build_current_vectors(
    df_per_game: pd.DataFrame,
    base_year: int = 2025,
) -> pd.DataFrame:
    """
    Build current-player vectors.  Each player gets exactly one row
    representing their profile as of base_year (age = their age in base_year).

    Parameters
    ----------
    df_per_game : pd.DataFrame
        Per-game stats including the 3 seasons leading up to base_year.
    base_year : int
        The season we're projecting *from* (e.g. 2025 = projecting 2025-26).
    """
    recent = df_per_game[
        df_per_game["season"].between(base_year - 3, base_year - 1)
    ].drop_duplicates(subset=["player", "age"]).copy()

    players = recent["player"].unique()
    rows = []

    for player in players:
        # Determine age in base_year
        player_rows = recent[recent["player"] == player]
        # Find the most recent season's age and extrapolate
        latest = player_rows.loc[player_rows["season"].idxmax()]
        age_in_base = int(latest["age"]) + (base_year - int(latest["season"]))
        rows.append(_build_vector_row(player, age_in_base, recent, include_future=False))

    result = pd.DataFrame(rows)
    log.info("Current player vectors: %d players", len(result))
    return result


def _build_vector_row(
    player: str,
    age: int,
    df: pd.DataFrame,
    include_future: bool = False,
) -> dict:
    """Build a single (player, age) vector row."""
    player_df = df[df["player"] == player].set_index("age")

    row = {"player": player, "age": age}

    # Trailing years (year-3 through year-1 relative to this age)
    for rel_year in _TRAILING:
        abs_age = age + rel_year
        for stat in _SIM_STATS:
            col = f"{stat}_year{rel_year}"
            if abs_age in player_df.index and stat in player_df.columns:
                row[col] = player_df.at[abs_age, stat] or 0.0
            else:
                row[col] = 0.0

    # Future years (year+1 through year+4) — only for historical comps
    if include_future:
        for rel_year in _FUTURE:
            abs_age = age + rel_year
            for stat in _SIM_STATS:
                col = f"{stat}_year{rel_year}"
                if abs_age in player_df.index and stat in player_df.columns:
                    row[col] = player_df.at[abs_age, stat] or 0.0
                else:
                    row[col] = 0.0

    return row


# ---------------------------------------------------------------------------
# Similarity computation
# ---------------------------------------------------------------------------

SimilarityMethod = Literal["cosine", "euclidean", "manhattan"]


def find_similar_players(
    current_player: str,
    current_age: int,
    current_vec: np.ndarray,
    historical_vecs: pd.DataFrame,
    n: int = 10,
    age_window: int = 1,
    method: SimilarityMethod = "euclidean",
    scale: bool = True,
) -> pd.DataFrame:
    """
    Find the N most similar historical (player, age) pairs.

    Parameters
    ----------
    current_player : str
    current_age : int
    current_vec : np.ndarray, shape (len(SIM_COLS),)
    historical_vecs : pd.DataFrame
        Output of build_historical_vectors().
    n : int
        Number of comps to return.
    age_window : int
        How many years ± to include in the age filter.
    method : str
        'cosine', 'euclidean', or 'manhattan'.
    scale : bool
        If True, z-score each feature before computing distances.
        Recommended for euclidean/manhattan to equalise stat scales.

    Returns
    -------
    pd.DataFrame with columns: player, age, similarity_score, + all sim/future cols.
    """
    # Filter by age proximity, exclude the current player
    candidates = historical_vecs[
        (historical_vecs["player"] != current_player) &
        (historical_vecs["age"].between(current_age - age_window, current_age + age_window))
    ].copy()

    if candidates.empty:
        log.warning("No historical comps found for %s (age %d).", current_player, current_age)
        return pd.DataFrame()

    # Extract feature matrix
    feat_cols = [c for c in SIM_COLS if c in candidates.columns]
    hist_matrix = candidates[feat_cols].to_numpy(dtype=float)
    curr_matrix = current_vec.reshape(1, -1)[:, :len(feat_cols)]

    if scale:
        scaler = StandardScaler()
        all_data = np.vstack([hist_matrix, curr_matrix])
        all_scaled = scaler.fit_transform(all_data)
        hist_matrix = all_scaled[:-1]
        curr_matrix = all_scaled[-1:].reshape(1, -1)

    if method == "cosine":
        scores = cosine_similarity(curr_matrix, hist_matrix).flatten()
        candidates["similarity_score"] = scores
        candidates = candidates.sort_values("similarity_score", ascending=False)

    elif method == "euclidean":
        dists = np.sqrt(np.sum((hist_matrix - curr_matrix) ** 2, axis=1))
        candidates["similarity_score"] = 1 / (1 + dists)
        candidates = candidates.sort_values("similarity_score", ascending=False)

    elif method == "manhattan":
        dists = np.sum(np.abs(hist_matrix - curr_matrix), axis=1)
        candidates["similarity_score"] = 1 / (1 + dists)
        candidates = candidates.sort_values("similarity_score", ascending=False)

    else:
        raise ValueError(f"Unknown similarity method: {method!r}")

    # One row per historical player (best matching age)
    top = (
        candidates
        .drop_duplicates(subset="player", keep="first")
        .head(n)
        .reset_index(drop=True)
    )
    return top


# ---------------------------------------------------------------------------
# Projection from comps
# ---------------------------------------------------------------------------

def project_from_comps(
    similar_rows: pd.DataFrame,
    n_future: int = 4,
    baseline_weight: float = 100.0,
) -> dict[int, dict[str, float]]:
    """
    Use similar players' future trajectories to project the current player.

    The SPS projection (from projections.py) acts as a high-weight baseline.
    Each comp contributes proportionally to its similarity score.

    This implements the stub from the LaMelo Brunson notebook:
        "The baseline has a weight of 100.  The rest added with similarity score."

    Parameters
    ----------
    similar_rows : pd.DataFrame
        Output of find_similar_players(); must have similarity_score and
        {stat}_year{1..4} columns.
    n_future : int
        How many future seasons to project (1–4).
    baseline_weight : float
        Weight assigned to the SPS baseline row (if included).
        If similar_rows has no 'is_baseline' flag, all rows treated equally.

    Returns
    -------
    dict mapping future year offset → {stat: projected_per_game_value}
        e.g. {1: {'mp_per_game': 34.2, 'ast_per_game': 6.1, …}, 2: {…}, …}
    """
    projections: dict[int, dict[str, float]] = {}

    for rel_year in range(1, n_future + 1):
        future_stat_cols = {
            stat: f"{stat}_year{rel_year}"
            for stat in _SIM_STATS
        }

        # Check we have data for this future year in at least some comps
        available_cols = {
            stat: col
            for stat, col in future_stat_cols.items()
            if col in similar_rows.columns
        }

        if not available_cols:
            break

        # Weight each comp by its similarity score
        weights = similar_rows["similarity_score"].to_numpy(dtype=float)

        # Comps where all future stats are 0 = player retired before that year;
        # we don't want to drag projections toward 0 just from attrition.
        # Include only comps where the player actually played that year
        # (mp > 0 for that future year).
        mp_col = f"mp_per_game_year{rel_year}"
        if mp_col in similar_rows.columns:
            played_mask = similar_rows[mp_col].to_numpy() > 0
        else:
            played_mask = np.ones(len(similar_rows), dtype=bool)

        active_rows    = similar_rows[played_mask]
        active_weights = weights[played_mask]

        if active_rows.empty or active_weights.sum() == 0:
            projections[rel_year] = {stat: 0.0 for stat in available_cols}
            continue

        year_proj: dict[str, float] = {}
        for stat, col in available_cols.items():
            values  = active_rows[col].to_numpy(dtype=float)
            year_proj[stat] = float(np.average(values, weights=active_weights))

        projections[rel_year] = year_proj

    return projections


# ---------------------------------------------------------------------------
# Batch projection
# ---------------------------------------------------------------------------

def project_all(
    current_vecs: pd.DataFrame,
    historical_vecs: pd.DataFrame,
    n_comps: int = 10,
    n_future: int = 4,
    method: SimilarityMethod = "euclidean",
    age_window: int = 1,
) -> pd.DataFrame:
    """
    Run similarity-based projection for every current player.

    Returns a long-format DataFrame with columns:
        player, current_age, future_year (1–4), {stat}_proj, n_comps_used,
        top_comp_1, top_comp_2, top_comp_3  (names of most similar players)
    """
    feat_cols = [c for c in SIM_COLS if c in current_vecs.columns and c in historical_vecs.columns]
    rows = []

    for _, player_row in current_vecs.iterrows():
        player = player_row["player"]
        age    = int(player_row["age"])
        vec    = player_row[feat_cols].to_numpy(dtype=float)

        similar = find_similar_players(
            current_player=player,
            current_age=age,
            current_vec=vec,
            historical_vecs=historical_vecs,
            n=n_comps,
            age_window=age_window,
            method=method,
        )

        if similar.empty:
            continue

        top_comp_names = similar["player"].head(3).tolist()

        future = project_from_comps(similar, n_future)

        for rel_year, stat_dict in future.items():
            row = {
                "player":        player,
                "current_age":   age,
                "future_year":   rel_year,
                "projected_age": age + rel_year,
                "n_comps_used":  len(similar),
            }
            for i, name in enumerate(top_comp_names, 1):
                row[f"top_comp_{i}"] = name
            for stat, val in stat_dict.items():
                row[f"{stat}_proj"] = val
            rows.append(row)

    result = pd.DataFrame(rows)
    log.info("Similarity projections complete: %d player-season rows", len(result))
    return result


# ---------------------------------------------------------------------------
# Convenience runner
# ---------------------------------------------------------------------------

def run(player: Optional[str], base_year: int = 2025) -> pd.DataFrame:
    """
    End-to-end convenience wrapper.

    Loads per-game data from data/raw/, builds vectors, runs projections.
    Requires fetch.py to have been run.

    If `player` is specified, returns comps + projections for that player only.
    """
    from pathlib import Path

    raw_dir = Path(__file__).resolve().parents[2] / "data" / "raw"

    all_seasons = []
    for year in range(1980, base_year + 1):
        p = raw_dir / f"player_totals_{year}.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p)
        # Compute per-game stats from totals
        df["season"] = year
        for stat in ["x2p", "x3p", "ft", "trb", "ast", "stl", "blk", "tov"]:
            pg_col = f"{stat}_per_game"
            if stat in df.columns and "g" in df.columns:
                df[pg_col] = df[stat] / df["g"].replace(0, pd.NA)
        if "mp" in df.columns and "g" in df.columns:
            df["mp_per_game"] = df["mp"] / df["g"].replace(0, pd.NA)
        all_seasons.append(df)

    if not all_seasons:
        raise RuntimeError("No raw data found. Run fetch.py first.")

    full_df = pd.concat(all_seasons, ignore_index=True).fillna(0)

    hist_vecs = build_historical_vectors(full_df, last_season=base_year - 4)
    curr_vecs = build_current_vectors(full_df, base_year=base_year)

    if player:
        curr_vecs = curr_vecs[curr_vecs["player"] == player]
        if curr_vecs.empty:
            raise ValueError(f"Player '{player}' not found in current player vectors.")

    return project_all(curr_vecs, hist_vecs)


if __name__ == "__main__":
    import sys
    base   = int(sys.argv[1])    if len(sys.argv) > 1 else 2025
    target = sys.argv[2]         if len(sys.argv) > 2 else None
    results = run(target, base)
    print(results.to_string(index=False))

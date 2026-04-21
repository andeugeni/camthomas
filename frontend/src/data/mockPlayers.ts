// src/data/mockPlayers.ts
// ─────────────────────────────────────────────────────────────────────────────
// Single source of truth for the PlayerCard schema.
// This matches player_cards_2025.csv exactly.
//
// NOTE: columns that were in the old mock but aren't in the CSV are computed
// at runtime in playerUtils.ts from raw counting stats.
// ─────────────────────────────────────────────────────────────────────────────

export interface PlayerCard {
  // ── Identity ──────────────────────────────────────────────────────────────
  player_id: string;
  player: string;
  age: number;
  pos: string;
  tm: string;           // team abbreviation / full name from CSV
  season: number;

  // ── Draft ─────────────────────────────────────────────────────────────────
  draft_pick: number | null;
  draft_pct:  number | null;  // percentile rank of draft pick

  // ── Raw season totals (used to derive per-game stats) ─────────────────────
  g: number;
  gs: number;
  mp: number;
  mpg: number;
  fg: number;
  fga: number;
  x2p: number;
  x2pa: number;
  x3p: number;
  x3pa: number;
  ft: number;
  fta: number;
  orb: number;
  drb: number;
  trb: number;
  ast: number;
  stl: number;
  blk: number;
  tov: number;
  pf: number;
  pts: number;

  // ── Advanced rate stats ───────────────────────────────────────────────────
  ts_pct:   number | null;
  ft_pct:   number | null;
  usg_pct:  number | null;
  x3_freq:  number | null;
  ft_freq:  number | null;
  ast_pct:  number | null;
  tov_pct:  number | null;
  trb_pct:  number | null;
  blk_pct:  number | null;
  stl_pct:  number | null;

  // ── Percentile ranks (suffix _rank in CSV) ────────────────────────────────
  ts_pct_rank:  number;
  ft_pct_rank:  number;
  usg_pct_rank: number;
  x3_freq_rank: number;
  ft_freq_rank: number;
  ast_pct_rank: number;
  tov_pct_rank: number;
  trb_pct_rank: number;
  blk_pct_rank: number;
  stl_pct_rank: number;

  // ── Historical actual fantasy pts/g ──────────────────────────────────────
  actual_2018: number;
  actual_2019: number;
  actual_2020: number;
  actual_2021: number;
  actual_2022: number;
  actual_2023: number;
  actual_2024: number;
  actual_2025: number;

  // ── 5-year forward projections (fantasy pts/g) ────────────────────────────
  proj_y1: number;
  proj_y2: number;
  proj_y3: number;
  proj_y4: number;
  proj_y5: number;

  // ── Confidence intervals ──────────────────────────────────────────────────
  ci_lo_y1: number; ci_hi_y1: number;
  ci_lo_y2: number; ci_hi_y2: number;
  ci_lo_y3: number; ci_hi_y3: number;
  ci_lo_y4: number; ci_hi_y4: number;
  ci_lo_y5: number; ci_hi_y5: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Mock data — matches the real CSV schema exactly.
// Replace by running: python src/data/build_player_cards.py
// which writes frontend/src/data/players.json
// ─────────────────────────────────────────────────────────────────────────────

export const MOCK_PLAYERS: PlayerCard[] = [
  {
    player_id: "gilgesh01", player: "Shai Gilgeous-Alexander", age: 26,
    pos: "POINT GUARD", tm: "OKLAHOMA CITY THUNDER", season: 2025,
    draft_pick: 11, draft_pct: 71,
    g: 76, gs: 76, mp: 2598, mpg: 34.2,
    fg: 860, fga: 1656, x2p: 697, x2pa: 1221, x3p: 163, x3pa: 435,
    ft: 601, fta: 669, orb: 67, drb: 312, trb: 379,
    ast: 486, stl: 131, blk: 77, tov: 183, pf: 164, pts: 2484,
    ts_pct: null, ft_pct: null, usg_pct: null,
    x3_freq: 0.263, ft_freq: 0.404,
    ast_pct: null, tov_pct: null, trb_pct: null, blk_pct: null, stl_pct: null,
    ts_pct_rank: 50, ft_pct_rank: 50, usg_pct_rank: 50,
    x3_freq_rank: 18, ft_freq_rank: 91,
    ast_pct_rank: 50, tov_pct_rank: 50, trb_pct_rank: 50,
    blk_pct_rank: 50, stl_pct_rank: 50,
    actual_2018: 0, actual_2019: 1795.5, actual_2020: 2379.0,
    actual_2021: 1395.0, actual_2022: 2372.0, actual_2023: 3360.75,
    actual_2024: 3823.25, actual_2025: 0,
    proj_y1: 49.64, proj_y2: 48.92, proj_y3: 48.03, proj_y4: 46.63, proj_y5: 44.74,
    ci_lo_y1: 39.71, ci_hi_y1: 59.56, ci_lo_y2: 39.13, ci_hi_y2: 58.70,
    ci_lo_y3: 38.43, ci_hi_y3: 57.64, ci_lo_y4: 37.30, ci_hi_y4: 55.96,
    ci_lo_y5: 35.80, ci_hi_y5: 53.69,
  },
  {
    player_id: "edwaran01", player: "Anthony Edwards", age: 23,
    pos: "SHOOTING GUARD", tm: "MINNESOTA TIMBERWOLVES", season: 2025,
    draft_pick: 1, draft_pct: 100,
    g: 79, gs: 79, mp: 2871, mpg: 36.3,
    fg: 721, fga: 1612, x2p: 401, x2pa: 801, x3p: 320, x3pa: 811,
    ft: 415, fta: 496, orb: 61, drb: 389, trb: 450,
    ast: 359, stl: 91, blk: 51, tov: 249, pf: 150, pts: 2177,
    ts_pct: null, ft_pct: null, usg_pct: null,
    x3_freq: 0.503, ft_freq: 0.308,
    ast_pct: null, tov_pct: null, trb_pct: null, blk_pct: null, stl_pct: null,
    ts_pct_rank: 50, ft_pct_rank: 50, usg_pct_rank: 50,
    x3_freq_rank: 63, ft_freq_rank: 76,
    ast_pct_rank: 50, tov_pct_rank: 50, trb_pct_rank: 50,
    blk_pct_rank: 50, stl_pct_rank: 50,
    actual_2018: 0, actual_2019: 0, actual_2020: 0,
    actual_2021: 2284.5, actual_2022: 2581.25, actual_2023: 3280.0,
    actual_2024: 3359.5, actual_2025: 0,
    proj_y1: 42.19, proj_y2: 42.45, proj_y3: 42.51, proj_y4: 42.39, proj_y5: 42.09,
    ci_lo_y1: 33.76, ci_hi_y1: 50.63, ci_lo_y2: 33.96, ci_hi_y2: 50.94,
    ci_lo_y3: 34.01, ci_hi_y3: 51.01, ci_lo_y4: 33.91, ci_hi_y4: 50.86,
    ci_lo_y5: 33.67, ci_hi_y5: 50.51,
  },
];

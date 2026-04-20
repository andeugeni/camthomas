// src/data/mockPlayers.ts
// ─────────────────────────────────────────────────────────────────────────────
// Mock data mirroring player_cards_2025.csv schema.
// Swap this out once build_player_cards.py has been run:
//   import players from '@/data/players.json'  (generated from the CSV)
// ─────────────────────────────────────────────────────────────────────────────

export interface PlayerCard {
  player_id: string;
  player: string;
  age: number;
  team: string;
  pos: string;
  ht_inches: number;
  wt: number;
  draft_pick: number | null;

  // SPS projections
  proj_mpg: number;
  fantasy_pts: number;
  proj_x2p_pg: number;
  proj_x3p_pg: number;
  proj_ft_pg: number;
  proj_trb_pg: number;
  proj_ast_pg: number;
  proj_stl_pg: number;
  proj_blk_pg: number;
  proj_tov_pg: number;

  // Advanced rate stats
  ts_pct: number;
  ft_pct: number;
  usg_pct: number;
  x3_freq: number;
  ft_freq: number;
  ast_pct: number;
  tov_pct: number;
  trb_pct: number;
  blk_pct: number;
  stl_pct: number;

  // Percentile ranks (0–100)
  fantasy_pts_pct: number;
  proj_mpg_pct: number;
  ts_pct_pct: number;
  usg_pct_pct: number;
  trb_pct_pct: number;
  ast_pct_pct: number;
  stl_pct_pct: number;
  blk_pct_pct: number;

  // Historical actuals
  actual_2018: number;
  actual_2019: number;
  actual_2020: number;
  actual_2021: number;
  actual_2022: number;
  actual_2023: number;
  actual_2024: number;
  actual_2025: number;

  // 5-year forward projections
  proj_y1: number;
  proj_y2: number;
  proj_y3: number;
  proj_y4: number;
  proj_y5: number;

  // Confidence intervals
  ci_lo_y1: number; ci_hi_y1: number;
  ci_lo_y2: number; ci_hi_y2: number;
  ci_lo_y3: number; ci_hi_y3: number;
  ci_lo_y4: number; ci_hi_y4: number;
  ci_lo_y5: number; ci_hi_y5: number;

  category: string; // "MVP candidate" | "Star" | "Starter" | "Rotation" | "Fringe"
}

export const MOCK_PLAYERS: PlayerCard[] = [
  {
    player_id: "jokicni01", player: "Nikola Jokić", age: 30, team: "DEN", pos: "C",
    ht_inches: 83, wt: 284, draft_pick: 41,
    proj_mpg: 34.5, fantasy_pts: 68.2,
    proj_x2p_pg: 9.1, proj_x3p_pg: 1.0, proj_ft_pg: 5.8,
    proj_trb_pg: 12.8, proj_ast_pg: 8.9, proj_stl_pg: 1.3, proj_blk_pg: 0.8, proj_tov_pg: 3.0,
    ts_pct: 0.653, ft_pct: 0.815, usg_pct: 0.285, x3_freq: 0.14, ft_freq: 0.22,
    ast_pct: 0.44, tov_pct: 0.14, trb_pct: 0.22, blk_pct: 0.021, stl_pct: 0.017,
    fantasy_pts_pct: 99, proj_mpg_pct: 72, ts_pct_pct: 95, usg_pct_pct: 60,
    trb_pct_pct: 98, ast_pct_pct: 99, stl_pct_pct: 78, blk_pct_pct: 55,
    actual_2018: 32.4, actual_2019: 41.8, actual_2020: 53.9, actual_2021: 57.3,
    actual_2022: 62.1, actual_2023: 65.4, actual_2024: 67.8, actual_2025: 68.2,
    proj_y1: 66.0, proj_y2: 63.5, proj_y3: 60.1, proj_y4: 55.8, proj_y5: 50.2,
    ci_lo_y1: 58.0, ci_hi_y1: 74.0, ci_lo_y2: 54.0, ci_hi_y2: 73.0,
    ci_lo_y3: 49.0, ci_hi_y3: 71.0, ci_lo_y4: 42.0, ci_hi_y4: 69.0,
    ci_lo_y5: 34.0, ci_hi_y5: 66.0,
    category: "MVP candidate",
  },
  {
    player_id: "doncilu01", player: "Luka Dončić", age: 26, team: "LAL", pos: "PG/SF",
    ht_inches: 79, wt: 230, draft_pick: 3,
    proj_mpg: 36.5, fantasy_pts: 72.1,
    proj_x2p_pg: 7.4, proj_x3p_pg: 3.9, proj_ft_pg: 8.1,
    proj_trb_pg: 8.4, proj_ast_pg: 8.5, proj_stl_pg: 1.4, proj_blk_pg: 0.5, proj_tov_pg: 3.7,
    ts_pct: 0.598, ft_pct: 0.784, usg_pct: 0.365, x3_freq: 0.35, ft_freq: 0.42,
    ast_pct: 0.40, tov_pct: 0.16, trb_pct: 0.16, blk_pct: 0.008, stl_pct: 0.019,
    fantasy_pts_pct: 99, proj_mpg_pct: 90, ts_pct_pct: 76, usg_pct_pct: 99,
    trb_pct_pct: 82, ast_pct_pct: 97, stl_pct_pct: 85, blk_pct_pct: 30,
    actual_2018: 0, actual_2019: 38.2, actual_2020: 52.1, actual_2021: 58.7,
    actual_2022: 62.5, actual_2023: 65.0, actual_2024: 70.3, actual_2025: 72.1,
    proj_y1: 71.5, proj_y2: 70.8, proj_y3: 69.2, proj_y4: 66.5, proj_y5: 62.0,
    ci_lo_y1: 62.0, ci_hi_y1: 81.0, ci_lo_y2: 60.0, ci_hi_y2: 82.0,
    ci_lo_y3: 57.0, ci_hi_y3: 81.0, ci_lo_y4: 52.0, ci_hi_y4: 81.0,
    ci_lo_y5: 46.0, ci_hi_y5: 78.0,
    category: "MVP candidate",
  },
  {
    player_id: "gilgesh01", player: "Shai Gilgeous-Alexander", age: 27, team: "OKC", pos: "PG",
    ht_inches: 77, wt: 195, draft_pick: 11,
    proj_mpg: 33.8, fantasy_pts: 59.4,
    proj_x2p_pg: 7.2, proj_x3p_pg: 1.8, proj_ft_pg: 8.0,
    proj_trb_pg: 4.5, proj_ast_pg: 6.2, proj_stl_pg: 1.9, proj_blk_pg: 0.8, proj_tov_pg: 2.2,
    ts_pct: 0.632, ft_pct: 0.878, usg_pct: 0.310, x3_freq: 0.19, ft_freq: 0.40,
    ast_pct: 0.30, tov_pct: 0.10, trb_pct: 0.10, blk_pct: 0.015, stl_pct: 0.025,
    fantasy_pts_pct: 95, proj_mpg_pct: 65, ts_pct_pct: 89, usg_pct_pct: 75,
    trb_pct_pct: 55, ast_pct_pct: 80, stl_pct_pct: 95, blk_pct_pct: 48,
    actual_2018: 0, actual_2019: 0, actual_2020: 29.8, actual_2021: 38.1,
    actual_2022: 45.3, actual_2023: 52.1, actual_2024: 58.8, actual_2025: 59.4,
    proj_y1: 61.2, proj_y2: 62.5, proj_y3: 63.0, proj_y4: 61.5, proj_y5: 58.0,
    ci_lo_y1: 52.0, ci_hi_y1: 70.0, ci_lo_y2: 52.0, ci_hi_y2: 73.0,
    ci_lo_y3: 51.0, ci_hi_y3: 75.0, ci_lo_y4: 48.0, ci_hi_y4: 75.0,
    ci_lo_y5: 43.0, ci_hi_y5: 73.0,
    category: "MVP candidate",
  },
  {
    player_id: "antetgi01", player: "Giannis Antetokounmpo", age: 31, team: "MIL", pos: "PF",
    ht_inches: 83, wt: 242, draft_pick: 15,
    proj_mpg: 33.2, fantasy_pts: 63.5,
    proj_x2p_pg: 9.8, proj_x3p_pg: 0.4, proj_ft_pg: 7.1,
    proj_trb_pg: 11.0, proj_ast_pg: 6.5, proj_stl_pg: 1.1, proj_blk_pg: 1.0, proj_tov_pg: 3.2,
    ts_pct: 0.611, ft_pct: 0.649, usg_pct: 0.325, x3_freq: 0.05, ft_freq: 0.38,
    ast_pct: 0.32, tov_pct: 0.16, trb_pct: 0.21, blk_pct: 0.030, stl_pct: 0.015,
    fantasy_pts_pct: 97, proj_mpg_pct: 62, ts_pct_pct: 80, usg_pct_pct: 85,
    trb_pct_pct: 97, ast_pct_pct: 85, stl_pct_pct: 70, blk_pct_pct: 82,
    actual_2018: 35.2, actual_2019: 48.7, actual_2020: 55.9, actual_2021: 62.1,
    actual_2022: 63.8, actual_2023: 61.2, actual_2024: 62.9, actual_2025: 63.5,
    proj_y1: 61.5, proj_y2: 58.8, proj_y3: 55.4, proj_y4: 51.0, proj_y5: 45.5,
    ci_lo_y1: 53.0, ci_hi_y1: 70.0, ci_lo_y2: 48.0, ci_hi_y2: 69.0,
    ci_lo_y3: 43.0, ci_hi_y3: 68.0, ci_lo_y4: 37.0, ci_hi_y4: 65.0,
    ci_lo_y5: 28.0, ci_hi_y5: 63.0,
    category: "MVP candidate",
  },
  {
    player_id: "tatumja01", player: "Jayson Tatum", age: 27, team: "BOS", pos: "SF",
    ht_inches: 80, wt: 210, draft_pick: 3,
    proj_mpg: 36.0, fantasy_pts: 54.8,
    proj_x2p_pg: 5.8, proj_x3p_pg: 3.1, proj_ft_pg: 5.2,
    proj_trb_pg: 8.2, proj_ast_pg: 4.8, proj_stl_pg: 1.0, proj_blk_pg: 0.6, proj_tov_pg: 2.8,
    ts_pct: 0.578, ft_pct: 0.831, usg_pct: 0.312, x3_freq: 0.32, ft_freq: 0.28,
    ast_pct: 0.22, tov_pct: 0.13, trb_pct: 0.15, blk_pct: 0.011, stl_pct: 0.014,
    fantasy_pts_pct: 90, proj_mpg_pct: 88, ts_pct_pct: 65, usg_pct_pct: 78,
    trb_pct_pct: 79, ast_pct_pct: 60, stl_pct_pct: 62, blk_pct_pct: 40,
    actual_2018: 28.1, actual_2019: 34.5, actual_2020: 40.2, actual_2021: 48.6,
    actual_2022: 50.3, actual_2023: 52.8, actual_2024: 53.9, actual_2025: 54.8,
    proj_y1: 55.5, proj_y2: 56.2, proj_y3: 56.0, proj_y4: 54.5, proj_y5: 51.0,
    ci_lo_y1: 46.0, ci_hi_y1: 65.0, ci_lo_y2: 45.0, ci_hi_y2: 67.0,
    ci_lo_y3: 43.0, ci_hi_y3: 69.0, ci_lo_y4: 39.0, ci_hi_y4: 70.0,
    ci_lo_y5: 34.0, ci_hi_y5: 68.0,
    category: "Star",
  },
  {
    player_id: "brunsja01", player: "Jalen Brunson", age: 29, team: "NYK", pos: "PG",
    ht_inches: 74, wt: 190, draft_pick: 33,
    proj_mpg: 35.4, fantasy_pts: 48.3,
    proj_x2p_pg: 6.9, proj_x3p_pg: 2.5, proj_ft_pg: 5.2,
    proj_trb_pg: 3.4, proj_ast_pg: 6.7, proj_stl_pg: 0.9, proj_blk_pg: 0.2, proj_tov_pg: 2.4,
    ts_pct: 0.594, ft_pct: 0.847, usg_pct: 0.302, x3_freq: 0.26, ft_freq: 0.30,
    ast_pct: 0.34, tov_pct: 0.12, trb_pct: 0.07, blk_pct: 0.004, stl_pct: 0.012,
    fantasy_pts_pct: 84, proj_mpg_pct: 86, ts_pct_pct: 72, usg_pct_pct: 72,
    trb_pct_pct: 35, ast_pct_pct: 88, stl_pct_pct: 55, blk_pct_pct: 10,
    actual_2018: 0, actual_2019: 0, actual_2020: 0, actual_2021: 22.5,
    actual_2022: 32.1, actual_2023: 40.4, actual_2024: 47.9, actual_2025: 48.3,
    proj_y1: 48.0, proj_y2: 47.2, proj_y3: 45.8, proj_y4: 43.1, proj_y5: 39.2,
    ci_lo_y1: 40.0, ci_hi_y1: 56.0, ci_lo_y2: 37.0, ci_hi_y2: 57.0,
    ci_lo_y3: 34.0, ci_hi_y3: 57.0, ci_lo_y4: 30.0, ci_hi_y4: 56.0,
    ci_lo_y5: 24.0, ci_hi_y5: 54.0,
    category: "Star",
  },
  {
    player_id: "maxeyty01", player: "Tyrese Maxey", age: 25, team: "PHI", pos: "PG",
    ht_inches: 73, wt: 200, draft_pick: 21,
    proj_mpg: 37.2, fantasy_pts: 46.5,
    proj_x2p_pg: 5.8, proj_x3p_pg: 3.2, proj_ft_pg: 4.8,
    proj_trb_pg: 3.5, proj_ast_pg: 5.8, proj_stl_pg: 0.9, proj_blk_pg: 0.4, proj_tov_pg: 1.7,
    ts_pct: 0.605, ft_pct: 0.882, usg_pct: 0.278, x3_freq: 0.34, ft_freq: 0.28,
    ast_pct: 0.28, tov_pct: 0.09, trb_pct: 0.07, blk_pct: 0.008, stl_pct: 0.013,
    fantasy_pts_pct: 81, proj_mpg_pct: 94, ts_pct_pct: 78, usg_pct_pct: 62,
    trb_pct_pct: 38, ast_pct_pct: 74, stl_pct_pct: 56, blk_pct_pct: 28,
    actual_2018: 0, actual_2019: 0, actual_2020: 0, actual_2021: 0,
    actual_2022: 18.5, actual_2023: 28.9, actual_2024: 42.1, actual_2025: 46.5,
    proj_y1: 49.8, proj_y2: 52.1, proj_y3: 53.5, proj_y4: 53.0, proj_y5: 51.2,
    ci_lo_y1: 40.0, ci_hi_y1: 59.0, ci_lo_y2: 41.0, ci_hi_y2: 63.0,
    ci_lo_y3: 41.0, ci_hi_y3: 66.0, ci_lo_y4: 40.0, ci_hi_y4: 66.0,
    ci_lo_y5: 36.0, ci_hi_y5: 66.0,
    category: "Star",
  },
  {
    player_id: "edwaran01", player: "Anthony Edwards", age: 23, team: "MIN", pos: "SG",
    ht_inches: 76, wt: 225, draft_pick: 1,
    proj_mpg: 35.0, fantasy_pts: 50.2,
    proj_x2p_pg: 6.7, proj_x3p_pg: 2.8, proj_ft_pg: 5.1,
    proj_trb_pg: 5.5, proj_ast_pg: 5.1, proj_stl_pg: 1.3, proj_blk_pg: 0.5, proj_tov_pg: 3.1,
    ts_pct: 0.568, ft_pct: 0.812, usg_pct: 0.325, x3_freq: 0.29, ft_freq: 0.30,
    ast_pct: 0.24, tov_pct: 0.14, trb_pct: 0.10, blk_pct: 0.010, stl_pct: 0.018,
    fantasy_pts_pct: 86, proj_mpg_pct: 84, ts_pct_pct: 58, usg_pct_pct: 85,
    trb_pct_pct: 58, ast_pct_pct: 62, stl_pct_pct: 80, blk_pct_pct: 32,
    actual_2018: 0, actual_2019: 0, actual_2020: 0, actual_2021: 24.8,
    actual_2022: 36.5, actual_2023: 44.2, actual_2024: 49.8, actual_2025: 50.2,
    proj_y1: 53.8, proj_y2: 56.4, proj_y3: 58.1, proj_y4: 58.5, proj_y5: 57.0,
    ci_lo_y1: 44.0, ci_hi_y1: 63.0, ci_lo_y2: 45.0, ci_hi_y2: 68.0,
    ci_lo_y3: 46.0, ci_hi_y3: 70.0, ci_lo_y4: 45.0, ci_hi_y4: 72.0,
    ci_lo_y5: 42.0, ci_hi_y5: 72.0,
    category: "Star",
  },
];

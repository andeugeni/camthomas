// src/data/playerUtils.ts
// ─────────────────────────────────────────────────────────────────────────────
// All computed/derived values that the frontend needs but aren't in the CSV.
// Everything is derived from the raw counting stats that ARE in the CSV.
// ─────────────────────────────────────────────────────────────────────────────

import { PlayerCard } from "./mockPlayers";

// DraftKings scoring
const FW: Record<string, number> = {
  x2p: 1.5, x3p: 2.25, ft: 0.75,
  trb: 1.25, ast: 1.25, stl: 2.0, blk: 2.0, tov: -1,
};


// ── Per-game stats derived from raw totals ────────────────────────────────────

export function perGame(p: PlayerCard) {
  const g = p.g || 1;
  return {
    pts:  p.pts  / g,
    x2p:  p.x2p  / g,
    x3p:  p.x3p  / g,
    ft:   p.ft   / g,
    trb:  p.trb  / g,
    ast:  p.ast  / g,
    stl:  p.stl  / g,
    blk:  p.blk  / g,
    tov:  p.tov  / g,
    orb:  p.orb  / g,
    drb:  p.drb  / g,
    fg:   p.fg   / g,
    fga:  p.fga  / g,
  };
}

// ── Current-season fantasy pts/g from raw totals ──────────────────────────────

export function currentFantasyPts(p: PlayerCard): number {
  const g = p.g || 1;
  return (
    (p.x2p / g) * FW.x2p +
    (p.x3p / g) * FW.x3p +
    (p.ft  / g) * FW.ft  +
    (p.trb / g) * FW.trb +
    (p.ast / g) * FW.ast +
    (p.stl / g) * FW.stl +
    (p.blk / g) * FW.blk +
    (p.tov / g) * FW.tov
  );
}

// ── Derived shooting stats (when advanced CSV fields are null) ────────────────

export function trueShooting(p: PlayerCard): number | null {
  if (p.ts_pct != null) return p.ts_pct;
  const denom = 2 * (p.fga + 0.44 * p.fta);
  return denom > 0 ? p.pts / denom : null;
}

export function ftPct(p: PlayerCard): number | null {
  if (p.ft_pct != null) return p.ft_pct;
  return p.fta > 0 ? p.ft / p.fta : null;
}

// ── Display helpers ───────────────────────────────────────────────────────────

export function fmtHeight(inches: number | null | undefined): string {
  if (!inches) return "—";
  return `${Math.floor(inches / 12)}'${inches % 12}"`;
}

export function fmtPct(v: number | null | undefined, decimals = 1): string {
  if (v == null || isNaN(v)) return "—";
  // values stored as 0–1 in CSV
  const scaled = Math.abs(v) <= 1 ? v * 100 : v;
  return `${scaled.toFixed(decimals)}%`;
}

export function fmtNum(v: number | null | undefined, decimals = 1): string {
  if (v == null || isNaN(v)) return "—";
  return v.toFixed(decimals);
}

// ── Percentile color ──────────────────────────────────────────────────────────

export function pctColor(rank: number): string {
  if (rank >= 75) return "var(--good)";
  if (rank >= 40) return "var(--mid)";
  return "var(--bad)";
}

// ── Short team name (CSV has full name like "OKLAHOMA CITY THUNDER") ──────────

export function shortTeam(tm: string): string {
  const MAP: Record<string, string> = {
    "ATLANTA HAWKS": "ATL", "BOSTON CELTICS": "BOS",
    "BROOKLYN NETS": "BKN", "CHARLOTTE HORNETS": "CHA",
    "CHICAGO BULLS": "CHI", "CLEVELAND CAVALIERS": "CLE",
    "DALLAS MAVERICKS": "DAL", "DENVER NUGGETS": "DEN",
    "DETROIT PISTONS": "DET", "GOLDEN STATE WARRIORS": "GSW",
    "HOUSTON ROCKETS": "HOU", "INDIANA PACERS": "IND",
    "LOS ANGELES CLIPPERS": "LAC", "LOS ANGELES LAKERS": "LAL",
    "MEMPHIS GRIZZLIES": "MEM", "MIAMI HEAT": "MIA",
    "MILWAUKEE BUCKS": "MIL", "MINNESOTA TIMBERWOLVES": "MIN",
    "NEW ORLEANS PELICANS": "NOP", "NEW YORK KNICKS": "NYK",
    "OKLAHOMA CITY THUNDER": "OKC", "ORLANDO MAGIC": "ORL",
    "PHILADELPHIA 76ERS": "PHI", "PHOENIX SUNS": "PHX",
    "PORTLAND TRAIL BLAZERS": "POR", "SACRAMENTO KINGS": "SAC",
    "SAN ANTONIO SPURS": "SAS", "TORONTO RAPTORS": "TOR",
    "UTAH JAZZ": "UTA", "WASHINGTON WIZARDS": "WAS",
  };
  return MAP[tm?.toUpperCase()] ?? tm?.slice(0, 3) ?? "—";
}

// ── Short position label ──────────────────────────────────────────────────────

export function shortPos(pos: string): string {
  const MAP: Record<string, string> = {
    "POINT GUARD": "PG", "SHOOTING GUARD": "SG", "SMALL FORWARD": "SF",
    "POWER FORWARD": "PF", "CENTER": "C",
    "PG": "PG", "SG": "SG", "SF": "SF", "PF": "PF", "C": "C",
    "GUARD": "G", "FORWARD": "F",
  };
  return MAP[pos?.toUpperCase()] ?? pos ?? "—";
}

// ── Category from proj_y1 ────────────────────────────────────────────────────

export function category(proj_fpts_y1: number): string {
  if (proj_fpts_y1 >= 55) return "MVP candidate";
  if (proj_fpts_y1 >= 45) return "Star";
  if (proj_fpts_y1 >= 35) return "Starter";
  if (proj_fpts_y1 >= 22) return "Rotation";
  return "Fringe";
}

// ── Historical actuals: convert raw season total → per-game fpts ─────────────
// The CSV stores actual_20XX as season total fantasy pts (not per-game).
// We don't have per-game broken out, so we display as-is and label accordingly.
// If the value is > 500 it's almost certainly a season total; divide by ~75.
// (A cleaner fix is to store per-game in build_player_cards.py directly.)

export function normaliseActual(raw: number, g?: number): number {
  if (!raw) return 0;
  // Heuristic: if value > 200, it's a season total — convert to per-game
  if (raw > 200) return g ? raw / g : raw / 75;
  return raw;
}

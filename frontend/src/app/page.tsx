"use client";

import { useState, useMemo } from "react";
import { MOCK_PLAYERS, PlayerCard } from "@/data/mockPlayers";
import { currentFantasyPts, shortTeam, shortPos } from "@/data/playerUtils";
import PlayerCardView from "@/components/PlayerCardView";
import styles from "@/styles/page.module.css";
import simData from "@/data/similarities.json";



// ── Data source ───────────────────────────────────────────────────────────────
// build_player_cards.py writes frontend/src/data/players.json.
// Falls back to mock data if that file doesn't exist yet.
let RAW_PLAYERS: PlayerCard[];
try {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const raw = require("@/data/player_cards.json") as PlayerCard[];
  RAW_PLAYERS = raw.length > 0 ? raw : MOCK_PLAYERS;
} catch {
  RAW_PLAYERS = MOCK_PLAYERS;
}

// Sort descending by proj_y1 (best projected player first)
const PLAYERS = [...RAW_PLAYERS].sort(
  (a, b) => (b.proj_y1 ?? 0) - (a.proj_y1 ?? 0)
);



const IS_MOCK = RAW_PLAYERS === MOCK_PLAYERS;

function rankColor(rank: number, total: number) {
  const pct = 1 - rank / total;
  if (pct >= 0.9) return "var(--good)";
  if (pct >= 0.6) return "var(--mid)";
  return "var(--text3)";
}

export default function Home() {
  const [search,   setSearch]   = useState("");
  const [selected, setSelected] = useState<PlayerCard>(PLAYERS[0]);
  const comps = (simData as Record<string, { comps: any[] }>)[selected.player_id]?.comps ?? [];

  const filtered = useMemo(() =>
    PLAYERS.filter(p =>
      p.player.toLowerCase().includes(search.toLowerCase()) ||
      shortTeam(p.tm).toLowerCase().includes(search.toLowerCase()) ||
      shortPos(p.pos).toLowerCase().includes(search.toLowerCase()) ||
      p.pos?.toLowerCase().includes(search.toLowerCase())
      
    ),
    [search]
  );

  return (
    <div className={styles.root}>
      {/* ── Sidebar ────────────────────────────────────── */}
      <aside className={styles.sidebar}>
        <div className={styles.sidebarHeader}>
          <span className={`${styles.logo} cond`}>CAMTHOMAS</span>
          <span className={styles.logoSub}>2024–25 · Fantasy Projections</span>
        </div>

        <input
          className={styles.search}
          placeholder="Search player, team, pos…"
          value={search}
          onChange={e => setSearch(e.target.value)}
        />

        <div className={styles.playerList}>
          {filtered.map((p) => {
            const rank  = PLAYERS.findIndex(x => x.player_id === p.player_id) + 1;
            const fpts  = currentFantasyPts(p);
            return (
              <button
                key={p.player_id}
                className={`${styles.playerRow} ${selected.player_id === p.player_id ? styles.playerRowActive : ""}`}
                onClick={() => setSelected(p)}
              >
                <span
                  className={`${styles.rankNum} mono`}
                  style={{ color: rankColor(rank, PLAYERS.length) }}
                >
                  {rank}
                </span>
                <div className={styles.playerInfo}>
                  <span className={`${styles.playerName} cond`}>{p.player}</span>
                  <span className={styles.playerMeta}>
                    {shortTeam(p.tm)} · {shortPos(p.pos)} · {p.age}
                  </span>
                </div>
                <span className={`${styles.playerPts} mono`}>{fpts.toFixed(1)}</span>
              </button>
            );
          })}
          {filtered.length === 0 && (
            <div className={styles.noResults}>No players found</div>
          )}
        </div>

        <div className={styles.sidebarFooter}>
          <span className={styles.footerNote}>
            {IS_MOCK
              ? "⚠ Mock data · run build_player_cards.py"
              : `${PLAYERS.length} players · player_cards_2026.csv`}
          </span>
          <span className={styles.footerNote} style={{ marginTop: 2 }}>
            Data: Basketball Reference · SPS + CARMELO
          </span>
        </div>
      </aside>

      {/* ── Main card ──────────────────────────────────── */}
      <main className={styles.main}>
        <PlayerCardView key={selected.player_id} player={selected} comps={comps} />
      </main>
    </div>
  );
}
